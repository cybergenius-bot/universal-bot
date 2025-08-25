import os
import openai
from openai import AsyncOpenAI

openai.api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def ask_ai(prompt: str) -> str:
    try:
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Error: {e}"

async def ask_ai(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()
