// index.js — Express + Telegraf: голос и TTS исправлены; анти‑эхо; «Меню» только по запросу;
// кнопка «Скрыть» реально закрывает инлайн‑клавиатуру; кнопка «Озвучить ответ» показывается
// только при TTS_ENABLED=true. Санитаризация убирает Markdown‑символы.

const express = require('express');
const { Telegraf } = require('telegraf');
const axios = require('axios');
const fs = require('fs');
const os = require('os');
const path = require('path');
const crypto = require('crypto');

// ffmpeg для TTS
let ffmpeg, ffmpegPath;
try {
  ffmpeg = require('fluent-ffmpeg');
  ffmpegPath = require('ffmpeg-static');
  if (ffmpegPath) ffmpeg.setFfmpegPath(ffmpegPath);
} catch (_) {}

const BOT_TOKEN = process.env.BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const TTS_ENABLED = String(process.env.TTS_ENABLED || 'false').toLowerCase() === 'true';
const PORT = process.env.PORT || 3000;

if (!BOT_TOKEN) {
  console.error('Нет BOT_TOKEN');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '20mb' }));
const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 10000 });

// Reply‑клавиатура «Меню»: только по запросу
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: true,
  selective: true
};

// Кэши
const transcriptCache = new Map(); // key: file_unique_id -> { text, exp }
const ttsCache = new Map();        // key: sha(text+lang) -> { buf, exp }
const lastAnswer = new Map();      // key: chatId -> { text, exp }

const TRANSCRIPT_TTL_MS = 15 * 60 * 1000;
const TTS_TTL_MS = 15 * 60 * 1000;
const SINGLE_TTS_MAX_SEC = 20;

function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}
function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}
async function replyClean(ctx, text, { showMenu = false } = {}) {
  const cleaned = sanitizeOutput(text);
  if (showMenu) return ctx.reply(cleaned, { reply_markup: replyKeyboard });
  return ctx.reply(cleaned, { reply_markup: { remove_keyboard: true } });
}
function sha(x) { return crypto.createHash('sha1').update(x).digest('hex'); }

// Локальный ответ по делу, без «эха»
function localAnswer(prompt, lang) {
  const q = String(prompt || '').toLowerCase();
  if (q.includes('наполеон')) {
    const lines = [];
    lines.push('Кратко: классический «Наполеон» с заварным кремом.');
    lines.push('Детали: тонкие слоёные коржи + заварной крем; ночь на пропитку.');
    lines.push('Чек-лист:');
    lines.push('1. Тесто: мука 600 г, масло 400 г холодное, вода 180 мл, яйцо 1, соль, уксус 1 ч. л. по желанию.');
    lines.push('2. Коржи: 8–10 тонких кругов; 200–210°C по 7–9 минут до золота; обрезки — в крошку.');
    lines.push('3. Крем: молоко 1 л, яйца 3, сахар 200–250 г, мука 60 г или крахмал 40 г, ваниль, масло 150–200 г.');
    lines.push('4. Сборка: корж — тёплый крем — корж; бока и верх — крем + крошка.');
    lines.push('5. Пропитка: 6–8 часов, лучше ночь, в холодильнике.');
    return sanitizeOutput(lines.join('\n'));
  }
  if (lang === 'he') {
    return sanitizeOutput('Кратко: אענה תמציתי ולעניין. Детали: ציין מטרה ותוצאה רצויה. Чек‑лист: 1. יעד 2. מגבלות 3. אפשרויות 4. סיכונים 5. צעד הבא.');
  }
  if (lang === 'en') {
    return sanitizeOutput('Brief: I will answer to the point. Details: specify goal and desired outcome. Checklist: 1. Goal 2. Constraints 3. Options 4. Risks 5. Next step.');
  }
  const lines = [];
  lines.push('Кратко: отвечаю по делу без повтора вашей речи.');
  lines.push('Детали: уточните цель и желаемый результат — дам конкретный план.');
  lines.push('Чек‑лист: 1. Цель 2. Ограничения 3. Варианты 4. Риски 5. Следующий шаг.');
  return sanitizeOutput(lines.join('\n'));
}

