/**
 * SmartPro 24/7 (U10j-Node)
 * — Без доменных заготовок. Универсальный промпт: модель сама определяет намерение (рецепт/страна/бизнес/иное)
 *   и подбирает формат ответа (рецептам — граммы/мл/температуры/шаги; аналитике — структура; и т. д.).
 * — По умолчанию одна Reply‑кнопка «Меню». По нажатию — разворачивается большая клавиатура (без инлайнов):
 *   Коротко / Средне / Глубоко / Голос + дубли /start /menu /help /pay /ref /version.
 *   После выбора режимов — клавиатура сворачивается обратно к одной кнопке «Меню».
 * — Длинные ответы одним сообщением. Голосовые распознаются (Whisper при OPENAI_API_KEY). TTS по кнопке «Голос».
 * — Вебхук асинхронный, секрет в заголовке x-telegram-bot-api-secret-token. Маршруты: /version, /telegram/railway123.
 *
 * ENV:
 *   BOT_TOKEN (required)
 *   SECRET_TOKEN=railway123 (required; совпадает с secret_token при setWebhook)
 *   OPENAI_API_KEY (optional; для профессиональных ответов, ASR и TTS)
 *   PRO_MIN_WORDS=800 (optional, базовый deep)
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
const MAX_CHARS = 3900; // запас до лимита 4096

if (!BOT_TOKEN) {
  console.error('ERROR: BOT_TOKEN is missing');
  process.exit(1);
}

const bot = new Telegraf(BOT_TOKEN);
bot.webhookReply = false; // важно: не отвечаем в HTTP вебхука

// ——— Клавиатуры (без инлайнов) ———
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

// ——— Команды ———
const BOT_COMMANDS = [
  { command: 'start', description: 'Запуск и краткая справка' },
  { command: 'menu', description: 'Меню и настройки' },
  { command: 'help', description: 'Помощь и правила ввода' },
  { command: 'pay', description: 'Тарифы и оплата' },
  { command: 'ref', description: 'Реферальная ссылка' },
  { command: 'version', description: 'Версия сборки' },
