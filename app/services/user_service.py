import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("serve")

try:
    from bot import app as bot_app  # type: ignore
    app = bot_app
    logger.info("serve.py: import bot:app - OK")
except Exception as e:
    logger.exception("serve.py: failed to import bot:app, enabling fallback: %s", e)
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="fallback-serve")

    @app.get("/health/live")
    async def health_live():
        return JSONResponse({"status": "ok"})

    @app.get("/health/ready")
    async def health_ready():
        return JSONResponse({"status": "starting", "import_bot_app": False})
