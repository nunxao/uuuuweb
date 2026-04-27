import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
    Message, CallbackQuery
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import re

BOT_TOKEN = "ТВОЙ_ТОКЕН_СЮДА"
ADMIN_IDS = [123456789]

users = {}
waiting_queue = []
active_chats = {}
reports = {}
muted_users = {}
banned_users = set()

AD_PATTERNS = [
    r'https?://',
    r't\.me/',
    r'@\w+',
    r'купить',
    r'продам',
    r'заработ',
    r'подпиш',
    r'бесплатн',
    r'скидка',
]

class Registration(StatesGroup):
    waiting_circle = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_search_gender = State()

class InChat(StatesGroup):
    chatting = State()
    waiting_report_reason = State()

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# [вставь сюда все остальные функции из первого кода]

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
