import json
import logging
import asyncio
import signal
import json
import database
import Classes
import dns
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from proxy import get_working_proxies, get_proxies
from browser import Browser
from aiogram.types import ParseMode
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Command
from aiogram.contrib.middlewares.logging import LoggingMiddleware
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import ChatActions
from database import add_user, get_user, get_durations, get_frequencies, get_base_rate
from geopy.geocoders import Nominatim
from geopy.adapters import AioHTTPAdapter
from dateutil.relativedelta import relativedelta


API_TOKEN = ''
ADMIN_USER_ID = ()
logging.basicConfig(level=logging.INFO)
browser = Browser()
print("Создан браузер")
bot = Bot(token=API_TOKEN, timeout=60)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
# proxies = get_working_proxies(10)
proxies = get_proxies()
dp.middleware.setup(LoggingMiddleware())

# Создайте класс для хранения стадий настройки мониторинга
class MonitoringSetupStates(StatesGroup):
    city = State()
    product = State()
    price_range = State()
    category = State()
    district = State()
    radius = State()
    coordinate = State()

async def get_address_by_coordinates_async(latitude: float, longitude: float) -> str:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://nominatim.openstreetmap.org/reverse?format=json&lat={latitude}&lon={longitude}") as response:
            data = await response.text()
            if response.status == 200:
                data_json = json.loads(data)
                if data_json:
                    return data_json.get('display_name')
                else:
                    return None
            else:
                return None

def get_city_coordinates(city_name):
    geolocator = Nominatim(user_agent="myGeocoder")
    location = geolocator.geocode(city_name)
    if location:
        return location.latitude, location.longitude
    else:
        return None

async def send_results(message, items):
    for item in items:
        text = f"<b>{item['title']}</b>\nЦена: {item['price']}₽\nСсылка: {item['link']}"
        await message.answer(text, parse_mode=ParseMode.HTML)

def create_menu() -> types.ReplyKeyboardMarkup:
    menu = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=1)

    btn1 = types.KeyboardButton("📝 Настроить новый мониторинг")
    btn2 = types.KeyboardButton("🎛 Управление существующим мониторингом")
    btn3 = types.KeyboardButton("💳 Тарифные планы")
    btn4 = types.KeyboardButton("❓ Помощь")

    menu.add(btn1, btn2, btn3, btn4)

    return menu

@dp.message_handler(commands=['start'])
async def start_command(message: types.Message):
    if await get_user(message.from_user.id) is None:
        user = Classes.User(message.from_user.id, message.from_user.username)
        await add_user(user)
    menu = create_menu()
    await message.answer("Добро пожаловать! Используйте кнопки для взаимодействия с ботом.", reply_markup=menu)

@dp.message_handler(lambda message: message.text == "❓ Помощь", state="*")
async def help_command(message: types.Message):
    await reset_monitoring_state(message.from_user.id)
    help_text = "Для поиска объявлений нажмите кнопку 'Поиск'. Вам потребуется указать город, поисковый запрос и максимальное количество страниц, разделенные запятыми. Например: Тверь, iphone SE, 2"
    await message.answer(help_text)

@dp.message_handler(lambda message: message.text == "💳 Тарифные планы", state="*")
async def show_tariff_plans(message: types.Message):
    await reset_monitoring_state(message.from_user.id)
    subscription = await database.get_subscription_by_user_id(message.from_user.id)
    if subscription and subscription.is_active():
        await show_inf_of_subscription(subscription, message.chat.id)
    else:
        frequencies = await get_frequencies()
        durations = await get_durations()
        base_rate = await get_base_rate()
        keyboard = create_tariff_plans_keyboard(frequencies, durations, base_rate)
        await message.answer("Тарифные планы (максимальное количество объявлений - 3):", reply_markup=keyboard)

async def reset_monitoring_state(user_id):
    current_state = dp.current_state(user=user_id)
    state_name = await current_state.get_state()
    if state_name is not None and state_name.startswith("MonitoringSetupStates:"):
        await current_state.reset_state()

