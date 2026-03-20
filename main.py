import asyncio
import os
import sqlite3
import logging
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
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

def get_taksists():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE role = 'taksist'")
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

class AdminReply(StatesGroup):
    target_user = State()
    message_text = State()

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
        kb.append([KeyboardButton(text="📊 Statistika")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

cancel_kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🚫 Bekor qilish")]], resize_keyboard=True)

# --- HANDLERS ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user = get_user(message.from_user.id)
    if user:
        await message.answer("Xush kelibsiz!", reply_markup=main_menu(message.from_user.id))
    else:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Taksist 🚖"), KeyboardButton(text="Yo'lovchi 🙋‍♂️")]], resize_keyboard=True)
        await message.answer("Kim sifatida ro'yxatdan o'tasiz?", reply_markup=kb)
        await state.set_state(Registration.role)

@dp.message(Registration.role)
async def set_role(message: types.Message, state: FSMContext):
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(role=role)
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Kontakt yuborish 📱", request_contact=True)]], resize_keyboard=True))
    await state.set_state(Registration.phone)

@dp.message(Registration.phone, F.contact)
async def set_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    save_user(message.from_user.id, data['role'], message.contact.phone_number, message.from_user.full_name)
    await message.answer("Ro'yxatdan o'tdingiz!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- SAFAR REJALASHTIRISH (AUKSION BOSHLANISHI) ---
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
    user_info = get_user(message.from_user.id)
    
    order_msg = (f"🔔 YANGI BUYURTMA!\n📍 Yo'nalish: {data['route']}\n"
                 f"👥 Yo'lovchi: {data['passengers']}\n⏰ Vaqt: {message.text}")
    
    taksists = get_taksists()
    for t_id in taksists:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Narx taklif qilish 💸", callback_data=f"bid_{message.from_user.id}")]])
        try: await bot.send_message(t_id, order_msg, reply_markup=kb)
        except: pass
    
    await message.answer("Buyurtmangiz taksistlarga yuborildi. Narxlarni kuting!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- TAKSIST NARX TAKLIF QILISHI ---
@dp.callback_query(F.data.startswith("bid_"))
async def taksist_bid(call: types.CallbackQuery, state: FSMContext):
    client_id = call.data.split("_")[1]
    await state.update_data(current_client=client_id)
    await call.message.answer("Ushbu buyurtma uchun narxingizni yozing (faqat raqamda):")
    await state.set_state(Auction.offer_price)

@dp.message(Auction.offer_price)
async def forward_bid_to_client(message: types.Message, state: FSMContext):
    data = await state.get_data()
    taksist_info = get_user(message.from_user.id)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Tanlash ✅", callback_data=f"win_{message.from_user.id}")]])
    
    await bot.send_message(data['current_client'], 
                           f"🚖 Taksistdan taklif:\n💰 Narx: {message.text} so'm\n⭐ Haydovchi: {taksist_info[2]}", 
                           reply_markup=kb)
    await message.answer("Narxingiz yo'lovchiga yuborildi!")
    await state.clear()

# --- YO'LOVCHI TANLASHI (YAKUN) ---
@dp.callback_query(F.data.startswith("win_"))
async def finalize_auction(call: types.CallbackQuery):
    taksist_id = call.data.split("_")[1]
    client_id = call.from_user.id
    
    client_info = get_user(client_id)
    taksist_info = get_user(taksist_id)
    
    # G'olib taksistga
    await bot.send_message(taksist_id, f"🥳 Siz tanlandingiz!\n👤 Mijoz: {client_info[2]}\n📞 Tel: {client_info[1]}\nTezroq bog'laning!")
    
    # Yo'lovchiga
    await call.message.answer(f"✅ Haydovchi tanlandi!\n📞 Tel: {taksist_info[1]}\nHaydovchi hozir siz bilan bog'lanadi.")
    
    # Boshqa taksistlarga xabar yuborish (bu yerda soddalashtirilgan, aslida barcha taklif berganlarni saqlash kerak)
    await call.message.delete()

# --- ADMINGA XABAR VA JAVOB ---
@dp.message(F.text.contains("Adminga"))
async def admin_contact_start(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:", reply_markup=cancel_kb)
    await state.set_state(AdminReply.message_text)

@dp.message(AdminReply.message_text)
async def send_admin_with_reply(message: types.Message, state: FSMContext):
    if message.text == "🚫 Bekor qilish":
        await state.clear()
        return await message.answer("Bekor qilindi.", reply_markup=main_menu(message.from_user.id))
    
    user_info = get_user(message.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Javob berish ✍️", callback_data=f"reply_{message.from_user.id}")]])
    
    await bot.send_message(ADMIN_ID, f"✉️ YANGI XABAR:\n👤 Ism: {user_info[2]}\n📞 Tel: {user_info[1]}\n🆔 ID: {message.from_user.id}\n\n📝 Xabar: {message.text}", reply_markup=kb)
    await message.answer("Xabaringiz adminga yuborildi!", reply_markup=main_menu(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("reply_"))
async def admin_reply_start(call: types.CallbackQuery, state: FSMContext):
    user_id = call.data.split("_")[1]
    await state.update_data(target_user=user_id)
    await call.message.answer("Foydalanuvchiga yuboriladigan javob matnini yozing:")
    await state.set_state(AdminReply.target_user)

@dp.message(AdminReply.target_user)
async def admin_send_reply_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    try:
        await bot.send_message(data['target_user'], f"👨‍💻 Admin javobi:\n\n{message.text}")
        await message.answer("Javob yuborildi!")
    except: await message.answer("Xato! Foydalanuvchi botni bloklagan bo'lishi mumkin.")
    await state.clear()

async def main():
    init_db()
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
