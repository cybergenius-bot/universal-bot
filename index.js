/**
 * SmartPro 24/7 (U10h-Node)
 * — Один ответ одним сообщением (текст), без инлайнов и без TTS по умолчанию
 * — Постоянная Reply‑клавиатура: Меню, Коротко, Средне, Глубоко, Голос
 * — Кнопки "Коротко/Средне/Глубоко" задают длину ответа; "Голос" включает/выключает аудио-озвучку (OpenAI TTS)
 * — Асинхронный вебхук (нет таймаутов), секретный заголовок, анти‑эхо, автодетект RU/HE
 * — Маршруты: GET /version, GET /telegram/railway123, POST /telegram/railway123
 *
 * ENV (Railway → Variables):
 *   BOT_TOKEN          (required)
 *   SECRET_TOKEN=railway123  (required; совпадает с setWebhook&secret_token)
 *   OPENAI_API_KEY     (optional для длинных ответов и TTS/ASR; без него — локальный фолбэк и без озвучки)
 *   PRO_MIN_WORDS=800  (optional, базовый deep)
 *   PRO_MAX_WORDS=1200 (optional, базовый deep)
 */

const express = require('express');
const { Telegraf } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

const BASE_MIN = Number(process.env.PRO_MIN_WORDS || 800);
const BASE_MAX = Number(process.env.PRO_MAX_WORDS || 1200);
const MAX_CHARS = 3900; // запас до телеграм-лимита 4096

if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
bot.webhookReply = false; // критично: отвечаем асинхронно, не в HTTP-вебхуке

// ——— Постоянная Reply‑клавиатура без инлайнов ———
const replyKeyboard = {
  keyboard: [
    [{ text: 'Меню' }],
    [{ text: 'Коротко' }, { text: 'Средне' }, { text: 'Глубоко' }],
    [{ text: 'Голос' }]
  ],
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

// ——— Простая «сессия» в памяти: настройки на чат ———
const session = new Map(); // chatId -> { depth: 'short'|'medium'|'deep', tts: boolean }
function getSession(chatId) {
  const def = { depth: 'deep', tts: false };
  if (!session.has(chatId)) session.set(chatId, def);
  const s = session.get(chatId);
  // защита от пустых
  if (!s.depth) s.depth = 'deep';
  if (typeof s.tts !== 'boolean') s.tts = false;
  return s;
}

// ——— Утилиты ———
function sanitizeOutput(text) {
  if (!text) return '';
  let t = text
    .replace(/[`*_#]/g, '')                 // убрать markdown-символы
    .replace(/^\s*>[^\n]*$/gm, s => s.replace(/^>\s?/, '')) // убрать цитаты
    .replace(/^\s*-\s+/gm, '')              // убрать тире-маркеры
    .replace(/\n{3,}/g, '\n\n')             // нормализовать пустые строки
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

// Таймаут-обёртка
async function withTimeout(promiseFactory, ms, name = 'timeout') {
  const controller = new AbortController();
  const t = setTimeout(() => controller.abort(), ms);
  try {
    return await promiseFactory(controller.signal);
  } catch (e) {
    if (e.name === 'AbortError') throw new Error(name);
    throw e;
  } finally {
    clearTimeout(t);
  }
}

// Конструируем промпт с учётом глубины
function structurePrompt(userTopic, depth = 'deep') {
  const topic = (userTopic || '').trim();
  let minW = BASE_MIN, maxW = BASE_MAX;
  if (depth === 'short') { minW = 200; maxW = 350; }
  if (depth === 'medium') { minW = 500; maxW = 700; }
  // deep = по умолчанию BASE_MIN..BASE_MAX
  const instructionsRu = `
Ты — профессиональный аналитик. Дай развёрнутый ответ ${minW}–${maxW} слов на русском, одним сообщением, без списков с «-», без Markdown, без цитирования вопроса и без воды. Структура строго по разделам с чёткими подзаголовками:
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

async function openaiChatAnswer(topic, depth) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key');
  const { system, user } = structurePrompt(topic, depth);
  const body = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    temperature: 0.5,
    max_tokens: depth === 'short' ? 500 : depth === 'medium' ? 900 : 1200
  };
  const doFetch = (signal) => fetch('https://api.openai.com/v1/chat/completions', {
    method: 'POST',
    headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal
  });
  const res = await withTimeout(doFetch, 15000, 'openai_chat_timeout');
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`openai_chat_http_${res.status}: ${txt}`);
  }
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content || '';
  return ensureOneMessageLimit(sanitizeOutput(content));
}