@dp.message_handler(lambda message: message.text == "📝 Настроить новый мониторинг", state="*")
async def new_monitoring(message: types.Message, state: FSMContext):
    subscription = await database.get_subscription_by_user_id(message.from_user.id)
    if subscription and subscription.is_active():
        await reset_monitoring_state(message.from_user.id)
        await message.answer("Привет! 👋 Давай начнём настройку мониторинга на Авито. "
                             "Сначала, пожалуйста, укажи город, в котором ты хочешь искать товары. 🌇")
        await state.update_data(coordinates=None)
        await state.update_data(district=None)
        await state.update_data(radius=None)
        await MonitoringSetupStates.city.set()
    else:
        if subscription:
            # Отображение данных пользователю
            await show_inf_of_subscription(subscription, message.chat.id)
        await message.answer("Для использования сервиса, необходимо приобрести подписку!\n Ознакомится со стоимостью и "
                              "условиями можно в разделе '💳 Тарифные планы'.")



async def show_inf_of_subscription(subscription, chat_id):
    start_date = datetime.strptime(subscription.start_date, "%Y-%m-%d %H:%M:%S.%f")
    end_date = datetime.strptime(subscription.end_date, "%Y-%m-%d %H:%M:%S.%f")
    title = "Срок вашей подписки истек" if not subscription.is_active() else "Информация о вашей подписке"
    await bot.send_message(
        chat_id=chat_id,
        text=f"{title}:\n\n"
             f"Дата начала: {start_date.strftime('%H:%M %d.%m.%Y')}\n"
             f"Дата окончания: {end_date.strftime('%H:%M %d.%m.%Y')}\n"
             f"Частота мониторинга: {subscription.frequency.name}\n"
             f"Длительность: {subscription.duration.name}"
    )

# Обработчик ввода города
@dp.message_handler(lambda message: message.text != "📝 Настроить новый мониторинг", state=MonitoringSetupStates.city)
async def process_city(message: types.Message, state: FSMContext):
    # Сохраняем город в контексте FSM
    await state.update_data(city=message.text)

    # keyboard = types.InlineKeyboardMarkup()
    # keyboard.add(types.InlineKeyboardButton("Загрузить районы", callback_data="load_districts"))
    # keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_districts"))
    #
    # await bot.send_message(
    #     chat_id=message.chat.id,
    #     text="Укажите район, либо пропустите этот пункт (по умолчанию мониторинг ведется по всему населенному пункту):",
    #     reply_markup=keyboard,
    # )
    await message.answer("Отлично! Теперь давай уточним, какой товар ты ищешь? 🛍 Напиши название товара.")
    await MonitoringSetupStates.next()  # переход к следующему состоянию

@dp.message_handler(lambda message: message.text != "📝 Настроить новый мониторинг", state=MonitoringSetupStates.product)
async def process_product(message: types.Message, state: FSMContext):
    # Сохраняем продукт в контексте FSM
    await state.update_data(product=message.text.strip())

    # keyboard = types.InlineKeyboardMarkup()
    # keyboard.add(types.InlineKeyboardButton("Загрузить категории", callback_data="load_categories"))
    # keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_categories"))
    #
    # await bot.send_message(
    #     chat_id=message.chat.id,
    #     text="Укажите категорию, либо пропустите этот пункт (по умолчанию мониторинг ведется по всем категориям):",
    #     reply_markup=keyboard,
    # )
    await message.answer("Супер! 💡 Теперь давай определимся с ценовым диапазоном. "
                         "Введи минимальную и максимальную цены через дефис, например: '1000-5000'. 💸")
    await MonitoringSetupStates.next()  # переход к следующему состоянию

