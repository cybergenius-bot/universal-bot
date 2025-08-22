import os
import openai

openai.api_key = os.getenv("OPENAI_API_KEY")

async def ask_ai(prompt):
    response = openai.ChatCompletion.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}]
    )
    return response.choices[0].message.content.strip()