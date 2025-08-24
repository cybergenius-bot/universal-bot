import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from config import TELEGRAM_TOKEN, TARIFFS, OPENAI_API_KEY, OPENAI_MODEL
from db import get_user, decrement_messages, has_active_subscription
from openai import AsyncOpenAI
import os


openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)


logging.basicConfig(level=logging.INFO)


# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = await get_user(update.effective_user.id)
await update.message.reply_text(f"Привет! У тебя {user['messages_left']} сообщений. После этого нужно оплатить тариф.")


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
bot_username = (await context.bot.get_me()).username
link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
await update.message.reply_text(f"🎁 Поделись этой ссылкой с друзьями:\n{link}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
print("Получено сообщение:", update.message.text)
tg_id = update.effective_user.id
user = await get_user(tg_id)
subscribed = await has_active_subscription(tg_id)


if subscribed or user["messages_left"] > 0:
if not subscribed:
await decrement_messages(tg_id)


try:
completion = await openai_client.chat.completions.create(
model=OPENAI_MODEL,
messages=[
{"role": "system", "content": "Ты ассистент, помогай пользователю максимально подробно."},
{"role": "user", "content": update.message.text}
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
[InlineKeyboardButton(f"💡 20 ответов - $10", callback_data="buy_start")],
[InlineKeyboardButton(f"🧠 200 ответов - $30", callback_data="buy_standard")],
[InlineKeyboardButton(f"♾️ Безлимит - $50", callback_data="buy_premium")]
]
await update.message.reply_text("❌ У тебя закончились сообщения. Выбери тариф:", reply_markup=InlineKeyboardMarkup(keyboard))


# Main with Webhook
def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("invite", invite))