# Обработчик ввода диапазона цен
@dp.message_handler(lambda message: message.text != "📝 Настроить новый мониторинг", state=MonitoringSetupStates.price_range)
async def process_price_range(message: types.Message, state: FSMContext):
    # Проверяем формат введенного диапазона цен
    if '-' in message.text:
        min_price, max_price = message.text.split('-')
        if min_price.isdigit() and max_price.isdigit():
            # Сохраняем диапазон цен в контексте FSM
            await state.update_data(min_price=int(min_price), max_price=int(max_price))
            sent_message = await message.answer("Проверка введенных данных ...")
            asyncio.create_task(send_long_chat_action(message.chat.id, ChatActions.TYPING, 12))
            user_data = await state.get_data()
            city = dns.city_transliteration(user_data.get('city'))
            url = f"https://www.avito.ru/{city}?q={user_data.get('product').replace(' ', '+')}"
            print(url)
            await bot.edit_message_text(chat_id=message.chat.id, message_id=sent_message.message_id, text=""
                                        "Секунду, собираем дополнительную информацию для точности ...")
            # Отправляем длительное действие чата перед началом загрузки категорий
            asyncio.create_task(send_long_chat_action(message.chat.id, ChatActions.TYPING, 12))
            try:
                url, categories, districts, radius = await dns.get_data_and_url(browser, url,
                                                                            user_data.get('min_price'),
                                                                            user_data.get('max_price'))
                await state.update_data(categories=categories)
                await state.update_data(districts=districts)
                await state.update_data(radius=radius)
                await state.update_data(url=url)
                keyboard = types.InlineKeyboardMarkup()
                keyboard.add(types.InlineKeyboardButton("Загрузить категории", callback_data="load_categories"))
                keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_categories"))
                await bot.delete_message(chat_id=message.chat.id, message_id=sent_message.message_id)
                await bot.send_message(
                    chat_id=message.chat.id,
                    text="Укажите категорию, либо пропустите этот пункт (по умолчанию мониторинг "
                         "ведется по всем категориям):",
                    reply_markup=keyboard,
                )
                await MonitoringSetupStates.next()  # переход к следующему состоянию
            except Exception as e:
                if url:
                    await state.update_data(url=url)
                    text = f"Упс! 😅 Произошла ошибка.\n"\
                           "Скорее всего, дело в неправильно указанном городе. 🤔 "\
                           "Пожалуйста, перейди по этой ссылке и проверь, что такая страница существует: "\
                           f"{url}\n\n"\
                           "Если ссылка не работает, давай начнём настройку заново! 🔄 Введи ближайший к твоему населённому пункту областной или районный город. "\
                           "Не волнуйся, позже ты сможешь указать точные координаты города и выбрать радиус поиска. 📍\n\n"\
                           "Нажми '📝 Настроить новый мониторинг', чтобы продолжить. Если ничего не помогает, сообщи об ошибке. 🙏"
                    sent_message = await message.answer(text=text)
                    sent_message_id = sent_message.message_id
                    keyboard = types.InlineKeyboardMarkup()
                    keyboard.add(types.InlineKeyboardButton("Сообщить об ошибке",
                                                            callback_data=f"send_error_report:{sent_message_id}"))

                    await bot.edit_message_reply_markup(chat_id=message.chat.id, message_id=sent_message_id,
                                                        reply_markup=keyboard)
        else:
            await message.answer("Пожалуйста, введите корректный диапазон цен.")
    else:
        await message.answer("Пожалуйста, введите диапазон цен в формате 'мин-макс', например, '100-500'.")

@dp.callback_query_handler(lambda call: call.data.startswith('send_error_report'), state=MonitoringSetupStates.price_range)
async def process_radius_none(call: types.CallbackQuery, state: FSMContext):
    _, message_id = call.data.split(":")
    user_data = await state.get_data()
    user = await database.get_user(call.from_user.id)
    start_date = datetime.strptime(user.subscription.start_date, "%Y-%m-%d %H:%M:%S.%f")
    end_date = datetime.strptime(user.subscription.end_date, "%Y-%m-%d %H:%M:%S.%f")
    await bot.delete_message(call.message.chat.id, message_id)
    await bot.send_message(958742622, text=f"Ошибка у пользователя: {user.user_name}\n"
                                           f"Попытка мониторинга: {user_data.get('url')}\n"
                                           f"Не удается получить информацию об элементах страницы!\n\n"
                                           f"Информация о подписке:\n"
                                           f"Дата начала: {start_date.strftime('%H:%M %d.%m.%Y')}\n"
                                           f"Дата окончания: {end_date.strftime('%H:%M %d.%m.%Y')}\n"
                                           f"Частота мониторинга: {user.subscription.frequency.name}\n"
                                           f"Длительность: {user.subscription.duration.name}"
                           )
    await call.message.answer(f"Передали информацию о проблеме. Обещаем починить все в короткие сроки. 👨‍🔧\n")

# Обработчик выбора района
@dp.callback_query_handler(lambda call: call.data.startswith('district_'), state=MonitoringSetupStates.district)
async def process_district(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    districts = user_data.get('districts')
    district = [item for item in districts if item['title'] == call.data.split("_")[1]]

    # Сохраняем категорию в контексте FSM
    await state.update_data(district=district[0])

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Выбрать радиус", callback_data="load_radius"))
    # keyboard.add(types.InlineKeyboardButton("Указать точные координаты", callback_data="set_coordinates"))
    keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_radius"))

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="Укажите координаты и радиус поиска 🗺️,\n"
             "если хочешь скратить область мониторинга.🔎",
        reply_markup=keyboard,
    )
    await call.answer("Район выбран")
    # await MonitoringSetupStates.next()  # переход к следующему состоянию

