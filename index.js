// index.js — Node (Express + Telegraf) с демо-ASR/TTS, анти‑эхо, строгим UX и вебхуком
// Требуются пакеты: express, telegraf, fluent-ffmpeg, ffmpeg-static, gtts

const express = require('express');
const { Telegraf } = require('telegraf');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

// ffmpeg для TTS конвертации в OGG (voice)
let ffmpeg;
let ffmpegPath;
try {
  ffmpeg = require('fluent-ffmpeg');
  ffmpegPath = require('ffmpeg-static');
  if (ffmpegPath) ffmpeg.setFfmpegPath(ffmpegPath);
} catch (_) {
  // если нет зависимостей — TTS будет отключён
}

// ENV
const BOT_TOKEN = process.env.BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const PORT = process.env.PORT || 3000;

if (!BOT_TOKEN) {
  console.error('Ошибка: отсутствует BOT_TOKEN в переменных окружения.');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '10mb' }));

// Telegraf
const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 9000 });

// Строгий UX: одна Reply‑кнопка «Меню» всегда
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: false,
  selective: true,
};

// Память: кэши и лимиты
const transcriptCache = new Map(); // key: file_unique_id -> { text, exp }
const ttsCache = new Map();        // key: hash(text+lang) -> { buf, exp }
const lastAnswer = new Map();      // key: chatId -> { text, exp }
const userQuota = new Map();       // key: userId -> { ttsSec, voiceSec, resetAt }

// Параметры демо
const TRANSCRIPT_TTL_MS = 15 * 60 * 1000;
const TTS_TTL_MS = 15 * 60 * 1000;
const QUOTA_TTS_SEC_PER_DAY = 120;   // ~2 мин в день
const QUOTA_VOICE_SEC_PER_DAY = 60;  // ~1 мин в день
const SINGLE_TTS_MAX_SEC = 20;       // один ответ до ~20 сек
const ASR_MAX_SEC = 15;              // принимать короткие voice до ~10–15 сек

// Утилиты
function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}

function now() { return Date.now(); }

function ensureQuotaBucket(userId) {
  const b = userQuota.get(userId);
  if (!b || b.resetAt < now()) {
    userQuota.set(userId, {
      ttsSec: 0,
      voiceSec: 0,
      // простое скользящее окно 24 часа
      resetAt: now() + 24 * 60 * 60 * 1000,
    });
  }
  return userQuota.get(userId);
}

function addVoiceUsage(userId, seconds) {
  const b = ensureQuotaBucket(userId);
  b.voiceSec += seconds;
  return b.voiceSec <= QUOTA_VOICE_SEC_PER_DAY;
}

function estimateTtsSecondsByText(text) {
  // приблизительно 15 символов в секунду
  const charsPerSec = 15;
  return Math.ceil(text.length / charsPerSec);
}

function clampTtsTextForDuration(text, lang) {
  // ограничим до SINGLE_TTS_MAX_SEC
  const charsPerSec = 15;
  const maxChars = SINGLE_TTS_MAX_SEC * charsPerSec;
  let t = text;
  if (t.length > maxChars) {
    t = t.slice(0, maxChars);
    // стараться не резать слово в середине
    const idx = t.lastIndexOf(' ');
    if (idx > 0) t = t.slice(0, idx);
    t += ' …';
  }
  return t;
}

function addTtsUsage(userId, seconds) {
  const b = ensureQuotaBucket(userId);
  b.ttsSec += seconds;
  return b.ttsSec <= QUOTA_TTS_SEC_PER_DAY;
}

function cacheSet(map, key, val, ttlMs) {
  map.set(key, { ...val, exp: now() + ttlMs });
}

function cacheGet(map, key) {
  const v = map.get(key);
  if (!v) return null;
  if (v.exp < now()) {
    map.delete(key);
    return null;
  }
  return v;
}

function sha(input) {
  return crypto.createHash('sha1').update(input).digest('hex');
}

