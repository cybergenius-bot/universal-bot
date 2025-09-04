// index.js — Express + Telegraf: только текстовые ответы, без TTS; «Меню» — только по запросу.
// Зависимости: express, telegraf, axios (openai — опционально для реальных ответов)

const express = require('express');
const { Telegraf } = require('telegraf');
const axios = require('axios');
const fs = require('fs');
const os = require('os');
const path = require('path');

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

// Бот
const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 10000 });

// Reply‑клавиатура «Меню» (по запросу)
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: false,
  selective: true,
};

// Санитаризация: убираем # * _ ` и цитаты/тире‑маркеры; эмодзи и 1., 2., 3. — сохраняем
function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}

// Детект языка: RU/HE приоритет, EN — осторожный режим
function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}

// Отправка с управлением меню: по умолчанию — скрываем
async function replyClean(ctx, text, { showMenu = false } = {}) {
  const cleaned = sanitizeOutput(text);
  if (showMenu) {
    return ctx.reply(cleaned, { reply_markup: replyKeyboard });
  }
  return ctx.reply(cleaned, { reply_markup: { remove_keyboard: true } });
}

// LLM ответ (без «эха»). Если нет OPENAI_API_KEY — аккуратный фолбэк.
async function llmAnswer({ prompt, lang }) {
  const textPrompt = String(prompt || '').trim();

  if (!OPENAI_API_KEY) {
    if (lang === 'he') {
      return 'Кратко: אענה תכלס ולעניין. Детали: ציין מטרה ותוצאה רצויה. Чек-лист: 1. יעד 2. מגבלות 3. אפשרויות 4. סיכונים 5. צעד הבא.';
    }
    if (lang === 'en') {
      return 'Brief: I will respond to the point. Details: specify goal and desired outcome. Checklist: 1. Goal 2. Constraints 3. Options 4. Risks 5. Next step.';
    }
    return 'Кратко: отвечаю по делу. Детали: уточните цель и желаемый результат. Чек‑лист: 1. Цель 2. Ограничения 3. Варианты 4. Риски 5. Следующий шаг.';
  }

  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) {
    return 'Кратко: модель недоступна. Детали: добавьте зависимость openai и переменную OPENAI_API_KEY.';
  }

  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const sys = lang === 'he'
    ? 'ענה תמציתי ובעניין. אל תצטט את המשתמש. ללא סימוני Markdown. שמור על אמוג\'י ומספור 1., 2., 3.'
    : (lang === 'en'
        ? 'Reply concisely and to the point. Do not quote the user. No Markdown markers. Keep emojis and numbering 1., 2., 3.'
        : 'Отвечай кратко и по делу. Не цитируй пользователя. Без Markdown‑символов. Оставляй эмодзи и нумерацию 1., 2., 3.');

  const user = lang === 'he'
    ? `בקשה: ${textPrompt}\nהשב במבנה "Кратко:" "Детали:" "Чек-лист:" עם 1–5, בלי לצטט.`
    : (lang === 'en'
        ? `Request: ${textPrompt}\nRespond with sections "Кратко:" "Детали:" "Чек-лист:" (1–5), without quoting.`
        : `Запрос: ${textPrompt}\nДай ответ блоками "Кратко:" "Детали:" "Чек‑лист:" (1–5), без повтора речи пользователя.`);

  try {
    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0.4,
      messages: [
        { role: 'system', content: sys },
        { role: 'user', content: user }
      ]
    });
    return sanitizeOutput(res.choices?.[0]?.message?.content || '');
  } catch (e) {
    console.error('LLM error:', e?.response?.data || e.message);
    return 'Кратко: временная ошибка генерации. Детали: повторите позже. Чек‑лист: 1. Повтор 2. Короче 3. Позже.';
  }
}

// ===== Команды =====
bot.start(async (ctx) => {
  const msg = 'Привет. Я SmartPro 24/7. Голос — без эха. Клавиатура с Меню не всплывает сама. Нажмите Меню, когда нужны действия.';
  await replyClean(ctx, msg, { showMenu: true });
});

bot.command('version', async (ctx) => {
  await replyClean(ctx, 'UNIVERSAL GPT-4o — U10c-Node');
});

bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Голос до 10–15 сек. Без эха.');
  lines.push('2. Расшифровка — по кнопке, кэш 15 мин.');
  lines.push('3. Ответы — всегда текстом.');
  lines.push('4. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'), { showMenu: true });
});

