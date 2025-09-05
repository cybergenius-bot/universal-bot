/**
 * SmartPro 24/7 (U11b-Node)
 * — Один длинный профессиональный ответ одним сообщением. Без инлайнов. TTS отключён.
 * — Одна постоянная Reply‑кнопка «Меню». «Синее меню»: /start /menu /help /pay /ref /version /debug.
 * — Голос распознаём при OPENAI_API_KEY (Whisper), но отвечаем всегда текстом (анти‑эхо).
 * — Асинхронный вебхук + “typing” во время генерации + таймауты и гарантированный фолбэк.
 */

const express = require('express');
const { Telegraf } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

const PRO_MIN_WORDS = Number(process.env.PRO_MIN_WORDS || 800);
const PRO_MAX_WORDS = Number(process.env.PRO_MAX_WORDS || 1200);
const MAX_CHARS = 3900; // запас под лимит 4096

if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
bot.webhookReply = false; // критично: не отвечаем в HTTP вебхука

// ——— Постоянная Reply‑клавиатура ———
const replyKeyboard = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  is_persistent: true,
  one_time_keyboard: false,
  input_field_placeholder: 'Опишите тему запроса…'
};
const replyOptions = { reply_markup: replyKeyboard, disable_web_page_preview: true };

// ——— Команды ———
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
    .replace(/[`*_#]/g, '')                // убрать markdown-символы
    .replace(/^\s*>[^\n]*$/gm, s => s.replace(/^>\s?/, '')) // убрать цитаты
    .replace(/^\s*-\s+/gm, '')             // убрать тире-маркеры
    .replace(/\n{3,}/g, '\n\n')            // нормализовать пустые строки
    .trim();
  if (t.length > MAX_CHARS) t = t.slice(0, MAX_CHARS - 10).trim() + '…';
  return t;
}
function ensureOneMessageLimit(s) {
  if (!s) return s;
  return s.length <= MAX_CHARS ? s : s.slice(0, MAX_CHARS - 10).trim() + '…';
}
async function withTimeout(promiseFactory, ms, name = 'timeout') {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await promiseFactory(controller.signal);
  } catch (e) {
    if (e.name === 'AbortError') throw new Error(name);
    throw e;
  } finally {
    clearTimeout(timer);
  }
}
// «Печатает…» пока готовим ответ
function startTyping(ctx) {
  const chatId = ctx.chat.id;
  let stopped = false;
  const tick = async () => { if (!stopped) { try { await ctx.telegram.sendChatAction(chatId, 'typing'); } catch {} } };
  tick();
  const h = setInterval(tick, 5000);
  return () => { stopped = true; clearInterval(h); };
}

// ——— Универсальная модельная инструкция ———
function buildIntentPrompt(userTopic) {
  const topic = (userTopic || '').trim();
  const minW = PRO_MIN_WORDS;
  const maxW = PRO_MAX_WORDS;
  const system = `
Ты — профессиональный ассистент. Сам определяй намерение пользователя и выбирай формат ответа.
Всегда отвечай одним сообщением на русском (если явно не указано иное), без Markdown и без тире‑списков, деловой плотный стиль, полные абзацы. Объём ${minW}–${maxW} слов. Не цитируй вопрос и избегай «воды».

Правила выбора формата:
1) Кулинария/рецепт: технологическая карта с инвентарём, точными ингредиентами (г/мл/шт), пошаговой термообработкой (температуры/время), таймингом/выходом/хранением, «частые ошибки и исправление». Историю блюда не писать.
2) Аналитика (страны/город/бизнес/релокация): «Контекст», «Карта темы», «Практические шаги», «Риски», «Проф. советы», «Чек‑лист».
3) План/проект/обучение: цель, этапы, риски, метрики, критерии готовности, точки контроля.
4) Правила/процедуры/документы: требования, шаги, сроки, исключения, контрольные точки.
5) Сравнение/выбор: критерии, текстовая таблица (без Markdown), рекомендации, итог, условия пересмотра.
6) Если запрос неоднозначен: кратко обозначь 2–3 трактовки и ответь по наиболее вероятной.`;
  const user = `Тема: ${topic || 'универсальная тема'}. Сформируй ответ строго по правилам.`;
  return { system, user };
}

async function openaiChatAnswer(topic) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key');
  const { system, user } = buildIntentPrompt(topic);
  const body = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    temperature: 0.35,
    max_tokens: 1600
  };
  const res = await withTimeout(
    (signal) => fetch('https://api.openai.com/v1/chat/completions', {
      method: 'POST',
      headers: { Authorization: `Bearer ${OPENAI_API_KEY}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal
    }),
    20000,
    'openai_chat_timeout'
  );
  if (!res.ok) {
    const txt = await res.text().catch(() => '');
    throw new Error(`openai_chat_http_${res.status}: ${txt}`);
  }
  const data = await res.json();
  const content = data?.choices?.[0]?.message?.content || '';
  return ensureOneMessageLimit(sanitizeOutput(content));
}

