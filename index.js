// index.js — PRO-ответ одним сообщением (800–1200 слов) для текста и голоса.
// Строгий UX: одна Reply-кнопка «Меню», без инлайн-кнопок и TTS. Анти-эхо. Авто RU/HE приоритет, EN — осторожно.
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

// Настройка длины «PRO»-ответа
const PRO_MIN_WORDS = Number(process.env.PRO_MIN_WORDS || 800);
const PRO_MAX_WORDS = Number(process.env.PRO_MAX_WORDS || 1200);

if (!BOT_TOKEN) {
  console.error('Ошибка: отсутствует BOT_TOKEN');
  process.exit(1);
}

const app = express();
app.use(express.json({ limit: '20mb' }));

const bot = new Telegraf(BOT_TOKEN, { handlerTimeout: 15000 });

// Одна Reply-кнопка «Меню» — всегда видна
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  one_time_keyboard: false,
  selective: true
};

// Санитаризация: убираем # * _ `, цитаты и тире-маркеры; оставляем эмодзи и нумерацию 1., 2., 3.
function sanitizeOutput(s) {
  return String(s)
    .replace(/[#*_`]/g, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*-\s+/gm, '')
    .trim();
}

// Единая отправка: всегда с Reply-клавиатурой «Меню»
async function replyClean(ctx, text) {
  return ctx.reply(sanitizeOutput(text), { reply_markup: replyKeyboard });
}

function detectLang(ctx) {
  const lc = (ctx.from?.language_code || 'ru').toLowerCase();
  if (lc.startsWith('ru')) return 'ru';
  if (lc.startsWith('he')) return 'he';
  return 'en';
}

// Локальный PRO-генератор: формирует развернутый ответ даже без модели
function localProAnswer(prompt, lang) {
  const p = String(prompt || '').toLowerCase();

  // Спец-кейсы (можете расширять список)
  if (p.includes('рим')) {
    const sections = [];
    sections.push('Кратко: Рим — столица Италии и один из ключевых центров мировой истории, искусства и религии. Ниже — полный план, как увидеть главное, не теряя времени, и получить максимум пользы.');
    sections.push('Вводная и контекст. Рим расположен на холмах у Тибра. Исторический центр компактен, основные зоны интереса лежат на расстоянии пеших прогулок. Высокий сезон — весна и осень; летом жарко, зимой влажно, но мало туристов.');
    sections.push('Карта темы. Античность: Колизей, Форум, Палатин. Христианское наследие: Ватикан, базилика Святого Петра, катакомбы. Барокко: Фонтан Треви, Пьяцца Навона, Испанская лестница. Аутентичные районы: Трастевере, Тестаччо, Монти.');
    sections.push('Пошаговый маршрут на 3–4 дня. День 1: Колизей (утро), Форум и Палатин, Капитолий, Витториано, заход к Треви на закате. День 2: Пантеон — Пьяцца Навона — Кампо де’ Фьори — Трастевере (ужин). День 3: Ватикан — подъём на купол — музеи Ватикана — замок Сант-Анджело. День 4: катакомбы/Аппиева дорога, район Монти и нетуристические траттории.');
    sections.push('Инструменты и примеры. Билеты онлайн на Колизей и музеи Ватикана экономят 1–2 часа. Для транспорта — метро A/B и пешие маршруты. Воду наливать из городских фонтанчиков — это безопасно и бесплатно.');
    sections.push('Еда и кофе. На завтрак — корнетто и капучино «у стойки». Днём — пицца «ал тальо». Вечером — траттория в Трастевере/Тестаччо: карбонара, качо-э-пепе, суппли, артишоки по‑римски.');
    sections.push('Частые ошибки. Пытаться «успеть всё за день», идти в музеи в пиковые часы, игнорировать дресс-код храмов (нужны закрытые плечи/колени), брать кофе за столиком (в 2–3 раза дороже).');
    sections.push('Оценка сроков и бюджета. На базовую программу закладывайте 3 полных дня. Чек в траттории — средний, входные билеты в ключевые объекты — от недорогих до средних, бронирования заранее — must-have в сезон.');
    sections.push('Риски и безопасность. Туристические карманы — держите документы и деньги спереди. Заселение согласовывайте заранее, городской налог платится на месте. Дождевые дни — запасной план по музеям.');
    sections.push('Советы и итог. Начинайте день рано, делайте «якорные» точки утром, закаты — на Джаниколо. Держите офлайн-карты и брони. Рим — город плотных впечатлений: лучше меньше, но глубже, с паузами на кофе и наблюдение за жизнью.');
    sections.push('Чек-лист: 1. Брони на Колизей/Ватикан. 2. План по дням с буфером. 3. Дресс-код для храмов. 4. Офлайн-карты и страховка. 5. Список тратторий и кофе-баров.');
    return sanitizeOutput(sections.join('\n'));
  }

  if (p.includes('наполеон')) {
    const sections = [];
    sections.push('Кратко: классический торт «Наполеон» — тонкие слоёные коржи и заварной крем. Важно: холодное масло в тесте, тонкая раскатка и ночная пропитка.');
    sections.push('Ингредиенты теста. Мука 600 г; сливочное масло 400 г очень холодное; ледяная вода 180 мл; яйцо 1; соль щепотка; уксус 1 ч. л. (по желанию).');
    sections.push('Ингредиенты крема. Молоко 1 л; сахар 200–250 г; яйца 3; мука 60 г или крахмал 40 г; ваниль; сливочное масло 150–200 г.');
    sections.push('Тесто. Натрите масло в муку, быстро перетрите в крошку, добавьте яйцо, соль, воду. Замесите без перегрева, охладите 30–40 минут. Разделите на 8–10 частей.');
    sections.push('Коржи. Раскатайте очень тонко, наколите вилкой, обрежьте по шаблону, обрезки — на крошку. Выпекайте при 200–210°C 7–9 минут до золотистого.');
    sections.push('Крем. Растереть яйца с сахаром и мукой (крахмалом), влить горячее молоко, заварить до загустения, остудить и вмешать мягкое масло до шелковистой текстуры.');
    sections.push('Сборка и выдержка. Корж — тёплый крем — корж; обмазать бока и верх, посыпать крошкой. Пропитка 6–8 часов (лучше ночь) в холодильнике.');
    sections.push('Ошибки и риски. Тёплое масло в тесте (жёсткие коржи), недостаточная раскатка (толстые пласты), комки в креме (нужно просеивание и температурный контроль), спешка с пропиткой.');
    sections.push('Советы. Работайте быстро и холодно; раскатывайте «вверх-вниз» для равномерности; для стабильности добавьте щепотку соли в крем. Подавайте охлаждённым, острым ножом.');
    sections.push('Чек-лист: 1. Масло очень холодное. 2. Коржи тонкие. 3. Крем без комков. 4. Ночная пропитка. 5. Аккуратная подача.');
    return sanitizeOutput(sections.join('\n'));
  }

  // Универсальный развернутый ответ (тема общая: страна/город/понятие/план)
  const sections = [];
  if (lang === 'he') {
    sections.push('Кратко: אציג תשובה ארוכה ומקצועית עם הקשר, צעדים מעשיים, סיכונים וטיפים — הכל בהודעה אחת.');
    sections.push('רקע והקשר. נתחיל בהבנת הנושא ברמה גבוהה: מה זה, למה זה חשוב, ואיך זה משתלב בהקשר רחב יותר.');
    sections.push('מיפוי הנושא. נגדיר רכיבים מרכזיים, שחקנים מעורבים, כלים זמינים ומדדי הצלחה. נזהה תלויות וגבולות.');
    sections.push('צעדים מעשיים. תוכנית פעולה בשלבים: הכנה, ביצוע, בקרה ושיפור. לכל שלב — תוצרים, לוחות זמנים וכלים מוצעים.');
    sections.push('דוגמאות וכלים. נפרט דוגמאות יישום, תבניות, ובחירת כלים פרקטיים כדי לזרז ביצוע ללא ויתור על איכות.');
    sections.push('טעויות נפוצות. מה אנשים נוטים לפספס, וכיצד להימנע מכך — דרך בדיקות, תיעוד ורטרוספקטיבה.');
    sections.push('אומדן זמנים/עלויות. הערכה ריאלית עם טווחים, סיכונים ותלות חיצונית. חלופות במקרה של אילוצים.');
    sections.push('בטיחות/סיכונים. מה עלול להשתבש, איך מודדים מראש, ואילו צעדי מניעה/התאוששות נוקטים.');
    sections.push('טיפים וסיכום. כללים קצרים ליישום עקבי, עוגנים לשיפור מתמיד, והצעד הראשון לביצוע מיידי.');
    sections.push('Чек-лист: 1. מטרה 2. משאבים ולוחות זמנים 3. חלופות 4. סיכונים 5. צעד ראשון.');
  } else if (lang === 'en') {
    sections.push('Brief: Below is a long, professional single-message answer with context, actionable steps, risks, and tips.');
    sections.push('Background and context. Clarify the what/why and the broader frame so choices are informed and trade‑offs explicit.');
    sections.push('Topic map. Components, stakeholders, tools, and success metrics. Identify dependencies and constraints.');
    sections.push('Action plan. Phased steps with deliverables, timelines, and suggested tools. Include checkpoints and quality gates.');
    sections.push('Examples and tools. Patterns, templates, and practical instruments to accelerate execution without losing quality.');
    sections.push('Common pitfalls. Frequent mistakes and how to avoid them via tests, documentation, and retrospectives.');
    sections.push('Time and cost. Realistic ranges with risk buffers, external dependencies, and fallback options.');
    sections.push('Safety and risks. What can go wrong, early indicators, and preventive/corrective actions.');
    sections.push('Tips and conclusion. Short rules for consistent delivery and a concrete first step to start now.');
    sections.push('Checklist: 1. Goal 2. Resources/timeline 3. Options 4. Risks 5. First step.');
  } else {
    sections.push('Кратко: ниже — развёрнутый профессиональный ответ в одном сообщении: контекст, карта темы, пошаговые действия, риски и советы.');
    sections.push('Вводная и контекст. Объясняем, что это, зачем и где границы задачи, чтобы выбрать правильные приоритеты.');
    sections.push('Карта темы. Составляющие, участники, инструменты, метрики успеха; зависимости и ограничения.');
    sections.push('Пошаговый план. Подготовка, реализация, контроль качества и улучшения. Для каждого шага — результаты, сроки и инструменты.');
    sections.push('Примеры и инструменты. Готовые паттерны, шаблоны и практические приёмы для быстрого старта без потери качества.');
    sections.push('Частые ошибки. Что ломается чаще всего и как этого избежать за счёт проверок и прозрачности.');
    sections.push('Сроки и бюджет. Реалистичные диапазоны со страховочными буферами и планом B при ограничениях.');
    sections.push('Риски и безопасность. Что может пойти не так, ранние индикаторы, профилактика и меры реакции.');
    sections.push('Советы и итог. Короткие правила для устойчивого результата и конкретный первый шаг.');
    sections.push('Чек-лист: 1. Цель 2. Ресурсы/сроки 3. Варианты 4. Риски 5. Первый шаг.');
  }
  return sanitizeOutput(sections.join('\n'));
}

// PRO-ответ через OpenAI (если ключ задан)
async function llmProAnswer({ prompt, lang }) {
  if (!OPENAI_API_KEY) return localProAnswer(prompt, lang);
  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return localProAnswer(prompt, lang);

  const client = new OpenAI({ apiKey: OPENAI_API_KEY });

  const sys = lang === 'he'
    ? `ענה תשובה ארוכה, מקצועית ומעשית (${PRO_MIN_WORDS}-${PRO_MAX_WORDS} מילים). אל תצטט את המשתמש. בלי סימוני Markdown. שמור אמוג'י ומספור 1., 2., 3.. סדר לפסקאות: רקע, מיפוי, צעדים, כלים/דוגמאות, טעויות, זמנים/עלויות, סיכונים/בטיחות, טיפים, סיכום. אם חסר מידע — הצג הנחות סבירות וענה בכל זאת במלואו.`
    : (lang === 'en'
        ? `Provide a long, professional, actionable answer (${PRO_MIN_WORDS}-${PRO_MAX_WORDS} words). Do not quote the user. No Markdown markers. Keep emojis and numbering 1., 2., 3.. Structure into: background, mapping, steps, tools/examples, pitfalls, time/cost, risks/safety, tips, summary. If info is missing, state assumptions and still answer fully.`
        : `Дай длинный профессиональный ответ (${PRO_MIN_WORDS}-${PRO_MAX_WORDS} слов). Не цитируй пользователя. Без символов Markdown. Эмодзи и нумерация 1., 2., 3. допустимы. Структура: вводная, карта темы, шаги, инструменты/примеры, ошибки, сроки/стоимость, риски/безопасность, советы, итог. Если данных не хватает — явно сформулируй допущения и всё равно ответь полно.`);

  const user = lang === 'he'
    ? `בקשה: ${String(prompt || '')}\nספק תשובה שלמה בהודעה אחת לפי ההנחיות.`
    : (lang === 'en'
        ? `Request: ${String(prompt || '')}\nProvide a complete single-message professional answer as instructed.`
        : `Запрос: ${String(prompt || '')}\nДай один полный профессиональный ответ в соответствии с инструкцией.`);

  try {
    const res = await client.chat.completions.create({
      model: 'gpt-4o-mini',
      temperature: 0.35,
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

// Whisper ASR при наличии ключа
async function asrWhisperOgg(oggPath, lang) {
  if (!OPENAI_API_KEY) return '';
  let OpenAI;
  try { ({ OpenAI } = require('openai')); } catch { OpenAI = null; }
  if (!OpenAI) return '';
  const client = new OpenAI({ apiKey: OPENAI_API_KEY });
  const opts = { file: fs.createReadStream(oggPath), model: 'whisper-1' };
  if (lang === 'ru') opts.language = 'ru';
  if (lang === 'he') opts.language = 'he';
  const tr = await client.audio.transcriptions.create(opts);
  return (tr.text || '').trim();
}

// Скачиваем voice OGG
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
  await replyClean(ctx, 'Привет. Я SmartPro 24/7. Одна кнопка Меню всегда снизу. Пишите текст или отправляйте короткое voice — дам развернутый профессиональный ответ одним сообщением.');
});

bot.command('menu', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом, одним сообщением.');
  lines.push('2. Голос до 10–15 сек — распознаю (если доступно) и отвечаю так же развернуто.');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'));
});

bot.command('version', async (ctx) => {
  await replyClean(ctx, 'UNIVERSAL GPT-4o — U10c-Node');
});

bot.hears('Меню', async (ctx) => {
  const lines = [];
  lines.push('Меню:');
  lines.push('1. Ответы — всегда текстом, одним сообщением.');
  lines.push('2. Голос — без «эха», распознавание при наличии ключа.');
  lines.push('3. Версия: /version. Вебхук: /telegram/railway123.');
  await replyClean(ctx, lines.join('\n'));
});

// Текст → PRO-ответ
bot.on('text', async (ctx) => {
  try {
    const lang = detectLang(ctx);
    const q = (ctx.message.text || '').trim();
    const a = await llmProAnswer({ prompt: q, lang });
    await replyClean(ctx, a);
  } catch (e) {
    await replyClean(ctx, 'Кратко: временная ошибка. Детали: повторите позже. Чек-лист: 1. Повтор 2. Короче 3. Позже.');
  }
});

// Голос → (ASR если есть) → PRO-ответ без «эха»
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
    } catch (_) { /* демо без ASR */ }

    const prompt = transcript && transcript.trim()
      ? transcript.trim()
      : (lang === 'he'
          ? 'בקשה קולית כללית. ספק תשובה מקצועית מלאה בנושא המבוקש, בהודעה אחת.'
          : (lang === 'en'
              ? 'General voice request. Provide a full professional single-message answer on the likely topic.'
              : 'Общий голосовой запрос. Дай один полный профессиональный ответ по вероятной теме запроса одним сообщением.'));
    const a = await llmProAnswer({ prompt, lang });
    await replyClean(ctx, a);
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
