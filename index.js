// index.js
// SmartPro 24/7 — демо-реализация на Telegraf + Express:
// - Одна кнопка «Меню» (ReplyKeyboard)
// - Полное инлайн-меню только по запросу и закрывается кнопкой
// - Демо-ASR и демо-TTS без расходов
// - Анти-эхо: распознанный текст не повторяем автоматически
// - Транскрипт только по кнопке
// - Автоопределение языка контента с гистерезисом (2 из 3), EN не выбирается на коротких токенах
// - Жесткая очистка Markdown-символов и маркеров
// - Кнопки под ответом: «Показать расшифровку», «Озвучить ответ», «Скрыть»

import express from "express";
import { Telegraf, Markup } from "telegraf";
import gTTS from "gtts";
import ffmpeg from "fluent-ffmpeg";
import ffmpegPath from "ffmpeg-static";
import fs from "fs";
import os from "os";
import path from "path";

// Конфигурация окружения (Railway)
const TOKEN  = process.env.TELEGRAM_BOT_TOKEN;
const SECRET = process.env.WEBHOOK_SECRET || "railway123";
const BASE   = process.env.BASE_URL || ""; // напр.: https://universal-bot-production.up.railway.app
if (!TOKEN) { console.error("ERROR: TELEGRAM_BOT_TOKEN не задан"); process.exit(1); }

// Принудительно включаем демо ASR/TTS по умолчанию (можно выключить DEMO_ASR=0 / DEMO_TTS=0)
const DEMO_ASR = (process.env.DEMO_ASR ?? "1") === "1";
const DEMO_TTS = (process.env.DEMO_TTS ?? "1") === "1";

// Инициализация
ffmpeg.setFfmpegPath(ffmpegPath);
const bot = new Telegraf(TOKEN);
const app = express();
app.use(express.json());

// Память пользователя (в проде → БД/Redis)
const uiLang = new Map();            // user_id -> язык интерфейса (ru|en|he)
const lastContentLangs = new Map();  // user_id -> последние 3 детекции
const contentLang = new Map();       // user_id -> стабильный язык контента

// Кэш ответов/транскриптов на 15 минут для кнопок под сообщениями
const msgTextCache = new Map();  // key: chatId:msgId -> text ответа бота
const asrCache     = new Map();  // key: chatId:msgId -> transcript

function putWithTTL(map, key, value, ttlMs = 15 * 60 * 1000) {
  map.set(key, value);
  const t = setTimeout(() => map.delete(key), ttlMs);
  if (t.unref) t.unref();
}

