import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# --- SOZLAMALAR ---
API_TOKEN = '8399783426:AAHyEHTD364aYa5uiniKwg6SuNq2Ign8QjU'
ADMIN_ID = 2085230699  # O'zingizning Telegram ID raqamingiz
CHANNELS = ["@NuroTaxi"]  # Majburiy a'zolik kanali (bot admin bo'lishi shart)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- RENDER HEALTH CHECK ---
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000)
    await site.start()

# --- DATABASE FUNKSIYALARI ---
def init_db():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, role TEXT, phone TEXT, username TEXT)''')
    conn.commit()
    conn.close()

def save_user(user_id, role, phone, username):
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?, ?)", (user_id, role, phone, username))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role, phone, username FROM users WHERE user_id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return res

def get_all_users():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    res = cursor.fetchall()
    conn.close()
    return [r[0] for r in res]

# --- MAJBURIY A'ZOLIK TEKSHIRUVI ---
async def check_sub(user_id):
    for channel in CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status == 'left':
                return False
        except Exception:
            return False
    return True

# --- STATES ---
class Registration(StatesGroup):
    role = State()
    phone = State()

class Order(StatesGroup):
    route = State()
    passengers = State()
    client_phone = State()

class AdminPanel(StatesGroup):
    broadcast_msg = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    user = get_user(user_id)
    if user and user[0] == 'taksist':
        markup.add("Adminga murojaat ✍️")
    else:
        markup.add("Safarni rejalashtirish 🗓", "Adminga xabar ✍️")
    
    if user_id == ADMIN_ID:
        markup.add("📊 Statistika", "📢 Reklama yuborish")
    return markup

# --- HANDLERS ---

@dp.message_handler(commands=['start'], state='*')
async def cmd_start(message: types.Message, state: FSMContext):
    await state.finish()
    
    if not await check_sub(message.from_user.id):
        markup = InlineKeyboardMarkup()
        for ch in CHANNELS:
            markup.add(InlineKeyboardButton("Kanalga a'zo bo'lish ➕", url=f"https://t.me/{ch.replace('@','')}"))
        markup.add(InlineKeyboardButton("Tekshirish ✅", callback_data="check_subs"))
        return await message.answer("Botdan foydalanish uchun kanalimizga a'zo bo'ling:", reply_markup=markup)

    user = get_user(message.from_user.id)
    if user:
        await message.answer("Xush kelibsiz!", reply_markup=main_menu(message.from_user.id))
    else:
        markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("Taksist 🚖", "Yo'lovchi 🙋‍♂️")
        await message.answer("Kim sifatida ro'yxatdan o'tasiz?", reply_markup=markup)
        await Registration.role.set()

@dp.callback_query_handler(text="check_subs")
async def check_callback(call: types.CallbackQuery, state: FSMContext):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await cmd_start(call.message, state)
    else:
        await call.answer("Siz hali a'zo emassiz!", show_alert=True)

@dp.message_handler(state=Registration.role)
async def set_role(message: types.Message, state: FSMContext):
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(role=role)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True).add(KeyboardButton("Kontakt 📱", request_contact=True))
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=markup)
    await Registration.phone.set()

@dp.message_handler(content_types=['contact'], state=Registration.phone)
async def set_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = f"@{message.from_user.username}" if message.from_user.username else "Yo'q"
    save_user(message.from_user.id, data['role'], message.contact.phone_number, username)
    await message.answer("Muvaffaqiyatli ro'yxatdan o'tdingiz!", reply_markup=main_menu(message.from_user.id))
    await state.finish()

# --- ADMIN PANEL FUNKSIYALARI ---
@dp.message_handler(lambda m: m.text == "📊 Statistika" and m.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    count = len(get_all_users())
    await message.answer(f"📊 Bot foydalanuvchilari soni: {count} ta")

@dp.message_handler(lambda m: m.text == "📢 Reklama yuborish" and m.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("🚫 Bekor qilish"))
    await AdminPanel.broadcast_msg.set()

@dp.message_handler(state=AdminPanel.broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.finish()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(ADMIN_ID))
    
    users = get_all_users()
    count = 0
    await message.answer("Xabar yuborish boshlandi...")
    for u_id in users:
        try:
            await bot.send_message(u_id, message.text)
            count += 1
            await asyncio.sleep(0.05) # Telegram bloklab qo'ymasligi uchun
        except: pass
    
    await message.answer(f"Xabar {count} ta foydalanuvchiga yetkazildi.", reply_markup=main_menu(ADMIN_ID))
    await state.finish()

# --- SAFAR VA ADMINGA MUROJAAT (Avvalgi mustahkam mantiq asosida) ---
# ... (Bu yerda avvalgi kodimizdagi Order va AdminContact handlerlari joylashadi) ...

if __name__ == '__main__':
    init_db()
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    executor.start_polling(dp, skip_updates=True)
