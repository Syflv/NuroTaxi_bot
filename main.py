import logging
import sqlite3
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Bot tokeningizni bura yozing
API_TOKEN = '8399783426:AAHyEHTD364aYa5uiniKwg6SuNq2Ign8QjU'

# Logging va Bot sozlamalari
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- DATABASE QISMI ---
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

# --- STATES (Holatlar) ---
class Registration(StatesGroup):
    role = State()
    phone = State()

class Order(StatesGroup):
    route = State()
    passengers = State()
    client_phone = State()

class Bid(StatesGroup):
    price = State()

# --- START ---
@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Taksist 🚖"), KeyboardButton("Yo'lovchi 🙋‍♂️"))
    await message.answer("Xush kelibsiz! Kim sifatida davom etasiz?", reply_markup=markup)
    await Registration.role.set()

@dp.message_handler(state=Registration.role)
async def process_role(message: types.Message, state: FSMContext):
    if message.text not in ["Taksist 🚖", "Yo'lovchi 🙋‍♂️"]:
        return await message.answer("Iltimos, tugmalardan birini tanlang.")
    
    role = 'taksist' if "Taksist" in message.text else 'yolovchi'
    await state.update_data(user_role=role)
    
    markup = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    markup.add(KeyboardButton("Kontaktni ulashish 📱", request_contact=True))
    await message.answer("Telefon raqamingizni yuboring:", reply_markup=markup)
    await Registration.phone.set()

@dp.message_handler(content_types=['contact'], state=Registration.phone)
async def process_phone(message: types.Message, state: FSMContext):
    data = await state.get_data()
    role = data['user_role']
    phone = message.contact.phone_number
    
    save_user(message.from_user.id, role, phone)
    
    if role == 'taksist':
        await message.answer("Siz taksist sifatida ro'yxatdan o'tdingiz. Yangi safarlar haqida xabar beramiz.", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add("Adminga murojaat ✍️"))
    else:
        markup = ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Safarni rejalashtirish 🗓", "Adminga xabar ✍️")
        await message.answer("Yo'lovchi sifatida ro'yxatdan o'tdingiz.", reply_markup=markup)
    await state.finish()

# --- BUYURTMA BERISH (YO'LOVCHI) ---
@dp.message_handler(lambda message: message.text == "Safarni rejalashtirish 🗓")
async def start_order(message: types.Message):
    await message.answer("Qayerdan qayerga bormoqchisiz?")
    await Order.route.set()

@dp.message_handler(state=Order.route)
async def process_route(message: types.Message, state: FSMContext):
    await state.update_data(route=message.text)
    await message.answer("Necha kishisiz?")
    await Order.passengers.set()

@dp.message_handler(state=Order.passengers)
async def process_passengers(message: types.Message, state: FSMContext):
    await state.update_data(passengers=message.text)
    await message.answer("Aloqa uchun telefon raqamingizni yozing:")
    await Order.client_phone.set()

@dp.message_handler(state=Order.client_phone)
async def process_client_phone(message: types.Message, state: FSMContext):
    order_data = await state.get_data()
    route = order_data['route']
    passengers = order_data['passengers']
    phone = message.text
    
    taxis = get_taxis()
    text = f"🆕 Yangi buyurtma!\n📍 Yo'nalish: {route}\n👥 Odam soni: {passengers}\n\nNarxingizni taklif qiling:"
    
    for taxi_id in taxis:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Narx yozish 💰", callback_data=f"bid_{message.from_user.id}_{phone}"))
        await bot.send_message(taxi_id, text, reply_markup=markup)
    
    await message.answer("Buyurtmangiz taksistlarga yuborildi. Narxlarni kuting.")
    await state.finish()

# --- NARX TAKLIF QILISH (TAKSIST) ---
@dp.callback_query_handler(lambda c: c.data.startswith('bid_'))
async def taxi_bid(callback_query: types.CallbackQuery, state: FSMContext):
    _, client_id, client_phone = callback_query.data.split('_')
    await state.update_data(bid_client_id=client_id, bid_client_phone=client_phone)
    await bot.send_message(callback_query.from_user.id, "Mijoz uchun narxingizni yuboring (masalan: 20000):")
    await Bid.price.set()
    await callback_query.answer()

@dp.message_handler(state=Bid.price)
async def receive_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    client_id = data['bid_client_id']
    
    conn = sqlite3.connect('taxi_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
    taxi_phone = cursor.fetchone()[0]
    conn.close()

    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Tanlash ✅", callback_data=f"accept_{message.from_user.id}_{taxi_phone}"))
    
    await bot.send_message(client_id, f"Haydovchidan taklif: {message.text} so'm", reply_markup=markup)
    await message.answer("Narxingiz mijozga yuborildi.")
    await state.finish()

# --- TANLASH (YO'LOVCHI) ---
@dp.callback_query_handler(lambda c: c.data.startswith('accept_'))
async def accept_taxi(callback_query: types.CallbackQuery):
    _, taxi_id, taxi_phone = callback_query.data.split('_')
    
    # Mijozga haydovchi raqami
    await callback_query.message.answer(f"✅ Haydovchi tanlandi!\n📞 Tel: {taxi_phone}\nBog'lanishingiz mumkin.")
    
    # Haydovchiga mijoz raqami
    await bot.send_message(taxi_id, "✅ Mijoz sizni tanladi!")
    
    await callback_query.answer("Muvaffaqiyatli tanlandi!")

if __name__ == '__main__':
    init_db()
    executor.start_polling(dp, skip_updates=True)