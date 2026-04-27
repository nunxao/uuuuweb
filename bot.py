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
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
import re

# ========== НАСТРОЙКИ ==========
BOT_TOKEN = "8618184200:AAEre1ANM53LzxtG1knwYIuEUe2jlGwEC9Q"
ADMIN_IDS = [7938213817]
WEBHOOK_HOST = "https://enjjoy.pythonanywhere.com"
WEBHOOK_PATH = "/webhook"

# ========== ИНИЦИАЛИЗАЦИЯ ==========
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ========== ХРАНИЛИЩА ==========
users = {}
waiting_queue = []
active_chats = {}
reports = {}
muted_users = {}
banned_users = set()

# ========== РЕКЛАМНЫЕ ПАТТЕРНЫ ==========
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
    r'акци[ия]',
    r'кредит',
    r'микрозайм',
    r'ставк[аи]',
    r'слив',
    r'интим',
    r'взросл',
    r'18\+',
    r'чат',
    r'канал',
    r'приват',
    r'го[у]?лос[у]?',
    r'опрос',
]

# ========== СОСТОЯНИЯ FSM ==========
class Registration(StatesGroup):
    waiting_circle = State()
    waiting_gender = State()
    waiting_age = State()
    waiting_search_gender = State()

class InChat(StatesGroup):
    chatting = State()
    waiting_report_reason = State()

# ========== КЛАВИАТУРЫ ==========
def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔍 Искать собеседника")],
            [KeyboardButton(text="📊 Мой профиль"), KeyboardButton(text="🔄 Сменить пол")],
            [KeyboardButton(text="ℹ️ Помощь")],
        ],
        resize_keyboard=True
    )

def stop_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏹ Остановить диалог", callback_data="stop_chat"),
            InlineKeyboardButton(text="📸 Скрин собеседника", callback_data="screenshot_partner"),
        ],
        [
            InlineKeyboardButton(text="📞 Обменяться контактами", callback_data="exchange_contacts"),
            InlineKeyboardButton(text="🚨 Репорт", callback_data="report_user"),
        ],
    ])

# ========== ПРОВЕРКА РЕКЛАМЫ ==========
def check_ad(text: str) -> bool:
    text_lower = text.lower()
    for pattern in AD_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

# ========== ПРОВЕРКА МУТА ==========
def is_muted(user_id: int) -> bool:
    if user_id in muted_users:
        if datetime.now() < muted_users[user_id]:
            return True
        else:
            del muted_users[user_id]
    return False

# ========== СТАРТ ==========
@dp.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id in banned_users:
        await message.answer("⛔ Вы забанены.")
        return
    if user_id in users and users[user_id].get("кружок_пройден"):
        await message.answer("👋 С возвращением! Используй меню.", reply_markup=main_menu())
        return
    await message.answer(
        "👋 Добро пожаловать в анонимный чат!\n\n"
        "🎯 Сначала подтверди свой пол.\n"
        "📸 Отправь кружок (видеосообщение), где видно твоё лицо.\n"
        "⏱ У тебя 5 минут."
    )
    await state.set_state(Registration.waiting_circle)

# ========== ПОЛУЧЕНИЕ КРУЖКА ==========
@dp.message(Registration.waiting_circle, F.video_note)
async def receive_circle(message: Message, state: FSMContext):
    user_id = message.from_user.id
    await message.answer(
        "✅ Кружок получен!\n\n👤 Теперь выбери свой пол:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🙋‍♀️ Девушка", callback_data="gender_female"),
                InlineKeyboardButton(text="🙋‍♂️ Парень", callback_data="gender_male"),
            ]
        ])
    )
    await state.set_state(Registration.waiting_gender)

@dp.message(Registration.waiting_circle)
async def wrong_circle(message: Message):
    await message.answer("❌ Нужен именно кружок (видеосообщение). Попробуй ещё раз.")

