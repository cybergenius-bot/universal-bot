import express from "express";
import { Telegraf, Markup } from "telegraf";
import gTTS from "gtts";
import ffmpeg from "fluent-ffmpeg";
import ffmpegPath from "ffmpeg-static";
import fs from "fs";
import os from "os";
import path from "path";

// Конфигурация (переменные окружения на Railway)
const TOKEN  = process.env.TELEGRAM_BOT_TOKEN;             // обязательно
const SECRET = process.env.WEBHOOK_SECRET || "railway123"; // совпадает с путём вебхука
const BASE   = process.env.BASE_URL || "";                 // напр.: https://universal-bot-production.up.railway.app
if (!TOKEN) { console.error("ERROR: TELEGRAM_BOT_TOKEN не задан"); process.exit(1); }

// Инициализация
ffmpeg.setFfmpegPath(ffmpegPath);
const bot = new Telegraf(TOKEN);
const app = express();
app.use(express.json());

// Память пользователя (в проде — БД/Redis)
const uiLang = new Map();            // user_id -> язык интерфейса (ru|en|he)
const lastContentLangs = new Map();  // user_id -> последние 3 детекции
const contentLang = new Map();       // user_id -> стабильный язык контента

// Локализация интерфейса (фиксируется пользователем, по умолчанию RU)
function tUI(lang = "ru") {
  const t = {
    ru: { ready: "Готов. Выберите действие:", say: "Дай голосом", showTr: "Показать расшифровку", lang: "Сменить язык", mode: "Режим ответа", langChoose: "Выберите язык интерфейса:", langSaved: "Язык интерфейса сохранён.", ttsCaption: "Озвучено" },
    en: { ready: "Ready. Choose an action:", say: "Speak it", showTr: "Show transcript", lang: "Change language", mode: "Reply mode", langChoose: "Choose interface language:", langSaved: "Interface language saved.", ttsCaption: "Voiced" },
    he: { ready: "מוכן. בחרו פעולה:", say: "השמע בקול", showTr: "הצג תמלול", lang: "החלפת שפה", mode: "מצב תגובה", langChoose: "בחרו שפת ממשק:", langSaved: "שפת הממשק נשמרה.", ttsCaption: "הוקרא" }
  };
  return t[lang] || t.ru;
}
function mainKb(lang = "ru") {
  const t = tUI(lang);
  return Markup.keyboard([[t.say, t.showTr],[t.lang, t.mode]]).resize();
}

// Детект языка контента (без «скачков»)
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

// TTS с фолбэками → OGG/Opus
async function ttsToOgg(text, lang = "ru") {
  const tries = lang === "he" ? ["he","iw"] : (lang === "zh" ? ["zh-CN","zh-TW"] : [lang]);
  tries.push("en","ru");
  const mp3 = path.join(os.tmpdir(), `${Date.now()}.mp3`);
  const ogg = path.join(os.tmpdir(), `${Date.now()+1}.ogg`);
  let lastErr = null;
  for (const L of tries) {
    try {
      await new Promise((res, rej) => new gTTS(text, L).save(mp3, (e)=>e?rej(e):res()));
      await new Promise((res, rej) => ffmpeg(mp3).audioCodec("libopus").audioBitrate("48k").audioChannels(1).audioFrequency(48000).save(ogg).on("end",res).on("error",rej));
      return ogg;
    } catch(e){ lastErr = e; }
  }
  throw lastErr || new Error("TTS failed");
}

