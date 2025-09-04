// index.js — PRO-режим: длинные профессиональные ответы (800–1200 слов) для текста и голоса
// Строгий UX: одна Reply‑кнопка «Меню», без инлайн‑кнопок по умолчанию, без TTS по умолчанию
// Зависимости: express, telegraf, axios, (опционально) openai

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

// Режим ответов: pro — развернуто, compact — кратко (по умолчанию включаем pro)
const RESPONSE_MODE = (process.env.RESPONSE_MODE || 'pro').toLowerCase(); // 'pro' | 'compact'

if (!BOT_TOKEN) {
  console.error('Нет BOT_TOKEN');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '20mb' }));

const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 15000 });

// Одна Reply‑кнопка «Меню» — всегда видна
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: false,
  selective: true
};

// Санитаризация: убираем # * _ `, цитаты и тире‑маркеры. Эмодзи и 1., 2., 3. — сохраняются
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

// Единая функция отправки: всегда с одной Reply‑кнопкой «Меню»
async function replyClean(ctx, text) {
  return ctx.reply(sanitizeOutput(text), { reply_markup: replyKeyboard });
}

// Локальные подробные ответы без модели — чтобы «из коробки» было профессионально
function localProAnswer(prompt, lang) {
  const q = String(prompt || '').toLowerCase();

  // Пример: Рим — подробный путеводитель
  if (q.includes('рим')) {
    const lines = [];
    lines.push('Кратко: Рим — столица Италии и одна из главных столиц мировой истории и искусства. Город сочетает античность, христианское наследие и яркую современную жизнь, что делает его идеальным направлением для культурного и гастрономического путешествия.');
    lines.push('Детали:');
    lines.push('1. Обзор и география. Рим расположен на берегах Тибра, исторический центр компактен и удобен для пеших прогулок. Ключевые зоны: Колизей и Императорские форумы, район Пьяцца Навона — Пантеон — Треви, Испанская площадь, Трастевере, Ватикан.');
    lines.push('2. История в 6 строках. Основание — миф о Ромуле и Реме; Республика — право и инженерия; Империя — дороги и акведуки; Средневековье — папская власть; Ренессанс и барокко — Микеланджело и Бернини; современность — столица объединённой Италии.');
    lines.push('3. Топ‑10 объектов. Колизей; Римский форум; Палатин; Пантеон; Фонтан Треви; Пьяцца Навона; Испанская лестница; Собор Святого Петра и площади Ватикана; музеи Ватикана (Сикстинская капелла); базилика Санта‑Мария‑Маджоре.');
    lines.push('4. Маршрут на 3 дня. День 1: Колизей — Форум — Палатин — Капитолий — Витториано — Фонтан Треви к вечеру. День 2: Пантеон — Пьяцца Навона — Кампо‑де‑Фьори — Трастевере (ужин). День 3: Ватикан — Собор Петра (купол) — музеи Ватикана — мост Сант‑Анджело.');
    lines.push('5. Еда и районы. Для аутентики — Трастевере и Тестаччо: карбонара, качо‑э‑пепе, суппли, артишоки по‑римски. Завтраки — корнетто с капучино у стоек баров; лучшая пицца — «ал тальо» в районе Пратi и Трастевере.');
    lines.push('6. Логистика. Аэропорты Фьюмичино/Чампино, трансфер в центр — Leonardo Express или шаттлы. Внутри — пешком и метро линии A/B. Билеты на Колизей и музеи Ватикана лучше бронировать заранее, пиковые очереди утром и по понедельникам.');
    lines.push('7. Бюджет. Средний чек в траттории 15–25 евро на человека без вина. Кофе у стойки 1–2 евро. Музеи 12–22 евро. Городской налог на отели взимается на месте.');
    lines.push('8. Безопасность и этикет. Центр относительно безопасен, следите за кошельками в толпе. В храмах — скромная одежда (плечи/колени прикрыты). Воду наливайте из питьевых фонтанчиков «насони» — чистая и бесплатная.');
    lines.push('9. Лучшее время. Апрель–июнь и сентябрь–октябрь: мягкая погода, длинный световой день. Летом жарко, зимой дождливо, но мало туристов.');
    lines.push('10. Полезные советы. Планируйте рано утром «тяжёлые» объекты. На закате идите на холм Джаниколо. Держите мелочь для gelato и espresso. Бронируйте популярные рестораны заранее и счёт проверяйте сразу.');
    lines.push('Чек-лист: 1. Колизей и Ватикан забронировать онлайн. 2. Дни распределить между античностью, барокко и гастрономией. 3. Пит‑стопы: эспрессо утром, gelato днём, траттория вечером. 4. Одежда для храмов. 5. Страховка и карты офлайн.');
    return sanitizeOutput(lines.join('\n'));
  }

  // Пример: «Наполеон» — детальный рецепт
  if (q.includes('наполеон')) {
    const lines = [];
    lines.push('Кратко: классический торт «Наполеон» — тонкие слоёные коржи и заварной крем, ночная пропитка обеспечивает правильную текстуру.');
    lines.push('Детали:');
    lines.push('1. Ингредиенты теста: мука 600 г, холодное сливочное масло 400 г, ледяная вода 180 мл, яйцо 1, соль щепотка, уксус 1 ч. л. по желанию.');
    lines.push('2. Ингредиенты крема: молоко 1 л, сахар 200–250 г, яйца 3, мука 60 г или крахмал 40 г, ваниль, сливочное масло 150–200 г.');
    lines.push('3. Тесто: масло натереть в муку, добавить яйцо, воду, соль, быстро замесить без перегрева, охладить 30–40 минут. Разделить на 8–10 частей.');
    lines.push('4. Коржи: раскатать очень тонко, наколоть вилкой, вырезать круги, обрезки оставить на крошку. Выпекать при 200–210°C по 7–9 минут до золотистого.');
    lines.push('5. Крем: половину сахара с яйцами и мукой (или крахмалом) растереть, влить горячее молоко, заварить до загустения, остудить и ввести мягкое масло до гладкости.');
    lines.push('6. Сборка: корж — тёплый крем — корж; бока и верх обмазать, посыпать крошкой. Охлаждение 6–8 часов (лучше ночь).');
    lines.push('7. Ошибки: перегрев теста (коржи жесткие), недостаточная пропитка, слишком сладкий крем без баланса ванили и соли.');
    lines.push('Чек‑лист: 1. Масло реально холодное. 2. Коржи тонкие. 3. Крем заварен без комков. 4. Ночь на пропитку. 5. Аккуратная подача.');
    return sanitizeOutput(lines.join('\n'));
  }

  // Универсальный развернутый ответ по умолчанию
  if (lang === 'he') {
    return sanitizeOutput('Кратко: אענה תשובה מלאה ומעמיקה. Детали: אציג רקע, נקודות מפתח, שלבים מעשיים, סיכונים וטיפים, כדי שתתקבל תמונה שלמה להמשך פעולה. Чек‑лист: 1. מטרה 2. מסגרת זמן/משאבים 3. חלופות 4. סיכונים 5. צעד ראשון.');
  }
  if (lang === 'en') {
    return sanitizeOutput('Brief: I will provide a comprehensive, professional answer. Details: overview, key facts, actionable steps, risks, and tips so you have a complete plan. Checklist: 1. Goal 2. Timeline/resources 3. Options 4. Risks 5. First step.');
  }
  const lines = [];
  lines.push('Кратко: даю развернутый профессиональный ответ. Детали: ниже — контекст, ключевые факты, пошаговый план, риски и советы, чтобы вы получили полный результат одним сообщением.');
  lines.push('Чек‑лист: 1. Цель сформулирована 2. Ресурсы и сроки понятны 3. Варианты выбора 4. Риски и как их снизить 5. Конкретный первый шаг.');
  return sanitizeOutput(lines.join('\n'));
}

