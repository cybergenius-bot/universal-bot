import os
import uvicorn
from main import app  # импортируем приложение из main.py

if __name__ == "__main__":
    # Railway передает порт через переменную окружения PORT
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
