import asyncio
import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiohttp import web

# --- SOZLAMALAR ---
API_TOKEN = '8399783426:AAHyEHTD364aYa5uiniKwg6SuNq2Ign8QjU'
ADMIN_ID = 2085230699  # O'zingizning Telegram ID raqamingiz

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- DATABASE FUNKSIYALARI ---
def init_db():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, role TEXT, phone TEXT, username TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    cursor.execute("INSERT OR IGNORE INTO settings VALUES ('channel', '@NuroTaxi')")
    conn.commit()
    conn.close()

def get_setting(key):
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    res = cursor.fetchone()
    conn.close()
    return res[0] if res else "@NuroTaxi"

def update_setting(key, value):
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
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

# --- STATES ---
class Registration(StatesGroup):
    role = State()
    phone = State()

class Order(StatesGroup):
    route = State()
    passengers = State()
    travel_time = State()  # Safar vaqti qo'shildi
    client_phone = State()

class AdminStates(StatesGroup):
    broadcast_msg = State()
    new_channel = State()

class AdminContact(StatesGroup):
    waiting_msg = State()

# --- KLAVIATURALAR ---
def main_menu(user_id):
    kb = []
    user = get_user(user_id)
    if user and user[0] == 'taksist':
        kb.append([KeyboardButton(text="Adminga murojaat ✍️")])
    else:
        kb.append([KeyboardButton(text="Safarni rejalashtirish 🗓")])
        kb.append([KeyboardButton(text="Adminga xabar ✍️")])
    
    if user_id == ADMIN_ID:
        kb.append([KeyboardButton(text="📊 Statistika"), KeyboardButton(text="📢 Reklama")])
        kb.append([KeyboardButton(text="⚙️ Kanalni sozlash")])
    
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- MAJBURIY A'ZOLIK TEKSHIRUVI ---
async def check_sub(user_id):
    channel = get_setting('channel')
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        if member.status in ['left', 'kicked']:
            return False
    except:
        return False
    return True

# --- RENDER/RAILWAY HEALTH CHECK ---
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- HANDLERS ---
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    channel = get_setting('channel')
    
    if not await check_sub(message.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Kanalga a'zo bo'lish ➕", url=f"https://t.me/{channel.replace('@','')}")],
            [InlineKeyboardButton(text="Tekshirish ✅", callback_data="check_subs")]
        ])
        return await message.answer(f"Botdan foydalanish uchun {channel} kanaliga a'zo bo'ling:", reply_markup=kb)

    user = get_user(message.from_user.id)
    if user:
        await message.answer("Xush kelibsiz!", reply_markup=main_menu(message.from_user.id))
    else:
        kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="Taksist 🚖"), KeyboardButton(text="Yo'lovchi 🙋‍♂️")]
        ], resize_keyboard=True, one_time_keyboard=True)
        await message.answer("Kim sifatida ro'yxatdan o'tasiz?", reply_markup=kb)
        await state.set_state(Registration.role)

@dp.callback_query(F.data == "check_subs")
async def check_callback(call: types.CallbackQuery, state: FSMContext):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await cmd_start(call.message, state)
    else:
        await call.answer("Siz hali a'zo emassiz!", show_alert=True)

# --- RO'YXATDAN O'TISH ---
@dp.message(Registration.role)
async def set_role(message: types.Message, state: FSMContext):
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(role=role)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Kontakt 📱", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=kb)
    await state.set_state(Registration.phone)

@dp.message(Registration.phone, F.contact)
async def set_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    username = f"@{message.from_user.username}" if message.from_user.username else "Yo'q"
    save_user(message.from_user.id, data['role'], message.contact.phone_number, username)
    await message.answer("Muvaffaqiyatli ro'yxatdan o'tdingiz!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- SAFAR REJALASHTIRISH ---
@dp.message(F.text == "Safarni rejalashtirish 🗓")
async def start_order(message: types.Message, state: FSMContext):
    await message.answer("Qayerdan qayerga bormoqchisiz?\n(Masalan: Toshkent -> Samarqand)")
    await state.set_state(Order.route)

@dp.message(Order.route)
async def process_route(message: types.Message, state: FSMContext):
    await state.update_data(route=message.text)
    await message.answer("Nechta yo'lovchi? (Masalan: 3 kishi)")
    await state.set_state(Order.passengers)

@dp.message(Order.passengers)
async def process_passengers(message: types.Message, state: FSMContext):
    await state.update_data(passengers=message.text)
    await message.answer("Safar vaqtini yozing:\n(Masalan: Ertaga soat 08:00 da)")
    await state.set_state(Order.travel_time)

@dp.message(Order.travel_time)
async def process_time(message: types.Message, state: FSMContext):
    await state.update_data(travel_time=message.text)
    user_data = get_user(message.from_user.id)
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=f"{user_data[1]}")],
        [KeyboardButton(text="Boshqa raqam 📱", request_contact=True)]
    ], resize_keyboard=True)
    await message.answer("Bog'lanish uchun raqamingizni tasdiqlang:", reply_markup=kb)
    await state.set_state(Order.client_phone)

@dp.message(Order.client_phone)
async def process_order_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    phone = message.contact.phone_number if message.contact else message.text
    order_text = (f"🆕 YANGI BUYURTMA!\n"
                  f"📍 Yo'nalish: {data['route']}\n"
                  f"👥 Yo'lovchi: {data['passengers']}\n"
                  f"⏰ Vaqt: {data['travel_time']}\n"
                  f"📱 Tel: {phone}\n"
                  f"👤 Mijoz: @{message.from_user.username or 'Yo'q'}")
    
    await bot.send_message(ADMIN_ID, order_text)
    await message.answer("Buyurtmangiz adminga yuborildi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ADMINGA XABAR ---
@dp.message(F.text.contains("Adminga"))
async def start_contact(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True))
    await state.set_state(AdminContact.waiting_msg)

@dp.message(AdminContact.waiting_msg)
async def send_to_admin(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    await bot.send_message(ADMIN_ID, f"✉️ XABAR:\nID: {message.from_user.id}\n@{message.from_user.username}\n\n{message.text}")
    await message.answer("Yuborildi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ADMIN PANEL ---
@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    count = len(get_all_users())
    await message.answer(f"📊 Jami foydalanuvchilar: {count} ta")

@dp.message(F.text == "⚙️ Kanalni sozlash", F.from_user.id == ADMIN_ID)
async def set_channel_cmd(message: types.Message, state: FSMContext):
    await message.answer(f"Yangi kanal username'ini yuboring (masalan: @NuroTaxi):")
    await state.set_state(AdminStates.new_channel)

@dp.message(AdminStates.new_channel)
async def update_channel(message: types.Message, state: FSMContext):
    if message.text.startswith("@"):
        update_setting('channel', message.text)
        await message.answer(f"Kanal yangilandi: {message.text}", reply_markup=main_menu(ADMIN_ID))
        await state.clear()
    else: await message.answer("Xato! @ bilan boshlang.")

@dp.message(F.text == "📢 Reklama", F.from_user.id == ADMIN_ID)
async def admin_broadcast(message: types.Message, state: FSMContext):
    await message.answer("Reklama matnini yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True))
    await state.set_state(AdminStates.broadcast_msg)

@dp.message(AdminStates.broadcast_msg)
async def send_broadcast(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(ADMIN_ID))
    users = get_all_users()
    for u_id in users:
        try:
            await bot.send_message(u_id, message.text)
            await asyncio.sleep(0.05)
        except: pass
    await message.answer("Tayyor!", reply_markup=main_menu(ADMIN_ID))
    await state.clear()

async def main():
    init_db()
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