// Локальные расширенные фолбэки (на случай отсутствия ключа/таймаута)
function localFallback(topicRaw) {
  const q = (topicRaw || '').toLowerCase();
  const base = (name) => [
    `Контекст и вводные. ${name}: ключевые историко-географические ориентиры, современная роль в регионе и мире, практическое значение для путешественника, инвестора или релоканта.`,
    `Карта темы. Институции и право; экономика и рынки; инфраструктура и логистика; культура и язык; быт и сервисы; связь и цифровая среда. По каждому блоку — где искать первичные данные, на что смотреть и какие метрики критичны.`,
    `Практические шаги. План на 30–60 дней: сбор базовой информации и документов; оценка стоимости жизни/доходов; карта рисков; пилотные контакты; пробный визит/удалённый тест; финализация решения; трекер метрик и контрольные точки.`,
    `Риски и ограничения. Регуляторные, финансовые, инфраструктурные, культурно-языковые и операционные. Для каждого — как выявить заранее, как снизить, какой план Б.`,
    `Профессиональные советы. Опираться на первичные источники и официальные реестры; валидировать выводы через 2–3 независимых источника; подключать локальные комьюнити.`,
    `Чек-лист действий. 1) Цели и критерии успеха; 2) Бюджет и сроки; 3) Документы и легализация; 4) Жильё и инфраструктура; 5) Работа/бизнес; 6) Страхование и медицина; 7) Связь и банки; 8) Сообщество и язык; 9) План адаптации; 10) Контроль и пересмотр решений.`
  ].join('\n\n');

  if (q.includes('герман') || q.includes('germany')) return ensureOneMessageLimit(sanitizeOutput(base('Германия')));
  if (q.includes('бали') || q.includes('bali')) return ensureOneMessageLimit(sanitizeOutput(base('Бали')));
  if (q.includes('румыни') || q.includes('romania')) return ensureOneMessageLimit(sanitizeOutput(base('Румыния')));
  if (q.includes('молдова') || q.includes('moldova')) return ensureOneMessageLimit(sanitizeOutput(base('Молдова')));
  if (q.includes('рим') || q.includes('rome')) return ensureOneMessageLimit(sanitizeOutput(base('Рим')));
  if (q.includes('наполеон')) return ensureOneMessageLimit(sanitizeOutput(base('Наполеон')));
  if (q.includes('беларус') || q.includes('белорусс') || q.includes('belarus')) return ensureOneMessageLimit(sanitizeOutput(base('Беларусь')));
  if (q.includes('китай') || q.includes('china')) return ensureOneMessageLimit(sanitizeOutput(base('Китай')));
  return ensureOneMessageLimit(sanitizeOutput(base('Тема')));
}

async function generateProAnswer(topic, depth) {
  try {
    return await openaiChatAnswer(topic, depth);
  } catch (e) {
    console.error('OpenAI failed, use fallback:', e.message);
    return localFallback(topic);
  }
}

// ASR (распознавание voice) — работает только при наличии OPENAI_API_KEY
async function transcribeVoice(fileUrl) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key_asr');
  const fileRes = await withTimeout(
    (signal) => fetch(fileUrl, { signal }),
    15000,
    'asr_file_timeout'
  );
  if (!fileRes.ok) throw new Error(`asr_file_http_${fileRes.status}`);
  const buf = await fileRes.arrayBuffer();
  const blob = new Blob([buf], { type: 'audio/ogg' });

  const form = new FormData();
  form.append('file', blob, 'voice.ogg');
  form.append('model', 'whisper-1');
  form.append('response_format', 'text');

  const asrRes = await withTimeout(
    (signal) => fetch('https://api.openai.com/v1/audio/transcriptions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}` },
      body: form,
      signal
    }),
    20000,
    'asr_timeout'
  );
  if (!asrRes.ok) {
    const txt = await asrRes.text().catch(() => '');
    throw new Error(`asr_http_${asrRes.status}: ${txt}`);
  }
  const text = await asrRes.text();
  return (text || '').trim();
}