// ===== Текст: только письменный ответ, без инлайн‑кнопок и без всплывающего «Меню» =====
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const userText = (ctx.message.text || '').trim();
    const answer = await llmAnswer({ prompt: userText, lang });
    await replyClean(ctx, answer);
  } catch (e) {
    console.error('text error:', e);
    await replyClean(ctx, 'Кратко: временная ошибка. Детали: повторите позже. Чек‑лист: 1. Короче 2. Позже 3. Поддержка.');
  }
});

// ===== Голос: отвечаем ПИСЬМЕННО. Инлайн‑кнопки только для расшифровки/скрыть. НИКАКОГО TTS =====
bot.on('voice', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const v = ctx.message.voice;
    const fid = v.file_unique_id || v.file_id;

    // Скачиваем файл; если нет ASR — дадим ответ по делу по умолчанию
    let transcript = '';
    try {
      if (OPENAI_API_KEY) {
        const f = await ctx.telegram.getFile(v.file_id);
        const url = `https://api.telegram.org/file/bot${BOT_TOKEN}/${f.file_path}`;
        const oggTmp = path.join(os.tmpdir(), `voice_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
        const resp = await axios.get(url, { responseType: 'stream' });
        await new Promise((resolve, reject) => {
          const w = fs.createWriteStream(oggTmp);
          resp.data.pipe(w);
          w.on('finish', resolve);
          w.on('error', reject);
        });
        // Whisper — опционально
        let OpenAI;
        try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
        if (OpenAI) {
          const client = new OpenAI({ apiKey: OPENAI_API_KEY });
          const tr = await client.audio.transcriptions.create({
            file: fs.createReadStream(oggTmp),
            model: 'whisper-1',
            language: lang === 'he' ? 'he' : (lang === 'en' ? 'en' : 'ru')
          });
          transcript = (tr.text || '').trim();
        }
        try { fs.unlinkSync(oggTmp); } catch {}
      }
    } catch (err) {
      console.error('ASR error:', err?.response?.data || err.message);
    }

    const prompt = transcript || (lang === 'he'
      ? 'בקשה קולית קצרה. תן תשובה תמציתית ורלוונטית ללא ציטוט.'
      : (lang === 'en'
          ? 'Short voice request. Provide a concise, relevant answer without quoting.'
          : 'Короткий голосовой запрос. Дай ответ по делу, без повтора речи пользователя.'));
    const answer = await llmAnswer({ prompt, lang });

    // Инлайн‑кнопки ТОЛЬКО: показать расшифровку (если есть) и скрыть
    const inline = { inline_keyboard: [] };
    if (transcript && transcript.trim()) {
      inline.inline_keyboard.push([{ text: 'Показать расшифровку', callback_data: `show_transcript:${fid}` }]);
    }
    inline.inline_keyboard.push([{ text: 'Скрыть', callback_data: 'hide' }]);

    await ctx.reply(sanitizeOutput(answer), { reply_markup: inline });
    // Кэш транскрипта (простой на 15 мин — можно доработать при необходимости)
    if (transcript) {
      voiceTranscripts.set(fid, { text: sanitizeOutput(transcript), exp: Date.now() + 15 * 60 * 1000 });
    }
  } catch (e) {
    console.error('voice error:', e);
    await replyClean(ctx, 'Кратко: получил голос. Детали: временная ошибка обработки. Чек‑лист: 1. Повторите позже 2. Короткое voice 3. Поддержка.');
  }
});

// Простой кэш для транскриптов (на 15 мин)
const voiceTranscripts = new Map();
function getTranscript(fid) {
  const v = voiceTranscripts.get(fid);
  if (!v) return null;
  if (v.exp < Date.now()) { voiceTranscripts.delete(fid); return null; }
  return v.text;
}

// Callback: показать расшифровку / скрыть
bot.on('callback_query', async (ctx) => {
  try {
    const data = ctx.callbackQuery.data || '';
    if (data === 'hide') {
      try { await ctx.editMessageReplyMarkup(undefined); } catch {}
      await ctx.answerCbQuery('Скрыто');
      return;
    }
    if (data.startsWith('show_transcript:')) {
      const fid = data.split(':')[1];
      const text = fid ? getTranscript(fid) : null;
      await ctx.answerCbQuery(text ? 'Готово' : 'Недоступно');
      await replyClean(ctx, text || 'Транскрипт недоступен. Попробуйте ещё раз.');
      return;
    }
    await ctx.answerCbQuery('OK');
  } catch (e) {
    console.error('callback error:', e);
    try { await ctx.answerCbQuery('Ошибка'); } catch {}
  }
});

// ===== HTTP маршруты =====
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
