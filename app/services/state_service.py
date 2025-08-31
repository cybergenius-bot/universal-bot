import logging
from importlib import import_module

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("serve")

app = None
errors = []
for mod in ["bot", "main.bot", "src.bot", "app.bot"]:
    try:
        m = import_module(mod)
        app = getattr(m, "app")
        logger.info("serve.py: import %s:app - OK", mod)
        break
    except Exception as e:
        errors.append(f"{mod}: {e}")

if app is None:
    logger.error("serve.py: failed to import bot:app. Tried: %s", "; ".join(errors))
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    app = FastAPI(title="fallback-serve")

    @app.get("/health/live")
    async def health_live():
        return JSONResponse({"status": "ok"})

    @app.get("/health/ready")
    async def health_ready():
        return JSONResponse({"status": "starting", "import_bot_app": False, "errors": errors})
