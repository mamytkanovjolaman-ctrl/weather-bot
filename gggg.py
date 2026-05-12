import asyncio
import json
import os
import aiohttp
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from groq import Groq

# ================== КЛЮЧИ ==================
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()
client = Groq(api_key=GROQ_API_KEY)
scheduler = AsyncIOScheduler()

# ================== БАЗА ДАННЫХ ==================
DB_FILE = "users.json"

def load_users():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users(users):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)

# ================== КЛАВИАТУРА ==================
def main_menu():
    kb = [
        [KeyboardButton(text="🌤️ Погода сейчас")],
        [KeyboardButton(text="⚙️ Изменить настройки")],
        [KeyboardButton(text="ℹ️ Мои данные")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# ================== ПОИСК ГОРОДА (Nominatim) ==================
async def find_city(city_name: str):
    """Ищет любой город/место в мире и возвращает координаты."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": city_name,
        "format": "json",
        "limit": 1,
        "addressdetails": 1
    }
    headers = {"User-Agent": "WeatherBot/1.0"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data:
                        result = data[0]
                        return {
                            "lat": float(result["lat"]),
                            "lon": float(result["lon"]),
                            "name": result.get("display_name", city_name).split(",")[0]
                        }
    except Exception as e:
        print(f"Ошибка поиска города: {e}")
    return None

# ================== ПОГОДА (Open-Meteo) ==================
async def get_weather(lat: float, lon: float):
    """Получает погоду по координатам — любая точка мира."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": [
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "wind_speed_10m",
            "weather_code",
            "precipitation"
        ],
        "wind_speed_unit": "ms",
        "timezone": "auto"
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"Ошибка погоды: {e}")
    return None

def parse_weather_code(code: int) -> tuple:
    """Расшифровывает код погоды в описание и эмодзи."""
    codes = {
        0: ("Ясное небо", "☀️"),
        1: ("Преимущественно ясно", "🌤️"),
        2: ("Переменная облачность", "⛅"),
        3: ("Пасмурно", "☁️"),
        45: ("Туман", "🌫️"),
        48: ("Туман с инеем", "🌫️"),
        51: ("Лёгкая морось", "🌦️"),
        53: ("Морось", "🌦️"),
        55: ("Сильная морось", "🌧️"),
        61: ("Небольшой дождь", "🌧️"),
        63: ("Дождь", "🌧️"),
        65: ("Сильный дождь", "🌧️"),
        71: ("Небольшой снег", "❄️"),
        73: ("Снег", "❄️"),
        75: ("Сильный снег", "❄️"),
        80: ("Ливень", "🌧️"),
        81: ("Сильный ливень", "⛈️"),
        85: ("Снегопад", "❄️"),
        95: ("Гроза", "⛈️"),
        99: ("Гроза с градом", "⛈️"),
    }
    return codes.get(code, ("Переменная облачность", "🌤️"))

# ================== СОВЕТ ОТ ИИ ==================
async def get_advice(name: str, temp: float, description: str) -> str:
    prompt = (
        f"Пользователя зовут {name}. На улице {temp}°C, погода: {description}.\n"
        f"Напиши короткое дружелюбное пожелание (1-2 предложения) "
        f"с советом по одежде. Используй эмодзи. Обращайся по имени."
    )
    try:
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100
        )
        return completion.choices[0].message.content
    except:
        return f"Хорошего дня, {name}! 😊"

# ================== ФОРМАТ СООБЩЕНИЯ ==================
async def format_weather_message(name: str, city_name: str, lat: float, lon: float) -> str:
    data = await get_weather(lat, lon)
    if not data:
        return "😔 Не удалось получить погоду. Попробуй позже."

    current = data["current"]
    temp = round(current["temperature_2m"])
    feels_like = round(current["apparent_temperature"])
    humidity = current["relative_humidity_2m"]
    wind = round(current["wind_speed_10m"])
    code = current["weather_code"]
    description, emoji = parse_weather_code(code)

    advice = await get_advice(name, temp, description)

    hour = datetime.now().hour
    if 5 <= hour < 12:
        greeting = "🌅 Доброе утро"
    elif 12 <= hour < 18:
        greeting = "☀️ Добрый день"
    else:
        greeting = "🌙 Добрый вечер"

    return (
        f"{greeting}, {name}!\n\n"
        f"{emoji} {description}\n"
        f"📍 {city_name}\n"
        f"🌡️ Температура: {temp}°C\n"
        f"🤔 Ощущается как: {feels_like}°C\n"
        f"💧 Влажность: {humidity}%\n"
        f"💨 Ветер: {wind} м/с\n\n"
        f"{advice}"
    )

