import os
from openai import OpenAI

# Ключ API (задать в Railway → Variables)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Клиент OpenAI (без proxies)
client = OpenAI(api_key=OPENAI_API_KEY)

def ask_ai(prompt: str) -> str:
    """
    Запрашивает ответ у ИИ.
    Возвращает текст ответа или заглушку при ошибке.
    """
    try:
        response = client.responses.create(
            model="gpt-4.1-mini",  # Можно gpt-4.1 или gpt-4o
            input=prompt,
            temperature=0.85,      # Живые ответы
            max_output_tokens=500
        )
        return response.output_text.strip()

    except Exception as e:
        print(f"[AI ERROR] {e}")  # Лог в Railway
        return "🤖 Упс, что-то пошло не так, но мы скоро продолжим!"