function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}

// Минимальный ответ генератора (без эха)
function buildStructuredAnswer(lang) {
  if (lang === 'he') {
    const lines = [];
    lines.push('Кратко: получил голос и понял задачу. Отвечаю תכלס ולעניין.');
    lines.push('Детали: אתן תשובה ממוקדת ורלוונטית לפי ההקשר, בלי לחזור על מה שאמרת.');
    lines.push('Чек-лист:');
    lines.push('1. Цель: להבהיר יעד קצר ומדיד.');
    lines.push('2. Ограничения: זמן, תקציב, איכות, סיכונים.');
    lines.push('3. Варианты: 2–3 גישות מעשיות.');
    lines.push('4. Риски: מה יכול להשתבש ואיך לצמצם.');
    lines.push('5. Следующий шаг: פעולה אחת קונקרטית עכשיו.');
    return sanitizeOutput(lines.join('\n'));
  }
  if (lang === 'en') {
    const lines = [];
    lines.push('Brief: voice received, task understood. I will reply concisely without repeating your speech.');
    lines.push('Details: a focused, context-aware response will follow.');
    lines.push('Checklist:');
    lines.push('1. Goal: clarify a short, measurable outcome.');
    lines.push('2. Constraints: time, budget, quality, risks.');
    lines.push('3. Options: 2–3 practical approaches.');
    lines.push('4. Risks: what could go wrong and mitigations.');
    lines.push('5. Next step: one concrete action now.');
    return sanitizeOutput(lines.join('\n'));
  }
  const lines = [];
  lines.push('Кратко: получил голос и понял задачу. Отвечаю по делу без повтора вашей речи.');
  lines.push('Детали: дам фокусированный ответ с учётом контекста.');
  lines.push('Чек-лист:');
  lines.push('1. Цель: уточнить краткий измеримый результат.');
  lines.push('2. Ограничения: время, бюджет, качество, риски.');
  lines.push('3. Варианты: 2–3 практичных подхода.');
  lines.push('4. Риски: что может пойти не так и как снизить.');
  lines.push('5. Следующий шаг: одно конкретное действие сейчас.');
  return sanitizeOutput(lines.join('\n'));
}

