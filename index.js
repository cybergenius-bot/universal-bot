/**
 * SmartPro 24/7 (U10k-Node)
 * — Универсальный промпт: модель сама определяет намерение (рецепт/аналитика/план/сравнение и т. д.)
 *   и подбирает формат ответа. Никаких доменных "заготовок" с готовым текстом.
 * — По умолчанию одна Reply‑кнопка «Меню». По нажатию — разворачивается большая клавиатура (без инлайнов):
 *   Коротко / Средне / Глубоко / Голос + дубли /start /menu /help /pay /ref /version.
 *   После выбора — клавиатура сворачивается обратно к одной «Меню».
 * — Длинные ответы одним сообщением. Голосовые распознаются (Whisper при OPENAI_API_KEY). Опциональный TTS по кнопке «Голос».
 * — Асинхронный вебхук, x-telegram-bot-api-secret-token, маршруты: /version, /telegram/railway123.
 */

const express = require('express');
const { Telegraf } = require('telegraf');

const BOT_TOKEN = process.env.BOT_TOKEN;
const SECRET_TOKEN = process.env.SECRET_TOKEN || 'railway123';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const PORT = process.env.PORT || 3000;

const BASE_MIN = Number(process.env.PRO_MIN_WORDS || 800);
const BASE_MAX = Number(process.env.PRO_MAX_WORDS || 1200);
const MAX_CHARS = 3900;

if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
bot.webhookReply = false; // отвечаем асинхронно

// Клавиатуры (без инлайнов)
const kbSmall = {
  keyboard: [[{ text: 'Меню' }]],
  resize_keyboard: true,
  is_persistent: true,
  one_time_keyboard: false,
  input_field_placeholder: 'Опишите тему запроса…'
};
const kbBig = {
  keyboard: [
    [{ text: 'Коротко' }, { text: 'Средне' }, { text: 'Глубоко' }],
    [{ text: 'Голос' }],
    [{ text: '/start' }, { text: '/menu' }, { text: '/help' }],
    [{ text: '/pay' }, { text: '/ref' }, { text: '/version' }]
  ],
  resize_keyboard: true,
  is_persistent: true,
  one_time_keyboard: false
};
const replySmall = { reply_markup: kbSmall, disable_web_page_preview: true };
const replyBig = { reply_markup: kbBig, disable_web_page_preview: true };

