// index.js — Express + Telegraf с демо-ASR/TTS, анти‑эхо и реальными ответами при наличии OPENAI_API_KEY
// Требуются пакеты: express, telegraf, axios, openai, fluent-ffmpeg, ffmpeg-static, gtts

const express = require('express');
const { Telegraf } = require('telegraf');
const axios = require('axios');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

let ffmpeg, ffmpegPath;
try {
  ffmpeg = require('fluent-ffmpeg');
  ffmpegPath = require('ffmpeg-static');
  if (ffmpegPath) ffmpeg.setFfmpegPath(ffmpegPath);
} catch (_) {}

const { OpenAI } = (() => {
  try { return require('openai'); } catch (_) { return { OpenAI: null }; }
})();

// ENV
const BOT_TOKEN = process.env.BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

if (!BOT_TOKEN) {
  console.error('Ошибка: отсутствует BOT_TOKEN.');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '20mb' }));

const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 10000 });

// Строгий UX: постоянная Reply‑клавиатура
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: false,
  selective: true,
};

// Кэши и лимиты
const transcriptCache = new Map(); // key: file_unique_id -> { text, exp }
const ttsCache = new Map();        // key: sha(lang+text) -> { buf, exp }
const lastAnswer = new Map();      // key: chatId -> { text, exp }
const userQuota = new Map();       // key: userId -> { ttsSec, voiceSec, resetAt }

const TRANSCRIPT_TTL_MS = 15 * 60 * 1000;
const TTS_TTL_MS = 15 * 60 * 1000;
const QUOTA_TTS_SEC_PER_DAY = 120;
const QUOTA_VOICE_SEC_PER_DAY = 60;
const SINGLE_TTS_MAX_SEC = 20;
const ASR_MAX_SEC = 15;

// Утилиты
function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}
function now() { return Date.now(); }
function sha(x) { return crypto.createHash('sha1').update(x).digest('hex'); }

function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}
function ensureQuota(userId) {
  const b = userQuota.get(userId);
  if (!b || b.resetAt < now()) {
    userQuota.set(userId, { ttsSec: 0, voiceSec: 0, resetAt: now() + 24 * 60 * 60 * 1000 });
  }
  return userQuota.get(userId);
}
function addVoiceUsage(userId, sec) {
  const b = ensureQuota(userId);
  b.voiceSec += sec;
  return b.voiceSec <= QUOTA_VOICE_SEC_PER_DAY;
}
function estimateTtsSeconds(text) {
  const charsPerSec = 15;
  return Math.ceil(text.length / charsPerSec);
}
function clampTtsText(text) {
  const charsPerSec = 15;
  const maxChars = SINGLE_TTS_MAX_SEC * charsPerSec;
  if (text.length <= maxChars) return text;
  let t = text.slice(0, maxChars);
  const cut = t.lastIndexOf(' ');
  if (cut > 0) t = t.slice(0, cut);
  return t + ' …';
}
function addTtsUsage(userId, sec) {
  const b = ensureQuota(userId);
  b.ttsSec += sec;
  return b.ttsSec <= QUOTA_TTS_SEC_PER_DAY;
}
function cacheSet(map, key, val, ttl) {
  map.set(key, { ...val, exp: now() + ttl });
}
function cacheGet(map, key) {
  const v = map.get(key);
  if (!v) return null;
  if (v.exp < now()) { map.delete(key); return null; }
  return v;
}