# @dp.callback_query_handler(lambda c: c.data.startswith('set_coordinates'), state=MonitoringSetupStates.district)
# async def load_radius_callback(callback_query: types.CallbackQuery, state: FSMContext):
#     user_data = await state.get_data()
#     await bot.send_message(chat_id=callback_query.message.chat.id, text="Укажи населенный пункт и субъект, в котором он распологается 🏡:")
#     await MonitoringSetupStates.coordinate.set()


# @dp.message_handler(lambda message: message.text != "📝 Настроить новый мониторинг", state=MonitoringSetupStates.coordinate)
# async def process_city(message: types.Message, state: FSMContext):
#     # Сохраняем город в контексте FSM
#     await state.update_data(city_from_coordinate=message.text)
#     coordinates = get_city_coordinates(message.text)
#     await state.update_data(coordinates=coordinates)
#     keyboard = types.InlineKeyboardMarkup()
#     keyboard.add(types.InlineKeyboardButton("Загрузить категории", callback_data="load_categories"))
#     keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_categories"))
#     await message.answer("Отлично! Теперь давай уточним, какой товар ты ищешь? 🛍 Напиши название товара.")
#     await bot.send_location(message.chat.id, coordinates[0], coordinates[1])
#     await MonitoringSetupStates.next()  # переход к следующему состоянию

@dp.message_handler(content_types=types.ContentType.LOCATION, state=MonitoringSetupStates.coordinate)
async def process_coordinates(message: types.Message, state: FSMContext):
    # Получаем новые координаты пользователя
    coordinates = (message.location.latitude, message.location.longitude)

    # Обновляем координаты в контексте FSM
    await state.update_data(coordinates=coordinates)

    # Завершаем процесс настройки мониторинга
    await display_user_data_message(message, state)
    await message.answer("Настройка мониторинга завершена. Спасибо!")
    await state.finish()

async def display_user_data_message(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    # Извлечение данных
    city = user_data.get('city', None)
    product_name = user_data.get('product', None)
    category_name = user_data.get('category', {}).get('title', None) if user_data.get('category') is not None else None
    category_link = user_data.get('category', {}).get('link', None) if user_data.get('category') is not None else None
    url = user_data.get('url', None)
    min_price = user_data.get('min_price', None)
    max_price = user_data.get('max_price', None)
    coordinates = user_data.get('coordinates', None)
    district = user_data.get('district', {}).get('number', None) if user_data.get('district') is not None else None
    radius = user_data.get('radius', {}).get('title', None) if user_data.get('radius') is not None else None
    subscription = await database.get_subscription_by_user_id(message.from_user.id)
    user = Classes.User(message.from_user.id, message.from_user.username, subscription)
    if coordinates:
        address = await get_address_by_coordinates_async(coordinates[0], coordinates[1])
    else:
        coordinates = get_city_coordinates(city)
        address = city
    # Реализовать выбор частоты
    f = dns.get_url_param_value(url, 'f')
    url_new = dns.add_parameters_to_url(category_link, f, district, radius, coordinates)
    await database.add_monitoring(user, user.subscription.frequency, city, product_name, url_new, datetime.now(),
                                  min_price, max_price)
    # Отображение данных пользователю
    await message.answer(f"Вот и всё! 👏 Твои настройки мониторинга на Авито готовы! Вот что мы получили:\n\n"
                              f"Локация: {address if address is not None else city}\n"
                              f"Координаты: широта {coordinates[0]}, долгота {coordinates[1]}\n"
                              f"Наименование продукта: {product_name}\n"
                              f"Категория: {category_name}\n"
                              f"Ценовой диапазон: {min_price}-{max_price}\n"
                              f"Ссылка: {url_new}")

# Обработчик выбора радиуса
@dp.callback_query_handler(lambda call: call.data.startswith('radius_'), state=MonitoringSetupStates.radius)
async def process_district(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    radiuses = user_data.get('radius')
    radius = [item for item in radiuses if str(item['title']) == call.data.split("_")[1]]
    # Сохраняем категорию в контексте FSM
    await state.update_data(radius=radius[0])
    await  bot.send_message(call.message.chat.id, text="Отправь свои географические координаты с "
                                                       "помощью функции отправки геолокации. 📍"
                                                       "Для этого открой диалоговое окно для отправки вложений "
                                                       "(иконка в форме скрепки)📎 и выбери 'Местоположение'.")
    await MonitoringSetupStates.next()  # переход к следующему состоянию
    await call.answer("Радиус выбран")



@dp.callback_query_handler(lambda c: c.data.startswith('load_radius'), state=MonitoringSetupStates.radius)
async def load_radius_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id, text="Загрузка может занять несколько секунд...")
    user_data = await state.get_data()
    keyboard = create_inline_keyboard(user_data["radius"], 'radius', page=0)

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Ещё чуть-чуть! 🎯 Выбери радиус поиска в пределах выбранного района (например: 1 км, 3 км, 5 км, и т.д.):",
        reply_markup=keyboard,
    )
    # await MonitoringSetupStates.next()