// PRO‑ответ через OpenAI при наличии ключа
async function llmProAnswer({ prompt, lang }) {
  if (!OPENAI_API_KEY) return localProAnswer(prompt, lang);

  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return localProAnswer(prompt, lang);

  const client = new OpenAI({ apiKey: OPENAI_API_KEY });

  // Инструкция для «профессионального длинного ответа» без эха и Markdown‑знаков
  const sys = lang === 'he'
    ? 'ענה תשובה ארוכה ומקצועית, 800–1200 מילים, בלי לצטט את המשתמש, בלי סימוני Markdown, שמור אמוג\'י ומספור 1., 2., 3.. חלק לפסקאות מסודרות: רקע, מיפוי נושא, צעדים מעשיים, כלים/דוגמאות, טעויות נפוצות, אומדן זמנים/עלויות, בטיחות/סיכונים, טיפים וסיכום. אם חסר מידע — הנח הנחות במפורש ואל תשאל שאלות המשך.'
    : (lang === 'en'
        ? 'Provide a long, professional answer (800–1200 words), no quoting the user, no Markdown markers, keep emojis and numbering 1., 2., 3.. Structure into paragraphs: background, topic mapping, actionable steps, tools/examples, common pitfalls, time/cost estimate, safety/risks, tips, summary. If info is missing, state reasonable assumptions explicitly; do not ask follow-ups.'
        : 'Дай длинный профессиональный ответ 800–1200 слов. Не цитируй пользователя. Без символов Markdown. Эмодзи и нумерация 1., 2., 3. разрешены. Структурируй по абзацам: вводная и контекст, карта темы, пошаговые действия, инструменты/примеры, частые ошибки, оценка сроков/стоимости, риски/безопасность, советы и итог. Если данных не хватает — явно укажи допущения и всё равно дай полноценный ответ без уточняющих вопросов.');

  const user = lang === 'he'
    ? `בקשה: ${String(prompt || '')}\nספק תשובה שלמה לפי ההנחיות.`
    : (lang === 'en'
        ? `Request: ${String(prompt || '')}\nProvide the full, single-message professional answer as instructed.`
        : `Запрос: ${String(prompt || '')}\nДай один полный профессиональный ответ согласно инструкциям выше.`);

  try {
    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0.3,
      messages: [
        { role: 'system', content: sys },
        { role: 'user', content: user }
      ]
    });
    const txt = res.choices?.[0]?.message?.content || '';
    return sanitizeOutput(txt || localProAnswer(prompt, lang));
  } catch (e) {
    console.error('LLM error:', e?.response?.data || e.message);
    return localProAnswer(prompt, lang);
  }
}

