# Основные импорты и конфигурация
import sqlite3
import os
import telebot
import random
import string
from telebot import types
from config import CARDS_PER_PAGE, CARDS_PER_ROW, VENDORS_PER_ROW, TOKEN, STATE_ADD_VIDEOCARD, ADMIN_IDS, CHANNEL_ID
from get_total_videocards import get_total_videocards, get_card_id_by_name, get_unique_vendors, \
    get_total_videocards_by_vendor
bot = telebot.TeleBot(TOKEN)

# Глобальные переменные для отслеживания состояния пользователей
user_states = {}
user_data = {}
waiting_for_post = {}
post_data = {}

# Словарь для сопоставления производителей
MANUFACTURER_MAPPING = {
    "Другие": "Other",
    "AMD": "AMD",
    "Nvidia": "Nvidia",
    "Intel": "Intel"
}

# Функции для работы с консолями
def generate_unique_id(length=8):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def get_total_consoles():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Consoles")
    total_consoles = cursor.fetchone()[0]
    conn.close()
    return total_consoles


def search_consoles_by_name(search_term):
    terms = search_term.split()
    query_parts = []
    params = []

    for term in terms:
        query_parts.append("(LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ?)")
        wildcard_term = f"%{term.lower()}%"
        params.extend([wildcard_term, wildcard_term])

    query = "SELECT name, manufacturer FROM Consoles WHERE " + " AND ".join(query_parts)

    try:
        with sqlite3.connect('videocards.db') as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        return []


def send_console_search_results_buttons(bot, chat_id, search_term, results, page=1, message_id=None):
    CARDS_PER_PAGE = 5
    CARDS_PER_ROW = 2
    total_cards = len(results)
    total_pages = (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    if total_pages == 0:
        bot.send_message(chat_id, f"По запросу '{search_term}' ничего не найдено.")
        return

    start_idx = (page - 1) * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, total_cards)

    keyboard = types.InlineKeyboardMarkup(row_width=CARDS_PER_ROW)
    for result in results[start_idx:end_idx]:
        try:
            name, manufacturer = result
            button_text = f"{manufacturer} {name}"
            keyboard.add(types.InlineKeyboardButton(button_text, callback_data=f"console_model_{name}"))
        except ValueError:
            continue

    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"console_page_{search_term}_{page - 1}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"console_page_{search_term}_{page + 1}"))
        keyboard.row(*nav_buttons)

    text = f"Результаты поиска консолей для: '{search_term}' (стр. {page}/{total_pages})"

    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('console_page_'))
def handle_console_search_pagination(call):
    _, _, search_term, page = call.data.split('_')
    page = int(page)
    results = search_consoles_by_name(search_term)
    send_console_search_results_buttons(
        bot=bot,
        chat_id=call.message.chat.id,
        search_term=search_term,
        results=results,
        page=page,
        message_id=call.message.message_id
    )


def get_console_manufacturers():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT manufacturer FROM Consoles ORDER BY manufacturer")
    manufacturers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return manufacturers


def get_consoles_by_manufacturer(manufacturer):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM Consoles WHERE LOWER(manufacturer) = LOWER(?) ORDER BY name",
        (manufacturer.lower(),)
    )
    consoles = [row[0] for row in cursor.fetchall()]
    conn.close()
    return consoles


