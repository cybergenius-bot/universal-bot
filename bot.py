import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from config import TELEGRAM_TOKEN, OPENAI_API_KEY, OPENAI_MODEL
from db import get_user, decrement_messages, has_active_subscription
from openai import AsyncOpenAI
import os


# Инициализация OpenAI GPT-4o
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


logging.basicConfig(level=logging.INFO)


# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = await get_user(update.effective_user.id)
await update.message.reply_text(
f"Привет! У тебя {user['messages_left']} сообщений. После этого нужно оплатить тариф."
)


# Команда /invite
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
bot_username = (await context.bot.get_me()).username
link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
await update.message.reply_text(f"🎁 Поделись этой ссылкой с друзьями:\n{link}")


# Обработка обычных сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
logging.info("Получено сообщение: %s", update.message.text)
tg_id = update.effective_user.id
user = await get_user(tg_id)
subscribed = await has_active_subscription(tg_id)


if subscribed or user["messages_left"] > 0:
if not subscribed:
await decrement_messages(tg_id)


prompt = update.message.text
try:
completion = await openai_client.chat.completions.create(
model=OPENAI_MODEL,
messages=[
{
"role": "system",
"content": (
"Ты — GPT-4o, профессиональный универсальный ассистент. Ты отвечаешь на языке пользователя, будь то русский, английский, арабский и т.д."
" Отвечай глубоко, профессионально, понятно и без ограничений по темам."
" Ты умеешь писать код, тексты, научные и бизнес-работы, давать советы, объяснять, рассуждать."
)
},
{"role": "user", "content": prompt}
],
temperature=0.7
)
reply = completion.choices[0].message.content
await update.message.reply_text(reply)
except Exception as e:
logging.exception("Ошибка OpenAI")
await update.message.reply_text("❌ Ошибка при обращении к GPT.")
else:
keyboard = [
[InlineKeyboardButton("💡 20 ответов - $10", callback_data="buy_start")],
[InlineKeyboardButton("🧠 200 ответов - $30", callback_data="buy_standard")],
[InlineKeyboardButton("♾️ Безлимит - $50", callback_data="buy_premium")]
]
await update.message.reply_text("❌ У тебя закончились сообщения. Выбери тариф:", reply_markup=InlineKeyboardMarkup(keyboard))


# Запуск через Webhook
def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("invite", invite))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


port = int(os.environ.get("PORT", 8080))
url = os.environ.get("WEBHOOK_URL")
app.run_webhook(listen="0.0.0.0", port=port, webhook_url=f"{url}/bot{TELEGRAM_TOKEN}")


if __name__ == "__main__":
main()