// TTS (озвучка текста) — OpenAI audio/speech, без ffmpeg
async function synthesizeSpeech(text) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key_tts');
  const body = {
    model: 'gpt-4o-mini-tts',
    voice: 'alloy',
    input: text,
    format: 'mp3' // отправим как audio (mp3); "voice message" (OGG Opus) не обязателен
  };
  const res = await withTimeout(
    (signal) => fetch('https://api.openai.com/v1/audio/speech', {
      method: 'POST',
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal
    }),
    20000,
    'tts_timeout'
  );
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`tts_http_${res.status}: ${txt}`);
  }
  const arrayBuf = await res.arrayBuffer();
  return Buffer.from(arrayBuf);
}

// ——— Логирование ———
bot.use(async (ctx, next) => {
  try {
    const t = ctx.updateType;
    const msg = ctx.message || ctx.update?.message;
    const info = msg?.text ? `text="${(msg.text || '').slice(0,80)}"` : (msg?.voice ? `voice_dur=${msg.voice.duration}s` : '');
    console.log(`[update] ${t} chat=${msg?.chat?.id} user=${msg?.from?.id} ${info}`);
  } catch {}
  return next();
});

bot.catch((err, ctx) => {
  console.error('Telegraf error:', err);
  if (ctx?.chat?.id) ctx.reply('Временная ошибка. Повторите запрос текстом.', replyOptions).catch(() => {});
});

// ——— Команды ———
bot.start(async (ctx) => {
  const s = getSession(ctx.chat.id);
  const welcome = [
    'SmartPro 24/7 готов. Пишите тему текстом или голосом — получите профессиональный ответ без инлайнов.',
    'Кнопки снизу: Меню, Коротко, Средне, Глубоко, Голос (включает/выключает аудио-озвучку).',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`,
    'Синее меню: /start /menu /help /pay /ref /version /debug.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(welcome), replyOptions);
});

bot.command('menu', async (ctx) => {
  const s = getSession(ctx.chat.id);
  const text = [
    'Меню',
    '— Кнопки снизу управляют режимом: Коротко/Средне/Глубоко и Голос (озвучка).',
    '— Голосовые до ~15 сек распознаются; ответ — текстом, а при включённой озвучке добавим аудио.',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('help', async (ctx) => {
  const text = [
    'Как получить лучший ответ:',
    '1) Укажите цель и контекст (страна/город, сроки, бюджет, формат — туризм/релокация/бизнес).',
    '2) Выберите глубину кнопками: Коротко / Средне / Глубоко.',
    '3) При желании включите «Голос» — добавим аудио-озвучку ответа.',
    'Ответы формируются одним сообщением (текст), без цитирования вопроса. При включённой озвучке добавляется аудио.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('pay', async (ctx) => {
  const text = [
    'Тарифы (демо): 10 / 20 / 50 USD.',
    'Оплата и рефералы активируются после стабилизации ядра.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

bot.command('ref', async (ctx) => {
  const uid = ctx.from?.id || 0;
  const link = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=ref_${uid}` : 'Ссылка будет доступна после инициализации бота';
  await ctx.reply(sanitizeOutput(`Ваша реф‑ссылка:\n${link}`), replyOptions);
});

bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT‑4o — U10h-Node', replyOptions);
});

bot.command('debug', async (ctx) => {
  try {
    const info = await bot.telegram.getWebhookInfo();
    const masked = {
      url: info.url,
      allowed_updates: info.allowed_updates,
      pending_update_count: info.pending_update_count,
      last_error_date: info.last_error_date,
      last_error_message: info.last_error_message,
      secret_token_set: Boolean(SECRET_TOKEN),
      openai_key_present: !!OPENAI_API_KEY,
      version: 'U10h-Node'
    };
    await ctx.reply(JSON.stringify(masked, null, 2), replyOptions);
  } catch (e) {
    await ctx.reply('DEBUG error: ' + e.message, replyOptions);
  }
});

