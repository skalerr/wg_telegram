import telebot
from telebot import types # для указание типов
import time
import datetime
import subprocess
import sys
import os
import glob
import qrcode
import re
from config import *
#from config import *

class ServerConfig:
    def __init__(self):
        self.ip_base = "10.20.20"  # Default IP base
        self.port = "51830"        # Default port
        self.next_ip = 2           # Start from .2
        self.load_config()
    
    def load_config(self):
        try:
            with open('server_config.txt', 'r') as f:
                lines = f.readlines()
                for line in lines:
                    if '=' in line:
                        key, value = line.strip().split('=')
                        if key == 'ip_base':
                            self.ip_base = value
                        elif key == 'port':
                            self.port = value
                        elif key == 'next_ip':
                            self.next_ip = int(value)
        except FileNotFoundError:
            self.save_config()
    
    def save_config(self):
        with open('server_config.txt', 'w') as f:
            f.write(f"ip_base={self.ip_base}\n")
            f.write(f"port={self.port}\n")
            f.write(f"next_ip={self.next_ip}\n")
    
    def get_next_ip(self):
        current = self.next_ip
        self.next_ip += 1
        self.save_config()
        return f"{self.ip_base}.{current}"
    
    def remove_ip(self, last_octet):
        # No need to decrement next_ip as we want to keep moving forward
        pass

    def validate_ip_base(self, ip_base):
        pattern = r'^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){2}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
        return bool(re.match(pattern, ip_base))
    
    def validate_port(self, port):
        try:
            port_num = int(port)
            return 1024 <= port_num <= 65535
        except ValueError:
            return False

# Create global server config instance
server_config = ServerConfig()

config = ""
# Создаем экземпляр бота
bot = telebot.TeleBot(api_tg)

def save_config(message):
    global config
    config = message.text
    print("----------------")
    print(config)
    print("----------------")
    string = str(config)
    bot.send_message(message.chat.id, "Настройки конфигурации сохранены")
    return string

def qr(name_qr, chat_id):
    # Чтение содержимого файла
    with open(name_qr, 'r') as file:
        text = file.read()
    # Создание объекта QR-кода
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(text)
    qr.make(fit=True)
    # Создание изображения QR-кода
    img = qr.make_image(fill_color='black', back_color='white')
    # Сохранение изображения в файл
    img_path = "my_qrcode.png"
    img.save("my_qrcode.png")
    # Отправка QR-кода через Telegram бота
    with open(img_path, 'rb') as f:
        bot.send_photo(chat_id=chat_id, photo=f)
    # Удаление QR-кода
    os.remove(img_path)

def check_message(message):
    valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_!? ')
    new_message = ''.join(c if c in valid_chars else '_' for c in message)
    new_message = new_message.replace(' ', '_')
    return new_message.lower().strip()

def check_number_in_range(number):
    try:
        num = int(number)
        if 2 <= num <= 253:
            return True
        else:
            return False
    except ValueError:
        return False

def buttons(message):
#    bot.send_message(message.chat.id, text="Привет хозяин")
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    botton32 = types.KeyboardButton("Конфиги")
    botton42 = types.KeyboardButton("Удалить_конфиг")
    botton41 = types.KeyboardButton("Добавить_конфиг")
    back = types.KeyboardButton("Назад")
    markup.add(botton32, botton41, botton42, back)
    bot.send_message(message.chat.id, text="Выполни запрос", reply_markup=markup)

def del_vpn(message):
    if message.sticker is not None:
        bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не стикер.')
        buttons(message)
    elif message.voice is not None:
        bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не голосовое сообщение.')
        buttons(message)
    elif message.document is not None:
        bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не документ.')
        buttons(message)
    else:
        config_string = check_message(message.text)
        if check_number_in_range(message.text):
            subprocess.run(['scripts/del_cl.sh', config_string])
            script_path = os.path.dirname(os.path.realpath(__file__))
            rm_user_script = os.path.join(script_path, "rm_user.sh")
            subprocess.run([rm_user_script, f"{server_config.ip_base}.{config_string}"])
            bot.send_message(message.chat.id, f"IP-адрес {server_config.ip_base}.{config_string} успешно удален.")
            print(f"{message.text} находится в допустимом диапазоне.")
        else:
            print(f"{message.text} не находится в допустимом диапазоне.")
            bot.send_message(message.chat.id, f"IP-адрес {server_config.ip_base}.{config_string} не может быть удален. Введите число от 2 до 253")
    buttons(message)