// Команды
const BOT_COMMANDS = [
  { command: 'start', description: 'Запуск и краткая справка' },
  { command: 'menu', description: 'Меню и настройки' },
  { command: 'help', description: 'Помощь и правила ввода' },
  { command: 'pay', description: 'Тарифы и оплата' },
  { command: 'ref', description: 'Реферальная ссылка' },
  { command: 'version', description: 'Версия сборки' },
  { command: 'debug', description: 'Диагностика вебхука/окружения' }
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

// Сессия на чат: глубина/озвучка
const session = new Map(); // chatId -> { depth: 'short'|'medium'|'deep', tts: boolean }
function getSession(chatId) {
  if (!session.has(chatId)) session.set(chatId, { depth: 'deep', tts: false });
  const s = session.get(chatId);
  if (!s.depth) s.depth = 'deep';
  if (typeof s.tts !== 'boolean') s.tts = false;
  return s;
}

// Утилиты
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

// Универсальный промпт: авто-определение намерения и формат ответа
function intentAwarePrompt(userTopic, depth = 'deep') {
  const topic = (userTopic || '').trim();

  const minW = depth === 'short' ? 200 : depth === 'medium' ? 500 : BASE_MIN;
  const maxW = depth === 'short' ? 350 : depth === 'medium' ? 700 : BASE_MAX;

  const system = `
Ты — профессиональный ассистент. Самостоятельно определяй намерение пользователя и выбирай корректный формат ответа. 
Всегда отвечай одним сообщением на русском (если явно не указано иное), без Markdown и без тире‑списков, деловой плотный стиль, полные абзацы. Объём ${minW}–${maxW} слов. Избегай цитирования вопроса и «воды».

Правила выбора формата (строго соблюдать):
1) Кулинария/рецепты/блюда: дай технологическую карту с инвентарём, точными ингредиентами (г/мл/шт), пошаговым приготовлением с температурами и временем, таймингом/выходом/хранением и блоком «частые ошибки и их исправление». Не рассказывай историю блюда.
2) Страны/города/релокация/бизнес/анализ: структура — «Контекст», «Карта темы», «Практические шаги», «Риски», «Проф. советы», «Чек‑лист».
3) Обучение/план/проект: цель, этапы, риски, метрики, критерии готовности и точки контроля.
4) Правила/процедуры/документы: требования, шаги, сроки, исключения, контрольные точки.
5) Сравнение/выбор: критерии сравнения, текстовая таблица (без Markdown), рекомендации, итоговый выбор, условия пересмотра.
6) Если запрос неоднозначен: в начале коротко уточни предполагаемый контекст и предложи 2–3 трактовки, затем дай ответ по наиболее вероятной.

Всегда избегай пустословия. Нумерация 1., 2., 3. допустима. Не повторяй формулировки пользователя.`;

  const user = `Тема: ${topic || 'универсальная тема'}. Сформируй ответ строго по правилам.`;
  return { system, user };
}

async function openaiChatAnswer(topic, depth) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key');
  const { system, user } = intentAwarePrompt(topic, depth);
  const body = {
    model: 'gpt-4o-mini',
    messages: [
      { role: 'system', content: system },
      { role: 'user', content: user }
    ],
    temperature: 0.35,
    max_tokens: depth === 'short' ? 800 : depth === 'medium' ? 1200 : 1600
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

// Универсальный фолбэк (без доменных текстов): каркас под любую тему
function universalFallback(topic, depth) {
  const isRecipe = /(рецепт|как приготовить|ингредиент|грамм|тесто|крем|торт|пирог|recipe|ingredients)/i.test(topic || '');
  if (isRecipe) {
    // Без ключа дать «точные граммы» невозможно — даём краткую технологическую схему, честно сообщая ограничение
    return ensureOneMessageLimit(sanitizeOutput([
      'Рецепт: технологическая карта (общее руководство без точных граммов).',
      '1) Инвентарь: весы, миски, венчик, лопатка, сотейник, духовка, пергамент.',
      '2) Ингредиенты: база (мука, жир, жидкость, разрыхляющие/связующие) подбираются по типу блюда; точные граммы требует кулинарной спецификации.',
      '3) Приготовление: подготовка; смешивание/замес; выдержка/охлаждение; формовка; термообработка при профильной температуре; стабилизация/остывание.',
      '4) Тайминг/выход/хранение: зависит от массы/формы; критично выдерживать отдых и охлаждение.',
      '5) Частые ошибки: несоответствие температур; перевзбивание/недовар; нарушение пропорций. Решение: работать по техкарте и контролировать температуры.',
      'Для точной рецептуры укажите продукт/масштаб и включите OPENAI_API_KEY на сервере — тогда я дам полный рецепт с граммами и температурами одним сообщением.'
    ].join('\n')));
  }
  return ensureOneMessageLimit(sanitizeOutput([
    'Контекст и вводные. Сформулируйте цель, ограничения и критерии успеха; почему тема важна сейчас.',
    'Карта темы. Требования/данные; ресурсы/компетенции; процессы/инструменты; риски/допущения; метрики/контроль.',
    'Практические шаги. План на 30–60 дней: подготовка, пилот, проверка гипотез, масштабирование, подведение итогов.',
    'Риски и ограничения. Регуляторные, финансовые, технические, операционные; индикаторы, снижение, план Б.',
    'Профессиональные советы. Первичные источники, валидация двумя независимыми источниками, резерв 10–20%.',
    'Чек‑лист. 1) Цель/KPI; 2) Ответственные; 3) Бюджет/сроки; 4) Данные/доступы; 5) Право/комплаенс; 6) Риски/план Б; 7) Коммуникации; 8) Метрики; 9) Эскалация; 10) Ретроспектива.'
  ].join('\n\n')));
}

async function generateAnswer(topic, depth) {
  try {
    return await openaiChatAnswer(topic, depth);
  } catch (e) {
    console.error('OpenAI failed, universal fallback used:', e.message);
    return universalFallback(topic || '', depth);
  }
}

// ASR (voice → text) Whisper
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

// TTS (по кнопке «Голос»)
async function synthesizeSpeech(text) {
  if (!OPENAI_API_KEY) throw new Error('no_openai_key_tts');
  const body = { model: 'gpt-4o-mini-tts', voice: 'alloy', input: text, format: 'mp3' };
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

// Логи и ловля ошибок
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
  if (ctx?.chat?.id) ctx.reply('Временная ошибка. Повторите запрос.', replySmall).catch(() => {});
});

// Команды
bot.start(async (ctx) => {
  const s = getSession(ctx.chat.id);
  const welcome = [
    'SmartPro 24/7 готов. По умолчанию снизу одна кнопка «Меню». Нажмите — развернётся большое меню (без инлайнов).',
    'Коротко/Средне/Глубоко — длина ответа. «Голос» — включает/выключает озвучку. Команды доступны и как синие /команды, и в большом меню.',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(welcome), replySmall);
});
bot.command('menu', async (ctx) => {
  const s = getSession(ctx.chat.id);
  const text = [
    'Меню',
    '— Выберите глубину: Коротко / Средне / Глубоко.',
    '— «Голос» — переключатель озвучки ответа.',
    '— Команды: /start /menu /help /pay /ref /version.',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyBig);
});
bot.command('help', async (ctx) => {
  const text = [
    'Как получить точный результат:',
    '1) Опишите тему естественно — бот сам определит формат (рецепт, план, аналитика и др.).',
    '2) При необходимости переключите глубину: Коротко / Средне / Глубоко.',
    '3) Для аудио‑версии ответа нажмите «Голос».'
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replySmall);
});
bot.command('pay', async (ctx) => {
  await ctx.reply('Тарифы (демо): 10 / 20 / 50 USD. Подключим после стабилизации ядра.', replySmall);
});
bot.command('ref', async (ctx) => {
  const uid = ctx.from?.id || 0;
  const link = BOT_USERNAME ? `https://t.me/${BOT_USERNAME}?start=ref_${uid}` : 'Ссылка появится после инициализации бота';
  await ctx.reply(sanitizeOutput(`Ваша реф‑ссылка:\n${link}`), replySmall);
});
bot.command('version', async (ctx) => {
  await ctx.reply('UNIVERSAL GPT‑4o — U10k-Node', replySmall);
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
      version: 'U10k-Node'
    };
    await ctx.reply(JSON.stringify(masked, null, 2), replySmall);
  } catch (e) {
    await ctx.reply('DEBUG error: ' + e.message, replySmall);
  }
});