@dp.callback_query_handler(lambda call: call.data.startswith('skip_radius'), state=MonitoringSetupStates.radius)
async def process_radius_none(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await MonitoringSetupStates.next()  # переход к следующему состоянию
    await state.update_data(coordinates=None)
    await state.update_data(radius=None)
    # Завершаем процесс настройки мониторинга
    await display_user_data(call, state)
    await call.message.answer("Настройка мониторинга завершена. Спасибо!")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith('load_districts'), state=MonitoringSetupStates.district)
async def load_districts_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id, text="Загрузка может занять несколько секунд...")
    user_data = await state.get_data()
    districts = user_data.get('districts', [])
    if not districts:
        await process_district_none(callback_query, state)  # Переход к другому обработчику
        return
    # city = dns.city_transliteration(user_data.get('city'))
    # url = f"https://www.avito.ru/{city}?q={user_data.get('product').replace(' ', '+')}"
    # print(url)
    # # Отправляем длительное действие чата перед началом загрузки категорий
    # chat_id = callback_query.message.chat.id
    # asyncio.create_task(send_long_chat_action(chat_id, ChatActions.TYPING, 12))  # Задайте продолжительность действия
    # url, _, districts, radius = await dns.get_data_and_url(browser, city, user_data.get('product'),
    #                                                        user_data.get('min_price'), user_data.get('max_price'))
    # await state.update_data(districts=districts)
    # await state.update_data(radius=radius)
    # await state.update_data(url=url)
    # # keyboard = create_inline_keyboard(categories)
    keyboard = create_inline_keyboard(user_data.get('districts'), 'district', page=0)
    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Отличный выбор! 👍 Теперь давай определимся с районом. Вот список районов в твоем городе:",
        reply_markup=keyboard,
    )

@dp.callback_query_handler(lambda call: call.data.startswith('skip_districts'), state=MonitoringSetupStates.district)
async def process_district_none(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await state.update_data(district=None)
    await call.answer("Мониторинг по всем районам")

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Выбрать радиус", callback_data="load_radius"))
    keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_radius"))

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="Укажите радиус поиска, либо пропустите этот пункт:",
        reply_markup=keyboard,
    )
    await MonitoringSetupStates.next()  # переход к следующему состоянию
    # await MonitoringSetupStates.next()  # переход к следующему состоянию

async def send_long_chat_action(chat_id, action, duration):
    while duration > 0:
        await bot.send_chat_action(chat_id, action)
        await asyncio.sleep(4)  # Ожидание между отправками действий чата
        duration -= 4

# Создаем обработчик для кнопок с InlineKeyboard
@dp.callback_query_handler(lambda c: c.data.startswith('load_categories'), state=MonitoringSetupStates.category)
async def load_categories_callback(callback_query: types.CallbackQuery, state: FSMContext):
    await bot.answer_callback_query(callback_query.id, text="Загрузка может занять несколько секунд...")
    user_data = await state.get_data()
    keyboard = create_inline_keyboard(user_data.get('categories'), 'category', page=0)

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Великолепно! 😊 Теперь выбери категорию товара из списка ниже:",
        reply_markup=keyboard,
    )