def add_vpn(message):
    if message.chat.id in mainid:
        if message.sticker is not None:
            bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не стикер.')
            buttons(message)
        elif message.voice is not None:
            bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не голосовое сообщение.')
            buttons(message)
        elif message.document is not None:
            bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не документ.')
            buttons(message)
        else:
            config_string = check_message(message.text)
            next_ip = server_config.get_next_ip()
            subprocess.run(['scripts/add_cl.sh', config_string, next_ip, server_config.port])
            bot.send_message(message.chat.id, f"Конфиг {config_string}.conf создан с IP {next_ip}")
            config_file_path = f"/etc/wireguard/{config_string}_cl.conf"
            qr(config_file_path, message.chat.id)
            with open(config_file_path, 'rb') as file:
                bot.send_document(message.chat.id, file)
            with open(config_file_path, 'r') as file:
                config_content = file.read()
            bot.send_message(message.chat.id, config_content)
            bot.send_message(message.chat.id, "Конфигурационный файл успешно отправлен.")
            buttons(message)

@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.id in mainid:
#        bot.send_message(message.chat.id, text="Привет избранный!!")
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        btn1q = types.KeyboardButton("Мониторинг")
        btn2q = types.KeyboardButton("Администрирование")
        markup.add(btn1q, btn2q)
        bot.send_message(message.chat.id, text="{0.first_name}, добро пожаловать в бот управления VPN Wireguard".format(message.from_user), reply_markup=markup)
    elif(str(message.chat.id) != mainid):
        bot.send_message(message.chat.id, text="Привет, {0.first_name}! Ты заплутал!!".format(message.from_user))

@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    # Обработка сообщения со стикером
    bot.reply_to(message, 'Вы отправили стикер!')

@bot.message_handler(commands=["id"])
def id(message):
    bot.send_message(message.chat.id, text="Id :"+str(message.chat.id)+"\nusername :"+str(message.from_user.username))
    print(str(message.chat.id))

@bot.message_handler(content_types=['text'])
def func(message):
    if message.chat.id in mainid:
#        bot.send_message(message.chat.id, text="Привет избранный!!")
        formatted_message = check_message(message.text)
        print(formatted_message)
        if not formatted_message:  # Проверяем, что сообщение не пустое
            return
        if(message.text == "Мониторинг"):