// Hears (большая клавиатура)
bot.hears('Меню', async (ctx) => {
  const s = getSession(ctx.chat.id);
  const text = [
    'Меню',
    '— Выберите глубину: Коротко / Средне / Глубоко.',
    '— «Голос» — переключатель озвучки ответа.',
    '— Команды: /start /menu /help /pay /ref /version.',
    `Текущие настройки: длина=${s.depth}; озвучка=${s.tts ? 'вкл' : 'выкл'}.`
  ].join('\n\n');
  await ctx.reply(sanitizeOutput(text), replyBig);
});
bot.hears('Коротко', async (ctx) => {
  const s = getSession(ctx.chat.id); s.depth = 'short';
  await ctx.reply('Режим длины: КОРОТКО.', replySmall);
});
bot.hears('Средне', async (ctx) => {
  const s = getSession(ctx.chat.id); s.depth = 'medium';
  await ctx.reply('Режим длины: СРЕДНЕ.', replySmall);
});
bot.hears('Глубоко', async (ctx) => {
  const s = getSession(ctx.chat.id); s.depth = 'deep';
  await ctx.reply('Режим длины: ГЛУБОКО.', replySmall);
});
bot.hears('Голос', async (ctx) => {
  const s = getSession(ctx.chat.id); s.tts = !s.tts;
  await ctx.reply(`Озвучка: ${s.tts ? 'ВКЛ' : 'ВЫКЛ'}.`, replySmall);
});

// Текст
bot.on('text', async (ctx) => {
  try {
    const txt = (ctx.message?.text || '').trim();
    if (!txt || ['Меню','Коротко','Средне','Глубоко','Голос'].includes(txt)) return;

    const s = getSession(ctx.chat.id);
    const answer = await generateAnswer(txt, s.depth);
    await ctx.reply(answer, replySmall);

    if (s.tts && OPENAI_API_KEY) {
      try {
        const audioText = answer.length > 1000 ? answer.slice(0, 1000) + '…' : answer;
        const buf = await synthesizeSpeech(audioText);
        await ctx.replyWithAudio({ source: buf, filename: 'answer.mp3' }, { title: 'Аудио‑ответ', reply_markup: kbSmall });
      } catch (e) {
        console.error('TTS failed:', e.message);
        await ctx.reply('Озвучка временно недоступна. Текст уже отправлен.', replySmall);
      }
    }
  } catch (e) {
    console.error('text handler error:', e.message);
    await ctx.reply('Временная ошибка. Повторите запрос.', replySmall);
  }
});

// Голос
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
      return ctx.reply('Распознавание сейчас недоступно. Отправьте тему текстом.', replySmall);
    }

    const s = getSession(ctx.chat.id);
    const answer = await generateAnswer(topic || 'Пожалуйста, сформулируйте тему запроса.', s.depth);
    await ctx.reply(answer, replySmall);

    if (s.tts && OPENAI_API_KEY) {
      try {
        const audioText = answer.length > 1000 ? answer.slice(0, 1000) + '…' : answer;
        const buf = await synthesizeSpeech(audioText);
        await ctx.replyWithAudio({ source: buf, filename: 'answer.mp3' }, { title: 'Аудио‑ответ', reply_markup: kbSmall });
      } catch (e) {
        console.error('TTS failed:', e.message);
        await ctx.reply('Озвучка временно недоступна. Текст уже отправлен.', replySmall);
      }
    }
  } catch (e) {
    console.error('voice handler error:', e.message);
    await ctx.reply('Не удалось обработать голосовое. Отправьте тему текстом.', replySmall);
  }
});

// Веб‑сервер и вебхук
const app = express();
app.use(express.json());

app.get('/version', (req, res) => {
  res.type('text/plain').send('UNIVERSAL GPT‑4o — U10k-Node');
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
