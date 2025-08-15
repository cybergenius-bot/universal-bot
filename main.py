import os
import asyncio
from fastapi import FastAPI, Request
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

TOKEN = os.getenv("TOKEN")  # Должен быть ТОЛЬКО токен от BotFather
WEBHOOK_URL