# ========== ВЫБОР ПОЛА ==========
@dp.callback_query(Registration.waiting_gender, F.data.startswith("gender_"))
async def choose_gender(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    gender = "female" if callback.data == "gender_female" else "male"
    if user_id not in users:
        users[user_id] = {}
    users[user_id]["пол"] = gender
    await callback.message.edit_text("✅ Пол сохранён.")
    await callback.message.answer("🎂 Сколько тебе лет? (от 14 до 80)\nПросто напиши число.")
    await state.set_state(Registration.waiting_age)

# ========== ВОЗРАСТ ==========
@dp.message(Registration.waiting_age, F.text.regexp(r'^\d+$'))
async def receive_age(message: Message, state: FSMContext):
    user_id = message.from_user.id
    age = int(message.text)
    if 14 <= age <= 80:
        users[user_id]["возраст"] = age
        await message.answer(
            "🔎 Кого хочешь найти?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="🙋‍♀️ Девушку", callback_data="search_female"),
                    InlineKeyboardButton(text="🙋‍♂️ Парня", callback_data="search_male"),
                    InlineKeyboardButton(text="👥 Без разницы", callback_data="search_any"),
                ]
            ])
        )
        await state.set_state(Registration.waiting_search_gender)
    else:
        await message.answer("❌ Возраст от 14 до 80. Попробуй ещё раз.")

@dp.message(Registration.waiting_age)
async def wrong_age(message: Message):
    await message.answer("❌ Напиши число (14-80).")

# ========== КОГО ИЩЕТ ==========
@dp.callback_query(Registration.waiting_search_gender, F.data.startswith("search_"))
async def choose_search(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    search_map = {
        "search_female": "female",
        "search_male": "male",
        "search_any": "any",
    }
    users[user_id]["ищет"] = search_map[callback.data]
    users[user_id]["кружок_пройден"] = True
    await callback.message.edit_text("✅ Настройки сохранены!")
    await callback.message.answer(
        "🎉 Ты успешно зарегистрирован!\n\n🔍 Жми «Искать собеседника», чтобы начать.",
        reply_markup=main_menu()
    )
    await state.clear()

# ========== ПОИСК СОБЕСЕДНИКА ==========
@dp.message(F.text == "🔍 Искать собеседника")
async def search_partner(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users or not users[user_id].get("кружок_пройден"):
        await message.answer("❌ Сначала заверши регистрацию. /start")
        return
    if is_muted(user_id):
        remaining = (muted_users[user_id] - datetime.now()).seconds
        await message.answer(f"🔇 Ты в муте ещё {remaining // 60} мин {remaining % 60} сек.")
        return
    if user_id in active_chats:
        await message.answer("❌ Ты уже в диалоге. Сначала останови его.")
        return
    if user_id in waiting_queue:
        await message.answer("⏳ Ты уже в очереди. Жди.")
        return

    user = users[user_id]
    for partner_id in waiting_queue:
        partner = users.get(partner_id)
        if not partner:
            waiting_queue.remove(partner_id)
            continue
        match = False
        if user["ищет"] == "any" or partner["ищет"] == "any":
            match = True
        elif user["ищет"] == partner["пол"] and partner["ищет"] == user["пол"]:
            match = True
        if match:
            waiting_queue.remove(partner_id)
            active_chats[user_id] = partner_id
            active_chats[partner_id] = user_id
            await message.answer(
                "✅ Мы нашли тебе собеседника!\n\n"
                f"👤 Пол: {'Девушка' if partner['пол'] == 'female' else 'Парень'}\n"
                f"🎂 Возраст: {partner['возраст']}\n\nОбщайтесь! Твои сообщения анонимны.",
                reply_markup=stop_keyboard()
            )
            await bot.send_message(
                partner_id,
                "✅ Мы нашли тебе собеседника!\n\n"
                f"👤 Пол: {'Девушка' if user['пол'] == 'female' else 'Парень'}\n"
                f"🎂 Возраст: {user['возраст']}\n\nОбщайтесь! Твои сообщения анонимны.",
                reply_markup=stop_keyboard()
            )
            return

    waiting_queue.append(user_id)
    await message.answer("⏳ Пока никого нет. Ты в очереди. Жди.")
    await state.set_state(InChat.chatting)

# ========== ПЕРЕСЫЛКА СООБЩЕНИЙ ==========
@dp.message(InChat.chatting)
async def chat_forward(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in active_chats:
        await message.answer("❌ Ты не в диалоге. Нажми «Искать собеседника».")
        await state.clear()
        return
    if is_muted(user_id):
        return
    text = message.text or message.caption or ""
    if check_ad(text):
        muted_users[user_id] = datetime.now() + timedelta(hours=1)
        await message.answer("🔇 Ты отмучен на 1 час за рекламу. Диалог остановлен.")
        partner_id = active_chats.pop(user_id, None)
        if partner_id:
            active_chats.pop(partner_id, None)
            await bot.send_message(partner_id, "⏹ Собеседник остановил диалог.")
        await state.clear()
        return
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⏹ Стоп", callback_data="stop_chat"),
            InlineKeyboardButton(text="📸 Скрин", callback_data="screenshot_partner"),
        ]
    ])
    partner_id = active_chats[user_id]
    await message.copy_to(partner_id, reply_markup=keyboard)

