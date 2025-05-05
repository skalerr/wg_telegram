import telebot
from telebot import types
import subprocess
import os

from config import api_tg, mainid

bot = telebot.TeleBot(api_tg)

# Для хранения промежуточных данных по каждому чату
pending_clients = {}

def buttons(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btns = ["Конфиги", "Добавить_конфиг", "Удалить_конфиг", "Назад"]
    markup.add(*[types.KeyboardButton(text) for text in btns])
    bot.send_message(message.chat.id, "Выполни запрос", reply_markup=markup)

def check_message(message: str) -> str:
    valid = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
    cleaned = ''.join(c if c in valid else '_' for c in message).lower()
    return cleaned.strip('_')

def check_number_in_range(number: str) -> bool:
    try:
        n = int(number)
        return 2 <= n <= 253
    except ValueError:
        return False

@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.id in mainid:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.add("Мониторинг", "Администрирование")
        bot.send_message(message.chat.id,
                         f"{message.from_user.first_name}, добро пожаловать в бот управления VPN Wireguard",
                         reply_markup=markup)
    else:
        bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Ты заплутал!!")

@bot.message_handler(content_types=['text'])
def func(message):
    if message.chat.id not in mainid:
        bot.send_message(message.chat.id, f"Привет, {message.from_user.first_name}! Ты заплутал!!")
        return

    text = message.text
    if text == "Добавить_конфиг":
        bot.send_message(message.chat.id, "Введите имя нового конфига (только латиница, цифры и подчёркивания)", 
                         reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(message, ask_ip_for_new_client)
    elif text == "Конфиги":
        # ... ваша логика
        pass
    # остальные команды...
    else:
        bot.send_message(message.chat.id, "На такую команду я не запрограммировал..")

def ask_ip_for_new_client(message):
    name = check_message(message.text)
    if not name:
        bot.send_message(message.chat.id, "Недопустимое имя. Введите заново.")
        bot.register_next_step_handler(message, ask_ip_for_new_client)
        return

    pending_clients[message.chat.id] = {'username': name}
    bot.send_message(message.chat.id,
                     f"Имя сохранено: {name}\nТеперь введите последний октет IP-адреса (2–253) для 10.10.0.X:",
                     reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(message, create_client_with_ip)

def create_client_with_ip(message):
    chat_id = message.chat.id
    if chat_id not in pending_clients:
        # что-то пошло не так
        bot.send_message(chat_id, "Ошибка состояния, начните заново.")
        return

    ip_octet = message.text.strip()
    if not check_number_in_range(ip_octet):
        bot.send_message(chat_id, "Неверный формат IP. Введите число от 2 до 253.")
        bot.register_next_step_handler(message, create_client_with_ip)
        return

    # проверим, не занят ли уже
    used = False
    cfg_path = "cofigs.txt"
    if os.path.exists(cfg_path):
        with open(cfg_path, 'r') as f:
            for line in f:
                if line.startswith(f"10.10.0.{ip_octet}"):
                    used = True
                    break
    if used:
        bot.send_message(chat_id, f"IP 10.10.0.{ip_octet} уже используется. Введите другой.")
        bot.register_next_step_handler(message, create_client_with_ip)
        return

    username = pending_clients[chat_id]['username']
    # вызов скрипта с двумя параметрами
    subprocess.run(['scripts/add_cl.sh', username, ip_octet])

    # отправляем клиенту всё, как раньше
    config_file = f"/etc/wireguard/{username}_cl.conf"
    # QR
    if os.path.isfile(config_file):
        with open(config_file, 'rb') as f:
            bot.send_photo(chat_id, f)
        with open(config_file, 'rb') as f:
            bot.send_document(chat_id, f)
        with open(config_file, 'r') as f:
            bot.send_message(chat_id, f.read())

    bot.send_message(chat_id, f"Клиент {username} с IP 10.10.0.{ip_octet} создан.")
    pending_clients.pop(chat_id, None)
    buttons(message)

bot.polling(none_stop=True)