@dp.callback_query_handler(lambda call: call.data.startswith('skip_categories'), state=MonitoringSetupStates.category)
async def process_category_none(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    url = f"https://www.avito.ru/{'all'}?q={user_data.get('product').replace(' ', '+')}"
    await state.update_data(category={'title': "Все категории", 'link': url})

    await call.answer("Мониторинг по всем категориям")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Загрузить районы", callback_data="load_districts"))
    keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_districts"))

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="Укажи район, либо пропусти этот пункт, если хочешь указать координаты и радиус поиска "
             "(по умолчанию мониторинг ведется по всему населенному пункту):",
        reply_markup=keyboard,
    )
    await MonitoringSetupStates.next()  # переход к следующему состоянию


@dp.callback_query_handler(lambda c: c.data.startswith('next_page_') or c.data.startswith('prev_page_'), state=MonitoringSetupStates.category)
async def paginate_categories_callback(callback_query: types.CallbackQuery, state: FSMContext):
    page = int(callback_query.data.split('_')[-1])
    user_data = await state.get_data()
    categories = user_data.get('categories')
    keyboard = create_inline_keyboard(categories, 'category', page=page)

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Выберите категорию:",
        reply_markup=keyboard,
    )

@dp.callback_query_handler(lambda c: c.data.startswith('next_page_') or c.data.startswith('prev_page_'), state=MonitoringSetupStates.district)
async def paginate_districts_callback(callback_query: types.CallbackQuery, state: FSMContext):
    page = int(callback_query.data.split('_')[-1])
    user_data = await state.get_data()
    categories = user_data.get('districts')
    keyboard = create_inline_keyboard(categories, 'district', page=page)

    await bot.edit_message_text(
        chat_id=callback_query.message.chat.id,
        message_id=callback_query.message.message_id,
        text="Выберите район:",
        reply_markup=keyboard,
    )

def truncate_category(category: str, max_bytes: int = 64) -> str:
    encoded_category = category.encode('utf-8')
    if len(encoded_category) <= max_bytes:
        return category

    truncated = encoded_category[:max_bytes].decode('utf-8', 'ignore')
    return truncated.rstrip()

def truncate_callback_data(data: str, max_length: int = 64) -> str:
    encoded_data = data.encode('utf-8')
    if len(encoded_data) > max_length:
        truncated_data = encoded_data[:max_length - 1 - 2].decode('utf-8', 'ignore').strip()
        data = truncated_data + "…"
    return data

def create_inline_keyboard(items: list, name: str, page: int = 0) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=2)
    start_index = page * 15
    end_index = start_index + 15

    for item in items[start_index:end_index]:
        if isinstance(item['title'], int):
            button = InlineKeyboardButton(text=str(item['title']), callback_data=f"{name}_{item['title']}")
        else:
            button = InlineKeyboardButton(text=truncate_category(item['title']),
                                          callback_data=truncate_callback_data(f"{name}_{item['title']}"))
        keyboard.add(button)

    # добавьте кнопки "далее" и "назад", если необходимо
    navigation_buttons = []
    total_pages = (len(items) + 14) // 15

    if page > 0:
        navigation_buttons.append(InlineKeyboardButton(text="Назад", callback_data=f"prev_page_{page - 1}"))

    if 0 < page < total_pages - 1:
        navigation_buttons.append(InlineKeyboardButton(text=f"{page + 1}/{total_pages}", callback_data="i"))

    if end_index < len(items):
        navigation_buttons.append(InlineKeyboardButton(text="Далее", callback_data=f"next_page_{page + 1}"))

    keyboard.row(*navigation_buttons)
    return keyboard

@dp.callback_query_handler(lambda c: c.data == 'i', state="*")
async def ignore_callback_query(callback_query: types.CallbackQuery):
    await bot.answer_callback_query(callback_query.id)

# Обработчик выбора категории
@dp.callback_query_handler(lambda call: call.data.startswith('category_'), state=MonitoringSetupStates.category)
async def process_category(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    categories = user_data.get('categories')
    category = [item for item in categories if item['title'] == call.data.split("_")[1]]

    # Сохраняем категорию в контексте FSM
    await state.update_data(category=category[0])

    await call.answer("Категория выбрана")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton("Загрузить районы", callback_data="load_districts"))
    keyboard.add(types.InlineKeyboardButton("Пропустить", callback_data="skip_districts"))

    await bot.send_message(
        chat_id=call.message.chat.id,
        text="Укажите район, либо пропустите этот пункт (по умолчанию мониторинг ведется по всему населенному пункту):",
        reply_markup=keyboard,
    )
    await MonitoringSetupStates.next()  # переход к следующему состоянию