def get_console_info(console_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT screenshot FROM Consoles WHERE name = ?", (console_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


@bot.callback_query_handler(func=lambda call: call.data == "console")
def handle_console_button(call):
    manufacturers = get_console_manufacturers()
    if not manufacturers:
        bot.send_message(call.message.chat.id, "Производители игровых приставок не найдены в базе данных.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(manufacturer, callback_data=f"console_manufacturer_{manufacturer}")
        for manufacturer in manufacturers
    ]
    keyboard.add(*buttons)

    keyboard.row(
        types.InlineKeyboardButton("Назад", callback_data="back_to_main"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    bot.send_message(call.message.chat.id, "Выберите производителя игровой приставки:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("console_manufacturer_"))
def handle_console_manufacturer(call):
    manufacturer = call.data.split("console_manufacturer_")[1]
    consoles = get_consoles_by_manufacturer(manufacturer)
    if not consoles:
        bot.send_message(call.message.chat.id, f"Консоли производителя {manufacturer} не найдены.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for console in consoles:
        keyboard.add(types.InlineKeyboardButton(console, callback_data=f"console_model_{console}"))

    keyboard.row(
        types.InlineKeyboardButton("Назад", callback_data="console"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    bot.send_message(call.message.chat.id, f"Выберите модель консоли {manufacturer}:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("console_model_"))
def handle_console_model(call):
    if not is_user_subscribed(call.message.chat.id):
        send_subscription_request(call.message.chat.id)
        return

    console_name = call.data.split("console_model_")[1]
    screenshot_path = get_console_info(console_name)

    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT manufacturer FROM Consoles WHERE name = ?", (console_name,))
    result = cursor.fetchone()
    conn.close()

    manufacturer = result[0] if result else "Неизвестный производитель"

    text = (
        "Для каждой консоли тяжело подобрать ТП. "
        "Поэтому в большинстве случаев рекомендуем использовать очень мягкие термопрокладки.\n\n"
        f"{manufacturer} {console_name}"
    )

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        types.InlineKeyboardButton("В начало", callback_data="back_to_main"),
        types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as photo:
            bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=keyboard)
    else:
        bot.send_message(call.message.chat.id, f"Фото для {manufacturer} {console_name} не найдено.\n\n{text}",
                         reply_markup=keyboard)


# Функции для работы с материнскими платами
def get_total_motherboards():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Motherboards")
    total_motherboards = cursor.fetchone()[0]
    conn.close()
    return total_motherboards


@bot.callback_query_handler(func=lambda call: call.data.startswith('motherboard_page_'))
def handle_motherboard_search_pagination(call):
    _, _, search_term, page = call.data.split('_')
    page = int(page)
    results = search_motherboards_by_name(search_term)
    send_motherboard_search_results_buttons(
        bot=bot,
        chat_id=call.message.chat.id,
        search_term=search_term,
        results=results,
        page=page,
        message_id=call.message.message_id
    )


def search_motherboards_by_name(search_term):
    terms = search_term.split()
    query_parts = []
    params = []

    for term in terms:
        query_parts.append("(LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ?)")
        wildcard_term = f"%{term.lower()}%"
        params.extend([wildcard_term, wildcard_term])

    query = "SELECT name, manufacturer FROM Motherboards WHERE " + " AND ".join(query_parts)

    try:
        with sqlite3.connect('videocards.db') as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        return []


def get_motherboard_manufacturers():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT manufacturer FROM Motherboards ORDER BY LOWER(manufacturer)")
    manufacturers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return manufacturers


def get_motherboards_by_manufacturer(manufacturer):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM Motherboards WHERE LOWER(manufacturer) = LOWER(?) ORDER BY name",
        (manufacturer.lower(),)
    )
    motherboards = [row[0] for row in cursor.fetchall()]
    conn.close()
    return motherboards


def get_motherboard_info(motherboard_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT screenshot FROM Motherboards WHERE name = ?", (motherboard_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


@bot.callback_query_handler(func=lambda call: call.data == "motherboard")
def handle_motherboard_button(call):
    bot.answer_callback_query(call.id)
    manufacturers = get_motherboard_manufacturers()
    if not manufacturers:
        bot.send_message(call.message.chat.id, "Производители материнских плат не найдены в базе данных.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(manufacturer, callback_data=f"motherboard_manufacturer_{manufacturer}")
        for manufacturer in manufacturers
    ]
    keyboard.add(*buttons)

    keyboard.row(
        types.InlineKeyboardButton("Назад", callback_data="back_to_main"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    bot.send_message(call.message.chat.id, "Выберите производителя материнской платы:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data == "motherboard")
def handle_motherboard_button(call):
    manufacturers = get_motherboard_manufacturers()
    if not manufacturers:
        bot.send_message(call.message.chat.id, "Производители материнских плат не найдены в базе данных.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        types.InlineKeyboardButton(manufacturer, callback_data=f"motherboard_manufacturer_{manufacturer}")
        for manufacturer in manufacturers
    ]
    keyboard.add(*buttons)
    keyboard.add(types.InlineKeyboardButton("Назад", callback_data="back_to_main"))

    bot.send_message(call.message.chat.id, "Выберите производителя материнской платы:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("motherboard_manufacturer_"))
def handle_motherboard_manufacturer(call):
    manufacturer = call.data.split("motherboard_manufacturer_")[1]
    motherboards = get_motherboards_by_manufacturer(manufacturer)
    if not motherboards:
        bot.send_message(call.message.chat.id, f"Материнские платы производителя {manufacturer} не найдены.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for motherboard in motherboards:
        keyboard.add(types.InlineKeyboardButton(motherboard, callback_data=f"motherboard_model_{motherboard}"))

    keyboard.row(
        types.InlineKeyboardButton("Назад", callback_data="motherboard"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    bot.send_message(call.message.chat.id, f"Выберите модель материнской платы {manufacturer}:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("motherboard_model_"))
def handle_motherboard_model(call):
    if not is_user_subscribed(call.message.chat.id):
        send_subscription_request(call.message.chat.id)
        return

    motherboard_name = call.data.split("motherboard_model_")[1]
    screenshot_path = get_motherboard_info(motherboard_name)

    text = (
        "Для каждого ноутбука тяжело подобрать ТП. "
        "Поэтому в большинстве случаев рекомендуем использовать очень мягкие термопрокладки.\n\n"
        f"{motherboard_name}"
    )

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.row(
        types.InlineKeyboardButton("В начало", callback_data="back_to_main"),
        types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    if screenshot_path and os.path.exists(screenshot_path):
        with open(screenshot_path, "rb") as photo:
            bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=keyboard)
    else:
        bot.send_message(call.message.chat.id, f"Фото для {motherboard_name} не найдено.\n\n{text}",
                         reply_markup=keyboard)


def send_laptop_search_results_buttons(bot, chat_id, search_term, results, page=1, message_id=None):
    CARDS_PER_PAGE = 5
    CARDS_PER_ROW = 2
    total_cards = len(results)
    total_pages = (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE
    if total_pages == 0:
        bot.send_message(chat_id, f"По запросу '{search_term}' ничего не найдено.")
        return

    start_idx = (page - 1) * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, total_cards)

    keyboard = types.InlineKeyboardMarkup(row_width=CARDS_PER_ROW)
    for result in results[start_idx:end_idx]:
        try:
            name, manufacturer = result
            button_text = f"{manufacturer} {name}"
            keyboard.add(types.InlineKeyboardButton(button_text, callback_data=f"laptop_model_{name}"))
        except ValueError:
            continue

    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton("⬅️", callback_data=f"laptop_page_{search_term}_{page - 1}"))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton("➡️", callback_data=f"laptop_page_{search_term}_{page + 1}"))
        keyboard.row(*nav_buttons)

    text = f"Результаты поиска ноутбуков для: '{search_term}' (стр. {page}/{total_pages})"
    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith('laptop_page_'))
def handle_laptop_search_pagination(call):
    _, _, search_term, page = call.data.split('_')
    page = int(page)
    results = search_laptops_by_name(search_term)
    send_laptop_search_results_buttons(
        bot=bot,
        chat_id=call.message.chat.id,
        search_term=search_term,
        results=results,
        page=page,
        message_id=call.message.message_id
    )


def search_laptops_by_name(search_term):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()

    if ' ' in search_term:
        # Если несколько слов, ищем каждое в отдельности
        terms = search_term.split()
        query_parts = " AND ".join(["(LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ?)"] * len(terms))
        params = []
        for term in terms:
            wildcard_term = f"%{term.lower()}%"
            params.extend([wildcard_term, wildcard_term])
    else:
        # Если одно слово, ищем как раньше
        query_parts = "(LOWER(name) LIKE ? OR LOWER(manufacturer) LIKE ?)"
        params = [f"%{search_term.lower()}%", f"%{search_term.lower()}%"]

    query = f"SELECT name, manufacturer FROM Laptops WHERE {query_parts}"
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    return results


def get_laptop_manufacturers():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT manufacturer FROM Laptops ORDER BY manufacturer")
    manufacturers = [row[0] for row in cursor.fetchall()]
    conn.close()
    return manufacturers


def get_laptops_by_manufacturer(manufacturer):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM Laptops WHERE manufacturer = ? ORDER BY name", (manufacturer,))
    laptops = [row[0] for row in cursor.fetchall()]
    conn.close()
    return laptops


def get_laptop_info(laptop_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT screenshot FROM Laptops WHERE name = ?", (laptop_name,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None


@bot.callback_query_handler(func=lambda call: call.data == "laptop")
def handle_laptop_button(call):
    manufacturers = get_laptop_manufacturers()
    if not manufacturers:
        bot.send_message(call.message.chat.id, "Производители ноутбуков не найдены в базе данных.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)

    buttons = [
        types.InlineKeyboardButton(manufacturer, callback_data=f"laptop_manufacturer_{manufacturer}")
        for manufacturer in manufacturers
    ]
    keyboard.add(*buttons)

    keyboard.add(types.InlineKeyboardButton("Назад", callback_data="back_to_main"))

    bot.send_message(call.message.chat.id, "Выберите производителя ноутбука:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("laptop_manufacturer_"))
def handle_laptop_manufacturer(call):
    manufacturer = call.data.split("laptop_manufacturer_")[1]
    laptops = get_laptops_by_manufacturer(manufacturer)
    if not laptops:
        bot.send_message(call.message.chat.id, f"Ноутбуки производителя {manufacturer} не найдены.")
        return

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    for laptop in laptops:
        keyboard.add(types.InlineKeyboardButton(laptop, callback_data=f"laptop_model_{laptop}"))

    keyboard.row(
        types.InlineKeyboardButton("Назад", callback_data="laptop"),
        types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp")
    )

    bot.send_message(call.message.chat.id, f"Выберите модель ноутбука {manufacturer}:", reply_markup=keyboard)


@bot.callback_query_handler(func=lambda call: call.data.startswith("laptop_model_"))
def handle_laptop_model(call):
    if not is_user_subscribed(call.message.chat.id):
        send_subscription_request(call.message.chat.id)
        return

    laptop_name = call.data.split("laptop_model_")[1]
    screenshot_path = get_laptop_info(laptop_name)

    text = (
        "Для каждого ноутбука тяжело подобрать ТП. "
        "Поэтому в большинстве случаев рекомендуем использовать очень мягкие термопрокладки.\n\n"
        f"{laptop_name}"
    )

    if screenshot_path and os.path.exists(screenshot_path):
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.row(
            types.InlineKeyboardButton("В начало", callback_data="back_to_main"),
            types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot")
        )
        keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

        with open(screenshot_path, "rb") as photo:
            bot.send_photo(call.message.chat.id, photo, caption=text, reply_markup=keyboard)
    else:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.row(
            types.InlineKeyboardButton("В начало", callback_data="back_to_main"),
            types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot")
        )
        keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
        bot.send_message(call.message.chat.id, f"Фото для {laptop_name} не найдено.\n\n{text}", reply_markup=keyboard)


def get_total_laptops():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(id) FROM Laptops")
    total_laptops = cursor.fetchone()[0]
    conn.close()
    return total_laptops


def get_videocards_by_vendor_page(producer, vendor, page):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    offset = (page - 1) * CARDS_PER_PAGE
    query = """
        SELECT name
        FROM Videocards
        WHERE LOWER(manufacturer) = LOWER(?) AND LOWER(vendor) = LOWER(?)
        ORDER BY name
        LIMIT ? OFFSET ?
    """
    cursor.execute(query, (producer, vendor, CARDS_PER_PAGE, offset))
    videocards = [row[0] for row in cursor.fetchall()]
    conn.close()
    return videocards


def send_videocards_buttons(chat_id, producer, vendor, page=1, message_id=None):
    total_cards = get_total_videocards_by_vendor(producer, vendor)
    videocards = get_videocards_by_vendor_page(producer, vendor, page)

    total_pages = (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    keyboard = types.InlineKeyboardMarkup(row_width=CARDS_PER_ROW)
    for i in range(0, len(videocards), CARDS_PER_ROW):
        row_buttons = [
            types.InlineKeyboardButton(card,
                                       callback_data=f"videocard_{producer}_{vendor}_{get_card_id_by_name(producer, vendor, card)}")
            for card in videocards[i:i + CARDS_PER_ROW]
        ]
        keyboard.add(*row_buttons)

    navigation_buttons = []
    if page > 1:
        navigation_buttons.append(
            types.InlineKeyboardButton("⬅️", callback_data=f"prev_{producer}_{vendor}_{page - 1}")
        )
    if page * CARDS_PER_PAGE < total_cards:
        navigation_buttons.append(
            types.InlineKeyboardButton("➡️", callback_data=f"next_{producer}_{vendor}_{page + 1}")
        )
    keyboard.add(*navigation_buttons)
    keyboard.add(
        types.InlineKeyboardButton("Назад", callback_data=f"back_to_vendor_{producer}"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))

    text = (
        f"3/3 Видеокарты - {producer.capitalize()} - {vendor.capitalize()}\n"
        f"Страница {page} из {total_pages}\nВыберите видеокарту:"
    )

    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)


def get_videocard_info(producer, vendor, card_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    query = """
        SELECT name, screenshot
        FROM Videocards
        WHERE LOWER(manufacturer) = LOWER(?) AND LOWER(vendor) = LOWER(?) AND LOWER(name) = LOWER(?)
    """
    cursor.execute(query, (producer, vendor, card_name))
    result = cursor.fetchone()
    conn.close()
    return result


def is_user_subscribed(user_id):
    try:
        chat_member = bot.get_chat_member(CHANNEL_ID, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        return False


def send_videocard_info(chat_id, producer=None, vendor=None, card_id=None, message_id=None):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    query = """
        SELECT name, screenshot, vendor
        FROM Videocards
        WHERE ROWID = ?
    """
    cursor.execute(query, (card_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:  # Проверяем, что данные существуют
        bot.send_message(chat_id, "Информация о выбранной видеокарте не найдена.",
                         reply_markup=get_videocard_keyboard(producer, vendor))
        return

    name, screenshot, vendor = result
    text = (
        "Для каждой видеокарты тяжело подобрать ТП. "
        "Поэтому в большинстве случаев рекомендуем использовать очень мягкие термопрокладки.\n\n"
        f"{vendor} {name}"
    )

    if screenshot and os.path.exists(screenshot):
        with open(screenshot, 'rb') as image:
            bot.send_photo(chat_id, image, caption=text, reply_markup=get_videocard_keyboard(producer, vendor))
    else:
        bot.send_message(chat_id, "Скриншот для этой видеокарты отсутствует.",
                         reply_markup=get_videocard_keyboard(producer, vendor))


def send_subscription_request(chat_id):
    bot.send_message(
        chat_id,
        "Чтобы продолжить, подпишитесь на наш канал по кнопке ниже, а затем повторите запрос!",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton("Подписаться", url=f"https://t.me/+LcPrRrK1QM00MjYy")
        )
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith('videocard_'))
def handle_videocard_callback(call):
    bot.answer_callback_query(call.id)
    if not is_user_subscribed(call.message.chat.id):
        send_subscription_request(call.message.chat.id)
        return

    parts = call.data.split("_")
    if len(parts) != 4 or not parts[3].isdigit():  # Проверяем формат данных
        bot.send_message(call.message.chat.id, "Произошла ошибка. Попробуйте снова.")
        return

    _, producer, vendor, card_id = parts
    card_id = int(card_id)
    send_videocard_info(call.message.chat.id, producer, vendor, card_id)


def get_videocard_keyboard(producer, vendor):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("В начало", callback_data="back_to_main"),
        types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
    return keyboard


def send_vendors_keyboard(chat_id, display_manufacturer, vendors, internal_manufacturer=None):
    if internal_manufacturer is None:
        internal_manufacturer = display_manufacturer

    keyboard = types.InlineKeyboardMarkup(row_width=VENDORS_PER_ROW)
    for i in range(0, len(vendors), VENDORS_PER_ROW):
        row_buttons = [
            types.InlineKeyboardButton(vendor, callback_data=f"vendor_{internal_manufacturer}_{vendor}")
            for vendor in vendors[i:i + VENDORS_PER_ROW]
        ]
        keyboard.add(*row_buttons)
    keyboard.add(
        types.InlineKeyboardButton("Назад", callback_data="gpu"),
        types.InlineKeyboardButton("В начало", callback_data="back_to_main")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
    bot.send_message(chat_id, f"2/3 Вендоры - {display_manufacturer}\nВыберите вендора:", reply_markup=keyboard)


def search_videocards_by_name(search_term):
    terms = search_term.split()
    query_parts = []
    params = []
    for term in terms:
        query_parts.append("(LOWER(name) LIKE ? OR LOWER(vendor) LIKE ? OR LOWER(manufacturer) LIKE ?)")
        wildcard_term = f"%{term.lower()}%"
        params.extend([wildcard_term, wildcard_term, wildcard_term])
    query = "SELECT ROWID, name, vendor, manufacturer FROM Videocards WHERE " + " AND ".join(query_parts)
    try:
        with sqlite3.connect('videocards.db') as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
        return results
    except sqlite3.Error as e:
        print(f"Ошибка SQL: {e}")
        return []

@bot.callback_query_handler(func=lambda call: call.data.startswith('page_'))
def handle_search_pagination(call):
    bot.answer_callback_query(call.id)
    _, search_term, page = call.data.split('_')
    page = int(page)
    results = search_videocards_by_name(search_term)
    send_search_results_buttons(
        bot=bot,
        chat_id=call.message.chat.id,
        search_term=search_term,
        results=results,
        page=page,
        message_id=call.message.message_id,
        device_type="Видеокарты"
    )

def send_search_results_buttons(bot, chat_id, search_term, results, page=1, message_id=None, device_type=None):
    CARDS_PER_PAGE = 5
    CARDS_PER_ROW = 2
    total_cards = len(results)
    total_pages = (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    if total_pages == 0:
        bot.send_message(chat_id, f"По запросу '{search_term}' ничего не найдено.")
        return

    start_idx = (page - 1) * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, total_cards)

    keyboard = types.InlineKeyboardMarkup(row_width=CARDS_PER_ROW)

    for result in results[start_idx:end_idx]:
        try:
            if len(result) >= 4:
                rowid, name, vendor, manufacturer = result
                button_text = f"{manufacturer} {vendor} {name}"
                keyboard.add(types.InlineKeyboardButton(
                    button_text,
                    callback_data=f"device_videocard_{rowid}"
                ))
            else:
                print(f"Неполные данные: {result}")
        except Exception as e:
            print(f"Ошибка при обработке результата: {e}, данные: {result}")

    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(types.InlineKeyboardButton(
                "⬅️",
                callback_data=f"search_prev_{search_term}_{page - 1}"
            ))
        if page < total_pages:
            nav_buttons.append(types.InlineKeyboardButton(
                "➡️",
                callback_data=f"search_next_{search_term}_{page + 1}"
            ))
        keyboard.row(*nav_buttons)

    text = f"Результаты поиска {device_type or 'устройств'} для: '{search_term}' (стр. {page}/{total_pages})"
    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)

@bot.callback_query_handler(func=lambda call: call.data.startswith('device_videocard_'))
def handle_videocard_selection(call):
    bot.answer_callback_query(call.id)

    try:
        card_id = int(call.data.split('_')[-1])
        send_videocard_info(
            chat_id=call.message.chat.id,
            card_id=card_id,
            message_id=call.message.message_id
        )
    except Exception as e:
        bot.send_message(call.message.chat.id, f"Ошибка при обработке выбора видеокарты: {e}")


@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return

    users_count = get_users_count()
    bot.send_message(message.chat.id, f"Количество пользователей, получающих рассылку: {users_count}")
def get_all_users():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM Users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_users_count():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM Users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def add_user_to_database(user_id, username, first_name, last_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()[0] > 0

    if not exists:
        cursor.execute("""
            INSERT INTO Users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, last_name))
        conn.commit()

    conn.close()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    username = message.from_user.username
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name

    add_user_to_database(user_id, username, first_name, last_name)

    total_videocards = get_total_videocards() or 0
    total_laptops = get_total_laptops() or 0
    total_motherboards = get_total_motherboards() or 0
    total_consoles = get_total_consoles() or 0

    welcome_text = (
        "Приветствуем тебя в нашем боте, созданным командой PCDAT!\n"
        "С его помощью ты можешь найти толщины термопрокладок для различных девайсов.\n"
        "Посмотреть все команды /help\n\n"
        'Ждем тебя в нашем чате по <a href="https://t.me/+jhQKs5sGZXEyN2Yy">СБОРКЕ ПК</a>, нас уже 7.000 человек!\n\n'
        "Выбери нужную категорию из списка:\n"
        "ТП - термопрокладки"
    )

    # Создаем клавиатуру
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(f"· Видеокарты ({total_videocards} шт.)", callback_data="gpu"))
    keyboard.add(types.InlineKeyboardButton(f"· Ноутбуки ({total_laptops} шт.)", callback_data="laptop"))
    keyboard.add(types.InlineKeyboardButton(f"· Материнские платы ({total_motherboards} шт.)", callback_data="motherboard"))
    keyboard.add(types.InlineKeyboardButton(f"· Игровые приставки ({total_consoles} шт.)", callback_data="console"))

    keyboard.row(
        types.InlineKeyboardButton("Нравится ваш бот", callback_data="like_bot"),
        types.InlineKeyboardButton("Связь с разработчиками", url="https://t.me/morgikoff")
    )
    keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
    keyboard.add(types.InlineKeyboardButton("Тесты термопаст", callback_data="tests_tp"))

    try:
        bot.send_message(
            message.chat.id,
            welcome_text,
            reply_markup=keyboard,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

@bot.callback_query_handler(func=lambda call: call.data == "tests_tp")
def handle_tests_button(call):
    send_tests(call.message)

@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call):
    bot.answer_callback_query(call.id)
    if call.data == "gpu":
        gpu_text = "1/3 Видеокарты\nВыберите производителя графического чипа:"
        gpu_keyboard = types.InlineKeyboardMarkup()
        gpu_keyboard.row(
            types.InlineKeyboardButton("AMD", callback_data="gpu_amd"),
            types.InlineKeyboardButton("Nvidia", callback_data="gpu_nvidia"),
            types.InlineKeyboardButton("Intel", callback_data="gpu_intel"),
            types.InlineKeyboardButton("Другие", callback_data="gpu_other")

        )
        gpu_keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
        gpu_keyboard.add(types.InlineKeyboardButton("Назад", callback_data="back_to_main"))
        bot.send_message(call.message.chat.id, gpu_text, reply_markup=gpu_keyboard)

    elif call.data == "back_to_main":
        send_welcome(call.message)

    elif call.data == "gpu_amd":
        vendors = get_unique_vendors("AMD")
        send_vendors_keyboard(call.message.chat.id, "AMD", vendors)

    elif call.data == "gpu_nvidia":
        vendors = get_unique_vendors("Nvidia")
        send_vendors_keyboard(call.message.chat.id, "Nvidia", vendors)

    elif call.data == "gpu_intel":
        vendors = get_unique_vendors("Intel")
        send_vendors_keyboard(call.message.chat.id, "Intel", vendors)


    elif call.data == "gpu_other":
        internal_manufacturer = "Other"
        display_manufacturer = "Другие"
        vendors = get_unique_vendors(internal_manufacturer)
        send_vendors_keyboard(call.message.chat.id, display_manufacturer, vendors, internal_manufacturer)

    elif call.data == "add_tp":
        add_videocard_request(call.message)

    elif call.data.startswith("next_") or call.data.startswith("prev_"):
        bot.answer_callback_query(call.id)
        _, producer, vendor, page = call.data.split("_")
        send_videocards_buttons(
            chat_id=call.message.chat.id,
            producer=producer,
            vendor=vendor,
            page=int(page),
            message_id=call.message.message_id
        )

    elif call.data.startswith("vendor_"):
        _, producer, vendor = call.data.split("_")
        send_videocards_buttons(call.message.chat.id, producer, vendor)

    elif call.data.startswith("back_to_vendor_"):
        _, producer = call.data.split("_")[2:]
        vendors = get_unique_vendors(producer)
        send_vendors_keyboard(call.message.chat.id, producer, vendors)

    elif call.data.startswith("card_"):
        data_parts = call.data.split("_")
        if len(data_parts) > 1 and data_parts[1].isdigit():
            card_id = int(data_parts[1])
        else:
            bot.send_message(call.message.chat.id, "Произошла ошибка. Попробуйте снова.")
            return
        send_videocard_info(call.message.chat.id, None, None, card_id)

    elif call.data == "like_bot":
        text = (
            "Мы очень рады если смогли кому-то помочь разработав данного бота!\n\n"
            "Если вы хотите нас отблагодарить, то присоединяйтесь к обсуждению в наших чатах и подписывайтесь на каналы!\n"
            "Наши каналы:\n\n"
            "[pcdatshop](https://t.me/+LcPrRrK1QM00MjYy) - комплектующие по низким ценам\n"
            "[pcdatestet](https://t.me/+bV57LPUZSVJkZDMy) - идеи для твоего рабочего места\n"
            "[pcdatproject](https://t.me/+yywIQhj1bks3ZGUy) - следи за выходом наших IT проектов и участвуй в голосованиях по их улучшению\n\n"
            "Наши чаты:\n"
            "[pcdatchat](https://t.me/+jhQKs5sGZXEyN2Yy) - наш чат по сборке ПК\n"
            "[pcdatchat2](https://t.me/+fdHoJUmyIzVkNTdi) - наш чат по компьютерной помощи\n\n"
            "Развивай компьютерное сообщество вместе с нами!"
        )
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("Связь с разработчиками", url="https://t.me/morgikoff"),
            types.InlineKeyboardButton("В начало", callback_data="back_to_main")
        )
        keyboard.add(types.InlineKeyboardButton("Добавить ТП", callback_data="add_tp"))
        bot.send_message(
            call.message.chat.id,
            text,
            reply_markup=keyboard,
            parse_mode="Markdown",
            disable_web_page_preview=True
        )



    elif call.data.startswith("search_next_") or call.data.startswith("search_prev_"):
        _, direction, search_term, page = call.data.split("_")
        page = int(page)
        results = search_videocards_by_name(search_term)
        if not isinstance(results, list):
            bot.send_message(call.message.chat.id, "Произошла ошибка при поиске. Попробуйте снова.")
            return
        send_search_results_buttons(bot, call.message.chat.id, search_term, results, page)

    elif call.data.startswith("back_to_videocard"):
        _, producer, vendor = call.data.split("_")[2:]
        send_videocards_buttons(call.message.chat.id, producer, vendor)


def get_videocards_by_search(search_term):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    query = """
        SELECT ROWID, name, vendor, manufacturer
        FROM Videocards
        WHERE LOWER(name) LIKE LOWER(?) OR LOWER(vendor) LIKE LOWER(?)
    """
    search_term_with_wildcards = f"%{search_term.lower()}%"
    cursor.execute(query, (search_term_with_wildcards, search_term_with_wildcards))
    results = cursor.fetchall()
    conn.close()
    return results


def send_motherboard_search_results_buttons(bot, chat_id, search_term, results, page=1, message_id=None):
    CARDS_PER_PAGE = 5
    CARDS_PER_ROW = 2
    total_cards = len(results)
    total_pages = (total_cards + CARDS_PER_PAGE - 1) // CARDS_PER_PAGE

    if total_pages == 0:
        bot.send_message(chat_id, f"По запросу '{search_term}' ничего не найдено.")
        return

    start_idx = (page - 1) * CARDS_PER_PAGE
    end_idx = min(start_idx + CARDS_PER_PAGE, total_cards)

    keyboard = types.InlineKeyboardMarkup(row_width=CARDS_PER_ROW)
    for result in results[start_idx:end_idx]:
        try:
            name, manufacturer = result
            button_text = f"{manufacturer} {name}"
            keyboard.add(types.InlineKeyboardButton(button_text, callback_data=f"motherboard_model_{name}"))
        except ValueError:
            continue

    if total_pages > 1:
        nav_buttons = []
        if page > 1:
            nav_buttons.append(
                types.InlineKeyboardButton("⬅️", callback_data=f"motherboard_page_{search_term}_{page - 1}"))
        if page < total_pages:
            nav_buttons.append(
                types.InlineKeyboardButton("➡️", callback_data=f"motherboard_page_{search_term}_{page + 1}"))
        keyboard.row(*nav_buttons)

    text = f"Результаты поиска материнских плат для: '{search_term}' (стр. {page}/{total_pages})"

    if message_id:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=keyboard
        )
    else:
        bot.send_message(chat_id, text, reply_markup=keyboard)


@bot.message_handler(commands=['search'])
def search_command(message):
    if not is_user_subscribed(message.chat.id):
        send_subscription_request(message.chat.id)
        return

    search_term = message.text[len('/search '):].strip()
    if not search_term:
        bot.send_message(message.chat.id, "Пожалуйста, введите запрос для поиска в формате /search [название устройства].")
        return

    videocard_results = search_videocards_by_name(search_term)
    laptop_results = search_laptops_by_name(search_term)
    motherboard_results = search_motherboards_by_name(search_term)
    console_results = search_consoles_by_name(search_term)

    found_results = False

    if videocard_results:
        send_search_results_buttons(bot, message.chat.id, search_term, videocard_results, device_type="Видеокарты")
        found_results = True

    if laptop_results:
        send_laptop_search_results_buttons(bot, message.chat.id, search_term, laptop_results)
        found_results = True

    if motherboard_results:
        send_motherboard_search_results_buttons(bot, message.chat.id, search_term, motherboard_results)
        found_results = True

    if console_results:
        send_console_search_results_buttons(bot, message.chat.id, search_term, console_results)
        found_results = True

    if not found_results:
        bot.send_message(message.chat.id, f"По запросу '{search_term}' ничего не найдено.")


@bot.message_handler(commands=['addv'])
def add_videocard_request(message):
    user_states[message.chat.id] = STATE_ADD_VIDEOCARD
    bot.send_message(
        message.chat.id,
        "*Введите данные о устройстве и прикрепите фото в одном сообщении:*\n\n"
        "  (videocard, laptop, motherboard или console)\n"
        " \n"
        "  (только для видеокарт)\n"
        " \n\n"
        "*Пример для видеокарты:*\n\n"
        "videocard\n"
        "Nvidia\n"
        "ASUS\n"
        "RTX 3060 Dual OC *12 GB*\n\n"
        "*Пример для ноутбука:*\n\n"
        "laptop\n"
        "Dell\n"
        "XPS 15\n\n"
        "*Пример для материнской платы:*\n\n"
        "motherboard\n"
        "ASUS\n"
        "ROG Strix Z690-E Gaming WiFi \n\n"
        "*Пример для игровой приставки:*\n\n"
        "console\n"
        "Sony\n"
        "PlayStation 5\n\n"
        "И прикрепите фото к этому сообщению.\n\n"
        "Если вы хотите отменить добавление, напишите **Отмена**.",
        parse_mode="Markdown"
    )


@bot.message_handler(func=lambda message: user_states.get(message.chat.id) == STATE_ADD_VIDEOCARD,
                     content_types=['text', 'photo'])
def handle_add_device_with_photo(message):
    chat_id = message.chat.id
    if message.text and message.text.strip().lower() == "отмена":
        bot.send_message(chat_id, "Добавление устройства отменено.")
        user_states.pop(chat_id, None)
        return

    if not message.photo:
        bot.send_message(chat_id, "Пожалуйста, прикрепите фото к сообщению.")
        return

    if not message.caption:
        bot.send_message(chat_id, "Пожалуйста, добавьте текст с данными о устройстве.")
        return

    lines = message.caption.split("\n")
    if len(lines) < 2:
        bot.send_message(
            chat_id,
            "Пожалуйста, введите данные в правильном формате:\n"
            "<Девайс> (videocard или laptop)\n"
            "<Производитель>\n"
            "<Вендор> (только для видеокарт)\n"
            "<Полное название устройства>",
            parse_mode="Markdown"
        )
        return

    device_type = lines[0].strip().lower()
    manufacturer = lines[1].strip()

    if device_type == "videocard":
        if len(lines) < 4:
            bot.send_message(chat_id, "Для видеокарты необходимо указать производителя, вендора и полное название.")
            return
        vendor = lines[2].strip()
        name = lines[3].strip()
        user_data[chat_id] = {
            "device_type": device_type,
            "manufacturer": manufacturer,
            "vendor": vendor,
            "name": name
        }
        handle_add_videocard_with_photo(message, chat_id, user_data[chat_id])


    elif device_type == "motherboard":
        if len(lines) < 3:
            bot.send_message(chat_id, "Для материнской платы необходимо указать производителя и полное название.")
            return
        manufacturer = lines[1].strip()
        name = lines[2].strip()
        user_data[chat_id] = {
            "device_type": device_type,
            "manufacturer": manufacturer,
            "name": name
        }
        handle_add_motherboard_with_photo(message, chat_id, user_data[chat_id])

    elif device_type == "console":
        if len(lines) < 3:
            bot.send_message(chat_id, "Для игровой приставки необходимо указать производителя и полное название.")
            return
        manufacturer = lines[1].strip()
        name = lines[2].strip()
        user_data[chat_id] = {
            "device_type": device_type,
            "manufacturer": manufacturer,
            "name": name
        }
        handle_add_console_with_photo(message, chat_id, user_data[chat_id])

    elif device_type == "laptop":
        if len(lines) < 3:
            bot.send_message(chat_id, "Для ноутбука необходимо указать производителя и полное название.")
            return
        name = lines[2].strip()
        user_data[chat_id] = {
            "device_type": device_type,
            "manufacturer": manufacturer,
            "name": name
        }
        handle_add_laptop_with_photo(message, chat_id, user_data[chat_id])

    else:
        bot.send_message(chat_id, "Неподдерживаемый тип устройства. Укажите 'videocard' или 'laptop'.")


def handle_add_console_with_photo(message, chat_id, user_entry):
    try:
        unique_id = generate_unique_id()

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        manufacturer = user_entry['manufacturer']
        name = user_entry['name']

        base_path = "Console"
        full_path = os.path.join(base_path, manufacturer, name)
        os.makedirs(full_path, exist_ok=True)

        file_name = f"{name}.jpg"
        file_path = os.path.join(full_path, file_name)

        with open(file_path, "wb") as new_file:
            new_file.write(downloaded_file)

        username = message.from_user.username if message.from_user.username else "Не указан"

        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Applications (application_id, user_id, device_type, manufacturer, name, screenshot_path, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (unique_id, chat_id, "console", manufacturer, name, file_path, "pending")
        )
        conn.commit()
        conn.close()

        for admin_id in ADMIN_IDS:
            with open(file_path, "rb") as photo:
                caption = (
                    f"📝 Новая заявка на добавление игровой приставки:\n"
                    f"ID заявки: {unique_id}\n"
                    f"Производитель: {manufacturer}\n"
                    f"Название: {name}\n"
                    f"Отправитель: @{username} (ID: {chat_id})\n"
                    f"/accept {unique_id} - подтвердить\n"
                    f"/cancel {unique_id} <причина> - отклонить\n"
                )
                bot.send_photo(admin_id, photo, caption=caption)

        bot.send_message(chat_id, "✅ Ваша заявка отправлена на рассмотрение модераторам.")
        user_states.pop(chat_id, None)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Произошла ошибка при обработке фото: {str(e)}")


def handle_add_videocard_with_photo(message, chat_id, user_entry):
    try:
        unique_id = generate_unique_id()

        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        manufacturer = user_entry['manufacturer']
        vendor = user_entry['vendor']
        name = user_entry['name']

        base_path = "Videocards"
        full_path = os.path.join(base_path, vendor, name)
        os.makedirs(full_path, exist_ok=True)

        file_name = f"{name}.jpg"
        file_path = os.path.join(full_path, file_name)
        with open(file_path, "wb") as new_file:
            new_file.write(downloaded_file)

        username = message.from_user.username if message.from_user.username else "Не указан"

        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Applications (application_id, user_id, device_type, manufacturer, vendor, name, screenshot_path, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (unique_id, chat_id, "videocard", manufacturer, vendor, name, file_path, "pending")
        )
        conn.commit()
        conn.close()

        for admin_id in ADMIN_IDS:
            with open(file_path, "rb") as photo:
                caption = (
                    f"📝 Новая заявка на добавление видеокарты:\n"
                    f"ID заявки: {unique_id}\n"
                    f"Производитель: {manufacturer}\n"
                    f"Вендор: {vendor}\n"
                    f"Название: {name}\n"
                    f"Отправитель: @{username} (ID: {chat_id})\n"
                    f"/accept {unique_id} - подтвердить\n"
                    f"/cancel {unique_id} <причина> - отклонить\n"
                )
                bot.send_photo(admin_id, photo, caption=caption)

        bot.send_message(chat_id, "✅ Ваша заявка отправлена на рассмотрение модераторам.")
        user_states.pop(chat_id, None)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Произошла ошибка при обработке фото: {str(e)}")


def handle_add_motherboard_with_photo(message, chat_id, user_entry):
    try:
        unique_id = generate_unique_id()
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        manufacturer = user_entry['manufacturer']
        name = user_entry['name']

        base_path = "Mother_board"
        full_path = os.path.join(base_path, f"{manufacturer} {name}")
        os.makedirs(full_path, exist_ok=True)

        file_name = f"{name}.jpg"
        file_path = os.path.join(full_path, file_name)

        with open(file_path, "wb") as new_file:
            new_file.write(downloaded_file)

        username = message.from_user.username if message.from_user.username else "Не указан"

        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Applications (application_id, user_id, device_type, manufacturer, name, screenshot_path, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (unique_id, chat_id, "motherboard", manufacturer, name, file_path, "pending")
        )
        conn.commit()
        conn.close()

        for admin_id in ADMIN_IDS:
            with open(file_path, "rb") as photo:
                caption = (
                    f"📝 Новая заявка на добавление материнской платы:\n"
                    f"ID заявки: {unique_id}\n"
                    f"Производитель: {manufacturer}\n"
                    f"Название: {name}\n"
                    f"Отправитель: @{username} (ID: {chat_id})\n"
                    f"/accept {unique_id} - подтвердить\n"
                    f"/cancel {unique_id} <причина> - отклонить\n"
                )
                bot.send_photo(admin_id, photo, caption=caption)

        bot.send_message(chat_id, "✅ Ваша заявка отправлена на рассмотрение модераторам.")
        user_states.pop(chat_id, None)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Произошла ошибка при обработке фото: {str(e)}")
def save_application_to_db(user_id, user_name, application_id, device_type):
    try:
        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO Applications (user_name, user_id, application_id, status, device_type)
            VALUES (?, ?, ?, ?, ?)
        """, (user_name, user_id, application_id, 'pending', device_type))
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error: {e}")
    finally:
        if conn:
            conn.close()

def handle_add_laptop_with_photo(message, chat_id, user_entry):
    try:
        unique_id = generate_unique_id()
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)

        manufacturer = user_entry['manufacturer']
        name = user_entry['name']

        base_path = "Laptop"
        full_path = os.path.join(base_path, f"{manufacturer} {name}")
        os.makedirs(full_path, exist_ok=True)

        file_name = f"{name}.jpg"
        file_path = os.path.join(full_path, file_name)

        with open(file_path, "wb") as new_file:
            new_file.write(downloaded_file)

        username = message.from_user.username if message.from_user.username else "Не указан"

        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO Applications (application_id, user_id, device_type, manufacturer, name, screenshot_path, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (unique_id, chat_id, "laptop", manufacturer, name, file_path, "pending")
        )
        conn.commit()
        conn.close()

        for admin_id in ADMIN_IDS:
            with open(file_path, "rb") as photo:
                caption = (
                    f"📝 Новая заявка на добавление ноутбука:\n"
                    f"ID заявки: {unique_id}\n"
                    f"Производитель: {manufacturer}\n"
                    f"Название: {name}\n"
                    f"Отправитель: @{username} (ID: {chat_id})\n"
                    f"/accept {unique_id} - подтвердить\n"
                    f"/cancel {unique_id} <причина> - отклонить\n"
                )
                bot.send_photo(admin_id, photo, caption=caption)

        bot.send_message(chat_id, "✅ Ваша заявка отправлена на рассмотрение модераторам.")
        user_states.pop(chat_id, None)

    except Exception as e:
        bot.send_message(chat_id, f"❌ Произошла ошибка при обработке фото: {str(e)}")

@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message,
                 "/start - Запустить бота\n/help - Показать этот список команд\n/addv - Добавить свои ТП\n/search <данные> - Поиск видеокарт по вашим данным\n/tests - Тесты термопрокладок\n/top - Топ пользователей, добавляющих заявки")

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    chat_id = message.chat.id

    if waiting_for_post.get(chat_id) != "waiting_for_media":
        return

    try:
        media_file_id = message.photo[-1].file_id

        post_data[chat_id]['media'] = {'file_id': media_file_id, 'type': "photo"}
        text = post_data[chat_id]['text']

        bot.send_photo(
            chat_id=chat_id,
            photo=media_file_id,
            caption=text,
            parse_mode="HTML"
        )

        keyboard = types.ReplyKeyboardMarkup(
            resize_keyboard=True,
            one_time_keyboard=True,
            row_width=2
        )
        keyboard.add(
            types.KeyboardButton("Да"),
            types.KeyboardButton("Нет")
        )
        bot.send_message(
            chat_id,
            "Подтвердите отправку поста (Да/Нет).",
            reply_markup=keyboard
        )

        waiting_for_post[chat_id] = "waiting_for_confirmation"

    except Exception as e:
        bot.send_message(chat_id, f"Произошла ошибка при обработке фото. Попробуйте снова.")

@bot.message_handler(commands=['tests'])
def send_tests(message):
    photo_paths = [
        "test/test1.jpg",
        "test/test2.jpg",
        "test/test3.jpg"
    ]
    caption = "Тесты термопаст"

    media_group = []
    try:
        photos = [open(photo_path, 'rb') for photo_path in photo_paths]
        for index, photo in enumerate(photos):
            if index == 0:
                media_group.append(types.InputMediaPhoto(photo, caption=caption))
            else:
                media_group.append(types.InputMediaPhoto(photo))
        bot.send_media_group(message.chat.id, media_group)
    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка при отправке альбома: {e}")

    finally:
        for photo in photos:
            photo.close()

def get_top_users(limit=10):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()

    query = """
        SELECT user_id, user_name, COUNT(*) AS total_submissions, 
               SUM(CASE WHEN status = 'accepted' THEN 1 ELSE 0 END) AS approved_submissions
        FROM Applications
        GROUP BY user_id, user_name
        ORDER BY approved_submissions DESC, total_submissions DESC
        LIMIT ?
    """
    cursor.execute(query, (limit,))
    results = cursor.fetchall()
    conn.close()
    return results


def add_user_to_database(user_id, username, first_name, last_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()[0] > 0

    if not exists:
        cursor.execute("""
            INSERT INTO Users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, last_name))
        conn.commit()

    conn.close()


@bot.message_handler(commands=['top'])
def handle_top_command(message):
    try:
        # Получаем топ пользователей из БД
        top_users = get_top_users(limit=10)

        if not top_users:
            bot.send_message(message.chat.id, "📭 Пока нет данных для топа.")
            return
        response = "🏆 Топ пользователей по заявкам:\n\n"

        for idx, (user_id, db_username, total, approved) in enumerate(top_users, start=1):
            username = db_username
            user_display = f"ID: {user_id}"
            if not username:
                try:
                    user_info = bot.get_chat(user_id)
                    username = user_info.username
                except Exception as e:
                    print(f"⚠️ Не удалось получить username для {user_id}: {e}")
            if username:
                user_display = f"@{username}"
            response += f"{idx}. {user_display} | Всего заявок: {total} | Подтверждено заявок: {approved}\n"
        bot.send_message(message.chat.id, response)

    except Exception as e:
        error_msg = f"🚨 Ошибка при формировании топа: {str(e)}"
        print(error_msg)
        bot.send_message(message.chat.id, "😢 Произошла ошибка при формировании топа. Попробуйте позже.")


@bot.message_handler(commands=['allsend'])
def start_post(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return

    bot.send_message(message.chat.id, "Отправьте текст для рассылки.")
    waiting_for_post[message.chat.id] = "waiting_for_text"


@bot.message_handler(func=lambda message: waiting_for_post.get(message.chat.id) == "waiting_for_text")
def handle_text(message):
    chat_id = message.chat.id
    post_data[chat_id] = {'text': message.text, 'media': None}
    bot.send_message(chat_id, "Хотите добавить фото или видео? Отправьте файл, либо напишите 'нет'.")
    waiting_for_post[chat_id] = "waiting_for_media"


@bot.message_handler(content_types=["photo", "video"])
def handle_media(message):
    chat_id = message.chat.id
    if waiting_for_post.get(chat_id) != "waiting_for_media":
        return

    if message.photo:
        media_file_id = message.photo[-1].file_id
        media_type = "photo"
    elif message.video:
        media_file_id = message.video.file_id
        media_type = "video"
    else:
        bot.send_message(chat_id, "Не удалось определить тип медиа. Попробуйте снова.")
        return

    post_data[chat_id]['media'] = {'file_id': media_file_id, 'type': media_type}

    text = post_data[chat_id]['text']

    # Показываем пост с фото/видео
    if media_type == "photo":
        bot.send_photo(chat_id, media_file_id, caption=text, parse_mode="HTML")
    elif media_type == "video":
        bot.send_video(chat_id, media_file_id, caption=text, parse_mode="HTML")

    bot.send_message(chat_id, "Подтвердите отправку поста (Да/Нет).")
    waiting_for_post[chat_id] = "waiting_for_confirmation"


@bot.message_handler(func=lambda message: waiting_for_post.get(message.chat.id) == "waiting_for_media")
def handle_skip_media(message):
    if message.text.strip().lower() == "нет":
        chat_id = message.chat.id
        bot.send_message(chat_id, "Подтвердите отправку поста (Да/Нет).")
        waiting_for_post[chat_id] = "waiting_for_confirmation"


@bot.message_handler(func=lambda message: waiting_for_post.get(message.chat.id) == "waiting_for_confirmation")
def handle_confirmation(message):
    chat_id = message.chat.id
    confirmation = message.text.strip().lower()

    if confirmation == "да":
        bot.send_message(chat_id, "Начинаю рассылку...")
        users = get_all_users()
        success_count, failed_count = 0, 0
        text = post_data[chat_id]['text']
        media = post_data[chat_id]['media']

        for user_id in users:
            try:
                if media:
                    if media['type'] == "photo":
                        bot.send_photo(user_id, media['file_id'], caption=text, parse_mode="HTML")
                    elif media['type'] == "video":
                        bot.send_video(user_id, media['file_id'], caption=text, parse_mode="HTML")
                else:
                    bot.send_message(user_id, text, parse_mode="HTML")
                success_count += 1
            except Exception as e:
                failed_count += 1

        bot.send_message(chat_id, f"Рассылка завершена! Успешно: {success_count}, Ошибок: {failed_count}.")
    elif confirmation == "нет":
        bot.send_message(chat_id, "Рассылка отменена.")

    waiting_for_post.pop(chat_id, None)

@bot.message_handler(commands=['stats'])
def handle_stats(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return

    users_count = get_users_count()
    bot.send_message(message.chat.id, f"Количество пользователей, получающих рассылку: {users_count}")
def get_all_users():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT user_id FROM Users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_users_count():
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(DISTINCT user_id) FROM Users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

def add_user_to_database(user_id, username, first_name, last_name):
    conn = sqlite3.connect('videocards.db')
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM Users WHERE user_id = ?", (user_id,))
    exists = cursor.fetchone()[0] > 0

    if not exists:
        cursor.execute("""
            INSERT INTO Users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        """, (user_id, username, first_name, last_name))
        conn.commit()

    conn.close()

@bot.message_handler(commands=['accept'])
def handle_accept(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return

    try:
        application_id = message.text.split()[1]
        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()

        cursor.execute(
            "SELECT user_id, device_type, manufacturer, vendor, name, screenshot_path FROM Applications "
            "WHERE application_id = ? AND status = 'pending'", (application_id,))
        application = cursor.fetchone()

        if not application:
            bot.send_message(message.chat.id, f"Заявка с ID {application_id} не найдена или уже обработана.")
        else:
            user_id, device_type, manufacturer, vendor, name, screenshot_path = application

            if device_type == "videocard":
                cursor.execute("INSERT INTO Videocards (name, screenshot, manufacturer, vendor) VALUES (?, ?, ?, ?)",
                               (name, screenshot_path, manufacturer, vendor))
            else:
                table_map = {
                    "laptop": "Laptops",
                    "motherboard": "Motherboards",
                    "console": "Consoles"
                }
                table_name = table_map.get(device_type)
                if table_name:
                    cursor.execute(f"INSERT INTO {table_name} (name, screenshot, manufacturer) VALUES (?, ?, ?)",
                                   (name, screenshot_path, manufacturer))

            cursor.execute("UPDATE Applications SET status = 'accepted' WHERE application_id = ?", (application_id,))
            conn.commit()

            bot.send_message(message.chat.id, f"Заявка с ID {application_id} подтверждена и добавлена в базу данных.")
            bot.send_message(user_id, f"Ваша заявка с ID {application_id} подтверждена!")

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        conn.close()


@bot.message_handler(commands=['cancel'])
def handle_cancel(message):
    if message.chat.id not in ADMIN_IDS:
        bot.send_message(message.chat.id, "У вас нет прав для выполнения этой команды.")
        return

    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            bot.send_message(message.chat.id, "Используйте формат: /cancel <ID заявки> <причина>")
            return

        application_id, reason = parts[1], parts[2]
        conn = sqlite3.connect('videocards.db')
        cursor = conn.cursor()

        cursor.execute("SELECT user_id FROM Applications WHERE application_id = ? AND status = 'pending'",
                       (application_id,))
        application = cursor.fetchone()

        if not application:
            bot.send_message(message.chat.id, f"Заявка с ID {application_id} не найдена или уже обработана.")
        else:
            user_id = application[0]

            # Если reason нет в базе, уберите её из запроса
            cursor.execute("UPDATE Applications SET status = 'rejected' WHERE application_id = ?", (application_id,))
            conn.commit()

            bot.send_message(message.chat.id, f"Заявка с ID {application_id} отклонена.")
            bot.send_message(user_id, f"Ваша заявка с ID {application_id} отклонена. Причина: {reason}")

    except Exception as e:
        bot.send_message(message.chat.id, f"Ошибка: {e}")
    finally:
        conn.close()

bot.polling(none_stop=True)