// ——— Гарантированная генерация: OpenAI c таймаутом + фолбэк ———
function looksLikeRecipe(topic) {
  return /(рецепт|как приготовить|ингредиент|грамм|крем|тесто|торт|пирог|recipe|ingredients)/i.test(topic || '');
}
function universalFallback(topic) {
  const isRecipe = looksLikeRecipe(topic);
  if (isRecipe) {
    return ensureOneMessageLimit(sanitizeOutput([
      'Рецепт: технологическая карта (общее руководство без точных граммов).',
      '1) Инвентарь: весы, миски, венчик, лопатка, сотейник/кастрюля, духовка, пергамент.',
      '2) Ингредиенты: зависят от блюда и диаметра/массы; укажите точные параметры — рассчитаю пропорции.',
      '3) Этапы: подготовка → замес/смешивание → выдержка/охлаждение → формовка → выпечка/варка при профильной температуре → стабилизация/остывание.',
      '4) Тайминг/хранение: зависит от массы/формы; критично выдерживать отдых и охлаждение.',
      '5) Частые ошибки: несоответствие температур/пропорций; решение — строгая техкарта и контроль.'
    ].join('\n')));
  }
  return ensureOneMessageLimit(sanitizeOutput([
    'Контекст и вводные. Сформулируйте цель, ограничения и критерии успеха; почему тема важна сейчас.',
    'Карта темы. Требования/данные; ресурсы/компетенции; процессы/инструменты; риски/допущения; метрики/контроль.',
    'Практические шаги. План на 30–60 дней: подготовка, пилот, проверка гипотез, масштабирование, итоги.',
    'Риски и ограничения. Регуляторные, финансовые, технические, операционные; индикаторы, снижение, план Б.',
    'Профессиональные советы. Первичные источники, валидация 2+ независимыми источниками, резерв 10–20%.',
    'Чек‑лист. Цели/KPI; ответственные; бюджет/сроки; данные/доступы; право/комплаенс; риски/план Б; коммуникации; метрики; эскалация; ретроспектива.'
  ].join('\n\n')));
}
async function generateAnswer(topic) {
  try {
    return await openaiChatAnswer(topic);
  } catch (e) {
    console.error('OpenAI failed, universal fallback used:', e.message);
    return universalFallback(topic || '');
  }
}

