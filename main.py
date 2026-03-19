import logging
import sqlite3
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiohttp import web # Render uchun kerak

# --- SOZLAMALAR ---
API_TOKEN = '8399783426:AAHyEHTD364aYa5uiniKwg6SuNq2Ign8QjU'
ADMIN_ID = 2085230699 # O'z ID-ingizni yozing

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- RENDER UCHUN HEALTH CHECK (BOT O'CHIB QOLMASLIGI UCHUN) ---
async def handle_health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 10000) # Render kutayotgan port
    await site.start()

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, role TEXT, phone TEXT)''')
    conn.commit()
    conn.close()

def save_user(user_id, role, phone):
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users VALUES (?, ?, ?)", (user_id, role, phone))
    conn.commit()
    conn.close()

def get_taxis():
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE role = 'taksist'")
    taxis = cursor.fetchall()
    conn.close()
    return [t[0] for t in taxis]

# --- STATES ---
class Registration(StatesGroup):
    role = State()
    phone = State()

class Order(StatesGroup):
    route = State()
    passengers = State()
    client_phone = State()

class Bid(StatesGroup):
    price = State()

class AdminContact(StatesGroup):
    message = State()

# --- HANDLERS (AVVALGI FUNKSIYALAR) ---

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Taksist 🚖"), KeyboardButton("Yo'lovchi 🙋‍♂️"))
    await message.answer("Xush kelibsiz! Kim sifatida davom etasiz?", reply_markup=markup)
    await Registration.role.set()

@dp.message_handler(state=Registration.role)
async def process_role(message: types.Message, state: FSMContext):
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(user_role=role)
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Kontaktni ulashish 📱", request_contact=True))
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=markup)
    await Registration.phone.set()

@dp.message_handler(content_types=['contact'], state=Registration.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    role, phone = data['user_role'], message.contact.phone_number
    save_user(message.from_user.id, role, phone)
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == 'taksist':
        markup.add("Adminga murojaat ✍️")
        await message.answer("Taksist sifatida ro'yxatdan o'tdingiz.", reply_markup=markup)
    else:
        markup.add("Safarni rejalashtirish 🗓", "Adminga xabar ✍️")
        await message.answer("Yo'lovchi sifatida ro'yxatdan o'tdingiz.", reply_markup=markup)
    await state.finish()

@dp.message_handler(lambda m: "Adminga" in m.text)
async def admin_start(message: types.Message):
    await message.answer("Marhamat, xatolik yoki takliflarni yozing. Admin tezda bog'lanadi.", reply_markup=ReplyKeyboardRemove())
    await AdminContact.message.set()

@dp.message_handler(state=AdminContact.message)
async def admin_send(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"👤 Kimdan: {message.from_user.full_name}\n🆔 ID: {message.from_user.id}\n📝 Xabar: {message.text}")
    
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE user_id = ?", (message.from_user.id,))
    role = cursor.fetchone()[0]
    conn.close()
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    if role == 'taksist': markup.add("Adminga murojaat ✍️")
    else: markup.add("Safarni rejalashtirish 🗓", "Adminga xabar ✍️")
    
    await message.answer("Xabaringiz adminga yuborildi.", reply_markup=markup)
    await state.finish()

@dp.message_handler(lambda m: m.text == "Safarni rejalashtirish 🗓")
async def start_order(message: types.Message):
    await message.answer("Qayerdan qayerga bormoqchisiz?", reply_markup=ReplyKeyboardRemove())
    await Order.route.set()

@dp.message_handler(state=Order.route)
async def process_route(message: types.Message, state: FSMContext):
    await state.update_data(route=message.text)
    await message.answer("Necha kishisiz?")
    await Order.passengers.set()

@dp.message_handler(state=Order.passengers)
async def process_passengers(message: types.Message, state: FSMContext):
    await state.update_data(passengers=message.text)
    await message.answer("Aloqa uchun telefon raqamingiz:")
    await Order.client_phone.set()

@dp.message_handler(state=Order.client_phone)
async def process_client_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    route, passengers, phone = data['route'], data['passengers'], message.text
    taxis = get_taxis()
    for t_id in taxis:
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Narx yozish 💰", callback_data=f"bid_{message.from_user.id}_{phone}"))
        await bot.send_message(t_id, f"🆕 Safar!\n📍 Yo'nalish: {route}\n👥 Odam: {passengers}\n💰 Narx taklif qiling:", reply_markup=markup)
    await message.answer("Buyurtma taksistlarga yuborildi.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('bid_'))
async def taxi_bid(callback_query: types.CallbackQuery, state: FSMContext):
    _, c_id, c_phone = callback_query.data.split('_')
    await state.update_data(bid_client_id=c_id, bid_client_phone=c_phone)
    await bot.send_message(callback_query.from_user.id, "Mijozga narxingizni yozing:")
    await Bid.price.set()
    await callback_query.answer()

@dp.message_handler(state=Bid.price)
async def receive_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    c_id, c_phone = data['bid_client_id'], data['bid_client_phone']
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
    t_phone = cursor.fetchone()[0]
    conn.close()
    markup = InlineKeyboardMarkup().add(InlineKeyboardButton("Tanlash ✅", callback_data=f"accept_{message.from_user.id}_{t_phone}_{c_phone}"))
    await bot.send_message(c_id, f"Haydovchi narxi: {message.text} so'm", reply_markup=markup)
    await message.answer("Narx yuborildi.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('accept_'))
async def accept_taxi(callback_query: types.CallbackQuery):
    _, t_id, t_phone, c_phone = callback_query.data.split('_')
    markup = ReplyKeyboardMarkup(resize_keyboard=True).add("Safarni rejalashtirish 🗓", "Adminga xabar ✍️")
    await callback_query.message.answer(f"✅ Safar tasdiqlandi!\n🚖 Haydovchi tel: {t_phone}", reply_markup=markup)
    await bot.send_message(t_id, f"✅ Mijoz sizni tanladi!\n📞 Mijoz tel: {c_phone}")
    await callback_query.answer()

# --- BOTNI ISHGA TUSHIRISH ---
if __name__ == '__main__':
    init_db()
    # Web serverni fonda ishga tushirish
    loop = asyncio.get_event_loop()
    loop.create_task(start_web_server())
    # Botni ishga tushirish
    executor.start_polling(dp, skip_updates=True)