// ——— Обработка нажатий по Reply‑кнопкам (они приходят как обычный текст) ———
bot.hears('Коротко', async (ctx) => {
  const s = getSession(ctx.chat.id);
  s.depth = 'short';
  await ctx.reply('Готово: режим длины — КОРОТКО.', replyOptions);
});
bot.hears('Средне', async (ctx) => {
  const s = getSession(ctx.chat.id);
  s.depth = 'medium';
  await ctx.reply('Готово: режим длины — СРЕДНЕ.', replyOptions);
});
bot.hears('Глубоко', async (ctx) => {
  const s = getSession(ctx.chat.id);
  s.depth = 'deep';
  await ctx.reply('Готово: режим длины — ГЛУБОКО.', replyOptions);
});
bot.hears('Голос', async (ctx) => {
  const s = getSession(ctx.chat.id);
  s.tts = !s.tts;
  await ctx.reply(`Озвучка: ${s.tts ? 'ВКЛ' : 'ВЫКЛ'}.`, replyOptions);
});
bot.hears('Меню', async (ctx) => {
  const s = getSession(ctx.chat.id);
  const text = [
    'Меню',
    '— Выберите глубину: Коротко / Средне / Глубоко.',
    '— Переключатель «Голос» включает/выключает аудио-озвучку ответа.',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});

// ——— Текстовые запросы ———
bot.on('text', async (ctx) => {
  try {
    const text = (ctx.message?.text || '').trim();
    // служебные кнопки уже отловлены через hears; здесь — обычные темы
    if (!text || ['Меню','Коротко','Средне','Глубоко','Голос'].includes(text)) return;

    const s = getSession(ctx.chat.id);
    const answer = await generateProAnswer(text, s.depth);

    // 1) всегда отправляем текст (единое длинное сообщение)
    await ctx.reply(answer, replyOptions);

    // 2) если включена озвучка и есть ключ — добавляем аудио-версию
    if (s.tts && OPENAI_API_KEY) {
      try {
        // Для аудио берём умеренно сокращённый вариант (обрежем до ~800–1000 символов)
        const audioText = answer.length > 1000 ? answer.slice(0, 1000) + '…' : answer;
        const audioBuf = await synthesizeSpeech(audioText);
        await ctx.replyWithAudio(
          { source: audioBuf, filename: 'answer.mp3' },
          { title: 'Аудио‑ответ', reply_markup: replyKeyboard }
        );
      } catch (ttsErr) {
        console.error('TTS failed:', ttsErr.message);
        await ctx.reply('Озвучка временно недоступна. Текстовый ответ уже отправлен.', replyOptions);
      }
    }
  } catch (e) {
    console.error('text handler error:', e.message);
    await ctx.reply('Временная ошибка обработки. Повторите запрос текстом.', replyOptions);
  }
});

// ——— Голосовые ———
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

    const s = getSession(ctx.chat.id);
    const answer = await generateProAnswer(topic || 'Пожалуйста, сформулируйте тему запроса.', s.depth);

    // 1) текст — всегда
    await ctx.reply(answer, replyOptions);

    // 2) при включенной озвучке — аудио
    if (s.tts && OPENAI_API_KEY) {
      try {
        const audioText = answer.length > 1000 ? answer.slice(0, 1000) + '…' : answer;
        const audioBuf = await synthesizeSpeech(audioText);
        await ctx.replyWithAudio(
          { source: audioBuf, filename: 'answer.mp3' },
          { title: 'Аудио‑ответ', reply_markup: replyKeyboard }
        );
      } catch (ttsErr) {
        console.error('TTS failed:', ttsErr.message);
        await ctx.reply('Озвучка временно недоступна. Текстовый ответ уже отправлен.', replyOptions);
      }
    }
  } catch (e) {
    console.error('voice handler error:', e.message);
    await ctx.reply('Не удалось обработать голосовое. Отправьте тему текстом.', replyOptions);
  }
});

// ——— Веб‑сервер и вебхук ———
const app = express();
app.use(express.json());

// Быстрая проверка версии
app.get('/version', (req, res) => {
  res.type('text/plain').send('UNIVERSAL GPT‑4o — U10h-Node');
});

// Проверка, что отвечает Node
app.get('/telegram/railway123', (req, res) => {
  res.type('text/plain').send('Webhook OK');
});

// Асинхронный вебхук: сразу 200 OK, обработка — в фоне
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