# ========== ОСТАНОВКА ДИАЛОГА ==========
@dp.callback_query(F.data == "stop_chat")
async def stop_chat(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    partner_id = active_chats.pop(user_id, None)
    if partner_id:
        active_chats.pop(partner_id, None)
        await bot.send_message(partner_id, "⏹ Собеседник остановил диалог.", reply_markup=main_menu())
    await callback.message.edit_text("⏹ Диалог остановлен.")
    await callback.message.answer("Главное меню:", reply_markup=main_menu())
    await state.clear()

# ========== СКРИН СОБЕСЕДНИКА ==========
@dp.callback_query(F.data == "screenshot_partner")
async def screenshot_partner(callback: CallbackQuery):
    user_id = callback.from_user.id
    partner_id = active_chats.get(user_id)
    if not partner_id:
        await callback.answer("❌ Нет активного диалога.", show_alert=True)
        return
    partner = users.get(partner_id, {})
    info = (
        "📸 ИНФОРМАЦИЯ О СОБЕСЕДНИКЕ\n"
        f"👤 Пол: {'Девушка' if partner.get('пол') == 'female' else 'Парень'}\n"
        f"🎂 Возраст: {partner.get('возраст', 'неизвестно')}\n"
        f"🆔 ID: {partner_id}\n⏱ В чате с: сейчас"
    )
    await callback.message.answer(info)
    await callback.answer("✅ Информация отправлена в чат.", show_alert=True)

# ========== ОБМЕН КОНТАКТАМИ ==========
@dp.callback_query(F.data == "exchange_contacts")
async def exchange_contacts(callback: CallbackQuery):
    user_id = callback.from_user.id
    partner_id = active_chats.get(user_id)
    if not partner_id:
        await callback.answer("❌ Нет активного диалога.", show_alert=True)
        return
    user = users.get(user_id, {})
    user_info = (
        "📞 ЗАПРОС НА ОБМЕН КОНТАКТАМИ\n"
        f"От: {'Девушка' if user.get('пол') == 'female' else 'Парень'}, {user.get('возраст')} лет\n"
        "Согласен обменяться контактами?"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"accept_exchange_{user_id}"),
            InlineKeyboardButton(text="❌ Нет", callback_data="decline_exchange"),
        ]
    ])
    await bot.send_message(partner_id, user_info, reply_markup=keyboard)
    await callback.answer("✅ Запрос отправлен.", show_alert=True)