// TTS: gTTS mp3 -> ogg/opus
async function ttsToOggBuffer(text, lang) {
  let gTTS;
  try { gTTS = require('gtts'); } catch (_) { throw new Error('TTS недоступен (нет gtts).'); }
  if (!ffmpeg) throw new Error('TTS недоступен (нет ffmpeg).');

  text = sanitizeOutput(text);
  const mp3Tmp = path.join(os.tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const oggTmp = path.join(os.tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);

  await new Promise((resolve, reject) => {
    const tts = new gTTS(text, lang === 'he' ? 'he' : (lang === 'en' ? 'en' : 'ru'));
    tts.save(mp3Tmp, (err) => err ? reject(err) : resolve());
  });
  await new Promise((resolve, reject) => {
    ffmpeg(mp3Tmp)
      .audioCodec('libopus')
      .format('ogg')
      .audioBitrate('48k')
      .on('error', reject)
      .on('end', resolve)
      .save(oggTmp);
  });
  const buf = await fs.promises.readFile(oggTmp);
  try { fs.unlinkSync(mp3Tmp); } catch (_) {}
  try { fs.unlinkSync(oggTmp); } catch (_) {}
  return buf;
}

// LLM: ответ по делу, без «эха»
async function llmAnswer({ prompt, lang }) {
  if (!OPENAI_API_KEY || !OpenAI) {
    // Фолбэк без затрат
    if (lang === 'he') {
      return sanitizeOutput('Кратко: дам ответ по делу при доступе к модели. Детали: для полноценного ответа включите OPENAI_API_KEY или отправьте вопрос текстом. Чек‑лист: 1. Сформулируйте цель 2. Ограничения 3. Варианты 4. Риски 5. Следующий шаг.');
    }
    if (lang === 'en') {
      return sanitizeOutput('Brief: to give a specific answer I need model access. Details: enable OPENAI_API_KEY or send a short text. Checklist: 1. Goal 2. Constraints 3. Options 4. Risks 5. Next step.');
    }
    return sanitizeOutput('Кратко: чтобы ответить предметно, включите OPENAI_API_KEY или пришлите вопрос текстом. Детали: модель пока недоступна. Чек‑лист: 1. Цель 2. Ограничения 3. Варианты 4. Риски 5. Следующий шаг.');
  }
  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const sys = lang === 'he'
    ? 'ענה תמציתי ובעניין, בלי לצטט את דברי המשתמש. בלי סימוני Markdown. שמור על שורות קצרות, שמור אמוג\'י ומספור 1., 2., 3.'
    : (lang === 'en'
        ? 'Reply concisely and to the point, without quoting the user. No Markdown markers. Keep emojis and numbering 1., 2., 3.'
        : 'Отвечай кратко и по делу, без повтора речи пользователя. Без Markdown‑символов. Оставляй эмодзи и нумерацию 1., 2., 3.');
  const user = lang === 'he'
    ? `בקשה קולית/טקסט: ${prompt}\nענה תכל\'ס, מבלי לצטט את הבקשה. מבנה: "Кратко:", "Детали:", "Чек-лист:" עם 1.–5.`
    : (lang === 'en'
        ? `Voice/Text request: ${prompt}\nRespond to the point without quoting the user. Structure: "Кратко:", "Детали:", "Чек-лист:" with items 1–5.`
        : `Голос/текст: ${prompt}\nОтветь по делу, не цитируй пользователя. Структура: "Кратко:", "Детали:", "Чек-лист:" с пунктами 1–5.`);
  const res = await client.chat.completions.create({
    model: 'gpt-4o-mini',
    temperature: 0.4,
    messages: [
      { role: 'system', content: sys },
      { role: 'user', content: user }
    ]
  });
  const txt = res.choices?.[0]?.message?.content || '';
  return sanitizeOutput(txt || 'Кратко: готово. Детали: контент временно недоступен. Чек‑лист: 1. Повтор 2. Короче 3. Позже 4. 5.');
}

// ASR: Whisper при наличии ключа
async function asrWhisper(oggPath, langPref) {
  if (!OPENAI_API_KEY || !OpenAI) {
    return null; // демо без затрат — вернём null
  }
  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const fileStream = fs.createReadStream(oggPath);
  const opts = { file: fileStream, model: 'whisper-1' };
  if (langPref === 'ru') opts.language = 'ru';
  if (langPref === 'he') opts.language = 'he';
  const tr = await client.audio.transcriptions.create(opts);
  return (tr.text || '').trim();
}

// Получение файла Telegram и конвертация к ogg/opus -> ogg/opus (оставим исходный, Whisper переварит mp3/wav тоже)
async function downloadVoiceOgg(ctx, fileId) {
  const f = await ctx.telegram.getFile(fileId);
  const url = `https://api.telegram.org/file/bot${BOT_TOKEN}/${f.file_path}`;
  const oggTmp = path.join(os.tmpdir(), `voice_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
  const resp = await axios.get(url, { responseType: 'stream' });
  await new Promise((resolve, reject) => {
    const w = fs.createWriteStream(oggTmp);
    resp.data.pipe(w);
    w.on('finish', resolve);
    w.on('error', reject);
  });
  // при необходимости можно перегнать в wav/mp3, но Whisper умеет ogg/opus
  return oggTmp;
}

// Команды
bot.start(async (ctx) => {
  const msg = sanitizeOutput('Привет. Я работаю 24/7. Одна кнопка Меню, без звёздочек и решёток. Голос — без эха. Нажмите Меню для подсказок.');
  await ctx.reply(msg, { reply_markup: replyKeyboard });
});
bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT-4o — U10c-Node', { reply_markup: replyKeyboard });
});
bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Голос до 10–15 сек. Без эха.');
  lines.push('2. Расшифровка — по кнопке, кэш 15 мин.');
  lines.push('3. Озвучка ответа — по кнопке, до ~20 сек.');
  lines.push('4. Лимиты: TTS ~2 мин/день, голос ~1 мин/день.');
  lines.push('5. Версия: /version. Вебхук: /telegram/railway123.');
  await ctx.reply(sanitizeOutput(lines.join('\n')), { reply_markup: replyKeyboard });
});

// Текст → реальный ответ (LLM при наличии ключа)
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const text = (ctx.message.text || '').trim();
    const answer = await llmAnswer({ prompt: text, lang });
    const final = sanitizeOutput(answer);
    cacheSet(lastAnswer, String(ctx.chat.id), { text: final }, TTS_TTL_MS);
    await ctx.reply(final, { reply_markup: replyKeyboard });
  } catch (e) {
    console.error('text error:', e);
    await ctx.reply(sanitizeOutput('Кратко: временная ошибка. Детали: повторите позже. Чек‑лист: 1. Короче 2. Позже 3. Поддержка 4. 5.'), { reply_markup: replyKeyboard });
  }
});

// Голос → ASR (если есть) → LLM по делу, без «эха»
bot.on('voice', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const v = ctx.message.voice;
    const dur = Math.max(0, Math.min(ASR_MAX_SEC, v?.duration || 0));
    const ok = addVoiceUsage(ctx.from.id, dur);
    if (!ok) {
      await ctx.reply(sanitizeOutput('Кратко: дневной лимит голосовых исчерпан. Детали: попробуйте завтра. Чек‑лист: 1. Текстом 2. Короткий голос 3. Позже.'), { reply_markup: replyKeyboard });
      return;
    }

    const fid = v.file_unique_id || v.file_id;
    let transcript = null;

    // Скачиваем ogg и распознаём (если ключ есть)
    let oggPath = null;
    try {
      oggPath = await downloadVoiceOgg(ctx, v.file_id);
      if (OPENAI_API_KEY && OpenAI) {
        transcript = await asrWhisper(oggPath, lang);
      }
    } catch (err) {
      console.error('asr download/whisper error:', err);
    } finally {
      if (oggPath) { try { fs.unlinkSync(oggPath); } catch (_) {} }
    }

    if (!transcript || !transcript.trim()) {
      // Демо без затрат — сохраняем заглушку в кэш
      const demoText = lang === 'he'
        ? `דמו: אורך קול ~ ${dur} שניות.`
        : (lang === 'en' ? `Demo: voice length ~ ${dur} sec.` : `Демо: длина голоса ~ ${dur} сек.`);
      cacheSet(transcriptCache, fid, { text: sanitizeOutput(demoText) }, TRANSCRIPT_TTL_MS);
    } else {
      cacheSet(transcriptCache, fid, { text: sanitizeOutput(transcript) }, TRANSCRIPT_TTL_MS);
    }

    // Генерация ответа по делу (но без «эха») — используем расшифровку, если есть, иначе короткий prompt
    const prompt = transcript && transcript.trim()
      ? transcript.trim()
      : (lang === 'he' ? 'בקשה קולית קצרה, תן תשובה תמציתית ורלוונטית.' :
         lang === 'en' ? 'Short voice request, provide a concise, relevant answer.' :
         'Короткий голосовой запрос, дай по делу ответ.');
    const answer = await llmAnswer({ prompt, lang });
    const replyText = sanitizeOutput(answer);

    // Инлайн‑кнопки: Показать расшифровку, Озвучить ответ, Скрыть
    const inlineKeyboard = {
      inline_keyboard: [
        [{ text: 'Показать расшифровку', callback_data: `show_transcript:${fid}` },
         { text: 'Озвучить ответ', callback_data: `tts_reply:${ctx.chat.id}` }],
        [{ text: 'Скрыть', callback_data: 'hide' }]
      ]
    };

    cacheSet(lastAnswer, String(ctx.chat.id), { text: replyText }, TTS_TTL_MS);
    await ctx.reply(replyText, { reply_markup: inlineKeyboard });
  } catch (e) {
    console.error('voice handler error:', e);
    await ctx.reply(sanitizeOutput('Кратко: получил голос. Детали: внутренняя ошибка обработки. Чек‑лист: 1. Повторите позже 2. Сократите длительность 3. Сообщите в поддержку.'), { reply_markup: replyKeyboard });
  }
});

// Callback: показать расшифровку / озвучить ответ / скрыть
bot.on('callback_query', async (ctx) => {
  try {
    const data = ctx.callbackQuery.data || '';
    if (data === 'hide') {
      try { await ctx.editMessageReplyMarkup(undefined); } catch (_) {}
      await ctx.answerCbQuery('Скрыто');
      return;
    }
    if (data.startsWith('show_transcript:')) {
      const fid = data.split(':')[1];
      const cached = fid ? cacheGet(transcriptCache, fid) : null;
      const text = cached?.text || 'Транскрипт недоступен.';
      await ctx.answerCbQuery('Готово');
      await ctx.reply(sanitizeOutput(`Транскрипт: ${text}`), { reply_markup: replyKeyboard });
      return;
    }
    if (data.startsWith('tts_reply:')) {
      const chatKey = data.split(':')[1] || String(ctx.chat.id);
      const cached = cacheGet(lastAnswer, chatKey);
      if (!cached || !cached.text) {
        await ctx.answerCbQuery('Нет текста для озвучки');
        return;
      }
      const lang = detectLang(ctx);
      const textClamped = clampTtsText(cached.text);
      const ttsSec = Math.min(SINGLE_TTS_MAX_SEC, estimateTtsSeconds(textClamped));
      const ok = addTtsUsage(ctx.from.id, ttsSec);
      if (!ok) {
        await ctx.answerCbQuery('Лимит TTS исчерпан');
        await ctx.reply(sanitizeOutput('Кратко: дневной лимит TTS исчерпан. Детали: попробуйте завтра или сократите текст. Чек‑лист: 1. Меньше текста 2. Позже 3. Поддержка.'), { reply_markup: replyKeyboard });
        return;
      }
      try {
        const key = sha(`${lang}::${textClamped}`);
        let entry = cacheGet(ttsCache, key);
        if (!entry) {
          const buf = await ttsToOggBuffer(textClamped, lang);
          entry = { buf };
          cacheSet(ttsCache, key, entry, TTS_TTL_MS);
        }
        await ctx.answerCbQuery('Озвучиваю');
        await ctx.replyWithVoice({ source: entry.buf, filename: 'reply.ogg' }, { reply_markup: replyKeyboard });
      } catch (e) {
        console.error('tts error:', e);
        await ctx.answerCbQuery('Ошибка TTS');
        await ctx.reply(sanitizeOutput('Кратко: озвучка временно недоступна. Детали: внутренняя ошибка TTS. Чек‑лист: 1. Повторите позже 2. Проверьте зависимости 3. Сообщите в поддержку.'), { reply_markup: replyKeyboard });
      }
      return;
    }
    await ctx.answerCbQuery('OK');
  } catch (e) {
    console.error('callback error:', e);
    try { await ctx.answerCbQuery('Ошибка'); } catch (_) {}
  }
});

// ====== Express маршруты ======
app.get('/version', (req, res) => res.status(200).send('UNIVERSAL GPT-4o — U10c-Node'));
app.get('/telegram/railway123', (req, res) => res.status(200).send('Webhook OK'));
app.post('/telegram/railway123', (req, res, next) => {
  const got = req.get('x-telegram-bot-api-secret-token');
  if (SECRET_TOKEN && got !== SECRET_TOKEN) return res.status(401).send('Unauthorized');
  return next();
}, bot.webhookCallback('/telegram/railway123'));
app.get('/', (req, res) => res.status(200).send('OK'));

app.listen(PORT, () => {
  console.log('Server started on port', PORT);
  console.log('GET /version → 200');
  console.log('GET /telegram/railway123 → Webhook OK');
});
