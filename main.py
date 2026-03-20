import asyncio
import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web

# --- SOZLAMALAR ---
API_TOKEN = '8399783426:AAHyEHTD364aYa5uiniKwg6SuNq2Ign8QjU'
ADMIN_ID = 2085230699 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, role TEXT, phone TEXT, username TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)')
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
    travel_time = State()

class Auction(StatesGroup):
    offer_price = State()

class AdminStates(StatesGroup):
    broadcast_msg = State()
    new_channel = State()
    reply_text = State()

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

cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True)

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def check_sub(user_id):
    channel = get_setting('channel')
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
        return member.status not in ['left', 'kicked']
    except: return False

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
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Taksist 🚖"), KeyboardButton(text="Yo'lovchi 🙋‍♂️")]], resize_keyboard=True)
        await message.answer("Kim sifatida ro'yxatdan o'tasiz?", reply_markup=kb)
        await state.set_state(Registration.role)

@dp.callback_query(F.data == "check_subs")
async def check_callback(call: types.CallbackQuery, state: FSMContext):
    if await check_sub(call.from_user.id):
        await call.message.delete()
        await cmd_start(call.message, state)
    else: await call.answer("Siz hali a'zo emassiz!", show_alert=True)

# --- RO'YXATDAN O'TISH ---
@dp.message(Registration.role)
async def set_role(message: types.Message, state: FSMContext):
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(role=role)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Kontakt yuborish 📱", request_contact=True)]], resize_keyboard=True)
    await message.answer("Telefon raqamingizni yuboring yoki yozib qoldiring:", reply_markup=kb)
    await state.set_state(Registration.phone)

@dp.message(Registration.phone)
async def set_phone(message: types.Message, state: FSMContext):
    phone = message.contact.phone_number if message.contact else message.text
    data = await state.get_data()
    save_user(message.from_user.id, data['role'], phone, message.from_user.full_name)
    await message.answer("Muvaffaqiyatli ro'yxatdan o'tdingiz!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- SAFAR REJALASHTIRISH ---
@dp.message(F.text == "Safarni rejalashtirish 🗓")
async def start_order(message: types.Message, state: FSMContext):
    await message.answer("Qayerdan qayerga bormoqchisiz?", reply_markup=cancel_kb)
    await state.set_state(Order.route)

@dp.message(Order.route)
async def process_route(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    await state.update_data(route=message.text)
    await message.answer("Nechta yo'lovchi?", reply_markup=cancel_kb)
    await state.set_state(Order.passengers)

@dp.message(Order.passengers)
async def process_passengers(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    await state.update_data(passengers=message.text)
    await message.answer("Safar vaqtini yozing:", reply_markup=cancel_kb)
    await state.set_state(Order.travel_time)

@dp.message(Order.travel_time)
async def finish_order(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    
    data = await state.get_data()
    order_msg = (f"🔔 YANGI BUYURTMA!\n📍 Yo'nalish: {data['route']}\n"
                 f"👥 Yo'lovchi: {data['passengers']}\n⏰ Vaqt: {message.text}")
    
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE role = 'taksist'")
    taksists = cursor.fetchall()
    conn.close()

    for t in taksists:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Narx taklif qilish 💸", callback_data=f"bid_{message.from_user.id}")]])
        try: await bot.send_message(t[0], order_msg, reply_markup=kb)
        except: pass
    
    await message.answer("Buyurtma yuborildi. Narxlarni kuting!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- AUKSION LOGIKASI ---
@dp.callback_query(F.data.startswith("bid_"))
async def taksist_bid(call: types.CallbackQuery, state: FSMContext):
    client_id = call.data.split("_")[1]
    await state.update_data(current_client=client_id)
    await call.message.answer("Narxingizni kiriting (faqat raqam):")
    await state.set_state(Auction.offer_price)

@dp.message(Auction.offer_price)
async def forward_bid(message: types.Message, state: FSMContext):
    data = await state.get_data()
    t_info = get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Tanlash ✅", callback_data=f"win_{message.from_user.id}")]])
    await bot.send_message(data['current_client'], f"🚖 Taksist taklifi:\n💰 Narx: {message.text} so'm\n⭐ Ism: {t_info[2]}", reply_markup=kb)
    await message.answer("Narx yuborildi!")
    await state.clear()

@dp.callback_query(F.data.startswith("win_"))
async def finalize(call: types.CallbackQuery):
    t_id = call.data.split("_")[1]
    c_info = get_user(call.from_user.id)
    t_info = get_user(t_id)
    await bot.send_message(t_id, f"🥳 Siz tanlandingiz!\n👤 Mijoz: {c_info[2]}\n📞 Tel: {c_info[1]}")
    await call.message.answer(f"✅ Tanlandi! Taksist raqami: {t_info[1]}")
    await call.message.delete()

# --- ADMIN PANEL FUNKSIYALARI ---
@dp.message(F.text == "📊 Statistika", F.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    count = len(get_all_users())
    await message.answer(f"📊 Jami foydalanuvchilar: {count} ta")

@dp.message(F.text == "⚙️ Kanalni sozlash", F.from_user.id == ADMIN_ID)
async def set_channel(message: types.Message, state: FSMContext):
    current = get_setting('channel')
    await message.answer(f"Hozirgi kanal: {current}\nYangi kanal username'ini kiriting (@ bilan):", reply_markup=cancel_kb)
    await state.set_state(AdminStates.new_channel)

@dp.message(AdminStates.new_channel)
async def update_ch(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(ADMIN_ID))
    if message.text.startswith("@"):
        update_setting('channel', message.text)
        await message.answer(f"Yangilandi: {message.text}", reply_markup=main_menu(ADMIN_ID))
        await state.clear()
    else: await message.answer("Xato! @ bilan boshlang.")

@dp.message(F.text == "📢 Reklama", F.from_user.id == ADMIN_ID)
async def admin_ads(message: types.Message, state: FSMContext):
    await message.answer("Reklama xabarini yozing:", reply_markup=cancel_kb)
    await state.set_state(AdminStates.broadcast_msg)

@dp.message(AdminStates.broadcast_msg)
async def send_ads(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(ADMIN_ID))
    users = get_all_users()
    for u in users:
        try: await bot.send_message(u, message.text); await asyncio.sleep(0.05)
        except: pass
    await message.answer("Yuborildi!", reply_markup=main_menu(ADMIN_ID))
    await state.clear()

# --- ADMIN BILAN ALOQA ---
@dp.message(F.text.contains("Adminga"))
async def contact_admin(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:", reply_markup=cancel_kb)
    await state.set_state(AdminContact.waiting_msg)

@dp.message(AdminContact.waiting_msg)
async def forward_admin(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    u = get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Javob berish ✍️", callback_data=f"rep_{message.from_user.id}")]])
    await bot.send_message(ADMIN_ID, f"✉️ XABAR:\n👤 {u[2]}\n📞 {u[1]}\n📝 {message.text}", reply_markup=kb)
    await message.answer("Yuborildi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("rep_"))
async def rep_start(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(target=call.data.split("_")[1])
    await call.message.answer("Javobingizni yozing:")
    await state.set_state(AdminStates.reply_text)

@dp.message(AdminStates.reply_text)
async def rep_send(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try: await bot.send_message(data['target'], f"👨‍💻 Admin javobi:\n\n{message.text}")
    except: pass
    await message.answer("Javob yuborildi!", reply_markup=main_menu(ADMIN_ID))
    await state.clear()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