@dp.callback_query(F.data.startswith("accept_exchange_"))
async def accept_exchange(callback: CallbackQuery):
    user_id = callback.from_user.id
    requester_id = int(callback.data.split("_")[-1])
    try:
        requester_chat = await bot.get_chat(requester_id)
        requester_contact = f"@{requester_chat.username}" if requester_chat.username else f"tg://user?id={requester_id}"
    except:
        requester_contact = f"tg://user?id={requester_id}"
    user_contact = f"@{callback.from_user.username}" if callback.from_user.username else f"tg://user?id={user_id}"
    await callback.message.edit_text(f"✅ Контакты:\nТвой: {user_contact}\nСобеседник: {requester_contact}")
    await bot.send_message(requester_id, f"✅ Контакты:\nТвой: {requester_contact}\nСобеседник: {user_contact}")

@dp.callback_query(F.data == "decline_exchange")
async def decline_exchange(callback: CallbackQuery):
    await callback.message.edit_text("❌ Обмен контактами отклонён.")

# ========== РЕПОРТ ==========
@dp.callback_query(F.data == "report_user")
async def report_user(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    partner_id = active_chats.get(user_id)
    if not partner_id:
        await callback.answer("❌ Нет активного диалога.", show_alert=True)
        return
    await callback.message.answer("🚨 Напиши причину жалобы (одно сообщение).\nАдминистрация рассмотрит.")
    await state.set_state(InChat.waiting_report_reason)

@dp.message(InChat.waiting_report_reason)
async def receive_report(message: Message, state: FSMContext):
    user_id = message.from_user.id
    partner_id = active_chats.get(user_id)
    if not partner_id:
        await message.answer("❌ Диалог уже завершён.")
        await state.clear()
        return
    report_text = f"🚨 РЕПОРТ\nОт: {user_id}\nНа: {partner_id}\nПричина: {message.text}"
    for admin_id in ADMIN_IDS:
        await bot.send_message(admin_id, report_text)
    await message.answer("✅ Жалоба отправлена администрации.")
    await state.clear()

# ========== ПРОФИЛЬ ==========
@dp.message(F.text == "📊 Мой профиль")
async def show_profile(message: Message):
    user_id = message.from_user.id
    user = users.get(user_id, {})
    if not user.get("кружок_пройден"):
        await message.answer("❌ Сначала зарегистрируйся. /start")
        return
    text = (
        "📊 ТВОЙ ПРОФИЛЬ\n"
        f"👤 Пол: {'Девушка' if user['пол'] == 'female' else 'Парень'}\n"
        f"🎂 Возраст: {user['возраст']}\n"
        f"🔎 Ищешь: {'Девушку' if user['ищет'] == 'female' else 'Парня' if user['ищет'] == 'male' else 'Без разницы'}\n"
        f"🆔 Твой ID: {user_id}"
    )
    await message.answer(text)

# ========== СМЕНА ПОЛА ==========
@dp.message(F.text == "🔄 Сменить пол")
async def change_gender(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("/start")
        return
    await message.answer(
        "👤 Выбери новый пол:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🙋‍♀️ Девушка", callback_data="change_female"),
                InlineKeyboardButton(text="🙋‍♂️ Парень", callback_data="change_male"),
            ]
        ])
    )

@dp.callback_query(F.data.startswith("change_"))
async def confirm_change_gender(callback: CallbackQuery):
    user_id = callback.from_user.id
    new_gender = "female" if callback.data == "change_female" else "male"
    users[user_id]["пол"] = new_gender
    await callback.message.edit_text(f"✅ Пол изменён на {'Девушка' if new_gender == 'female' else 'Парень'}.")

# ========== WEBHOOK НАСТРОЙКА ==========
async def set_webhook():
    await bot.set_webhook(url=WEBHOOK_HOST + WEBHOOK_PATH)

async def on_startup(app):
    await set_webhook()
    logging.info("Webhook установлен")

async def on_shutdown(app):
    await bot.delete_webhook()
    logging.info("Webhook удалён")

# ========== ЗАПУСК ==========
def main():
    logging.basicConfig(level=logging.INFO)
    app = web.Application()
    webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot)
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)
    web.run_app(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
    