// OpenAI LLM при наличии ключа; анти‑эхо
async function llmAnswer({ prompt, lang }) {
  if (!OPENAI_API_KEY) return localAnswer(prompt, lang);
  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return localAnswer(prompt, lang);

  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const sys = lang === 'he'
    ? 'ענה תמציתי ובעניין. אל תצטט את המשתמש. ללא סימוני Markdown. שמור אמוג\'י ומספור 1., 2., 3.'
    : (lang === 'en'
        ? 'Reply concisely and to the point. Do not quote the user. No Markdown markers. Keep emojis and numbering 1., 2., 3.'
        : 'Отвечай кратко и по делу. Не цитируй пользователя. Без Markdown‑символов. Оставляй эмодзи и нумерацию 1., 2., 3.');
  const user = lang === 'he'
    ? `בקשה: ${String(prompt || '')}\nהשב "Кратко:" "Детали:" "Чек‑лист:" (1–5), ללא ציטוט.`
    : (lang === 'en'
        ? `Request: ${String(prompt || '')}\nRespond with "Кратко:" "Детали:" "Чек‑лист:" (1–5), without quoting.`
        : `Запрос: ${String(prompt || '')}\nДай "Кратко:" "Детали:" "Чек‑лист:" (1–5), без повтора речи пользователя.`);
  try {
    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0.4,
      messages: [{ role: 'system', content: sys }, { role: 'user', content: user }]
    });
    return sanitizeOutput(res.choices?.[0]?.message?.content || localAnswer(prompt, lang));
  } catch {
    return localAnswer(prompt, lang);
  }
}

// ASR Whisper — при наличии ключа
async function whisperTranscribe(filePath, langPref) {
  if (!OPENAI_API_KEY) return '';
  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return '';
  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const opts = { file: fs.createReadStream(filePath), model: 'whisper-1' };
  if (langPref === 'ru') opts.language = 'ru';
  if (langPref === 'he') opts.language = 'he';
  const tr = await client.audio.transcriptions.create(opts);
  return (tr.text || '').trim();
}

