/**
 * SmartPro 24/7 (Node + Telegraf + Express)
 * Цель: один длинный профессиональный ответ (800–1200 слов) одним сообщением, без инлайнов и без TTS,
 *       одна Reply-кнопка «Меню» всегда видна, «синее меню» команд Telegram, анти-эхо (не цитировать пользователя),
 *       маршруты /version, /telegram/railway123 (GET/POST), секрет для вебхука.
 *
 * Требуются переменные окружения:
 *   BOT_TOKEN         — токен Telegram бота
 *   SECRET_TOKEN      — 'railway123' (должен совпадать с вебхуком)
 *   OPENAI_API_KEY    — ключ OpenAI (для длинных ответов по любой теме и распознавания голосовых)
 *   PRO_MIN_WORDS     — опционально (по умолчанию 800)
 *   PRO_MAX_WORDS     — опционально (по умолчанию 1200)
 */

const express = require('express');
const { Telegraf, Markup } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

const PRO_MIN_WORDS = Number(process.env.PRO_MIN_WORDS || 800);
const PRO_MAX_WORDS = Number(process.env.PRO_MAX_WORDS || 1200);

// Ограничение Телеграма: 4096 символов. Держим запас.
const MAX_CHARS = 3900;

// Для формирования реф-ссылок
let BOT_USERNAME = '';

// Единая Reply-клавиатура (всегда видна)
const replyKeyboard = Markup.keyboard([['Меню']]).resize().oneTime(false); // Telegraf автоматически сделает persistent для повторной отправки

// Команды “синего меню”
const BOT_COMMANDS = [
  { command: 'start', description: 'Запуск и краткая справка' },
  { command: 'menu', description: 'Меню и инструкции' },
  { command: 'help', description: 'Помощь и правила ввода' },
  { command: 'pay', description: 'Тарифы и оплата' },
  { command: 'ref', description: 'Реферальная ссылка' },
  { command: 'version', description: 'Версия сборки' }
];

// Инициализация бота
if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}
const bot = new Telegraf(BOT_TOKEN);

// Установка команд и получение username
(async () => {
  try {
    await bot.telegram.setMyCommands(BOT_COMMANDS);
    const me = await bot.telegram.getMe();
    BOT_USERNAME = me.username || '';
    console.log('Bot username:', BOT_USERNAME);
  } catch (e) {
    console.error('Failed to init bot metadata:', e.message);
  }
})();

// ===== ВСПОМОГАТЕЛЬНЫЕ =====
function sanitizeOutput(text) {
  if (!text) return '';
  // Удаляем потенциальную разметку/цитаты/маркеры, оставляем цифры и эмодзи
  let t = text
    // убрать markdown-символы
    .replace(/[`*_#]/g, '')
    // убрать цитаты '>' в начале строк
    .replace(/^\s*>[^\n]*$/gm, s => s.replace(/^>\s?/, ''))
    // убирать тире-маркеры в начале строк
    .replace(/^\s*-\s+/gm, '')
    // нормализуем множественные пустые строки
    .replace(/\n{3,}/g, '\n\n')
    .trim();

  // Одно сообщение: строго не превышаем лимит
  if (t.length > MAX_CHARS) t = t.slice(0, MAX_CHARS - 10).trim() + '…';
  return t;
}

function detectLang(s) {
  if (!s) return 'ru';
  const hasCyr = /[А-Яа-яЁё]/.test(s);
  const hasHeb = /[\u0590-\u05FF]/.test(s);
  if (hasHeb) return 'he';
  if (hasCyr) return 'ru';
  return 'ru'; // приоритет RU, EN — осторожный режим, но фиксируем RU по умолчанию для стабильности
}

function ensureOneMessageLimit(s) {
  if (!s) return s;
  if (s.length <= MAX_CHARS) return s;
  return s.slice(0, MAX_CHARS - 10).trim() + '…';
}

function structurePrompt(userTopic, lang = 'ru') {
  // Без эха: используем тему, но не цитируем дословно
  const topic = (userTopic || '').trim();
  const minWords = PRO_MIN_WORDS;
  const maxWords = PRO_MAX_WORDS;

  // Жёсткая структура разделов
  const instructionsRu = `
Ты — профессиональный аналитик. Дай развёрнутый ответ ${minWords}–${maxWords} слов на русском, одним сообщением, без списков с «-», без Markdown, без цитирования вопроса и без воды. Структура строго по разделам с чёткими подзаголовками:
1) Контекст и вводные
2) Карта темы
3) Практические шаги
4) Риски и ограничения
5) Профессиональные советы
6) Чек-лист действий