# ================== УВЕДОМЛЕНИЯ ==================
async def send_notifications():
    users = load_users()
    now = datetime.now()
    current_time = f"{now.hour:02d}:{now.minute:02d}"
    for user_id, data in users.items():
        if data.get("notify_time") == current_time and data.get("lat"):
            try:
                msg = await format_weather_message(
                    data["name"], data["city"],
                    data["lat"], data["lon"]
                )
                await bot.send_message(int(user_id), msg)
            except Exception as e:
                print(f"Ошибка отправки {user_id}: {e}")

# ================== СОСТОЯНИЯ ==================
user_states = {}

# ================== КОМАНДЫ ==================
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id in users and users[user_id].get("lat"):
        name = users[user_id]["name"]
        await message.answer(
            f"С возвращением, {name}! 👋",
            reply_markup=main_menu()
        )
    else:
        user_states[user_id] = "waiting_name"
        await message.answer(
            "👋 Привет! Я буду присылать тебе погоду каждый день!\n\n"
            "Как тебя зовут?"
        )

@dp.message(F.text == "🌤️ Погода сейчас")
async def weather_now(message: types.Message):
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id not in users or not users[user_id].get("lat"):
        await message.answer("Сначала настрой бота — напиши /start")
        return
    u = users[user_id]
    await message.answer("🌍 Получаю погоду...")
    msg = await format_weather_message(u["name"], u["city"], u["lat"], u["lon"])
    await message.answer(msg)

@dp.message(F.text == "⚙️ Изменить настройки")
async def change_settings(message: types.Message):
    user_id = str(message.from_user.id)
    user_states[user_id] = "waiting_name"
    await message.answer("Давай обновим данные!\n\nКак тебя зовут?")

@dp.message(F.text == "ℹ️ Мои данные")
async def my_data(message: types.Message):
    user_id = str(message.from_user.id)
    users = load_users()
    if user_id in users:
        u = users[user_id]
        await message.answer(
            f"👤 Имя: {u.get('name', '—')}\n"
            f"📍 Город: {u.get('city', '—')}\n"
            f"⏰ Время уведомлений: {u.get('notify_time', '—')}"
        )
    else:
        await message.answer("Нет данных. Напиши /start")

# ================== ОСНОВНОЙ ХЕНДЛЕР ==================
@dp.message()
async def handle_message(message: types.Message):
    user_id = str(message.from_user.id)
    text = message.text.strip()
    state = user_states.get(user_id)
    users = load_users()

    # Ждём имя
    if state == "waiting_name":
        clean = text.lower()
        for phrase in ["меня зовут", "я ", "мое имя", "моё имя"]:
            clean = clean.replace(phrase, "")
        name = clean.strip().title()
        if user_id not in users:
            users[user_id] = {}
        users[user_id]["name"] = name
        save_users(users)
        user_states[user_id] = "waiting_city"
        await message.answer(
            f"Приятно познакомиться, {name}! 😊\n\n"
            f"📍 Напиши свой город на любом языке:\n"
            f"Например: Бишкек, Кимдже, Moscow, New York"
        )
        return

    # Ждём город
    if state == "waiting_city":
        await message.answer("🔍 Ищу город...")
        city_data = await find_city(text)
        if not city_data:
            await message.answer(
                "😔 Не нашёл такое место. Попробуй написать иначе."
            )
            return
        users[user_id]["city"] = city_data["name"]
        users[user_id]["lat"] = city_data["lat"]
        users[user_id]["lon"] = city_data["lon"]
        save_users(users)
        user_states[user_id] = "waiting_time"
        await message.answer(
            f"✅ Найдено: {city_data['name']}!\n\n"
            f"⏰ В какое время присылать погоду каждый день?\n"
            f"Напиши в формате ЧЧ:ММ\n"
            f"Например: 07:00 или 08:30"
        )
        return

    # Ждём время
    if state == "waiting_time":
        try:
            datetime.strptime(text, "%H:%M")
            users[user_id]["notify_time"] = text
            save_users(users)
            user_states.pop(user_id, None)
            name = users[user_id]["name"]
            city = users[user_id]["city"]
            await message.answer(
                f"🎉 Всё готово, {name}!\n\n"
                f"📍 Город: {city}\n"
                f"⏰ Буду присылать погоду каждый день в {text}\n\n"
                f"Хорошего дня! 😊",
                reply_markup=main_menu()
            )
        except ValueError:
            await message.answer("❌ Напиши время так: 07:00 или 08:30")
        return

    await message.answer("Используй кнопки меню 😊", reply_markup=main_menu())

# ================== ЗАПУСК ==================
async def main():
    scheduler.add_job(send_notifications, "cron", minute="*")
    scheduler.start()
    print("✅ Погодный бот запущен! Любой город мира 🌍")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())