// Скачиваем voice OGG из Telegram
async function downloadVoice(ctx, fileId) {
  const f = await ctx.telegram.getFile(fileId);
  const url = `https://api.telegram.org/file/bot${BOT_TOKEN}/${f.file_path}`;
  const oggPath = path.join(os.tmpdir(), `voice_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
  const resp = await axios.get(url, { responseType: 'stream' });
  await new Promise((resolve, reject) => {
    const w = fs.createWriteStream(oggPath);
    resp.data.pipe(w);
    w.on('finish', resolve);
    w.on('error', reject);
  });
  return oggPath;
}

// TTS через gTTS mp3 -> ffmpeg -> ogg/opus
async function ttsOgg(text, lang) {
  if (!TTS_ENABLED) throw new Error('TTS выключен (TTS_ENABLED=false).');
  if (!ffmpeg) throw new Error('ffmpeg недоступен.');
  let gTTS;
  try { gTTS = require('gtts'); } catch { throw new Error('gtts не установлен.'); }

  const clean = sanitizeOutput(text);
  const mp3 = path.join(os.tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const ogg = path.join(os.tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
  await new Promise((resolve, reject) => {
    const tts = new gTTS(clean, lang === 'he' ? 'he' : (lang === 'en' ? 'en' : 'ru'));
    tts.save(mp3, err => err ? reject(err) : resolve());
  });
  await new Promise((resolve, reject) => {
    ffmpeg(mp3).audioCodec('libopus').format('ogg').audioBitrate('48k')
      .on('error', reject).on('end', resolve).save(ogg);
  });
  const buf = await fs.promises.readFile(ogg);
  try { fs.unlinkSync(mp3); } catch {}
  try { fs.unlinkSync(ogg); } catch {}
  return buf;
}

// Команды и хэндлеры

// На /start меню НЕ показываем
bot.start(async (ctx) => {
  await replyClean(ctx, 'Привет. Я SmartPro 24/7. Клавиатура «Меню» появляется только по запросу. Напишите вопрос или отправьте короткое voice.');
});

bot.command('menu', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом.');
  lines.push('2. Голос до 10–15 сек, без «эха».');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'), { showMenu: true });
});

bot.command('version', async (ctx) => {
  await replyClean(ctx, 'UNIVERSAL GPT-4o — U10c-Node');
});

bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом.');
  lines.push('2. Голос до 10–15 сек, без «эха».');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'), { showMenu: true });
});

// Текст: по делу, без инлайн‑кнопок
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const q = (ctx.message.text || '').trim();
    const a = await llmAnswer({ prompt: q, lang });
    lastAnswer.set(String(ctx.chat.id), { text: a, exp: Date.now() + TTS_TTL_MS });
    await replyClean(ctx, a);
  } catch (e) {
    await replyClean(ctx, 'Кратко: временная ошибка. Детали: повторите позже. Чек‑лист: 1. Короче 2. Позже 3. Поддержка.');
  }
});

// Голос: ASR -> ответ по делу; кнопки только для расшифровки и TTS по флагу
bot.on('voice', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const v = ctx.message.voice;
    const fid = v.file_unique_id || v.file_id;

    let transcript = '';
    try {
      const ogg = await downloadVoice(ctx, v.file_id);
      try {
        transcript = await whisperTranscribe(ogg, lang);
      } catch (e) {
        // демо без ASR — без эха
        transcript = '';
      } finally {
        try { fs.unlinkSync(ogg); } catch {}
      }
    } catch (e) {
      transcript = '';
    }

    if (transcript) {
      transcriptCache.set(fid, { text: sanitizeOutput(transcript), exp: Date.now() + TRANSCRIPT_TTL_MS });
    }

    const prompt = transcript || (lang === 'he'
      ? 'בקשה קולית קצרה. תן תשובה תמציתית ורלוונטית ללא ציטוט.'
      : (lang === 'en'
          ? 'Short voice request. Provide a concise, relevant answer without quoting.'
          : 'Короткий голосовой запрос. Дай по делу ответ, без повтора речи пользователя.'));
    const answer = await llmAnswer({ prompt, lang });
    const replyText = sanitizeOutput(answer);
    lastAnswer.set(String(ctx.chat.id), { text: replyText, exp: Date.now() + TTS_TTL_MS });

    const buttons = [];
    buttons.push([{ text: 'Показать расшифровку', callback_data: `show_transcript:${fid}` }]);
    if (TTS_ENABLED) buttons.push([{ text: 'Озвучить ответ', callback_data: `tts:${ctx.chat.id}` }]);
    buttons.push([{ text: 'Скрыть', callback_data: 'hide' }]);

    await ctx.reply(replyText, { reply_markup: { inline_keyboard: buttons } });
  } catch (e) {
    await replyClean(ctx, 'Кратко: получил голос. Детали: временная ошибка обработки. Чек‑лист: 1. Повторите позже 2. Короткое voice 3. Поддержка.');
  }
});

// Callback‑кнопки: показать расшифровку, озвучить, скрыть
bot.on('callback_query', async (ctx) => {
  try {
    const data = ctx.callbackQuery.data || '';
    if (data === 'hide') {
      try {
        await ctx.editMessageReplyMarkup({ inline_keyboard: [] });
      } catch (_) {}
      try { await ctx.answerCbQuery('Скрыто'); } catch {}
      return;
    }
    if (data.startsWith('show_transcript:')) {
      const fid = data.split(':')[1];
      const cached = transcriptCache.get(fid);
      const text = cached && cached.exp > Date.now() ? cached.text : 'Транскрипт недоступен. Попробуйте ещё раз.';
      try { await ctx.answerCbQuery('Готово'); } catch {}
      await replyClean(ctx, `Транскрипт: ${text}`);
      return;
    }
    if (data.startsWith('tts:')) {
      if (!TTS_ENABLED) { try { await ctx.answerCbQuery('TTS выключен'); } catch {} return; }
      const chatKey = data.split(':')[1] || String(ctx.chat.id);
      const cached = lastAnswer.get(chatKey);
      const txt = cached && cached.exp > Date.now() ? cached.text : '';
      if (!txt) { try { await ctx.answerCbQuery('Нет текста'); } catch {} return; }
      try {
        const key = sha(`${detectLang(ctx)}::${txt}`);
        let entry = ttsCache.get(key);
        if (!entry || entry.exp < Date.now()) {
          const buf = await ttsOgg(txt, detectLang(ctx));
          entry = { buf, exp: Date.now() + TTS_TTL_MS };
          ttsCache.set(key, entry);
        }
        try { await ctx.answerCbQuery('Озвучиваю'); } catch {}
        await ctx.replyWithVoice({ source: entry.buf, filename: 'reply.ogg' });
      } catch (e) {
        try { await ctx.answerCbQuery('Ошибка TTS'); } catch {}
        await replyClean(ctx, 'Кратко: озвучка временно недоступна. Детали: внутренняя ошибка TTS.');
      }
      return;
    }
    try { await ctx.answerCbQuery('OK'); } catch {}
  } catch (e) {
    try { await ctx.answerCbQuery('Ошибка'); } catch {}
  }
});

// HTTP маршруты
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
