import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from config import TELEGRAM_TOKEN, TARIFFS, OPENAI_API_KEY, OPENAI_MODEL
from db import get_user, decrement_messages, has_active_subscription
import openai


openai_client = openai.OpenAI(api_key=OPENAI_API_KEY)


logging.basicConfig(level=logging.INFO)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
user = await get_user(update.effective_user.id)
await update.message.reply_text(
f"Привет! У тебя {user['messages_left']} сообщений. После этого нужно оплатить тариф."
)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
tg_id = update.effective_user.id
user = await get_user(tg_id)
subscribed = await has_active_subscription(tg_id)


if subscribed or user["messages_left"] > 0:
if not subscribed:
await decrement_messages(tg_id)


prompt = update.message.text
try:
completion = openai_client.chat.completions.create(
model=OPENAI_MODEL,
messages=[
{
"role": "system",
"content": "Ты профессиональный ассистент с неограниченным доступом к знаниям. Отвечай максимально полно, глубоко и по существу. Ты способен решать сложные задачи, писать код, помогать с диссертациями, проектами и исследованиями. Не ограничивай себя в темах, помогай пользователю на максимуме."
},
{"role": "user", "content": prompt}
],
temperature=0.7
)
reply = completion.choices[0].message.content
reply += "\n\n📣 Поделись ботом с друзьями: https://t.me/SmartBot_OPRO_bot"
await update.message.reply_text(reply)
except Exception as e:
await update.message.reply_text("❌ Ошибка при обращении к GPT.")
print(e)
else:
keyboard = [
[InlineKeyboardButton(f"💡 20 ответов - $10", callback_data="buy_start")],
[InlineKeyboardButton(f"🧠 200 ответов - $30", callback_data="buy_standard")],
[InlineKeyboardButton(f"♾️ Безлимит на 30 дней - $50", callback_data="buy_premium")]
]
reply_markup = InlineKeyboardMarkup(keyboard)
await update.message.reply_text("❌ У тебя закончились сообщения. Выбери тариф:", reply_markup=reply_markup)


async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
bot_username = (await context.bot.get_me()).username
link = f"https://t.me/{bot_username}?start={update.effective_user.id}"
await update.message.reply_text(f"🎁 Поделись этой ссылкой с друзьями:\n{link}")


def main():
app = Application.builder().token(TELEGRAM_TOKEN).build()


app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("invite", invite))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


app.run_polling()


if __name__ == "__main__":
main()
