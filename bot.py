import logging
from fastapi.responses import JSONResponse
import traceback

logger = logging.getLogger("bot_logger")
logging.basicConfig(level=logging.INFO)

@app.post("/telegram")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        logger.info(f"Webhook received: {data}")
        update = Update.de_json(data, bot)
        await application.process_update(update)
        return {"ok": True}
    except Exception as e:
        tb = traceback.format_exc()
        logger.error(f"Error in webhook processing: {e}\n{tb}")
        return JSONResponse(status_code=200, content={"ok": True})

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    logger.info(f"Handling message from {user_id}: \"{text}\"")
    await update.message.reply_text("Я точно сейчас тебе отвечу — WebHook работает!")

application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
