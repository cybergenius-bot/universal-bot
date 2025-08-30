Проект: Универсальный Telegram‑бот (FastAPI + PTB) с GPT‑4o, Vision, Whisper, TTS, тарифами, PayPal.

1) Файлы в корне:
- bot.py
- requirements.txt
- Dockerfile
- Procfile (необязательно)
- .dockerignore
- .env.example
- README.md

2) Переменные в Railway → Variables:
- TELEGRAM_TOKEN, TELEGRAM_WEBHOOK_SECRET, BOT_USERNAME
- BASE_URL, PUBLIC_BASE_URL (ваш домен Railway https://<name>.up.railway.app)
- OPENAI_API_KEY, OPENAI_MODEL (например gpt-4o-mini)
- DATABASE_URL (Postgres) или временно sqlite строка
- PAYPAL_BASE (sandbox на тест), PAYPAL_CLIENT_ID, PAYPAL_SECRET, PAYPAL_WEBHOOK_ID
- Параметры планов: PLAN_*

3) Деплой на Railway:
- Service → Settings → Builder: Dockerfile
- Custom Start Command: можно оставить пустым (берётся из Dockerfile)
- Pre-deploy Command: пусто
- Redeploy

4) Проверка:
- Health: https://<ваш_домен>/health/live → 200 OK
- Webhook info (PowerShell):
  curl.exe -s "https://api.telegram.org/bot<ТОКЕН>/getWebhookInfo"
- (Опционально) Установить вебхук тем же секретом:
  curl.exe -s "https://api.telegram.org/bot<ТОКЕН>/setWebhook?url=https://<ваш_домен>/telegram&secret_token=<СЕКРЕТ>&allowed_updates=%5B%22message%22%2C%22callback_query%22%5D&max_connections=40&drop_pending_updates=true"

5) Тест в Telegram:
- /start → приветствие
- Текстовый запрос → LLM-ответ (длинные ответы режутся автоматически)
- “ответь голосом” в запросе → придёт аудио MP3
- Фото с подписью → Vision-ответ
- Голосовое → распознавание и ответ
- Видео/кружок → конспект
- /pricing → тарифы, /buy → кнопки PayPal (ссылка approve), оплата в Sandbox, webhook активирует тариф.
- /ref → персональная реф‑ссылка
- /exchange → партнёрские ссылки

Примечания:
- В проде reloader выключен (запуск через Gunicorn + UvicornWorker).
- Секрет вебхука должен совпадать в переменной TELEGRAM_WEBHOOK_SECRET и при setWebhook