Пиши плотным деловым стилем, сохраняй законченность мысли в каждом абзаце, избегай пышной публицистики и сторителлинга, если явно не просили. Не выдавай расшифровку голоса и не повторяй формулировки пользователя.`;

  return {
    system: instructionsRu,
    user: `Тема: ${topic || 'универсальная справка по запрошенной теме'}. Сформируй ответ по структуре.`
  };
}

async function openaiChatAnswer(topic, lang = 'ru') {
  // Используем fetch (Node 20+) без SDK
  const { system, user } = structurePrompt(topic, lang);

  const body = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    temperature: 0.5,
    max_tokens: 1400
  };

  const res = await fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(body)
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`OpenAI chat error: ${res.status} ${txt}`);
  }
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content || '';
  return ensureOneMessageLimit(sanitizeOutput(content));
}

// Простой тематический фолбэк (локальные развернутые заготовки)
function localFallback(topicRaw) {
  const topic = (topicRaw || '').toLowerCase();
  const base = (tName) => {
    return [
      `Контекст и вводные. ${tName}: кратко — ключевые особенности, историко-географические ориентиры, современная роль в регионе и мире, практическая ценность для путешественника, инвестора или релоканта.`,
      `Карта темы. Разбейте рассмотрение на блоки: институции и право, экономика и рынки, инфраструктура и логистика, культура и язык, быт и повседневные сервисы, связи и коммуникации. Для каждого блока опишите, где искать первичные данные, на что смотреть при оценке, какие показатели критичны.`,
      `Практические шаги. Подготовьте пошаговый план на 30–60 дней: сбор базовой информации и документов; оценка стоимости жизни и доходов; карта рисков; пилотные контакты; пробный визит или удаленный тест; финализация решения; трекер метрик и контрольные точки.`,
      `Риски и ограничения. Разделите на регуляторные, финансовые, инфраструктурные, культурно-языковые и операционные. Для каждого риска — как обнаружить заранее, как снизить, какой план Б.`,
      `Профессиональные советы. Опирайтесь на проверяемые источники, локальные комьюнити и первичную статистику; предпочитайте официальные реестры и витрины данных; валидируйте выводы через сравнение 2–3 независимых источников.`,
      `Чек-лист действий. 1) Цели и критерии успеха; 2) Бюджет и сроки; 3) Документы и легализация; 4) Жилье и инфраструктура; 5) Работа/бизнес; 6) Страхование и медицина; 7) Связь и банки; 8) Сообщество и язык; 9) План адаптации; 10) Контроль и пересмотр решений.`
    ].join('\n\n');
  };

  if (topic.includes('герман') || topic.includes('germany')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Германия')));
  }
  if (topic.includes('бали') || topic.includes('bali')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Бали')));
  }
  if (topic.includes('румыни') || topic.includes('romania')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Румыния')));
  }
  if (topic.includes('молдова') || topic.includes('moldova')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Молдова')));
  }
  if (topic.includes('рим') || topic.includes('rome')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Рим')));
  }
  if (topic.includes('наполеон')) {
    return ensureOneMessageLimit(sanitizeOutput(base('Наполеон')));
  }
  return ensureOneMessageLimit(sanitizeOutput(base('Тема')));
}

async function generateProAnswer(topic) {
  const lang = detectLang(topic);
  if (OPENAI_API_KEY) {
    try {
      return await openaiChatAnswer(topic, lang);
    } catch (e) {
      console.error('OpenAI chat failed, fallback used:', e.message);
      return localFallback(topic);
    }
  }
  // Без ключа — локальный расширенный фолбэк
  return localFallback(topic);
}

async function transcribeVoice(fileUrl) {
  if (!OPENAI_API_KEY) {
    throw new Error('OPENAI_API_KEY missing for ASR');
  }
  // Загружаем файл и шлём в Whisper
  const resp = await fetch(fileUrl);
  if (!resp.ok) throw new Error(`Cannot fetch voice file: ${resp.status}`);
  const buf = await resp.arrayBuffer();
  const blob = new Blob([buf], { type: 'audio/ogg' });

  const form = new FormData();
  form.append('file', blob, 'voice.ogg');
  form.append('model', 'whisper-1');
  form.append('response_format', 'text'); // вернёт чистый текст

  const r = await fetch('https://api.openai.com/v1/audio/transcriptions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
    body: form
  });
  if (!r.ok) {
    const txt = await r.text().catch(() => '');
    throw new Error(`ASR error: ${r.status} ${txt}`);
  }
  const text = await r.text();
  // Возвращаем распознанную тему, НО НЕ ПОКАЗЫВАЕМ её в ответе — анти-эхо
  return (text || '').trim();
}

// ===== ОБРАБОТЧИКИ БОТА =====
function replyOptions() {
  return { reply_markup: replyKeyboard.reply_markup, disable_web_page_preview: true };
}

// Команды
bot.start(async (ctx) => {
  const welcome = [
    'SmartPro 24/7 готов. Пишите тему текстом или голосом — получите один длинный профессиональный ответ без инлайнов и без озвучки.',
    'Всегда доступна одна Reply‑кнопка «Меню». Синее меню команд: /start, /menu, /help, /pay, /ref, /version.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(welcome), replyOptions());
});

bot.command('menu', async (ctx) => {
  const text = [
    'Меню',
    '— Отправьте тему (например: «План релокации в Румынию» или «Экономика Германии для инвестора»).',
    '— Голосовые до ~15 сек распознаются, но ответ всегда текстом в одном сообщении.',
    '— Никаких инлайн‑кнопок. Только одна Reply‑кнопка: «Меню».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions());
});

bot.command('help', async (ctx) => {
  const text = [
    'Как получить лучший ответ:',
    '1) Сформулируйте фокус (цель, срок, ограничения).',
    '2) Уточните контекст (страна/город, бюджет, формат — туризм/релокация/бизнес).',
    '3) Попросите конкретную структуру или чек‑лист, если нужно.',
    'Ответ придёт одним длинным сообщением, без цитирования вопроса и без «расшифровок».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions());
});

bot.command('pay', async (ctx) => {
  const text = [
    'Тарифы (демо): 10 / 20 / 50 USD.',
    'Оплата подключается после стабилизации ядра. Сейчас доступна полная функциональность в тестовом режиме.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions());
});

bot.command('ref', async (ctx) => {
  const uid = ctx.from?.id || 0;
  const link = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=ref_${uid}` : 'Ссылка будет доступна после инициализации бота';
  const text = `Ваша персональная реф‑ссылка:\n${link}`;
  await ctx.reply(sanitizeOutput(text), replyOptions());
});

bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT‑4o — U10c‑Node', replyOptions());
});

// Текстовые запросы
bot.on('text', async (ctx) => {
  try {
    const text = (ctx.message?.text || '').trim();
    if (!text || text === 'Меню') {
      return ctx.reply('Выберите действие или напишите тему запроса. Команды: /menu /help /pay /ref /version', replyOptions());
    }
    // Генерация длинного PRO‑ответа без эха
    const answer = await generateProAnswer(text);
    await ctx.reply(answer, replyOptions());
  } catch (e) {
    console.error('text handler error:', e.message);
    await ctx.reply('Временная ошибка обработки. Повторите запрос текстом.', replyOptions());
  }
});

// Голосовые: распознаём (если есть ключ), отвечаем длинным текстом, без показа транскрипта
bot.on('voice', async (ctx) => {
  try {
    const fileId = ctx.message?.voice?.file_id;
    if (!fileId) return;

    let topic = '';
    try {
      const link = await ctx.telegram.getFileLink(fileId);
      topic = await transcribeVoice(link.href);
    } catch (asrErr) {
      console.error('ASR failed:', asrErr.message);
      // Если нет ключа или ошибка ASR — просим дублировать текстом
      return ctx.reply('Я получил голосовое. Распознавание сейчас недоступно. Пожалуйста, отправьте тему текстом.', replyOptions());
    }

    const answer = await generateProAnswer(topic || 'Пожалуйста, сформулируйте тему запроса.');
    await ctx.reply(answer, replyOptions());
  } catch (e) {
    console.error('voice handler error:', e.message);
    await ctx.reply('Не удалось обработать голосовое. Отправьте тему текстом.', replyOptions());
  }
});

// ===== ВЕБ-СЕРВЕР И ВЕБХУК =====
const app = express();
app.use(express.json());

// Быстрая проверка версии
app.get('/version', (req, res) => {
  res.type('text/plain').send('UNIVERSAL GPT‑4o — U10c‑Node');
});

// Проверка, что отвечает Node
app.get('/telegram/railway123', (req, res) => {
  res.type('text/plain').send('Webhook OK');
});

// Приём вебхука Telegram с проверкой секретного заголовка
app.post('/telegram/railway123', (req, res) => {
  const secret = req.headers['x-telegram-bot-api-secret-token'];
  if (!secret || secret !== SECRET_TOKEN) {
    return res.status(401).send('Unauthorized');
  }
  bot.handleUpdate(req.body, res).catch((err) => {
    console.error('handleUpdate error:', err);
    res.status(200).send('OK'); // Телеграму отвечаем 200, чтобы не ретраился
  });
});

app.listen(PORT, () => {
  console.log(`Server listening on :${PORT}`);
});