// Простая ASR через Whisper при наличии ключа (OGG скачиваем, затем отправляем в OpenAI)
async function asrWhisperOgg(oggPath, langPref) {
  if (!OPENAI_API_KEY) return '';
  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return '';
  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const opts = { file: fs.createReadStream(oggPath), model: 'whisper-1' };
  if (langPref === 'ru') opts.language = 'ru';
  if (langPref === 'he') opts.language = 'he';
  const tr = await client.audio.transcriptions.create(opts);
  return (tr.text || '').trim();
}

async function downloadVoiceOgg(ctx, fileId) {
  const f = await ctx.telegram.getFile(fileId);
  const url = `https://api.telegram.org/file/bot${BOT_TOKEN}/${f.file_path}`;
  const ogg = path.join(os.tmpdir(), `voice_${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
  const resp = await axios.get(url, { responseType: 'stream' });
  await new Promise((resolve, reject) => {
    const w = fs.createWriteStream(ogg);
    resp.data.pipe(w);
    w.on('finish', resolve);
    w.on('error', reject);
  });
  return ogg;
}

// ===== Команды и обработчики =====

bot.start(async (ctx) => {
  await replyClean(ctx, 'Привет. Я SmartPro 24/7. Одна кнопка «Меню» всегда снизу. Пишите текст или отправляйте короткое voice — дам развернутый профессиональный ответ одним сообщением.');
});

bot.command('menu', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом, без «эха», в PRO‑формате.');
  lines.push('2. Голос до 10–15 сек: распознаю и отвечаю так же развернуто.');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'));
});

bot.command('version', async (ctx) => {
  await replyClean(ctx, 'UNIVERSAL GPT-4o — U10c-Node');
});

bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом, PRO‑режим.');
  lines.push('2. Голос — без «эха», распознавание при наличии ключа.');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'));
});

// Текст → всегда длинный профессиональный ответ
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const userText = (ctx.message.text || '').trim();
    const pro = RESPONSE_MODE === 'pro';
    const answer = pro ? await llmProAnswer({ prompt: userText, lang }) : localProAnswer(userText, lang);
    await replyClean(ctx, answer);
  } catch (e) {
    await replyClean(ctx, 'Кратко: временная ошибка. Детали: повторите позже. Чек‑лист: 1. Повтор 2. Короче 3. Позже.');
  }
});

// Голос → ASR (если есть) → длинный профессиональный ответ без «эха»
bot.on('voice', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    let transcript = '';
    try {
      const ogg = await downloadVoiceOgg(ctx, ctx.message.voice.file_id);
      try {
        transcript = await asrWhisperOgg(ogg, lang);
      } finally {
        try { fs.unlinkSync(ogg); } catch {}
      }
    } catch (_) { /* без ключа будет пусто — пойдём по fallback */ }

    // Если распознали — используем текст, иначе — общая формулировка для полноценного ответа
    const prompt = transcript && transcript.trim()
      ? transcript.trim()
      : (lang === 'he'
          ? 'בקשה קולית כללית. ספק תשובה מקצועית מלאה בנושא המבוקש, גם אם הניסוח חלקי.'
          : (lang === 'en'
              ? 'A general voice request. Provide a full professional, single-message answer on the likely topic, even if phrasing is partial.'
              : 'Общий голосовой запрос. Дай полный профессиональный ответ по вероятной теме запроса одним сообщением, даже если формулировка неполная.'));

    const pro = RESPONSE_MODE === 'pro';
    const answer = pro ? await llmProAnswer({ prompt, lang }) : localProAnswer(prompt, lang);
    await replyClean(ctx, answer);
  } catch (e) {
    await replyClean(ctx, 'Кратко: получил голос. Детали: временная ошибка обработки. Чек‑лист: 1. Повторите позже 2. Короткое voice 3. Поддержка.');
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
