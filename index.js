/**
 * SmartPro 24/7 (U10e-Node)
 * Длинный профессиональный ответ (800–1200 слов) одним сообщением, без инлайнов и без TTS.
 * Всегда одна Reply‑кнопка «Меню» (is_persistent). Автодетект языка (RU/HE приоритет; EN — осторожный режим).
 * Анти‑эхо, чистый текст. Маршруты: GET /version, GET /telegram/railway123, POST /telegram/railway123.
 * Вебхук: проверка x-telegram-bot-api-secret-token.
 *
 * ENV:
 *   BOT_TOKEN (required)
 *   SECRET_TOKEN=railway123 (required; совпадает с secret_token в setWebhook)
 *   OPENAI_API_KEY (optional, для длинных ответов по любой теме и ASR)
 *   PRO_MIN_WORDS=800 (optional)
 *   PRO_MAX_WORDS=1200 (optional)
 */

const express = require('express');
const { Telegraf } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

const PRO_MIN_WORDS = Number(process.env.PRO_MIN_WORDS || 800);
const PRO_MAX_WORDS = Number(process.env.PRO_MAX_WORDS || 1200);
const MAX_CHARS = 3900; // запас до лимита 4096

if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
// Критично: не отвечать в HTTP-ответе вебхука, чтобы избежать таймаутов
bot.webhookReply = false;

// ——— Параметры клавиатуры «Меню» (постоянная) ———
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  is_persistent: true,
  one_time_keyboard: false,
  input_field_placeholder: 'Опишите тему запроса…'
};
const replyOptions = { reply_markup: replyKeyboard, disable_web_page_preview: true };

// ——— Синие команды ———
const BOT_COMMANDS = [
  { command: 'start', description: 'Запуск и краткая справка' },
  { command: 'menu', description: 'Меню и инструкции' },
  { command: 'help', description: 'Помощь и правила ввода' },
  { command: 'pay', description: 'Тарифы и оплата' },
  { command: 'ref', description: 'Реферальная ссылка' },
  { command: 'version', description: 'Версия сборки' },
  { command: 'debug', description: 'Диагностика вебхука и окружения' }
];

let BOT_USERNAME = '';

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