async def display_user_data(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    # Извлечение данных
    city = user_data.get('city', None)
    product_name = user_data.get('product', None)
    category_name = user_data.get('category', {}).get('title', None) if user_data.get('category') is not None else None
    category_link = user_data.get('category', {}).get('link', None) if user_data.get('category') is not None else None
    url = user_data.get('url', None)
    min_price = user_data.get('min_price', None)
    max_price = user_data.get('max_price', None)
    coordinates = user_data.get('coordinates', None)
    district = user_data.get('district', {}).get('number', None) if user_data.get('district') is not None else None
    radius = user_data.get('radius', {}).get('title', None) if user_data.get('radius') is not None else None
    subscription = await database.get_subscription_by_user_id(call.from_user.id)
    user = Classes.User(call.from_user.id, call.from_user.username, subscription)
    if coordinates:
        address = await get_address_by_coordinates_async(coordinates[0], coordinates[1])
    else:
        coordinates = get_city_coordinates(city)
        address = city
    # Реализовать выбор частоты
    f = dns.get_url_param_value(url, 'f')
    url_new = dns.add_parameters_to_url(category_link, f, district, radius, coordinates)
    await database.add_monitoring(user, user.subscription.frequency, city, product_name, url_new, datetime.now(),
                                  min_price, max_price)
    await call.message.answer(f"Вот и всё! 👏 Твои настройки мониторинга на Авито готовы! Вот что мы получили:\n\n"
                              f"Локация: {address if address is not None else city}\n"
                              f"Координаты: широта {coordinates[0]}, долгота {coordinates[1]}\n"
                              f"Наименование продукта: {product_name}\n"
                              f"Категория: {category_name}\n"
                              f"Ценовой диапазон: {min_price}-{max_price}\n"
                              f"Ссылка: {url_new}")


def subscription_cost(frequency, duration, base_rate):

    if frequency.koef is None or duration.koef is None:
        raise ValueError("Invalid frequency or duration")

    cost = float(base_rate) * frequency.koef * duration.koef
    return int(cost)

def create_tariff_plans_keyboard(frequencies, durations, base_rate):
    keyboard = InlineKeyboardMarkup()
    # Добавляем заголовок таблицы
    header = [InlineKeyboardButton("Частота", callback_data="ignore")]
    for duration in durations:
        header.append(InlineKeyboardButton(duration.name, callback_data="ignore"))
    keyboard.row(*header)

    # Добавляем строки с данными
    for frequency in frequencies:
        row = [InlineKeyboardButton(frequency.name, callback_data="ignore")]
        for duration in durations:
            cost = subscription_cost(frequency, duration, base_rate)
            row.append(InlineKeyboardButton(str(cost), callback_data="choose_plan:{}:{}".format(frequency.frequency_id,
                                                                                                duration.duration_id)))
        keyboard.row(*row)

    return keyboard

@dp.callback_query_handler(lambda c: c.data.startswith('choose_plan') or c.data == "ignore")
async def choose_plan_callback(callback_query: types.CallbackQuery):
    if callback_query.data == "ignore":
        await bot.answer_callback_query(callback_query.id, text="")
    else:
        subscription = await database.get_subscription_by_user_id(callback_query.from_user.id)
        if subscription:
            await database.delete_subscription(subscription.subscription_id)
        _, frequency_id, duration_id = callback_query.data.split(':')
        frequency = await database.get_frequency(frequency_id)
        duration = await database.get_duration(duration_id)
        if pay_function_test:
            start_date = datetime.now()
            await database.add_subscription(start_date, start_date+timedelta(days=duration.value_in_day),
                                            frequency, duration, callback_query.from_user.id)
        await bot.answer_callback_query(callback_query.id, text="Вы выбрали тариф с частотой {} и продолжительностью "
                                                                "{}.".format(frequency.name, duration.name))

async def pay_function_test(user_id):
    return user_id in ADMIN_USER_ID

async def close_browser():
    await browser.close()

async def on_shutdown(dp):
    print("Закрыли браузер")
    await close_browser()

@dp.message_handler(lambda message: message.text == "/stop_script" and message.from_user.id in ADMIN_USER_ID)
async def stop_script(message: types.Message):
    await message.answer("Останавливаю скрипт...")
    dp.stop_polling()
    await on_shutdown(dp)

if __name__ == '__main__':
    executor.start_polling(dp, on_shutdown=on_shutdown)
