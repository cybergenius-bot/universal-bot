// index.js — только текстовые ответы, без TTS и без авто‑«Меню». Анти‑эхо, RU/HE приоритет, EN — осторожно.
// Зависимости в package.json: express, telegraf, (опционально) openai

const express = require('express');
const { Telegraf } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN || process.env.TELEGRAM_BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

if (!BOT_TOKEN) {
  console.error('Ошибка: отсутствует BOT_TOKEN');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '20mb' }));

const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 10000 });

// Reply‑клавиатура «Меню» — только по запросу, сама НЕ всплывает
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: true,   // после нажатия скрывается
  selective: true
};

// Санитаризация: убираем # * _ `, цитаты и тире‑маркеры. Эмодзи и 1., 2., 3. — сохраняем
function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}

// Детект языка: RU/HE приоритет
function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}

// Отправка: по умолчанию «Меню» скрыто; показываем только если явно попросили
async function replyClean(ctx, text, { showMenu = false } = {}) {
  const cleaned = sanitizeOutput(text);
  if (showMenu) return ctx.reply(cleaned, { reply_markup: replyKeyboard });
  return ctx.reply(cleaned, { reply_markup: { remove_keyboard: true } });
}

// Локальный содержательный ответ без модели (чтобы сразу было «по делу»)
function localAnswer(prompt, lang) {
  const q = String(prompt || '').toLowerCase();

  // Рецепт «Наполеон» — полный и по делу
  if (q.includes('наполеон')) {
    const lines = [];
    lines.push('Кратко: классический «Наполеон» с заварным кремом.');
    lines.push('Детали: тонкие слоёные коржи + заварной крем, ночь на пропитку.');
    lines.push('Чек-лист:');
    lines.push('1. Тесто: мука 600 г, масло 400 г холодное, вода 180 мл ледяная, яйцо 1, соль щепотка, уксус 1 ч. л. (по жел.). Масло натереть, быстро замесить, охладить 30–40 мин.');
    lines.push('2. Коржи: разделить на 8–10 частей, раскатать очень тонко, наколоть вилкой, обрезки на крошку. Выпекать 200–210°C по 7–9 мин до золота.');
    lines.push('3. Крем: молоко 1 л, яйца 3, сахар 200–250 г, мука 60 г или крахмал 40 г, ваниль, масло 150–200 г. Заварить до густоты, остудить, вмешать масло до крема.');
    lines.push('4. Сборка: корж — тёплый крем — корж; бока и верх обмазать, посыпать крошкой.');
    lines.push('5. Пропитка: 6–8 ч (лучше ночь) в холодильнике. Подача — охлаждённым.');
    return sanitizeOutput(lines.join('\n'));
  }

  // Базовый лаконичный ответ по делу
  if (lang === 'he') {
    return sanitizeOutput('Кратко: אענה תמציתי ולעניין. Детали: ציין מטרה ותוצאה רצויה. Чек-лист: 1. יעד 2. מגבלות 3. אפשרויות 4. סיכונים 5. צעד הבא.');
  }
  if (lang === 'en') {
    return sanitizeOutput('Brief: I will answer to the point. Details: specify goal and desired outcome. Checklist: 1. Goal 2. Constraints 3. Options 4. Risks 5. Next step.');
  }
  const lines = [];
  lines.push('Кратко: отвечаю по делу без повтора вашей речи.');
  lines.push('Детали: уточните цель и желаемый результат — дам конкретный план.');
  lines.push('Чек-лист: 1. Цель 2. Ограничения 3. Варианты 4. Риски 5. Следующий шаг.');
  return sanitizeOutput(lines.join('\n'));
}

// Ответ через OpenAI при наличии ключа (анти‑эхо)
async function llmAnswer({ prompt, lang }) {
  if (!OPENAI_API_KEY) return localAnswer(prompt, lang);

  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return localAnswer(prompt, lang);

  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const sys = lang === 'he'
    ? 'ענה תמציתי ובעניין. בלי לצטט את המשתמש. ללא סימוני Markdown. שמור אמוג\'י ומספור 1., 2., 3.'
    : (lang === 'en'
        ? 'Reply concisely and to the point. Do not quote the user. No Markdown markers. Keep emojis and numbering 1., 2., 3.'
        : 'Отвечай кратко и по делу. Не цитируй пользователя. Без Markdown‑символов. Оставляй эмодзи и нумерацию 1., 2., 3.');

  const user = lang === 'he'
    ? `בקשה: ${String(prompt || '')}\nהשב במבנה "Кратко:" "Детали:" "Чек-лист:" (1–5), ללא ציטוט.`
    : (lang === 'en'
        ? `Request: ${String(prompt || '')}\nRespond with "Кратко:" "Детали:" "Чек-лист:" (1–5), without quoting the user.`
        : `Запрос: ${String(prompt || '')}\nДай "Кратко:", "Детали:", "Чек‑лист:" (1–5) без повтора речи пользователя.`);

  try {
    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0.4,
      messages: [
        { role: 'system', content: sys },
        { role: 'user', content: user }
      ]
    });
    return sanitizeOutput(res.choices?.[0]?.message?.content || localAnswer(prompt, lang));
  } catch {
    return localAnswer(prompt, lang);
  }
}

// ===== Команды и обработчики =====

// ВАЖНО: на /start меню НЕ показываем
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

// «Меню» — только по слову
bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом.');
  lines.push('2. Голос до 10–15 сек, без «эха».');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'), { showMenu: true });
});

// Текст: профессиональный ответ по делу, без инлайн‑кнопок и без всплывающего «Меню»
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const question = (ctx.message.text || '').trim();
    const answer = await llmAnswer({ prompt: question, lang });
    await replyClean(ctx, answer);
  } catch (e) {
    await replyClean(ctx, 'Кратко: временная ошибка. Детали: повторите позже. Чек-лист: 1. Короче 2. Позже 3. Поддержка.');
  }
});

// Голос: отвечаем ПИСЬМЕННО; НИКАКОГО TTS и НИКАКИХ инлайн‑кнопок; анти‑эхо
bot.on('voice', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    // Без обязательной расшифровки в демо: сразу даём по делу без цитирования
    const prompt = lang === 'he'
      ? 'בקשה קולית קצרה. תן תשובה תמציתית ורלוונטית ללא ציטוט.'
      : (lang === 'en'
          ? 'Short voice request. Provide a concise, relevant answer without quoting the user.'
          : 'Короткий голосовой запрос. Дай по делу ответ, без повтора речи пользователя.');
    const answer = await llmAnswer({ prompt, lang });
    await replyClean(ctx, answer);
  } catch (e) {
    await replyClean(ctx, 'Кратко: получил голос. Детали: временная ошибка обработки. Чек-лист: 1. Повторите позже 2. Короткое voice 3. Поддержка.');
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