// TTS: gTTS mp3 -> ffmpeg -> ogg/opus (Buffer)
async function ttsToOggBuffer(text, lang) {
  // динамический импорт gtts, чтобы не падать при отсутствии пакета
  let gTTS;
  try {
    gTTS = require('gtts');
  } catch (e) {
    throw new Error('TTS недоступен: пакет gtts не установлен.');
  }
  if (!ffmpeg) {
    throw new Error('TTS недоступен: ffmpeg не найден.');
  }

  text = sanitizeOutput(text);
  const mp3Tmp = path.join(require('os').tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const oggTmp = path.join(require('os').tmpdir(), `tts_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);

  // 1) генерируем mp3
  await new Promise((resolve, reject) => {
    const tts = new gTTS(text, lang === 'he' ? 'he' : (lang === 'en' ? 'en' : 'ru'));
    tts.save(mp3Tmp, (err) => (err ? reject(err) : resolve()));
  });

  // 2) mp3 -> ogg/opus через ffmpeg
  await new Promise((resolve, reject) => {
    ffmpeg(mp3Tmp)
      .audioCodec('libopus')
      .format('ogg')
      .audioBitrate('48k')
      .on('error', reject)
      .on('end', resolve)
      .save(oggTmp);
  });

  const buf = await fs.promises.readFile(oggTmp).finally(async () => {
    try { fs.unlinkSync(mp3Tmp); } catch (_) {}
    try { fs.unlinkSync(oggTmp); } catch (_) {}
  });

  return buf;
}

// Команды/хэндлеры
bot.start(async (ctx) => {
  const msg = sanitizeOutput('Привет. Я работаю 24/7. Никаких звёздочек и решёток: только чистый текст, эмодзи и нумерация 1., 2., 3. Нажмите Меню для подсказок.');
  await ctx.reply(msg, { reply_markup: replyKeyboard });
});

bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT-4o — U10c-Node', { reply_markup: replyKeyboard });
});

bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Голос: короткие сообщения до 10–15 сек, без эха.');
  lines.push('2. Транскрипт: только по кнопке, кэш 15 мин.');
  lines.push('3. Озвучка ответа: до ~20 сек, кэш 15 мин.');
  lines.push('4. Лимиты: TTS ~2 мин/день, голос ~1 мин/день.');
  lines.push('5. Вебхук: /telegram/railway123, версия: /version.');
  await ctx.reply(sanitizeOutput(lines.join('\n')), { reply_markup: replyKeyboard });
});

// Голос: анти‑эхо, ответ по структуре + инлайн‑кнопки
bot.on('voice', async (ctx) => {
  try {
    const voice = ctx.message.voice;
    const userId = ctx.from.id;
    const chatId = ctx.chat.id;
    const lang = detectLang(ctx);

    const dur = Math.max(0, Math.min(ASR_MAX_SEC, voice?.duration || 0));
    const ok = addVoiceUsage(userId, dur);
    if (!ok) {
      await ctx.reply(sanitizeOutput('Кратко: дневной лимит голосовых исчерпан. Детали: попробуйте завтра. Чек‑лист: 1. Отправьте текст 2. Сократите голос 3. Дождитесь сброса лимита.'), { reply_markup: replyKeyboard });
      return;
    }

    // Демо-ASR: транскрипт только по кнопке, без «эха»
    // Сохраняем плейсхолдер транскрипта в кэш на 15 мин
    const fid = voice.file_unique_id || voice.file_id;
    const demoTranscript = lang === 'he'
      ? `דמו: אורך קול ~ ${dur} שניות.`
      : (lang === 'en'
          ? `Demo: voice length ~ ${dur} sec.`
          : `Демо: длина голоса ~ ${dur} сек.`);
    cacheSet(transcriptCache, fid, { text: sanitizeOutput(demoTranscript) }, TRANSCRIPT_TTL_MS);

    // Формируем структурный ответ (без повтора речи)
    const replyText = buildStructuredAnswer(lang);

    // Инлайн‑кнопки под ответом (по сценариям voice)
    const inlineKeyboard = {
      inline_keyboard: [
        [{ text: 'Показать расшифровку', callback_data: `show_transcript:${fid}` },
         { text: 'Озвучить ответ', callback_data: `tts_reply:${chatId}` }],
        [{ text: 'Скрыть', callback_data: 'hide' }],
      ],
    };

    const sent = await ctx.reply(replyText, { reply_markup: inlineKeyboard });
    // Кэшируем последний ответ для TTS на 15 мин
    cacheSet(lastAnswer, String(chatId), { text: replyText }, TTS_TTL_MS);
  } catch (e) {
    console.error('voice handler error:', e);
    await ctx.reply(sanitizeOutput('Кратко: получил голос. Детали: временная ошибка обработки. Чек‑лист: 1. Повторите позже 2. Сократите длительность 3. Сообщите в поддержку.'), { reply_markup: replyKeyboard });
  }
});

// Callback: показать расшифровку
bot.on('callback_query', async (ctx) => {
  try {
    const data = ctx.callbackQuery.data || '';
    if (data === 'hide') {
      // закрыть инлайн‑клавиатуру
      try {
        await ctx.editMessageReplyMarkup(undefined);
      } catch (_) {}
      await ctx.answerCbQuery('Скрыто');
      return;
    }

    // show_transcript:<fid>
    if (data.startsWith('show_transcript:')) {
      const fid = data.split(':')[1];
      const cached = fid ? cacheGet(transcriptCache, fid) : null;
      const text = cached?.text || 'Транскрипт недоступен в демо‑режиме.';
      await ctx.answerCbQuery('Готово');
      await ctx.reply(sanitizeOutput(`Транскрипт (демо): ${text}`), { reply_markup: replyKeyboard });
      return;
    }

    // tts_reply:<chatId>
    if (data.startsWith('tts_reply:')) {
      const chatKey = data.split(':')[1] || String(ctx.chat.id);
      const cached = cacheGet(lastAnswer, chatKey);
      if (!cached || !cached.text) {
        await ctx.answerCbQuery('Нет текста для озвучки');
        return;
      }
      const userId = ctx.from.id;
      const lang = detectLang(ctx);
      // ограничим длительность TTS и учтём квоту
      const textClamped = clampTtsTextForDuration(cached.text, lang);
      const ttsSec = Math.min(SINGLE_TTS_MAX_SEC, estimateTtsSecondsByText(textClamped));
      const ok = addTtsUsage(userId, ttsSec);
      if (!ok) {
        await ctx.answerCbQuery('Лимит TTS исчерпан');
        await ctx.reply(sanitizeOutput('Кратко: дневной лимит TTS исчерпан. Детали: попробуйте завтра или сократите текст. Чек‑лист: 1. Меньше текста 2. Позже 3. Уведомить поддержку.'), { reply_markup: replyKeyboard });
        return;
      }

      // кэш по тексту и языку
      const key = sha(`${lang}::${textClamped}`);
      let bufEntry = cacheGet(ttsCache, key);
      try {
        if (!bufEntry) {
          const buf = await ttsToOggBuffer(textClamped, lang);
          bufEntry = { buf };
          cacheSet(ttsCache, key, bufEntry, TTS_TTL_MS);
        }
        await ctx.answerCbQuery('Озвучиваю');
        await ctx.replyWithVoice({ source: bufEntry.buf, filename: 'reply.ogg' }, { reply_markup: replyKeyboard });
      } catch (e) {
        console.error('tts error:', e);
        await ctx.answerCbQuery('Ошибка TTS');
        await ctx.reply(sanitizeOutput('Кратко: озвучка временно недоступна. Детали: внутренняя ошибка TTS. Чек‑лист: 1. Повторите позже 2. Проверьте зависимости 3. Сообщите в поддержку.'), { reply_markup: replyKeyboard });
      }
      return;
    }

    // прочее
    await ctx.answerCbQuery('OK');
  } catch (e) {
    console.error('callback error:', e);
    try { await ctx.answerCbQuery('Ошибка'); } catch (_) {}
  }
});

// Текстовые сообщения: базовый ответ и соблюдение UX
bot.on('message', async (ctx, next) => {
  // игнорируем, если это не текст и не voice (прочие типы нам не нужны)
  return next();
});

bot.catch((err, ctx) => {
  console.error('Telegraf error', err);
});

// ============ Express маршруты ============

// Быстрый пинг версии
app.get('/version', (req, res) => {
  res.status(200).send('UNIVERSAL GPT-4o — U10c-Node');
});

// Проверка, что отвечает Node на GET вебхука
app.get('/telegram/railway123', (req, res) => {
  res.status(200).send('Webhook OK');
});

// Защита секретом и приём вебхука от Telegram
app.post('/telegram/railway123', (req, res, next) => {
  const got = req.get('x-telegram-bot-api-secret-token');
  if (SECRET_TOKEN && got !== SECRET_TOKEN) {
    return res.status(401).send('Unauthorized');
  }
  return next();
}, bot.webhookCallback('/telegram/railway123'));

// Корневой пинг
app.get('/', (req, res) => {
  res.status(200).send('OK');
});

// Стартуем HTTP‑сервер
app.listen(PORT, () => {
  console.log(`Server started on port ${PORT}`);
  console.log('GET /version → 200');
  console.log('GET /telegram/railway123 → Webhook OK');
});