// ——— ASR (Whisper) ———
async function transcribeVoice(fileUrl) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key_asr');
  const fileRes = await withTimeout(
    (signal) => fetch(fileUrl, { signal }),
    18000,
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

// ——— Логи/ловля ошибок ———
bot.use(async (ctx, next) => {
  try {
    const t = ctx.updateType;
    const msg = ctx.message || ctx.update?.message;
    const info = msg?.text ? `text="${(msg.text || '').slice(0,100)}"` : (msg?.voice ? `voice_dur=${msg.voice.duration}s` : '');
    console.log(`[update] ${t} chat=${msg?.chat?.id} user=${msg?.from?.id} ${info}`);
  } catch {}
  return next();
});
bot.catch((err, ctx) => {
  console.error('Telegraf error:', err);
  if (ctx?.chat?.id) ctx.reply('Временная ошибка. Повторите запрос.', replyOptions).catch(() => {});
});

// ——— Команды ———
bot.start(async (ctx) => {
  const welcome = [
    'SmartPro 24/7 готов. Пишите тему текстом или голосом — получите один длинный профессиональный ответ без инлайнов и без озвучки.',
    'Всегда доступна одна Reply‑кнопка «Меню». Синее меню команд: /start /menu /help /pay /ref /version /debug.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(welcome), replyOptions);
});
bot.command('menu', async (ctx) => {
  const text = [
    'Меню',
    '— Отправьте тему (например: «Рецепт: торт Наполеон» или «Экономика Германии для инвестора»).',
    '— Голосовые до ~15 сек распознаются при наличии ключа, ответ — всегда одним длинным текстом.',
    '— Никаких инлайнов. Всегда одна Reply‑кнопка: «Меню».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});
bot.command('help', async (ctx) => {
  const text = [
    'Как получить лучший ответ:',
    '1) Опишите тему естественно — бот сам определит формат (рецепт, план, аналитика и др.).',
    '2) Для рецептов указывайте блюдо и диаметр/массу — это влияет на пропорции.',
    '3) Ответ придёт одним длинным сообщением, без цитирования вашего вопроса.'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyOptions);
});
bot.command('pay', async (ctx) => {
  await ctx.reply('Тарифы (демо): 10 / 20 / 50 USD. Подключим после стабилизации ядра.', replyOptions);
});
bot.command('ref', async (ctx) => {
  const uid = ctx.from?.id || 0;
  const link = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=ref_${uid}` : 'Ссылка появится после инициализации бота';
  await ctx.reply(sanitizeOutput(`Ваша реф‑ссылка:\n${link}`), replyOptions);
});
bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT‑4o — U11b-Node', replyOptions);
});
bot.command('debug', async (ctx) => {
  try {
    const info = await bot.telegram.getWebhookInfo();
    const masked = {
      url: info.url,
      allowed_updates: info.allowed_updates,
      pending_update_count: info.pending_update_count,
      last_error_message: info.last_error_message,
      secret_token_set: Boolean(SECRET_TOKEN),
      openai_key_present: !!OPENAI_API_KEY,
      version: 'U11b-Node'
    };
    await ctx.reply(JSON.stringify(masked, null, 2), replyOptions);
  } catch (e) {
    await ctx.reply('DEBUG error: ' + e.message, replyOptions);
  }
});

// ——— Текст ———
bot.on('text', async (ctx) => {
  try {
    const txt = (ctx.message?.text || '').trim();
    if (!txt || txt === 'Меню') {
      return ctx.reply('Выберите действие или напишите тему запроса. Команды: /menu /help /pay /ref /version /debug', replyOptions);
    }
    const stopTyping = startTyping(ctx);
    const answer = await generateAnswer(txt);
    stopTyping();
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
    const stopTyping = startTyping(ctx);
    let topic = '';
    try {
      const linkObj = await ctx.telegram.getFileLink(fileId);
      const url = typeof linkObj === 'string' ? linkObj : linkObj.href;
      topic = await transcribeVoice(url);
    } catch (asrErr) {
      console.error('ASR failed:', asrErr.message);
      stopTyping();
      return ctx.reply('Распознавание сейчас недоступно. Отправьте тему текстом.', replyOptions);
    }
    const answer = await generateAnswer(topic || 'Пожалуйста, сформулируйте тему запроса.');
    stopTyping();
    await ctx.reply(answer, replyOptions);
  } catch (e) {
    console.error('voice handler error:', e.message);
    await ctx.reply('Не удалось обработать голосовое. Отправьте тему текстом.', replyOptions);
  }
});

// ——— Веб‑сервер и вебхук ———
const app = express();
app.use(express.json());

app.get('/version', (req, res) => {
  res.type('text/plain').send('UNIVERSAL GPT‑4o — U11b-Node');
});
app.get('/telegram/railway123', (req, res) => {
  res.type('text/plain').send('Webhook OK');
});
app.post('/telegram/railway123', (req, res) => {
  const secret = req.headers['x-telegram-bot-api-secret-token'];
  if (!secret || secret !== SECRET_TOKEN) return res.status(401).send('Unauthorized');
  bot.handleUpdate(req.body).catch((err) => console.error('handleUpdate error:', err));
  res.status(200).send('OK');
});

app.listen(PORT, () => {
  console.log(`Server listening on :${PORT}`);
});