#            bot.send_message(message.chat.id, text="Здесь мониторинг vpn сервера")
            buttons(message)
        elif(message.text == "Администрирование"):
            if (1==1):
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                botton22 = types.KeyboardButton("Установка_Wireguard")
                botton_reset = types.KeyboardButton("Сохранить_конигурацию")
                botton_reset_up = types.KeyboardButton("Импортировать_конигурацию")
                botton_server_ip = types.KeyboardButton("Изменить_базовый_IP")
                botton_server_port = types.KeyboardButton("Изменить_порт")
                back = types.KeyboardButton("Назад")
                markup.add(botton22, botton_reset, botton_reset_up, botton_server_ip, botton_server_port, back)
                bot.send_message(message.chat.id, text="Выполни запрос", reply_markup=markup)
        elif message.text == "Изменить_базовый_IP":
            bot.send_message(message.chat.id, f"Текущий базовый IP: {server_config.ip_base}\nВведите новый базовый IP (например, 10.20.20):", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(message, change_base_ip)
        elif message.text == "Изменить_порт":
            bot.send_message(message.chat.id, f"Текущий порт: {server_config.port}\nВведите новый порт (1024-65535):", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(message, change_port)
        elif message.text == "Удалить_конфиг":
            bot.send_message(message.chat.id, "Введите последний октет ip, который нужно удалить.", reply_markup=types.ReplyKeyboardRemove())
            config_file_path_txt = f"cofigs.txt"
            with open(config_file_path_txt, 'rb') as file:
                config_content = file.read()
            bot.send_message(message.chat.id, config_content)
            bot.send_message(message.chat.id, "Введите последний октет ip, который нужно удалить. Например если нужно удалить ip адресс 10.10.0.47, то введите 47")
            bot.register_next_step_handler(message, del_vpn)
        elif message.text == "Добавить_конфиг":
            bot.send_message(message.chat.id, "Введите название нового конфига", reply_markup=types.ReplyKeyboardRemove())
            bot.register_next_step_handler(message, add_vpn)
        elif message.text == "Конфиги":
            bot.send_message(message.chat.id, "Вот ваша конфигурация Wireguard")
            config_file_path = f"/etc/wireguard/wg0.conf"
            with open(config_file_path, 'rb') as file:
                bot.send_document(message.chat.id, file)
            with open(config_file_path, 'r') as file:
                config_content = file.read()
            bot.send_message(message.chat.id, config_content)
            file_list = glob.glob('/etc/wireguard/*.conf')
            for file_path in file_list:
                if os.path.basename(file_path) != 'wg0.conf':
                    with open(file_path, 'rb') as file:
                        bot.send_document(message.chat.id, document=file)
            config_file_path_txt = f"cofigs.txt"
            with open(config_file_path_txt, 'rb') as file:
                config_content = file.read()
            bot.send_message(message.chat.id, config_content)
#            bot.send_message(message.chat.id, "Конфигурационный файл успешно отправлен.")
        elif message.text == "Сохранить_конигурацию":
            subprocess.run(['scripts/backup.sh'])
            print("ok")
            bot.send_message(message.chat.id, text="Резервная копия создана")
        elif message.text == "Импортировать_конигурацию":
            subprocess.run(['scripts/restore.sh'])
            print("ok2")
            bot.send_message(message.chat.id, text="Резервная копия импортированна")
        elif message.text == "Установка_Wireguard":
            # Проверка наличия файла
            file_path = '/etc/wireguard/wg0.conf'
            if os.path.isfile(file_path):
                print(f"Файл {file_path} существует.")
#                bot.send_message(message.chat.id, "Wireguard уже настроен. \nХотите настроить заново?")
#                bot.send_message(message.chat.id, "Хотите установить все заново?")
#                bot.send_message(message.chat.id, text="Привет хозяин")
                markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
                botton_yes = types.KeyboardButton("Да")
                botton_no = types.KeyboardButton("Нет")
                markup.add(botton_yes, botton_no)
                bot.send_message(message.chat.id, text="Wireguard уже настроен. \nХотите настроить заново?", reply_markup=markup)
            else:
                print(f"Файла {file_path} не существует.")
                bot.send_message(message.chat.id, "Запускаю установку Wireguard. \nПожалуйста дождитесь завершения установки.")
                subprocess.run(['scripts/start_wg.sh'])
                bot.send_message(message.chat.id, "Установка Wireguard завершена")
        elif (message.text == "Да"):
            bot.send_message(message.chat.id, "Удаляю конфиги!")
            command = "rm variables.sh && rm -r /etc/wireguard/ && mkdir /etc/wireguard/ && rm cofigs.txt"
            subprocess.run(command, shell=True)
#            # Удаление файла variables.sh
#            subprocess.run("rm variables.sh", shell=True)
#            # Удаление каталога /etc/wireguard/
#            subprocess.run("rm -r /etc/wireguard/", shell=True)
#            # Пауза для обеспечения времени на завершение предыдущей команды
#            time.sleep(10)
#            # Создание каталога /etc/wireguard/
#            subprocess.run("mkdir /etc/wireguard/", shell=True)
#            # Удаление файла cofigs.txt
#            subproces.run("rm cofigs.txt", shell=True)
            bot.send_message(message.chat.id, "Запускаю установку Wireguard")
            subprocess.run(['scripts/start_wg.sh'])
            bot.send_message(message.chat.id, "Установка Wireguard завершена")
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            button1 = types.KeyboardButton("Мониторинг")
            button2 = types.KeyboardButton("Администрирование")
            markup.add(button1, button2)
            bot.send_message(message.chat.id, text="Назад", reply_markup=markup)
        elif (message.text == "Нет"):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            button1 = types.KeyboardButton("Мониторинг")
            button2 = types.KeyboardButton("Администрирование")
            markup.add(button1, button2)
            bot.send_message(message.chat.id, text="Назад", reply_markup=markup)
        elif (message.text == "Назад"):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            button1 = types.KeyboardButton("Мониторинг")
            button2 = types.KeyboardButton("Администрирование")
            markup.add(button1, button2)
            bot.send_message(message.chat.id, text="Назад", reply_markup=markup)
        else:
            bot.send_message(message.chat.id, text="На такую комманду я не запрограммировал..")
        message_text = message.text
        print(message_text)
    elif(str(message.chat.id) != mainid):
        bot.send_message(message.chat.id, text="Привет, {0.first_name}! Ты заплутал!!".format(message.from_user))

def change_base_ip(message):
    if message.chat.id in mainid:
        new_ip_base = message.text.strip()
        if server_config.validate_ip_base(new_ip_base):
            server_config.ip_base = new_ip_base
            server_config.save_config()
            bot.send_message(message.chat.id, f"Базовый IP успешно изменен на {new_ip_base}")
        else:
            bot.send_message(message.chat.id, "Неверный формат IP. Пожалуйста, используйте формат X.X.X (например, 10.20.20)")
    buttons(message)

def change_port(message):
    if message.chat.id in mainid:
        new_port = message.text.strip()
        if server_config.validate_port(new_port):
            server_config.port = new_port
            server_config.save_config()
            bot.send_message(message.chat.id, f"Порт успешно изменен на {new_port}")
        else:
            bot.send_message(message.chat.id, "Неверный формат порта. Пожалуйста, введите число от 1024 до 65535")
    buttons(message)

bot.polling(none_stop=True)