// ——— Утилиты ———
function sanitizeOutput(text) {
  if (!text) return '';
  let t = text
    .replace(/[`*_#]/g, '')
    .replace(/^\s*>[^\n]*$/gm, s => s.replace(/^>\s?/, ''))
    .replace(/^\s*-\s+/gm, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  if (t.length > MAX_CHARS) t = t.slice(0, MAX_CHARS - 10).trim() + '…';
  return t;
}

function ensureOneMessageLimit(s) {
  if (!s) return s;
  return s.length <= MAX_CHARS ? s : s.slice(0, MAX_CHARS - 10).trim() + '…';
}

function detectLang(s) {
  if (!s) return 'ru';
  const hasCyr = /[А-Яа-яЁё]/.test(s);
  const hasHeb = /[\u0590-\u05FF]/.test(s);
  if (hasHeb) return 'he';
  if (hasCyr) return 'ru';
  return 'ru';
}

function structurePrompt(userTopic) {
  const topic = (userTopic || '').trim();
  const instructionsRu = `
Ты — профессиональный аналитик. Дай развёрнутый ответ ${PRO_MIN_WORDS}–${PRO_MAX_WORDS} слов на русском, одним сообщением, без списков с «-», без Markdown, без цитирования вопроса и без воды. Структура строго по разделам с чёткими подзаголовками:
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

async function openaiChatAnswer(topic) {
  const { system, user } = structurePrompt(topic);
  const body = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    temperature: 0.5,
    max_tokens: 1100
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
  if (topic.includes('герман') || topic.includes('germany')) return ensureOneMessageLimit(sanitizeOutput(base('Германия')));
  if (topic.includes('бали') || topic.includes('bali')) return ensureOneMessageLimit(sanitizeOutput(base('Бали')));
  if (topic.includes('румыни') || topic.includes('romania')) return ensureOneMessageLimit(sanitizeOutput(base('Румыния')));
  if (topic.includes('молдова') || topic.includes('moldova')) return ensureOneMessageLimit(sanitizeOutput(base('Молдова')));
  if (topic.includes('рим') || topic.includes('rome')) return ensureOneMessageLimit(sanitizeOutput(base('Рим')));
  if (topic.includes('наполеон')) return ensureOneMessageLimit(sanitizeOutput(base('Наполеон')));
  return ensureOneMessageLimit(sanitizeOutput(base('Тема')));
}

async function generateProAnswer(topic) {
  if (OPENAI_API_KEY) {
    try { return await openaiChatAnswer(topic); }
    catch (e) {
      console.error('OpenAI chat failed, fallback used:', e.message);
      return localFallback(topic);
    }
  }
  return localFallback(topic);
}

async function transcribeVoice(fileUrl) {
  if (!OPENAI_API_KEY) throw new Error('OPENAI_API_KEY missing for ASR');
  const resp = await fetch(fileUrl);
  if (!resp.ok) throw new Error(`Cannot fetch voice file: ${resp.status}`);
  const buf = await resp.arrayBuffer();
  const blob = new Blob([buf], { type: 'audio/ogg' });
  const form = new FormData();
  form.append('file', blob, 'voice.ogg');
  form.append('model', 'whisper-1');
  form.append('response_format', 'text');
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
  return (text || '').trim();
}

// ——— Логирование и отлов ошибок ———
bot.use(async (ctx, next) => {
  try {
    const t = ctx.updateType;
    const msg = ctx.message || ctx.update?.message;
    const info = msg?.text ? `text="${msg.text}"` : (msg?.voice ? 'voice' : '');
    console.log(`[update] type=${t} chat=${msg?.chat?.id} user=${msg?.from?.id} ${info}`);
  } catch {}
  return next();
});

bot.catch((err, ctx) => {
  console.error('Telegraf error:', err);
  if (ctx?.chat?.id) {
    // Мягко уведомим о сбое и одновременно вернём клавиатуру
    ctx.reply('Временная ошибка. Повторите запрос текстом.', replyOptions).catch(() => {});
  }
});

// ——— Команды ———
bot.start(async (ctx) => {
  const welcome = [
    'SmartPro 24/7 готов. Пишите тему текстом или голосом — получите один длинный профессиональный ответ без инлайнов и без озвучки.',
    'Всегда доступна одна Reply‑кнопка «Меню». Синее меню команд: /start, /menu, /help, /pay, /ref, /version.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(welcome), replyOptions);
});

bot.command('menu', async (ctx) => {
  const text = [
    'Меню',
    '— Отправьте тему (например: «План релокации в Румынию» или «Экономика Германии для инвестора»).',
    '— Голосовые до ~15 сек распознаются, но ответ всегда текстом в одном сообщении.',
    '— Никаких инлайн‑кнопок. Только одна Reply‑кнопка: «Меню».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('help', async (ctx) => {
  const text = [
    'Как получить лучший ответ:',
    '1) Сформулируйте фокус (цель, срок, ограничения).',
    '2) Уточните контекст (страна/город, бюджет, формат — туризм/релокация/бизнес).',
    '3) Попросите конкретную структуру или чек‑лист, если нужно.',
    'Ответ придёт одним длинным сообщением, без цитирования вопроса и без «расшифровок».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('pay', async (ctx) => {
  const text = [
    'Тарифы (демо): 10 / 20 / 50 USD.',
    'Оплата подключается после стабилизации ядра. Сейчас доступна полная функциональность в тестовом режиме.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('ref', async (ctx) => {
  const uid = ctx.from?.id || 0;
  const link = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=ref_${uid}` : 'Ссылка будет доступна после инициализации бота';
  const text = `Ваша персональная реф‑ссылка:\n${link}`;
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT‑4o — U10e-Node', replyOptions);
});

bot.command('debug', async (ctx) => {
  try {
    const info = await bot.telegram.getWebhookInfo();
    const masked = {
      url: info.url,
      has_custom_certificate: info.has_custom_certificate,
      pending_update_count: info.pending_update_count,
      ip_address: info.ip_address,
      last_error_date: info.last_error_date,
      last_error_message: info.last_error_message,
      max_connections: info.max_connections,
      allowed_updates: info.allowed_updates,
      secret_token_set: Boolean(SECRET_TOKEN),
      openai_key_present: OPENAI_API_KEY ? true : false,
      version: 'U10e-Node'
    };
    await ctx.reply('DEBUG:\n' + '```json\n' + JSON.stringify(masked, null, 2) + '\n```', {
      ...replyOptions,
      parse_mode: 'MarkdownV2' // только для блока кода в debug
    }).catch(async () => {
      await ctx.reply(JSON.stringify(masked, null, 2), replyOptions);
    });
  } catch (e) {
    await ctx.reply('DEBUG error: ' + e.message, replyOptions);
  }
});

// ——— Текст ———
bot.on('text', async (ctx) => {
  try {
    const text = (ctx.message?.text || '').trim();
    if (!text || text === 'Меню') {
      return ctx.reply('Выберите действие или напишите тему запроса. Команды: /menu /help /pay /ref /version', replyOptions);
    }
    const answer = await generateProAnswer(text);
    await ctx.reply(answer, replyOptions);
  } catch (e) {
    console.error('text handler error:', e.message);
    await ctx.reply('Временная ошибка обработки. Повторите запрос текстом.', replyOptions);
  }
});

// ——— Голос ———
bot.on('voice', async (ctx) => {
  try {
    const fileId = ctx.message?.voice?.file_id;
    if (!fileId) return;
    let topic = '';
    try {
      const linkObj = await ctx.telegram.getFileLink(fileId);
      const url = typeof linkObj === 'string' ? linkObj : linkObj.href;
      topic = await transcribeVoice(url);
    } catch (asrErr) {
      console.error('ASR failed:', asrErr.message);
      return ctx.reply('Я получил голосовое. Распознавание сейчас недоступно. Пожалуйста, отправьте тему текстом.', replyOptions);
    }
    const answer = await generateProAnswer(topic || 'Пожалуйста, сформулируйте тему запроса.');
    await ctx.reply(answer, replyOptions);
  } catch (e) {
    console.error('voice handler error:', e.message);
    await ctx.reply('Не удалось обработать голосовое. Отправьте тему текстом.', replyOptions);
  }
});

// ——— Веб-сервер и вебхук ———
const app = express();
app.use(express.json());

// Быстрая проверка версии
app.get('/version', (req, res) => {
  res.type('text/plain').send('UNIVERSAL GPT‑4o — U10e-Node');
});

// Проверка, что отвечает Node
app.get('/telegram/railway123', (req, res) => {
  res.type('text/plain').send('Webhook OK');
});

// Вебхук. Сразу 200 OK, обработка — асинхронно
app.post('/telegram/railway123', (req, res) => {
  const secret = req.headers['x-telegram-bot-api-secret-token'];
  if (!secret || secret !== SECRET_TOKEN) {
    return res.status(401).send('Unauthorized');
  }
  bot.handleUpdate(req.body).catch((err) => console.error('handleUpdate error:', err));
  res.status(200).send('OK');
});

app.listen(PORT, () => {
  console.log(`Server listening on :${PORT}`);
});