// Хендлеры
bot.start(async (ctx) => {
  const uid = ctx.from.id;
  if (!uiLang.has(uid)) uiLang.set(uid, "ru");
  const L = uiLang.get(uid);
  await ctx.reply(tUI(L).ready, mainKb(L));
});
bot.hears([tUI("ru").lang, tUI("en").lang, tUI("he").lang], async (ctx) => {
  const L = uiLang.get(ctx.from.id) || "ru";
  const t = tUI(L);
  await ctx.reply(t.langChoose, Markup.inlineKeyboard([
    [Markup.button.callback("Русский","ui_ru"), Markup.button.callback("English","ui_en")],
    [Markup.button.callback("עברית","ui_he")]
  ]));
});
bot.action(["ui_ru","ui_en","ui_he"], async (ctx) => {
  const map = { ui_ru:"ru", ui_en:"en", ui_he:"he" };
  const newL = map[ctx.callbackQuery.data] || "ru";
  uiLang.set(ctx.from.id, newL);
  await ctx.answerCbQuery(tUI(newL).langSaved);
  await ctx.editMessageText(tUI(newL).langSaved);
  await ctx.reply(tUI(newL).ready, mainKb(newL));
});
bot.hears([tUI("ru").say, tUI("en").say, tUI("he").say], async (ctx) => {
  const uid = ctx.from.id;
  const Lui = uiLang.get(uid) || "ru";
  const Lc  = contentLang.get(uid) || "ru";
  const demo = {
    ru:"Озвучка: Сохраняйте спокойствие и продолжайте. Это демо‑голос.",
    en:"Voice: Keep calm and carry on. This is a demo voice.",
    he:"קול: שמרו על קור רוח והמשיכו. זה קול הדגמה.",
    ja:"音声: 落ち着いて、前に進みましょう。これはデモ音声です。",
    ar:"صوت: تحلَّ بالهدوء وواصل. هذا صوت تجريبي."
  };
  const text = demo[Lc] || demo.ru;
  try {
    const ogg = await ttsToOgg(text, Lc);
    await ctx.replyWithVoice({ source: fs.createReadStream(ogg) }, { caption: tUI(Lui).ttsCaption });
  } catch {
    await ctx.reply("Не удалось озвучить. Попробуйте ещё раз.");
  }
});
bot.on("text", async (ctx, next) => {
  const uid = ctx.from.id;
  if (!uiLang.has(uid)) uiLang.set(uid, "ru");
  const Lui = uiLang.get(uid);
  const txt = (ctx.message.text || "").trim();
  let cand = detectScriptLang(txt) || "en";
  if (cand === "en" && txt.length < 12) cand = contentLang.get(uid) || "ru";
  const stable = updateContentLang(uid, cand);
  const msg = {
    ru:"Краткое резюме: понял запрос. Детали: отвечаю по‑русски. Чек‑лист: всё ок.",
    en:"Summary: got your request. Details: replying in English. Checklist: all good.",
    he:"תקציר: קיבלתי. פרטים: עונה בעברית. צ׳ק‑ליסט: הכל בסדר.",
    ja:"要約: 了解しました。詳細: 日本語で回答します。チェック: OKです。",
    ar:"ملخص: تم الاستلام. التفاصيل: سأرد بالعربية. قائمة التحقق: تمام."
  };
  await ctx.reply(msg[stable] || msg.ru, mainKb(Lui));
  return next && next();
});
bot.on("voice", async (ctx) => {
  const uid = ctx.from.id;
  const Lui = uiLang.get(uid) || "ru";
  const Lc  = contentLang.get(uid) || Lui;
  const text = {
    ru:"Краткое резюме: запрос принят. Детали: отвечаю по сути без повтора. Чек‑лист: уточним цель и следующий шаг.",
    en:"Summary: received. Details: answering to the point, no echo. Checklist: clarify goal and next step.",
    he:"תקציר: התקבל. פרטים: תשובה עניינית ללא חזרה. צ׳ק‑ליסט: נחדד מטרה וצעד הבא."
  }[Lc] || "Summary: received. I will answer to the point.";
  await ctx.reply(text);
  try {
    const ogg = await ttsToOgg(text, Lc);
    await ctx.replyWithVoice({ source: fs.createReadStream(ogg) }, { caption: tUI(Lui).ttsCaption });
  } catch {}
});

// Healthcheck + вебхук
app.get("/", (_, res) => res.status(200).send("OK"));
app.get(`/telegram/${SECRET}`, (_, res) => res.status(200).send("Webhook OK"));
app.post(`/telegram/${SECRET}`, (req, res) => {
  bot.handleUpdate(req.body, res).catch(() => res.sendStatus(200));
});

// Старт сервера и (если BASE задан) установка вебхука
const PORT = process.env.PORT || 3000;
app.listen(PORT, async () => {
  console.log(`Server on :${PORT}`);
  if (BASE) {
    const url = `${BASE}/telegram/${SECRET}`;
    try {
      await bot.telegram.setWebhook(url);
      console.log("Webhook set to:", url);
    } catch (e) {
      console.error("setWebhook error:", e.message);
    }
  }
});
