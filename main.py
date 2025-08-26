import telebot
from telebot import types
import subprocess
import os
import glob
import qrcode
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime
from config import api_tg, mainid, wg_local_ip_hint


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class WireGuardBot:
    def __init__(self, token: str, authorized_users: list, wg_ip_hint: str):
        self.bot = telebot.TeleBot(token)
        self.authorized_users = authorized_users
        self.wg_ip_hint = wg_ip_hint
        self.setup_handlers()
    
    def setup_handlers(self):
        self.bot.message_handler(commands=['start'])(self.start_command)
        self.bot.message_handler(commands=['id'])(self.id_command)
        self.bot.message_handler(content_types=['text'])(self.handle_text)
        self.bot.message_handler(content_types=['sticker'])(self.handle_sticker)
        self.bot.callback_query_handler(func=lambda call: True)(self.handle_callback)
    
    def is_authorized(self, chat_id: int) -> bool:
        return chat_id in self.authorized_users
    
    def send_unauthorized_message(self, message):
        self.bot.send_message(
            message.chat.id, 
            f"Привет, {message.from_user.first_name}! Ты заплутал!!"
        )

    def save_config(self, message):
        try:
            config_text = message.text
            logger.info(f"Saving config: {config_text}")
            self.bot.send_message(message.chat.id, "Настройки конфигурации сохранены")
            return config_text
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при сохранении конфигурации")

    def generate_qr_code(self, config_path: str, chat_id: int) -> bool:
        try:
            if not Path(config_path).exists():
                logger.error(f"Config file not found: {config_path}")
                return False
            
            with open(config_path, 'r', encoding='utf-8') as file:
                text = file.read()
            
            qr_code = qrcode.QRCode(version=1, box_size=10, border=5)
            qr_code.add_data(text)
            qr_code.make(fit=True)
            
            img = qr_code.make_image(fill_color='black', back_color='white')
            img_path = Path("temp_qrcode.png")
            img.save(img_path)
            
            with open(img_path, 'rb') as f:
                self.bot.send_photo(chat_id=chat_id, photo=f)
            
            img_path.unlink()
            return True
            
        except Exception as e:
            logger.error(f"Error generating QR code: {e}")
            return False

    @staticmethod
    def sanitize_input(message: str) -> str:
        valid_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_')
        sanitized = ''.join(c if c in valid_chars else '_' for c in message)
        return sanitized.lower().strip()

    @staticmethod
    def is_valid_ip_octet(number_str: str) -> bool:
        try:
            num = int(number_str)
            return 2 <= num <= 253
        except ValueError:
            return False

    def show_main_buttons(self, message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        configs_btn = types.KeyboardButton("Конфиги")
        delete_btn = types.KeyboardButton("Удалить_конфиг")
        add_btn = types.KeyboardButton("Добавить_конфиг")
        back_btn = types.KeyboardButton("Назад")
        
        markup.add(configs_btn, add_btn, delete_btn, back_btn)
        self.bot.send_message(message.chat.id, text="Выполни запрос", reply_markup=markup)
    
    def show_monitoring_menu(self, message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        configs_btn = types.KeyboardButton("Конфиги")
        stats_btn = types.KeyboardButton("Статистика")
        monitor_btn = types.KeyboardButton("Монитор_клиентов")
        add_btn = types.KeyboardButton("Добавить_конфиг")
        delete_btn = types.KeyboardButton("Удалить_конфиг")
        recreate_btn = types.KeyboardButton("Пересоздать_конфиги")
        back_btn = types.KeyboardButton("Назад")
        
        markup.add(stats_btn, monitor_btn)
        markup.add(configs_btn)
        markup.add(add_btn, delete_btn)
        markup.add(recreate_btn)
        markup.add(back_btn)
        self.bot.send_message(message.chat.id, text="📊 Мониторинг VPN сервера", reply_markup=markup)

    def validate_message_type(self, message) -> bool:
        if message.sticker is not None:
            self.bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не стикер.')
            return False
        elif message.voice is not None:
            self.bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не голосовое сообщение.')
            return False
        elif message.document is not None:
            self.bot.reply_to(message, 'Пожалуйста, отправьте текстовое сообщение, а не документ.')
            return False
        return True
    
    def delete_vpn_config(self, message):
        if not self.validate_message_type(message):
            self.show_monitoring_menu(message)
            return
        
        try:
            if not self.is_valid_ip_octet(message.text):
                self.bot.send_message(
                    message.chat.id, 
                    f"IP-адрес не может быть удален. Введите число от 2 до 253"
                )
                self.show_monitoring_menu(message)
                return
            
            config_string = self.sanitize_input(message.text)
            
            # Execute deletion scripts with error handling
            result1 = subprocess.run(['scripts/del_cl.sh', config_string], capture_output=True, text=True)
            if result1.returncode != 0:
                logger.error(f"Failed to run del_cl.sh: {result1.stderr}")
                self.bot.send_message(message.chat.id, "Ошибка при удалении конфигурации")
                return
            
            script_path = Path(__file__).parent
            rm_user_script = script_path / "rm_user.sh"
            if rm_user_script.exists():
                result2 = subprocess.run([str(rm_user_script), config_string], capture_output=True, text=True)
                if result2.returncode != 0:
                    logger.error(f"Failed to run rm_user.sh: {result2.stderr}")
            
            self.bot.send_message(
                message.chat.id, 
                f"IP-адрес {self.wg_ip_hint}.{config_string} успешно удален."
            )
            logger.info(f"Deleted VPN config for IP {self.wg_ip_hint}.{config_string}")
            
        except Exception as e:
            logger.error(f"Error deleting VPN config: {e}")
            self.bot.send_message(message.chat.id, "Произошла ошибка при удалении конфигурации")
        
        self.show_monitoring_menu(message)



    def get_config_name(self, message):
        """First step: get config name"""
        if not self.is_authorized(message.chat.id):
            self.send_unauthorized_message(message)
            return
        
        if not self.validate_message_type(message):
            self.show_monitoring_menu(message)
            return
        
        try:
            config_name = self.sanitize_input(message.text)
            if not config_name:
                self.bot.send_message(message.chat.id, "Недопустимое имя конфигурации")
                self.show_monitoring_menu(message)
                return
            
            # Store config name and ask for IP
            self.temp_config_name = config_name
            self.show_ip_selection(message)
            
        except Exception as e:
            logger.error(f"Error getting config name: {e}")
            self.bot.send_message(message.chat.id, "Произошла ошибка")
            self.show_monitoring_menu(message)

    def show_ip_selection(self, message):
        """Show available IP addresses for selection"""
        try:
            # Get available IPs
            available_ips = self.get_available_ips()
            
            if not available_ips:
                self.bot.send_message(message.chat.id, "Нет доступных IP адресов")
                self.show_monitoring_menu(message)
                return
            
            # Create inline keyboard with available IPs
            markup = types.InlineKeyboardMarkup(row_width=3)
            buttons = []
            
            for ip_octet in available_ips[:15]:  # Show first 15 available IPs
                ip_addr = f"10.20.20.{ip_octet}"
                button = types.InlineKeyboardButton(
                    text=ip_addr, 
                    callback_data=f"select_ip:{ip_octet}"
                )
                buttons.append(button)
            
            # Add buttons in rows of 3
            for i in range(0, len(buttons), 3):
                markup.row(*buttons[i:i+3])
            
            # Add auto-select button
            auto_button = types.InlineKeyboardButton(
                text="🔄 Автовыбор", 
                callback_data="select_ip:auto"
            )
            markup.row(auto_button)
            
            self.bot.send_message(
                message.chat.id, 
                f"Выберите IP адрес для конфига **{self.temp_config_name}**:\n\n"
                f"Доступно IP адресов: {len(available_ips)}",
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing IP selection: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при получении доступных IP")
            self.show_monitoring_menu(message)

    def get_available_ips(self):
        """Get list of available IP octets (2-254)"""
        try:
            # Get existing configurations
            configs = self.scan_existing_configs()
            used_octets = set()
            
            for config_info in configs.values():
                octet = int(config_info['octet'])
                used_octets.add(octet)
            
            # Return available octets (2-254, excluding 1 for server)
            all_octets = set(range(2, 255))
            available_octets = sorted(list(all_octets - used_octets))
            
            return available_octets
            
        except Exception as e:
            logger.error(f"Error getting available IPs: {e}")
            return []

    def add_vpn_config(self, config_name, selected_ip=None):
        """Create VPN config with specified name and IP"""
        try:
            # Determine IP to use
            if selected_ip == "auto" or selected_ip is None:
                # Auto-select first available IP
                available_ips = self.get_available_ips()
                if not available_ips:
                    return False, "Нет доступных IP адресов"
                ip_octet = available_ips[0]
            else:
                ip_octet = int(selected_ip)
            
            # Execute add client script with IP parameter
            result = subprocess.run(
                ['scripts/add_cl.sh', config_name, str(ip_octet)], 
                capture_output=True, 
                text=True
            )
            
            if result.returncode != 0:
                logger.error(f"Failed to create VPN config: {result.stderr}")
                return False, f"Ошибка при создании конфигурации: {result.stderr}"
            
            return True, f"✅ Конфиг **{config_name}.conf** создан с IP 10.20.20.{ip_octet}"
            
        except Exception as e:
            logger.error(f"Error creating VPN config: {e}")
            return False, f"Произошла ошибка: {str(e)}"

    def uninstall_wireguard(self, message):
        try:
            chat_id = message.chat.id
            self.bot.send_message(chat_id, "Удаляю WireGuard и конфигурации...")
            
            commands = [
                "wg-quick down wg0",
                "apt-get remove -y wireguard wireguard-tools qrencode",
                "rm -rf /etc/wireguard",
                "rm -f /etc/sysctl.d/wg.conf",
                "sysctl --system"
            ]
            
            for cmd in commands:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.warning(f"Command failed: {cmd}, error: {result.stderr}")
            
            self.bot.send_message(chat_id, "WireGuard успешно удалён.")
            logger.info("WireGuard uninstalled successfully")
            
        except Exception as e:
            logger.error(f"Error uninstalling WireGuard: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при удалении WireGuard")
        
        self.show_monitoring_menu(message)

    def start_command(self, message):
        if self.is_authorized(message.chat.id):
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            monitoring_btn = types.KeyboardButton("Мониторинг")
            admin_btn = types.KeyboardButton("Администрирование")
            markup.add(monitoring_btn, admin_btn)
            
            welcome_text = f"{message.from_user.first_name}, добро пожаловать в бот управления VPN Wireguard"
            self.bot.send_message(message.chat.id, text=welcome_text, reply_markup=markup)
            logger.info(f"User {message.from_user.username} ({message.chat.id}) started the bot")
        else:
            self.send_unauthorized_message(message)
            logger.warning(f"Unauthorized access attempt from {message.chat.id}")

    def handle_sticker(self, message):
        self.bot.reply_to(message, 'Вы отправили стикер!')

    def handle_callback(self, call):
        """Handle inline keyboard callbacks"""
        if not self.is_authorized(call.from_user.id):
            self.bot.answer_callback_query(call.id, "Unauthorized")
            return
        
        try:
            if call.data.startswith("select_ip:"):
                selected_ip = call.data.split(":")[1]
                
                # Create config with selected IP
                config_name = getattr(self, 'temp_config_name', None)
                if not config_name:
                    self.bot.answer_callback_query(call.id, "Ошибка: имя конфига не найдено")
                    return
                
                success, message_text = self.add_vpn_config(config_name, selected_ip)
                
                # Edit the message to remove inline keyboard
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text=f"Создание конфига **{config_name}**...",
                    parse_mode='Markdown'
                )
                
                # Send result
                if success:
                    self.bot.send_message(call.message.chat.id, message_text, parse_mode='Markdown')
                    
                    # Try to send the config file
                    try:
                        config_file_path = Path(f"/etc/wireguard/{config_name}_cl.conf")
                        if config_file_path.exists():
                            with open(config_file_path, 'rb') as file:
                                self.bot.send_document(
                                    call.message.chat.id, 
                                    file, 
                                    caption=f"📄 Конфигурация {config_name}"
                                )
                        else:
                            logger.error(f"Config file not found: {config_file_path}")
                    except Exception as e:
                        logger.error(f"Error sending config file: {e}")
                else:
                    self.bot.send_message(call.message.chat.id, f"❌ {message_text}")
                
                self.show_monitoring_menu(call.message)
                self.bot.answer_callback_query(call.id)
                
        except Exception as e:
            logger.error(f"Error handling callback: {e}")
            self.bot.answer_callback_query(call.id, "Произошла ошибка")

    def id_command(self, message):
        user_info = f"Id: {message.chat.id}\nusername: {message.from_user.username}"
        self.bot.send_message(message.chat.id, text=user_info)
        logger.info(f"ID command used by {message.chat.id}")

    def handle_text(self, message):
        if not self.is_authorized(message.chat.id):
            self.send_unauthorized_message(message)
            return
        
        text = message.text.strip()
        if not text:
            return
        
        logger.info(f"User {message.chat.id} sent: {text}")
        
        if text == "Мониторинг":
            self.show_monitoring_menu(message)
        elif text == "Администрирование":
            self.show_admin_menu(message)
        elif text == "Удалить_конфиг":
            self.prompt_delete_config(message)
        elif text == "Добавить_конфиг":
            self.bot.send_message(message.chat.id, "Введите название нового конфига", reply_markup=types.ReplyKeyboardRemove())
            self.bot.register_next_step_handler(message, self.get_config_name)
        elif text == "Полное_удаление":
            self.confirm_uninstall(message)
        elif text == "Да удалить НАВСЕГДА":
            self.uninstall_wireguard(message)

        elif text == "Конфиги":
            self.send_configs(message)
        elif text == "Сохранить_конигурацию":
            self.backup_config(message)
        elif text == "Импортировать_конигурацию":
            self.restore_config(message)
        elif text == "Пересоздать_конфиги":
            self.recreate_configs(message)
        elif text == "Статистика":
            self.show_statistics(message)
        elif text == "Монитор_клиентов":
            self.show_clients_monitor(message)
        elif text == "Установка_Wireguard":
            self.install_wireguard(message)
        elif text == "Да":
            self.reinstall_wireguard(message)
        elif text == "Нет":
            self.show_main_menu(message)
        elif text == "Назад":
            self.show_main_menu(message)
        else:
            self.bot.send_message(message.chat.id, text="На такую команду я не запрограммировал..")
            logger.info(f"Unknown command from user {message.chat.id}: {text}")
    
    def show_main_menu(self, message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        monitoring_btn = types.KeyboardButton("Мониторинг")
        admin_btn = types.KeyboardButton("Администрирование")
        markup.add(monitoring_btn, admin_btn)
        self.bot.send_message(message.chat.id, text="Меню", reply_markup=markup)
    
    def show_admin_menu(self, message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        install_btn = types.KeyboardButton("Установка_Wireguard")
        uninstall_btn = types.KeyboardButton("Полное_удаление")
        backup_btn = types.KeyboardButton("Сохранить_конигурацию")
        restore_btn = types.KeyboardButton("Импортировать_конигурацию")
        back_btn = types.KeyboardButton("Назад")
        markup.add(install_btn, uninstall_btn, backup_btn, restore_btn, back_btn)
        self.bot.send_message(message.chat.id, text="Выполни запрос", reply_markup=markup)
    
    def confirm_uninstall(self, message):
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
        yes_btn = types.KeyboardButton("Да удалить НАВСЕГДА")
        no_btn = types.KeyboardButton("Нет")
        markup.add(yes_btn, no_btn)
        self.bot.send_message(
            message.chat.id, 
            text="Wireguard будет удален навсегда со всеми настройками.\nХотите продолжить?", 
            reply_markup=markup
        )
    
    def prompt_delete_config(self, message):
        self.bot.send_message(
            message.chat.id, 
            "Введите последний октет IP, который нужно удалить.", 
            reply_markup=types.ReplyKeyboardRemove()
        )
        
        try:
            configs_file = Path("configs.txt")
            if configs_file.exists():
                with open(configs_file, 'r', encoding='utf-8') as file:
                    config_content = file.read()
                self.bot.send_message(message.chat.id, config_content)
        except Exception as e:
            logger.error(f"Error reading configs file: {e}")
        
        self.bot.send_message(
            message.chat.id, 
            f"Введите последний октет IP. Например, для удаления {self.wg_ip_hint}.47 введите 47"
        )
        self.bot.register_next_step_handler(message, self.delete_vpn_config)
    
    def send_configs(self, message):
        try:
            self.bot.send_message(message.chat.id, "📁 Получение конфигураций WireGuard...")
            
            # Get client configurations info first
            configs = self.scan_existing_configs()
            
            # Send summary first
            if configs:
                summary_msg = f"📋 **Список конфигураций ({len(configs)} клиентов):**\n\n"
                
                sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
                for client_name, config_info in sorted_configs:
                    escaped_name = client_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]')
                    summary_msg += f"👤 **{escaped_name}** - {config_info['ip']}\n"
                
                self.bot.send_message(message.chat.id, summary_msg, parse_mode='Markdown')
            
            # Send main server config file
            main_config = Path("/etc/wireguard/wg0.conf")
            if main_config.exists():
                self.bot.send_message(message.chat.id, "🗺 Основная конфигурация сервера:")
                with open(main_config, 'rb') as file:
                    self.bot.send_document(message.chat.id, file, caption="🗺 wg0.conf - конфигурация сервера")
            
            # Send client configs with better organization
            if configs:
                self.bot.send_message(message.chat.id, f"📦 Отправляю клиентские конфигурации ({len(configs)} файлов)...")
                
                sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
                for client_name, config_info in sorted_configs:
                    try:
                        with open(config_info['file'], 'rb') as file:
                            caption = f"👤 {client_name} - {config_info['ip']}"
                            self.bot.send_document(message.chat.id, document=file, caption=caption)
                    except Exception as e:
                        logger.error(f"Error sending config file {config_info['file']}: {e}")
                        self.bot.send_message(
                            message.chat.id, 
                            f"⚠️ Ошибка отправки {client_name}: {str(e)[:100]}"
                        )
            else:
                self.bot.send_message(message.chat.id, "⚠️ Клиентские конфигурации не найдены")
            
            # Send configs summary file if exists
            configs_file = Path("configs.txt")
            if configs_file.exists():
                with open(configs_file, 'rb') as file:
                    self.bot.send_document(
                        message.chat.id, 
                        file, 
                        caption="📄 Сводка конфигураций"
                    )
            
            self.bot.send_message(message.chat.id, "✅ Все конфигурации отправлены")
            logger.info(f"Sent configs for {len(configs)} clients")
            
        except Exception as e:
            logger.error(f"Error sending configs: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при отправке конфигураций")
    
    def backup_config(self, message):
        try:
            result = subprocess.run(['scripts/backup.sh'], capture_output=True, text=True)
            if result.returncode == 0:
                self.bot.send_message(message.chat.id, "Резервная копия создана")
                logger.info("Configuration backed up successfully")
            else:
                logger.error(f"Backup failed: {result.stderr}")
                self.bot.send_message(message.chat.id, "Ошибка при создании резервной копии")
        except Exception as e:
            logger.error(f"Error during backup: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при создании резервной копии")
    
    def restore_config(self, message):
        try:
            result = subprocess.run(['scripts/restore.sh'], capture_output=True, text=True)
            if result.returncode == 0:
                self.bot.send_message(message.chat.id, "Резервная копия импортирована")
                logger.info("Configuration restored successfully")
            else:
                logger.error(f"Restore failed: {result.stderr}")
                self.bot.send_message(message.chat.id, "Ошибка при восстановлении резервной копии")
        except Exception as e:
            logger.error(f"Error during restore: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при восстановлении резервной копии")
    
    def install_wireguard(self, message):
        config_file = Path('/etc/wireguard/wg0.conf')
        
        if config_file.exists():
            logger.info(f"WireGuard config already exists: {config_file}")
            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            yes_btn = types.KeyboardButton("Да")
            no_btn = types.KeyboardButton("Нет")
            markup.add(yes_btn, no_btn)
            self.bot.send_message(
                message.chat.id, 
                text="Wireguard уже настроен.\nХотите настроить заново?", 
                reply_markup=markup
            )
        else:
            logger.info(f"WireGuard config not found: {config_file}")
            self.bot.send_message(
                message.chat.id, 
                "Запускаю установку Wireguard.\nПожалуйста дождитесь завершения установки."
            )
            self._run_wireguard_install(message)
    
    def reinstall_wireguard(self, message):
        try:
            self.bot.send_message(message.chat.id, "Удаляю конфиги...")
            
            cleanup_commands = [
                "rm -f variables.sh",
                "rm -rf /etc/wireguard/",
                "mkdir -p /etc/wireguard/",
                "rm -f configs.txt"
            ]
            
            for cmd in cleanup_commands:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode != 0:
                    logger.warning(f"Cleanup command failed: {cmd}, error: {result.stderr}")
            
            self.bot.send_message(message.chat.id, "Запускаю установку Wireguard")
            self._run_wireguard_install(message)
            
        except Exception as e:
            logger.error(f"Error during WireGuard reinstallation: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при переустановке WireGuard")
        
        self.show_main_menu(message)
    
    def _run_wireguard_install(self, message):
        try:
            result = subprocess.run(['scripts/start_wg.sh'], capture_output=True, text=True)
            if result.returncode == 0:
                self.bot.send_message(message.chat.id, "Установка Wireguard завершена")
                logger.info("WireGuard installation completed successfully")
            else:
                logger.error(f"WireGuard installation failed: {result.stderr}")
                self.bot.send_message(message.chat.id, "Ошибка при установке WireGuard")
        except Exception as e:
            logger.error(f"Error running WireGuard installation: {e}")
            self.bot.send_message(message.chat.id, "Ошибка при установке WireGuard")
    
    def scan_existing_configs(self) -> dict:
        """Scan /etc/wireguard/ for existing client configurations"""
        configs = {}
        wireguard_dir = Path('/etc/wireguard')
        
        if not wireguard_dir.exists():
            logger.warning("WireGuard directory does not exist")
            return configs
        
        try:
            # Find all client config files
            client_configs = list(wireguard_dir.glob('*_cl.conf'))
            
            for config_file in client_configs:
                try:
                    # Extract client name from filename (remove _cl.conf suffix)
                    client_name = config_file.stem.replace('_cl', '')
                    
                    # Read config to extract IP
                    with open(config_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Extract IP from Address line
                    ip_address = None
                    for line in content.split('\n'):
                        if line.strip().startswith('Address = '):
                            address_line = line.strip().replace('Address = ', '')
                            # Extract IP without subnet mask
                            ip_address = address_line.split('/')[0]
                            break
                    
                    if ip_address:
                        # Extract last octet
                        last_octet = ip_address.split('.')[-1]
                        configs[client_name] = {
                            'file': config_file,
                            'ip': ip_address,
                            'octet': last_octet
                        }
                        logger.info(f"Found config: {client_name} -> {ip_address}")
                    
                except Exception as e:
                    logger.error(f"Error reading config {config_file}: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"Error scanning WireGuard directory: {e}")
        
        return configs
    
    def recreate_configs_file(self, configs: dict) -> bool:
        """Recreate the configs.txt file based on existing configurations"""
        try:
            configs_content = []
            configs_content.append("# WireGuard Client Configurations")
            configs_content.append(f"# Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            configs_content.append("")
            
            if not configs:
                configs_content.append("No client configurations found.")
            else:
                configs_content.append(f"Total clients: {len(configs)}")
                configs_content.append("")
                configs_content.append("Client configurations:")
                
                # Sort by octet number
                sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
                
                for client_name, config_info in sorted_configs:
                    configs_content.append(f"  {client_name}: {config_info['ip']} (octet: {config_info['octet']})")
            
            # Write to configs.txt
            configs_file = Path('configs.txt')
            with open(configs_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(configs_content))
            
            logger.info(f"Recreated configs.txt with {len(configs)} entries")
            return True
            
        except Exception as e:
            logger.error(f"Error recreating configs file: {e}")
            return False
    
    def recreate_configs(self, message):
        """Recreate configuration files based on existing WireGuard configs"""
        try:
            self.bot.send_message(message.chat.id, "🔄 Сканирование существующих конфигураций...")
            
            # Scan existing configurations
            configs = self.scan_existing_configs()
            
            if not configs:
                self.bot.send_message(
                    message.chat.id, 
                    "⚠️ Не найдено клиентских конфигураций в /etc/wireguard/"
                )
                logger.info("No client configurations found for recreation")
                return
            
            # Recreate configs.txt file
            if self.recreate_configs_file(configs):
                success_msg = f"✅ Пересоздано конфигураций: {len(configs)}\n\n"
                success_msg += "Найденные клиенты:\n"
                
                # Sort by octet for display
                sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
                for client_name, config_info in sorted_configs[:10]:  # Show max 10 entries
                    success_msg += f"• {client_name}: {config_info['ip']}\n"
                
                if len(configs) > 10:
                    success_msg += f"... и ещё {len(configs) - 10} клиентов\n"
                
                self.bot.send_message(message.chat.id, success_msg)
                
                # Send the recreated configs.txt file
                try:
                    with open('configs.txt', 'rb') as f:
                        self.bot.send_document(
                            message.chat.id, 
                            f, 
                            caption="📄 Пересозданный файл конфигураций"
                        )
                except Exception as e:
                    logger.error(f"Error sending recreated configs file: {e}")
                
                logger.info(f"Successfully recreated configs for {len(configs)} clients")
            else:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Ошибка при пересоздании файла конфигураций"
                )
                
        except Exception as e:
            logger.error(f"Error during configs recreation: {e}")
            self.bot.send_message(
                message.chat.id, 
                "❌ Произошла ошибка при пересоздании конфигураций"
            )
    
    def show_clients_monitor(self, message):
        """Show detailed client monitoring with IPs and config names"""
        try:
            self.bot.send_message(message.chat.id, "🔍 Получение списка клиентов...")
            
            # Scan existing configurations
            configs = self.scan_existing_configs()
            
            if not configs:
                self.bot.send_message(
                    message.chat.id, 
                    "⚠️ Клиентские конфигурации не найдены"
                )
                return
            
            # Build detailed client list
            monitor_msg = f"👥 **Монитор клиентов WireGuard**\n\n"
            monitor_msg += f"📊 **Общая статистика:**\n"
            monitor_msg += f"• Активных клиентов: {len(configs)}\n"
            
            # Sort by IP octet for organized display
            sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
            
            monitor_msg += f"\n🗺 **Список клиентов:**\n"
            
            # Group clients for better display (max 20 per message)
            chunks = [sorted_configs[i:i+20] for i in range(0, len(sorted_configs), 20)]
            
            for chunk_idx, chunk in enumerate(chunks):
                if chunk_idx > 0:
                    monitor_msg = f"\n🗺 **Продолжение списка клиентов:**\n"
                
                for client_name, config_info in chunk:
                    # Get file modification time
                    try:
                        mod_time = datetime.fromtimestamp(config_info['file'].stat().st_mtime)
                        time_str = mod_time.strftime('%d.%m %H:%M')
                    except:
                        time_str = "N/A"
                    
                    # Get file size
                    try:
                        file_size = config_info['file'].stat().st_size
                        size_str = f"{file_size}B" if file_size < 1024 else f"{file_size//1024}KB"
                    except:
                        size_str = "N/A"
                    
                    # Format entry with emoji indicators and escape markdown
                    status_emoji = "🟢"  # Green circle for active
                    escaped_name = client_name.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]')
                    monitor_msg += f"{status_emoji} **{escaped_name}**\n"
                    monitor_msg += f"   🌍 IP: `{config_info['ip']}`\n"
                    monitor_msg += f"   📅 Создан: {time_str}\n"
                    monitor_msg += f"   📄 Размер: {size_str}\n\n"
                
                # Send message (split if too long)
                if len(monitor_msg) > 4000:
                    self.bot.send_message(message.chat.id, monitor_msg, parse_mode='Markdown')
                    monitor_msg = ""
            
            # Send remaining content
            if monitor_msg:
                self.bot.send_message(message.chat.id, monitor_msg, parse_mode='Markdown')
            
            # Add summary at the end
            if len(configs) > 20:
                summary_msg = f"\n📊 **Сводка:**\n"
                octets = [int(config['octet']) for config in configs.values()]
                used_octets = set(octets)
                available_octets = set(range(2, 254)) - used_octets
                
                summary_msg += f"• Используемые IP: {min(octets)}-{max(octets)}\n"
                summary_msg += f"• Свободно IP: {len(available_octets)}\n"
                
                # Show next available IPs
                next_available = sorted(available_octets)[:5]
                if next_available:
                    ips_str = ", ".join([f"{self.wg_ip_hint}.{octet}" for octet in next_available])
                    summary_msg += f"• Ближайшие свободные: {ips_str}\n"
                
                self.bot.send_message(message.chat.id, summary_msg, parse_mode='Markdown')
            
            logger.info(f"Client monitoring displayed for {len(configs)} clients")
            
        except Exception as e:
            logger.error(f"Error showing client monitor: {e}")
            self.bot.send_message(
                message.chat.id, 
                "❌ Ошибка при получении списка клиентов"
            )
    
    def show_statistics(self, message):
        """Show WireGuard server statistics"""
        try:
            self.bot.send_message(message.chat.id, "📊 Сбор статистики...")
            
            # Scan existing configurations
            configs = self.scan_existing_configs()
            
            # Get server status
            server_status = self.get_server_status()
            
            # Build statistics message
            stats_msg = "📊 **Статистика WireGuard сервера**\n\n"
            
            # Server info
            stats_msg += f"🟢 **Статус сервера:** {server_status['status']}\n"
            if server_status.get('interface'):
                stats_msg += f"🔌 **Интерфейс:** {server_status['interface']}\n"
            
            # Client statistics
            stats_msg += f"\n👥 **Клиентские конфигурации:**\n"
            stats_msg += f"• Всего клиентов: {len(configs)}\n"
            
            if configs:
                # IP range analysis
                octets = [int(config['octet']) for config in configs.values()]
                stats_msg += f"• Диапазон IP: {self.wg_ip_hint}.{min(octets)} - {self.wg_ip_hint}.{max(octets)}\n"
                
                # Available IPs
                used_octets = set(octets)
                available_octets = set(range(2, 254)) - used_octets
                stats_msg += f"• Свободных IP: {len(available_octets)}\n"
                
                # Recent configs
                stats_msg += f"\n🗓 **Последние клиенты:**\n"
                sorted_configs = sorted(
                    configs.items(), 
                    key=lambda x: x[1]['file'].stat().st_mtime, 
                    reverse=True
                )[:5]
                
                for client_name, config_info in sorted_configs:
                    mod_time = datetime.fromtimestamp(config_info['file'].stat().st_mtime)
                    stats_msg += f"• **{client_name}** ({config_info['ip']}) - {mod_time.strftime('%d.%m.%Y %H:%M')}\n"
            else:
                stats_msg += "• Клиентские конфигурации не найдены\n"
            
            # System info
            system_info = self.get_system_info()
            if system_info:
                stats_msg += f"\n💻 **Системная информация:**\n{system_info}"
            
            self.bot.send_message(message.chat.id, stats_msg, parse_mode='Markdown')
            logger.info(f"Statistics shown for {len(configs)} clients")
            
        except Exception as e:
            logger.error(f"Error showing statistics: {e}")
            self.bot.send_message(
                message.chat.id, 
                "❌ Ошибка при сборе статистики"
            )
    
    def get_server_status(self) -> dict:
        """Get WireGuard server status"""
        try:
            # Check if WireGuard is running (use ps instead of systemctl in container)
            result = subprocess.run(
                ['pgrep', '-f', 'wg-quick.*wg0'], 
                capture_output=True, 
                text=True
            )
            
            status = "✅ Активен" if result.returncode == 0 else "❌ Неактивен"
            
            # Get interface info if active
            interface_info = None
            if result.returncode == 0:
                wg_result = subprocess.run(['wg', 'show'], capture_output=True, text=True)
                if wg_result.returncode == 0 and wg_result.stdout:
                    interface_info = "wg0"
            
            return {
                'status': status,
                'interface': interface_info
            }
            
        except Exception as e:
            logger.error(f"Error getting server status: {e}")
            return {'status': '❓ Неизвестно'}
    
    def get_system_info(self) -> str:
        """Get basic system information"""
        try:
            info_parts = []
            
            # Disk usage for /etc/wireguard
            try:
                wg_dir = Path('/etc/wireguard')
                if wg_dir.exists():
                    total_size = sum(f.stat().st_size for f in wg_dir.rglob('*') if f.is_file())
                    info_parts.append(f"• Размер конфигов: {total_size / 1024:.1f} KB")
            except:
                pass
            
            # Uptime (simplified)
            try:
                uptime_result = subprocess.run(['uptime', '-p'], capture_output=True, text=True)
                if uptime_result.returncode == 0:
                    info_parts.append(f"• Uptime: {uptime_result.stdout.strip()}")
            except:
                pass
            
            return '\n'.join(info_parts) if info_parts else None
            
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return None

def main():
    try:
        if not api_tg:
            logger.error("Telegram API token not configured")
            return
        
        if not mainid:
            logger.error("No authorized users configured")
            return
        
        wg_bot = WireGuardBot(api_tg, mainid, wg_local_ip_hint)
        logger.info("Starting WireGuard Telegram Bot...")
        logger.info(f"Authorized users: {mainid}")
        wg_bot.bot.polling(none_stop=True, interval=0)
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Critical error: {e}")
        raise


if __name__ == "__main__":
    main()