// Санитайзер исходящего текста: убираем Markdown и маркеры списков; эмодзи и нумерация 1., 2., 3. сохраняются
function sanitizeOutput(s) {
  if (!s) return s;
  let out = String(s);
  out = out.replace(/[#*_`]/g, "");        // жесткая страховка
  out = out.replace(/^\s*>\s?.*$/gm, "");  // блок-цитаты
  out = out.replace(/^\s*[-–—]\s+/gm, ""); // маркеры списков тире
  out = out.replace(/\r\n/g, "\n");
  return out;
}
async function sendClean(ctx, text, extra = {}) {
  const clean = sanitizeOutput(text);
  return ctx.reply(clean, extra);
}
async function replyVoiceClean(ctx, oggPath, caption, extra = {}) {
  const cap = sanitizeOutput(caption || "");
  return ctx.replyWithVoice({ source: fs.createReadStream(oggPath) }, { caption: cap, ...extra });
}

// Локализация интерфейса (фиксируется пользователем, по умолчанию RU)
function tUI(lang = "ru") {
  const t = {
    ru: { hello: "Привет! Я SmartPro 24/7. Нажмите Меню, когда нужно открыть действия.", ready: "Готов. Выберите действие:", ttsCaption: "Озвучено", menuTitle: "Меню действий:", saved: "Сохранено." },
    en: { hello: "Hi! I’m SmartPro 24/7. Tap Menu when you need actions.", ready: "Ready. Choose an action:", ttsCaption: "Voiced", menuTitle: "Actions menu:", saved: "Saved." },
    he: { hello: "שלום! אני SmartPro 24/7. לחצו על תפריט כשצריך פעולות.", ready: "מוכן. בחרו פעולה:", ttsCaption: "הוקרא", menuTitle: "תפריט פעולות:", saved: "נשמר." }
  };
  return t[lang] || t.ru;
}

// Единственная Reply-клавиатура — компактная кнопка «Меню»
function mainKb() {
  return Markup.keyboard([["Меню"]]).resize().oneTime(false);
}

// Инлайн-меню (открывается по запросу и закрывается кнопкой)
function buildInlineMenu() {
  return Markup.inlineKeyboard([
    [Markup.button.callback("Профиль", "m_profile"), Markup.button.callback("Справка", "m_help")],
    [Markup.button.callback("Сменить язык", "m_lang"), Markup.button.callback("Режим ответа", "m_mode")],
    [Markup.button.callback("Скрыть", "m_close")]
  ]);
}
async function showInlineMenu(ctx) {
  const L = uiLang.get(ctx.from?.id) || "ru";
  return sendClean(ctx, tUI(L).menuTitle, buildInlineMenu());
}

// Детект языка контента + гистерезис (2 из 3), EN не выбираем на коротких токенах
const rx = {
  ru: /[А-Яа-яЁё]/, he: /[א-ת]/, ar: /[\u0600-\u06FF]/,
  ja: /[\u3040-\u30FF\u4E00-\u9FFF]/, ko: /[\uAC00-\uD7AF]/,
  zh: /[\u4E00-\u9FFF]/, en: /[A-Za-z]/
};
function detectScriptLang(text = "") {
  if (rx.ru.test(text)) return "ru";
  if (rx.he.test(text)) return "he";
  if (rx.ar.test(text)) return "ar";
  if (rx.ja.test(text)) return "ja";
  if (rx.ko.test(text)) return "ko";
  if (rx.zh.test(text)) return "zh";
  if (rx.en.test(text)) return "en";
  return null;
}
function updateContentLang(userId, candidate) {
  const arr = lastContentLangs.get(userId) || [];
  arr.push(candidate);
  if (arr.length > 3) arr.shift();
  lastContentLangs.set(userId, arr);
  const counts = {};
  for (const c of arr) counts[c] = (counts[c] || 0) + 1;
  let best = null, max = 0;
  for (const k in counts) if (counts[k] > max) { max = counts[k]; best = k; }
  if (max >= 2) contentLang.set(userId, best);
  return contentLang.get(userId) || candidate;
}

// Демо TTS в OGG/Opus (gTTS → MP3 → ffmpeg → OGG/Opus)
async function ttsToOgg(text, lang = "ru") {
  const tries = lang === "he" ? ["he","iw"] : (lang === "zh" ? ["zh-CN","zh-TW"] : [lang]);
  tries.push("en","ru");
  const mp3 = path.join(os.tmpdir(), `${Date.now()}_${Math.random().toString(36).slice(2)}.mp3`);
  const ogg = path.join(os.tmpdir(), `${Date.now()}_${Math.random().toString(36).slice(2)}.ogg`);
  let lastErr = null;
  for (const L of tries) {
    try {
      await new Promise((res, rej) => new gTTS(text, L).save(mp3, (e)=>e?rej(e):res()));
      await new Promise((res, rej) => ffmpeg(mp3)
        .audioCodec("libopus").audioBitrate("48k").audioChannels(1).audioFrequency(48000)
        .save(ogg).on("end",res).on("error",rej));
      try { fs.unlinkSync(mp3); } catch {}
      return ogg;
    } catch (e) { lastErr = e; }
  }
  try { fs.unlinkSync(mp3); } catch {}
  throw lastErr || new Error("TTS failed");
}

// Кнопки под ответом для голосовых и текстовых сообщений
function voiceInlineKb() {
  return Markup.inlineKeyboard([
    [Markup.button.callback("Показать расшифровку", "asr_show")],
    [Markup.button.callback("Озвучить ответ", "do_tts")],
    [Markup.button.callback("Скрыть", "v_close")]
  ]);
}

// Старт
bot.start(async (ctx) => {
  const uid = ctx.from.id;
  if (!uiLang.has(uid)) uiLang.set(uid, "ru");
  const L = uiLang.get(uid);
  await sendClean(ctx, tUI(L).hello, mainKb());
});

// Меню
bot.command("menu", async (ctx) => showInlineMenu(ctx));
bot.hears("Меню", async (ctx) => showInlineMenu(ctx));
bot.action("m_close", async (ctx) => {
  try { await ctx.editMessageReplyMarkup(); } catch {}
  await ctx.answerCbQuery("Закрыто");
});
bot.action("m_help", async (ctx) => {
  await ctx.answerCbQuery();
  await sendClean(ctx, "Подсказка: отправьте сообщение или короткое голосовое. Озвучка по кнопке под ответом, расшифровка по кнопке. Меню открывается по запросу и закрывается кнопкой.");
});
bot.action("m_profile", async (ctx) => {
  await ctx.answerCbQuery();
  const uid = ctx.from.id;
  const Lui = uiLang.get(uid) || "ru";
  const Lc  = contentLang.get(uid) || Lui;
  await sendClean(ctx, `Профиль\nКонтент-язык: ${Lc}\nИнтерфейс: ${Lui}\nОзвучка по кнопке: демо\nГолосовые: демо-ASR`);
});
bot.action("m_lang", async (ctx) => {
  await ctx.answerCbQuery();
  const kb = Markup.inlineKeyboard([
    [Markup.button.callback("Русский", "ui_ru"), Markup.button.callback("English", "ui_en"), Markup.button.callback("עברית", "ui_he")],
    [Markup.button.callback("Скрыть", "m_close")]
  ]);
  await sendClean(ctx, "Выберите язык интерфейса:", kb);
});
bot.action(["ui_ru","ui_en","ui_he"], async (ctx) => {
  const map = { ui_ru:"ru", ui_en:"en", ui_he:"he" };
  const newL = map[ctx.callbackQuery.data] || "ru";
  uiLang.set(ctx.from.id, newL);
  await ctx.answerCbQuery(tUI(newL).saved);
  try { await ctx.editMessageText(sanitizeOutput(tUI(newL).saved)); } catch {}
  await sendClean(ctx, tUI(newL).ready, buildInlineMenu());
});

// Текст: автоязык с гистерезисом, EN не выбираем на коротких
bot.on("text", async (ctx, next) => {
  const uid = ctx.from.id;
  if (!uiLang.has(uid)) uiLang.set(uid, "ru");
  const Lui = uiLang.get(uid);
  const txt = (ctx.message.text || "").trim();
  let cand = detectScriptLang(txt) || "en";
  if (cand === "en" && txt.length < 12) cand = contentLang.get(uid) || "ru";
  const stable = updateContentLang(uid, cand);
  const msg = {
    ru:"Кратко: понял запрос. Детали: отвечаю по-русски. Чек-лист: всё ок.",
    en:"Brief: got your request. Details: replying in English. Checklist: all good.",
    he:"תקציר: קיבלתי. פרטים: עונה בעברית. צ׳ק-ליסט: הכל בסדר."
  }[stable] || "Brief: got it.";
  const sent = await sendClean(ctx, msg, voiceInlineKb());
  const key = `${ctx.chat.id}:${sent.message_id}`;
  putWithTTL(msgTextCache, key, msg);
  return next && next();
});

// Голосовые и кружочки: анти-эхо, кнопки под ответом
bot.on(["voice","audio","video_note"], async (ctx) => {
  const uid = ctx.from.id;
  if (!uiLang.has(uid)) uiLang.set(uid, "ru");
  const Lui = uiLang.get(uid) || "ru";
  const Lc  = contentLang.get(uid) || Lui;

  // Демо-ASR: транскрипт-заменитель, реальное ASR подключим позже
  const transcript = {
    ru: "Демо-транскрипт: распознавание в эконом-режиме.",
    he: "תמליל הדגמה: זיהוי במצב חסכוני.",
    en: "Demo transcript: recognition in economy mode."
  }[Lc] || "Demo transcript.";

  const answer = {
    ru: "Кратко: получил голос и понял задачу. Детали: отвечу по делу без повтора вашей речи. Чек-лист: цель, ограничения, варианты, риски, следующий шаг.",
    he: "תקציר: קיבלתי קול והבנתי את הבקשה. פרטים: תשובה עניינית ללא חזרה על הדברים. צ׳ק-ליסט: מטרה, מגבלות, אפשרויות, סיכונים, צעד הבא.",
    en: "Brief: got your voice and understood the task. Details: answering to the point without echo. Checklist: goal, constraints, options, risks, next step."
  }[Lc] || "Brief: got your voice.";

  const sent = await sendClean(ctx, answer, voiceInlineKb());
  const key = `${ctx.chat.id}:${sent.message_id}`;
  putWithTTL(msgTextCache, key, answer);
  if (DEMO_ASR) putWithTTL(asrCache, key, transcript);
});

// Коллбеки под сообщениями: показать расшифровку, озвучить ответ, скрыть панель
bot.action("asr_show", async (ctx) => {
  await ctx.answerCbQuery();
  const chatId = ctx.chat.id;
  const msgId  = ctx.update.callback_query?.message?.message_id;
  const key = `${chatId}:${msgId}`;
  const tr = asrCache.get(key);
  if (!tr) return sendClean(ctx, "Транскрипт недоступен. Попробуйте ещё раз.");
  return sendClean(ctx, tr);
});
bot.action("do_tts", async (ctx) => {
  await ctx.answerCbQuery();
  if (!DEMO_TTS) return sendClean(ctx, "Озвучка временно недоступна.");
  const chatId = ctx.chat.id;
  const msgId  = ctx.update.callback_query?.message?.message_id;
  const key = `${chatId}:${msgId}`;
  const txt = msgTextCache.get(key);
  if (!txt) return sendClean(ctx, "Текст ответа не найден. Попросите бота ответить ещё раз.");
  const uid = ctx.from.id;
  const Lui = uiLang.get(uid) || "ru";
  const Lc  = contentLang.get(uid) || Lui;
  try {
    const ogg = await ttsToOgg(txt, Lc);
    return replyVoiceClean(ctx, ogg, tUI(Lui).ttsCaption);
  } catch {
    return sendClean(ctx, "Не удалось озвучить. Попробуйте ещё раз.");
  }
});
bot.action("v_close", async (ctx) => {
  try { await ctx.editMessageReplyMarkup(); } catch {}
  await ctx.answerCbQuery("Скрыто");
});

// Команды /start, /version
bot.command("version", async (ctx) => {
  await sendClean(ctx, "UNIVERSAL GPT-4o — HOTFIX7b-U10");
});

// Healthcheck + вебхук
app.get("/", (_, res) => res.status(200).send("OK"));
app.get(`/telegram/${SECRET}`, (_, res) => res.status(200).send("Webhook OK"));
app.get("/version", (_, res) => res.status(200).send("UNIVERSAL GPT-4o — HOTFIX7b-U10"));
app.post(`/telegram/${SECRET}`, (req, res) => {
  bot.handleUpdate(req.body, res).catch(() => res.sendStatus(200));
});

// Старт сервера и (если BASE задан) установка вебхука с нужными типами апдейтов
const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`Server on :${PORT}`);
  try {
    if (BASE) {
      const url = `${BASE}/telegram/${SECRET}`;
      await bot.telegram.setWebhook(url, {
        allowed_updates: ["message","callback_query"],
        secret_token: SECRET
      });
      console.log("Webhook set to:", url);
    } else {
      // Для локальной отладки можно использовать getUpdates (но не одновременно с вебхуком)
      // await bot.launch();
      console.log("BASE_URL не задан. Вебхук не установлен.");
    }
  } catch (e) {
    console.error("setWebhook error:", e.message);
  }
});

// Корректное завершение (если запускали bot.launch)
process.once("SIGINT", () => { try { bot.stop("SIGINT"); } catch {} process.exit(0); });
process.once("SIGTERM", () => { try { bot.stop("SIGTERM"); } catch {} process.exit(0); });
