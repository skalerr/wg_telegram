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

    def escape_markdown(self, text: str) -> str:
        """Escape special markdown characters"""
        return text.replace('_', '\\_').replace('*', '\\*').replace('[', '\\[').replace(']', '\\]').replace('`', '\\`')
    
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
        bulk_add_btn = types.KeyboardButton("Массовое_создание")
        delete_btn = types.KeyboardButton("Удалить_конфиг")
        bulk_delete_btn = types.KeyboardButton("Массовое_удаление")
        recreate_btn = types.KeyboardButton("Пересоздать_конфиги")
        back_btn = types.KeyboardButton("Назад")
        
        markup.add(stats_btn, monitor_btn)
        markup.add(configs_btn)
        markup.add(add_btn, bulk_add_btn)
        markup.add(delete_btn, bulk_delete_btn)
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
        """Delete VPN client configuration by name or IP octet"""
        if not self.validate_message_type(message):
            self.show_monitoring_menu(message)
            return
        
        try:
            input_text = self.sanitize_input(message.text.strip())
            
            # Get current configurations
            configs = self.scan_existing_configs()
            
            if not configs:
                self.bot.send_message(message.chat.id, "❌ Нет клиентов для удаления")
                self.show_monitoring_menu(message)
                return
            
            # Determine if input is client name or IP octet
            client_name = None
            ip_octet = None
            
            if input_text.isdigit():
                # Input is IP octet
                ip_octet = int(input_text)
                if not (2 <= ip_octet <= 254):
                    self.bot.send_message(
                        message.chat.id, 
                        "❌ IP октет должен быть от 2 до 254"
                    )
                    self.show_monitoring_menu(message)
                    return
                
                # Find client by IP octet
                for name, info in configs.items():
                    if int(info['octet']) == ip_octet:
                        client_name = name
                        break
                
                if not client_name:
                    self.bot.send_message(
                        message.chat.id, 
                        f"❌ Клиент с IP {self.wg_ip_hint}.{ip_octet} не найден"
                    )
                    self.show_monitoring_menu(message)
                    return
            else:
                # Input is client name
                if input_text not in configs:
                    self.bot.send_message(
                        message.chat.id, 
                        f"❌ Клиент '{input_text}' не найден"
                    )
                    self.show_monitoring_menu(message)
                    return
                
                client_name = input_text
                ip_octet = int(configs[client_name]['octet'])
            
            # Perform deletion
            success, message_text = self.perform_client_deletion(client_name, ip_octet, message.chat.id)
            
            if success:
                self.bot.send_message(message.chat.id, message_text, parse_mode='Markdown')
                logger.info(f"Successfully deleted client: {client_name} (IP: {self.wg_ip_hint}.{ip_octet})")
            else:
                self.bot.send_message(message.chat.id, f"❌ {message_text}")
                logger.error(f"Failed to delete client: {client_name} - {message_text}")
                
        except Exception as e:
            logger.error(f"Error deleting VPN config: {e}")
            self.bot.send_message(message.chat.id, "❌ Произошла ошибка при удалении конфигурации")
        
        self.show_monitoring_menu(message)

    def perform_client_deletion(self, client_name, ip_octet, chat_id):
        """Actually perform the client deletion"""
        try:
            self.bot.send_message(
                chat_id,
                f"🗑️ Удаление клиента **{self.escape_markdown(client_name)}**...",
                parse_mode='Markdown'
            )
            
            deleted_files = []
            errors = []
            
            # 1. Remove from main server config (wg0.conf)
            try:
                self.remove_client_from_server_config(client_name, ip_octet)
                deleted_files.append("server config peer")
            except Exception as e:
                errors.append(f"server config: {str(e)}")
            
            # 2. Remove client config file
            client_config_path = Path(f"/etc/wireguard/{client_name}_cl.conf")
            if client_config_path.exists():
                try:
                    client_config_path.unlink()
                    deleted_files.append("client config")
                except Exception as e:
                    errors.append(f"client config: {str(e)}")
            
            # 3. Remove client keys
            for key_type in ["privatekey", "publickey"]:
                key_path = Path(f"/etc/wireguard/{client_name}_{key_type}")
                if key_path.exists():
                    try:
                        key_path.unlink()
                        deleted_files.append(f"client {key_type}")
                    except Exception as e:
                        errors.append(f"{key_type}: {str(e)}")
            
            # 4. Update configs.txt
            try:
                self.update_configs_file_after_deletion(client_name, ip_octet)
                deleted_files.append("configs.txt entry")
            except Exception as e:
                errors.append(f"configs.txt: {str(e)}")
            
            # 5. Restart WireGuard
            try:
                result = subprocess.run(['wg-quick', 'down', 'wg0'], capture_output=True, text=True)
                result = subprocess.run(['wg-quick', 'up', 'wg0'], capture_output=True, text=True)
                if result.returncode == 0:
                    deleted_files.append("WireGuard restarted")
                else:
                    errors.append(f"WireGuard restart: {result.stderr}")
            except Exception as e:
                errors.append(f"WireGuard restart: {str(e)}")
            
            # Prepare result message
            if deleted_files and not errors:
                return True, f"✅ **Клиент '{client_name}' полностью удален**\n\n📂 Удалено: {', '.join(deleted_files)}"
            elif deleted_files and errors:
                return True, f"⚠️ **Клиент '{client_name}' частично удален**\n\n✅ Удалено: {', '.join(deleted_files)}\n❌ Ошибки: {', '.join(errors)}"
            else:
                return False, f"Не удалось удалить клиента: {', '.join(errors)}"
                
        except Exception as e:
            logger.error(f"Error in perform_client_deletion: {e}")
            return False, f"Критическая ошибка: {str(e)}"

    def remove_client_from_server_config(self, client_name, ip_octet):
        """Remove client peer from server wg0.conf"""
        config_path = Path("/etc/wireguard/wg0.conf")
        if not config_path.exists():
            raise Exception("Server config not found")
        
        # Read current config
        with open(config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find and remove client peer section
        new_lines = []
        skip_lines = 0
        peer_found = False
        
        for i, line in enumerate(lines):
            if skip_lines > 0:
                skip_lines -= 1
                continue
                
            # Look for the AllowedIPs line with our client's IP
            if line.strip() == f"AllowedIPs = {self.wg_ip_hint}.{ip_octet}/32":
                peer_found = True
                # Remove this line and the two lines before it ([Peer] and PublicKey)
                # Remove the last 2 lines from new_lines (they should be [Peer] and PublicKey)
                if len(new_lines) >= 2:
                    new_lines = new_lines[:-2]
                # Skip current line
                continue
            
            new_lines.append(line)
        
        if not peer_found:
            raise Exception(f"Peer with IP {self.wg_ip_hint}.{ip_octet} not found in server config")
        
        # Write updated config
        with open(config_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)

    def update_configs_file_after_deletion(self, client_name, ip_octet):
        """Update configs.txt after client deletion"""
        configs_file = Path("configs.txt")
        
        if not configs_file.exists():
            return  # File doesn't exist, nothing to update
        
        try:
            with open(configs_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # Remove lines containing the client
            new_lines = []
            for line in lines:
                # Skip lines that contain this client's info
                if not (client_name in line or f".{ip_octet} =" in line):
                    new_lines.append(line)
            
            # Write updated file
            with open(configs_file, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
                
        except Exception as e:
            logger.error(f"Error updating configs.txt: {e}")
            raise



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

    def start_bulk_creation(self, message):
        """Start bulk client creation process"""
        try:
            help_text = (
                "📋 **Массовое создание клиентов**\n\n"
                "Отправьте список имен клиентов в одном из форматов:\n\n"
                "**Формат 1 - Простой список:**\n"
                "```\n"
                "client1\n"
                "client2\n"
                "client3\n"
                "```\n\n"
                "**Формат 2 - С указанием IP:**\n"
                "```\n"
                "client1:5\n"
                "client2:10\n"
                "client3:15\n"
                "```\n"
                "(где число после ':' - последний октет IP)\n\n"
                "**Формат 3 - Смешанный:**\n"
                "```\n"
                "client1\n"
                "client2:20\n"
                "client3\n"
                "```\n\n"
                "⚠️ **Ограничения:**\n"
                "• Имена только латинские буквы, цифры, дефисы, подчеркивания\n"
                "• IP октеты от 2 до 254\n\n"
                "Отправьте список клиентов:"
            )
            
            self.bot.send_message(
                message.chat.id,
                help_text,
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            
            self.bot.register_next_step_handler(message, self.handle_bulk_creation)
            
        except Exception as e:
            logger.error(f"Error starting bulk creation: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при запуске массового создания")
            self.show_monitoring_menu(message)

    def handle_bulk_creation(self, message):
        """Handle bulk client creation"""
        if not self.is_authorized(message.chat.id):
            self.send_unauthorized_message(message)
            return
        
        if not self.validate_message_type(message):
            self.show_monitoring_menu(message)
            return
        
        try:
            # Parse client list
            client_list = self.parse_client_list(message.text)
            
            if not client_list:
                self.bot.send_message(message.chat.id, "❌ Не удалось распознать список клиентов")
                self.show_monitoring_menu(message)
                return
            
            
            # Validate clients
            validation_result = self.validate_bulk_clients(client_list)
            if not validation_result["valid"]:
                error_msg = f"❌ Ошибки в списке клиентов:\n{validation_result['errors']}"
                self.bot.send_message(message.chat.id, error_msg)
                self.show_monitoring_menu(message)
                return
            
            # Show confirmation
            self.show_bulk_confirmation(message, client_list)
            
        except Exception as e:
            logger.error(f"Error handling bulk creation: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при обработке списка")
            self.show_monitoring_menu(message)

    def parse_client_list(self, text):
        """Parse client list from text"""
        try:
            clients = []
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                if ':' in line:
                    # Format: client_name:ip_octet
                    name, ip_str = line.split(':', 1)
                    name = name.strip()
                    try:
                        ip_octet = int(ip_str.strip())
                        if ip_octet < 2 or ip_octet > 254:
                            continue
                    except ValueError:
                        continue
                    clients.append({"name": name, "ip": ip_octet})
                else:
                    # Format: client_name (auto IP)
                    clients.append({"name": line, "ip": "auto"})
            
            return clients
            
        except Exception as e:
            logger.error(f"Error parsing client list: {e}")
            return []

    def validate_bulk_clients(self, client_list):
        """Validate bulk client list"""
        try:
            errors = []
            names = set()
            used_ips = set()
            
            # Get existing configurations
            existing_configs = self.scan_existing_configs()
            existing_names = set(existing_configs.keys())
            existing_ips = set(int(config['octet']) for config in existing_configs.values())
            
            import re
            name_pattern = re.compile(r'^[a-zA-Z0-9_-]+$')
            
            for i, client in enumerate(client_list, 1):
                name = client["name"]
                ip_octet = client["ip"]
                
                # Validate name format
                if not name_pattern.match(name):
                    errors.append(f"Строка {i}: недопустимые символы в имени '{name}'")
                
                # Check name length
                if len(name) > 50:
                    errors.append(f"Строка {i}: имя '{name}' слишком длинное (макс 50 символов)")
                
                # Check for duplicate names in list
                if name in names:
                    errors.append(f"Строка {i}: дублирующееся имя '{name}'")
                names.add(name)
                
                # Check if name already exists
                if name in existing_names:
                    errors.append(f"Строка {i}: клиент '{name}' уже существует")
                
                # Validate IP if specified
                if ip_octet != "auto":
                    if ip_octet in used_ips:
                        errors.append(f"Строка {i}: дублирующийся IP .{ip_octet}")
                    if ip_octet in existing_ips:
                        errors.append(f"Строка {i}: IP .{ip_octet} уже используется")
                    used_ips.add(ip_octet)
            
            return {
                "valid": len(errors) == 0,
                "errors": "\n".join(errors)
            }
            
        except Exception as e:
            logger.error(f"Error validating bulk clients: {e}")
            return {"valid": False, "errors": "Ошибка при валидации списка"}

    def show_bulk_confirmation(self, message, client_list):
        """Show bulk creation confirmation"""
        try:
            # Count auto and manual IPs
            auto_count = sum(1 for c in client_list if c["ip"] == "auto")
            manual_count = len(client_list) - auto_count
            
            # Create preview
            preview_lines = []
            for i, client in enumerate(client_list[:10]):  # Show first 10
                ip_info = f"IP: .{client['ip']}" if client["ip"] != "auto" else "IP: авто"
                preview_lines.append(f"• **{self.escape_markdown(client['name'])}** ({ip_info})")
            
            if len(client_list) > 10:
                preview_lines.append(f"... и ещё {len(client_list) - 10} клиентов")
            
            confirmation_msg = (
                f"📋 **Подтверждение массового создания**\n\n"
                f"👥 **Клиентов к созданию:** {len(client_list)}\n"
                f"🔄 **Автоматический IP:** {auto_count}\n"
                f"📍 **Указанный IP:** {manual_count}\n\n"
                f"**Предварительный просмотр:**\n" + "\n".join(preview_lines) + "\n\n"
                f"⏱️ **Примерное время:** {len(client_list) * 3} сек.\n\n"
                f"Создать всех клиентов?"
            )
            
            # Create inline keyboard
            markup = types.InlineKeyboardMarkup()
            confirm_btn = types.InlineKeyboardButton(
                "✅ Создать всех", 
                callback_data="bulk_create_confirm"
            )
            cancel_btn = types.InlineKeyboardButton(
                "❌ Отменить", 
                callback_data="bulk_create_cancel"
            )
            markup.row(confirm_btn)
            markup.row(cancel_btn)
            
            # Store client list temporarily
            self.temp_bulk_clients = client_list
            
            self.bot.send_message(
                message.chat.id,
                confirmation_msg,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing bulk confirmation: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при подготовке создания")
            self.show_monitoring_menu(message)

    def perform_bulk_creation(self, message, client_list):
        """Actually perform bulk client creation"""
        try:
            # Edit message to show progress
            self.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text="⏳ **Массовое создание клиентов...**\n\nПожалуйста, подождите.",
                parse_mode='Markdown'
            )
            
            results = {
                "created": [],
                "failed": [],
                "total": len(client_list)
            }
            
            # Progress tracking
            progress_msg_id = None
            
            for i, client in enumerate(client_list, 1):
                try:
                    # Update progress every 5 clients or on last client
                    if i % 5 == 0 or i == len(client_list):
                        progress_text = (
                            f"⏳ **Создание клиентов...**\n\n"
                            f"📊 Прогресс: {i}/{len(client_list)}\n"
                            f"✅ Создано: {len(results['created'])}\n"
                            f"❌ Ошибок: {len(results['failed'])}\n\n"
                            f"Текущий клиент: **{self.escape_markdown(client['name'])}**"
                        )
                        
                        if progress_msg_id:
                            try:
                                self.bot.edit_message_text(
                                    chat_id=message.chat.id,
                                    message_id=progress_msg_id,
                                    text=progress_text,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                        else:
                            progress_msg = self.bot.send_message(
                                message.chat.id,
                                progress_text,
                                parse_mode='Markdown'
                            )
                            progress_msg_id = progress_msg.message_id
                    
                    # Create client
                    success, result_msg = self.add_vpn_config(client["name"], client["ip"])
                    
                    if success:
                        results["created"].append({
                            "name": client["name"],
                            "ip": client["ip"]
                        })
                        logger.info(f"Bulk creation: {client['name']} created successfully")
                    else:
                        results["failed"].append({
                            "name": client["name"],
                            "error": result_msg
                        })
                        logger.error(f"Bulk creation: {client['name']} failed - {result_msg}")
                    
                    # Small delay to prevent overwhelming
                    import time
                    time.sleep(0.5)
                    
                except Exception as e:
                    results["failed"].append({
                        "name": client["name"],
                        "error": str(e)
                    })
                    logger.error(f"Error creating client {client['name']}: {e}")
            
            # Send final results
            self.send_bulk_results(message, results)
            
            # Clean up temp data
            if hasattr(self, 'temp_bulk_clients'):
                delattr(self, 'temp_bulk_clients')
            
        except Exception as e:
            logger.error(f"Error performing bulk creation: {e}")
            self.bot.send_message(
                message.chat.id,
                f"❌ **Критическая ошибка при массовом создании:**\n{str(e)[:200]}",
                parse_mode='Markdown'
            )
            self.show_monitoring_menu(message)

    def send_bulk_results(self, message, results):
        """Send bulk creation results"""
        try:
            created_count = len(results["created"])
            failed_count = len(results["failed"])
            total_count = results["total"]
            
            # Create results summary
            if created_count == total_count:
                status_emoji = "✅"
                status_text = "Все клиенты созданы успешно!"
            elif created_count > 0:
                status_emoji = "⚠️"
                status_text = "Создание завершено с ошибками"
            else:
                status_emoji = "❌"
                status_text = "Не удалось создать ни одного клиента"
            
            summary_msg = (
                f"{status_emoji} **{status_text}**\n\n"
                f"📊 **Статистика:**\n"
                f"✅ Создано: {created_count}/{total_count}\n"
                f"❌ Ошибок: {failed_count}\n"
            )
            
            # Add created clients list
            if results["created"]:
                summary_msg += f"\n🟢 **Созданные клиенты:**\n"
                for client in results["created"][:10]:  # Show first 10
                    ip_info = f"(.{client['ip']})" if client["ip"] != "auto" else "(авто IP)"
                    summary_msg += f"• **{self.escape_markdown(client['name'])}** {ip_info}\n"
                
                if len(results["created"]) > 10:
                    summary_msg += f"... и ещё {len(results['created']) - 10} клиентов\n"
            
            # Add failed clients list
            if results["failed"]:
                summary_msg += f"\n🔴 **Ошибки:**\n"
                for client in results["failed"][:5]:  # Show first 5 errors
                    error_short = client["error"][:50] + "..." if len(client["error"]) > 50 else client["error"]
                    summary_msg += f"• **{self.escape_markdown(client['name'])}**: {error_short}\n"
                
                if len(results["failed"]) > 5:
                    summary_msg += f"... и ещё {len(results['failed']) - 5} ошибок\n"
            
            # Send results
            self.bot.send_message(message.chat.id, summary_msg, parse_mode='Markdown')
            
            # Send configs archive if there are created clients
            if results["created"]:
                self.send_bulk_configs_archive(message, results["created"])
            
            self.show_monitoring_menu(message)
            logger.info(f"Bulk creation completed: {created_count} created, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error sending bulk results: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при отправке результатов")

    def send_bulk_configs_archive(self, message, created_clients):
        """Send archive with all created configs"""
        try:
            if len(created_clients) <= 5:
                # Send configs individually for small batches
                for client in created_clients:
                    try:
                        config_file_path = Path(f"/etc/wireguard/{client['name']}_cl.conf")
                        if config_file_path.exists():
                            with open(config_file_path, 'rb') as f:
                                self.bot.send_document(
                                    message.chat.id,
                                    f,
                                    caption=f"📄 {client['name']}"
                                )
                    except Exception as e:
                        logger.error(f"Error sending individual config {client['name']}: {e}")
            else:
                # Create ZIP archive for large batches
                import zipfile
                import tempfile
                import os
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_zip:
                    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        configs_added = 0
                        for client in created_clients:
                            config_file_path = Path(f"/etc/wireguard/{client['name']}_cl.conf")
                            if config_file_path.exists():
                                zipf.write(
                                    config_file_path, 
                                    f"{client['name']}.conf"
                                )
                                configs_added += 1
                    
                    if configs_added > 0:
                        with open(temp_zip.name, 'rb') as f:
                            self.bot.send_document(
                                message.chat.id,
                                f,
                                caption=f"📦 Архив конфигураций ({configs_added} файлов)",
                                filename=f"wireguard_configs_{len(created_clients)}.zip"
                            )
                    
                    # Clean up
                    os.unlink(temp_zip.name)
                    
        except Exception as e:
            logger.error(f"Error creating configs archive: {e}")
            self.bot.send_message(message.chat.id, "⚠️ Не удалось создать архив конфигураций")

    def start_bulk_deletion(self, message):
        """Start bulk client deletion process"""
        try:
            # Get current configurations
            configs = self.scan_existing_configs()
            
            if not configs:
                self.bot.send_message(
                    message.chat.id,
                    "❌ Нет клиентов для удаления",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                self.show_monitoring_menu(message)
                return
            
            help_text = (
                "🗑️ **Массовое удаление клиентов**\n\n"
                "Отправьте список клиентов для удаления в одном из форматов:\n\n"
                "**Формат 1 - По именам:**\n"
                "```\n"
                "client1\n"
                "client2\n"
                "client3\n"
                "```\n\n"
                "**Формат 2 - По IP октетам:**\n"
                "```\n"
                "5\n"
                "10\n"
                "15\n"
                "```\n\n"
                "**Формат 3 - Смешанный:**\n"
                "```\n"
                "client1\n"
                "10\n"
                "client3\n"
                "```\n\n"
                "**Специальные команды:**\n"
                "• `*` или `all` - удалить ВСЕХ клиентов\n"
                "• `#комментарий` - строки игнорируются\n\n"
                f"**Текущие клиенты ({len(configs)}):**\n"
            )
            
            # Add current clients list (first 15)
            sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
            for i, (client_name, config_info) in enumerate(sorted_configs[:15]):
                escaped_name = self.escape_markdown(client_name)
                help_text += f"• **{escaped_name}** - {config_info['ip']} (октет: {config_info['octet']})\n"
            
            if len(configs) > 15:
                help_text += f"... и ещё {len(configs) - 15} клиентов\n"
            
            help_text += "\n⚠️ **ВНИМАНИЕ: Удаление необратимо!**\n\nОтправьте список для удаления:"
            
            self.bot.send_message(
                message.chat.id,
                help_text,
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            
            self.bot.register_next_step_handler(message, self.handle_bulk_deletion)
            
        except Exception as e:
            logger.error(f"Error starting bulk deletion: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при запуске массового удаления")
            self.show_monitoring_menu(message)

    def handle_bulk_deletion(self, message):
        """Handle bulk client deletion"""
        if not self.is_authorized(message.chat.id):
            self.send_unauthorized_message(message)
            return
        
        if not self.validate_message_type(message):
            self.show_monitoring_menu(message)
            return
        
        try:
            # Parse deletion list
            deletion_list = self.parse_deletion_list(message.text)
            
            if not deletion_list:
                self.bot.send_message(message.chat.id, "❌ Не удалось распознать список для удаления")
                self.show_monitoring_menu(message)
                return
            
            # Validate deletion list
            validation_result = self.validate_bulk_deletion(deletion_list)
            if not validation_result["valid"]:
                error_msg = f"❌ Ошибки в списке для удаления:\n{validation_result['errors']}"
                self.bot.send_message(message.chat.id, error_msg)
                self.show_monitoring_menu(message)
                return
            
            # Show confirmation
            self.show_bulk_deletion_confirmation(message, deletion_list, validation_result["clients_to_delete"])
            
        except Exception as e:
            logger.error(f"Error handling bulk deletion: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при обработке списка")
            self.show_monitoring_menu(message)

    def parse_deletion_list(self, text):
        """Parse deletion list from text"""
        try:
            items = []
            lines = text.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):  # Skip empty lines and comments
                    continue
                
                # Check for special commands
                if line.lower() in ['*', 'all', 'все']:
                    items.append({"type": "all"})
                elif line.isdigit():
                    # IP octet
                    octet = int(line)
                    if 2 <= octet <= 254:
                        items.append({"type": "ip", "value": octet})
                else:
                    # Client name
                    items.append({"type": "name", "value": line})
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing deletion list: {e}")
            return []

    def validate_bulk_deletion(self, deletion_list):
        """Validate bulk deletion list"""
        try:
            errors = []
            clients_to_delete = {}
            
            # Get existing configurations
            existing_configs = self.scan_existing_configs()
            
            if not existing_configs:
                return {"valid": False, "errors": "Нет клиентов для удаления"}
            
            for i, item in enumerate(deletion_list, 1):
                if item["type"] == "all":
                    # Delete all clients
                    clients_to_delete.update(existing_configs)
                    continue
                elif item["type"] == "ip":
                    # Find client by IP octet
                    octet = item["value"]
                    found = False
                    for name, config in existing_configs.items():
                        if int(config['octet']) == octet:
                            clients_to_delete[name] = config
                            found = True
                            break
                    
                    if not found:
                        errors.append(f"Строка {i}: IP октет {octet} не найден")
                        
                elif item["type"] == "name":
                    # Find client by name
                    name = item["value"]
                    if name in existing_configs:
                        clients_to_delete[name] = existing_configs[name]
                    else:
                        errors.append(f"Строка {i}: клиент '{name}' не найден")
            
            if not clients_to_delete and not errors:
                errors.append("Не найдено клиентов для удаления")
            
            return {
                "valid": len(errors) == 0,
                "errors": "\n".join(errors),
                "clients_to_delete": clients_to_delete
            }
            
        except Exception as e:
            logger.error(f"Error validating bulk deletion: {e}")
            return {"valid": False, "errors": "Ошибка при валидации списка"}

    def show_bulk_deletion_confirmation(self, message, deletion_list, clients_to_delete):
        """Show bulk deletion confirmation"""
        try:
            delete_count = len(clients_to_delete)
            
            # Create preview
            preview_lines = []
            for i, (client_name, config_info) in enumerate(sorted(clients_to_delete.items(), key=lambda x: int(x[1]['octet']))[:10]):
                preview_lines.append(f"• **{self.escape_markdown(client_name)}** - {config_info['ip']}")
            
            if len(clients_to_delete) > 10:
                preview_lines.append(f"... и ещё {len(clients_to_delete) - 10} клиентов")
            
            # Determine danger level
            if delete_count >= 10:
                danger_emoji = "⚠️"
                danger_text = "МАССОВОЕ УДАЛЕНИЕ"
            elif delete_count >= 5:
                danger_emoji = "🔶"
                danger_text = "Множественное удаление"
            else:
                danger_emoji = "🗑️"
                danger_text = "Удаление клиентов"
            
            confirmation_msg = (
                f"{danger_emoji} **{danger_text}**\n\n"
                f"🗂️ **Клиентов к удалению:** {delete_count}\n\n"
                f"**Будут удалены:**\n" + "\n".join(preview_lines) + "\n\n"
                f"⏱️ **Примерное время:** {delete_count * 2} сек.\n\n"
                f"🚨 **ВНИМАНИЕ: Это действие необратимо!**\n"
                f"Все файлы конфигураций и ключи будут удалены навсегда.\n\n"
                f"Продолжить удаление?"
            )
            
            # Create inline keyboard
            markup = types.InlineKeyboardMarkup()
            if delete_count >= 10:
                confirm_text = f"💥 УДАЛИТЬ ВСЕ {delete_count}"
            else:
                confirm_text = f"🗑️ Удалить {delete_count}"
                
            confirm_btn = types.InlineKeyboardButton(
                confirm_text, 
                callback_data="bulk_delete_confirm"
            )
            cancel_btn = types.InlineKeyboardButton(
                "❌ Отменить", 
                callback_data="bulk_delete_cancel"
            )
            markup.row(confirm_btn)
            markup.row(cancel_btn)
            
            # Store deletion list temporarily
            self.temp_bulk_deletion = clients_to_delete
            
            self.bot.send_message(
                message.chat.id,
                confirmation_msg,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing bulk deletion confirmation: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при подготовке удаления")
            self.show_monitoring_menu(message)

    def perform_bulk_deletion(self, message, clients_to_delete):
        """Actually perform bulk client deletion"""
        try:
            # Edit message to show progress
            self.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text="⏳ **Массовое удаление клиентов...**\n\nПожалуйста, подождите.",
                parse_mode='Markdown'
            )
            
            results = {
                "deleted": [],
                "failed": [],
                "total": len(clients_to_delete)
            }
            
            # Progress tracking
            progress_msg_id = None
            
            for i, (client_name, config_info) in enumerate(clients_to_delete.items(), 1):
                try:
                    # Update progress every 3 clients or on last client
                    if i % 3 == 0 or i == len(clients_to_delete):
                        progress_text = (
                            f"⏳ **Удаление клиентов...**\n\n"
                            f"📊 Прогресс: {i}/{len(clients_to_delete)}\n"
                            f"✅ Удалено: {len(results['deleted'])}\n"
                            f"❌ Ошибок: {len(results['failed'])}\n\n"
                            f"Текущий клиент: **{self.escape_markdown(client_name)}**"
                        )
                        
                        if progress_msg_id:
                            try:
                                self.bot.edit_message_text(
                                    chat_id=message.chat.id,
                                    message_id=progress_msg_id,
                                    text=progress_text,
                                    parse_mode='Markdown'
                                )
                            except:
                                pass
                        else:
                            progress_msg = self.bot.send_message(
                                message.chat.id,
                                progress_text,
                                parse_mode='Markdown'
                            )
                            progress_msg_id = progress_msg.message_id
                    
                    # Delete client
                    ip_octet = int(config_info['octet'])
                    success, result_msg = self.perform_client_deletion(client_name, ip_octet, message.chat.id)
                    
                    if success:
                        results["deleted"].append({
                            "name": client_name,
                            "ip": config_info['ip']
                        })
                        logger.info(f"Bulk deletion: {client_name} deleted successfully")
                    else:
                        results["failed"].append({
                            "name": client_name,
                            "error": result_msg
                        })
                        logger.error(f"Bulk deletion: {client_name} failed - {result_msg}")
                    
                    # Small delay to prevent overwhelming
                    import time
                    time.sleep(0.3)
                    
                except Exception as e:
                    results["failed"].append({
                        "name": client_name,
                        "error": str(e)
                    })
                    logger.error(f"Error deleting client {client_name}: {e}")
            
            # Send final results
            self.send_bulk_deletion_results(message, results)
            
            # Clean up temp data
            if hasattr(self, 'temp_bulk_deletion'):
                delattr(self, 'temp_bulk_deletion')
            
        except Exception as e:
            logger.error(f"Error performing bulk deletion: {e}")
            self.bot.send_message(
                message.chat.id,
                f"❌ **Критическая ошибка при массовом удалении:**\n{str(e)[:200]}",
                parse_mode='Markdown'
            )
            self.show_monitoring_menu(message)

    def send_bulk_deletion_results(self, message, results):
        """Send bulk deletion results"""
        try:
            deleted_count = len(results["deleted"])
            failed_count = len(results["failed"])
            total_count = results["total"]
            
            # Create results summary
            if deleted_count == total_count:
                status_emoji = "✅"
                status_text = "Все клиенты удалены успешно!"
            elif deleted_count > 0:
                status_emoji = "⚠️"
                status_text = "Удаление завершено с ошибками"
            else:
                status_emoji = "❌"
                status_text = "Не удалось удалить ни одного клиента"
            
            summary_msg = (
                f"{status_emoji} **{status_text}**\n\n"
                f"📊 **Статистика:**\n"
                f"🗑️ Удалено: {deleted_count}/{total_count}\n"
                f"❌ Ошибок: {failed_count}\n"
            )
            
            # Add deleted clients list
            if results["deleted"]:
                summary_msg += f"\n🟢 **Удаленные клиенты:**\n"
                for client in results["deleted"][:10]:  # Show first 10
                    summary_msg += f"• **{self.escape_markdown(client['name'])}** ({client['ip']})\n"
                
                if len(results["deleted"]) > 10:
                    summary_msg += f"... и ещё {len(results['deleted']) - 10} клиентов\n"
            
            # Add failed clients list
            if results["failed"]:
                summary_msg += f"\n🔴 **Ошибки:**\n"
                for client in results["failed"][:5]:  # Show first 5 errors
                    error_short = client["error"][:50] + "..." if len(client["error"]) > 50 else client["error"]
                    summary_msg += f"• **{self.escape_markdown(client['name'])}**: {error_short}\n"
                
                if len(results["failed"]) > 5:
                    summary_msg += f"... и ещё {len(results['failed']) - 5} ошибок\n"
            
            # Send results
            self.bot.send_message(message.chat.id, summary_msg, parse_mode='Markdown')
            
            self.show_monitoring_menu(message)
            logger.info(f"Bulk deletion completed: {deleted_count} deleted, {failed_count} failed")
            
        except Exception as e:
            logger.error(f"Error sending bulk deletion results: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при отправке результатов")

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
                    
                    # Check WireGuard status
                    import time
                    time.sleep(2)  # Wait for WireGuard to fully start
                    
                    try:
                        # Check if WireGuard is running
                        wg_status = subprocess.run(['pgrep', '-f', 'wg-quick.*wg0'], 
                                                 capture_output=True, text=True)
                        if wg_status.returncode == 0:
                            status_msg = "🟢 WireGuard сервер активен"
                        else:
                            status_msg = "🔴 WireGuard сервер неактивен"
                        
                        self.bot.send_message(call.message.chat.id, f"Статус сервера: {status_msg}")
                    except Exception as e:
                        logger.error(f"Error checking WireGuard status: {e}")
                    
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
                
            elif call.data.startswith("restore_confirm:"):
                temp_filename = call.data.split(":", 1)[1]
                self.perform_restore(call.message, temp_filename)
                self.bot.answer_callback_query(call.id)
                
            elif call.data == "restore_cancel":
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Импорт отменен"
                )
                self.show_admin_menu(call.message)
                self.bot.answer_callback_query(call.id)
                
            elif call.data == "bulk_create_confirm":
                client_list = getattr(self, 'temp_bulk_clients', [])
                if client_list:
                    self.perform_bulk_creation(call.message, client_list)
                else:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="❌ Данные для создания не найдены"
                    )
                self.bot.answer_callback_query(call.id)
                
            elif call.data == "bulk_create_cancel":
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Массовое создание отменено"
                )
                self.show_monitoring_menu(call.message)
                self.bot.answer_callback_query(call.id)
                
            elif call.data == "bulk_delete_confirm":
                clients_to_delete = getattr(self, 'temp_bulk_deletion', {})
                if clients_to_delete:
                    self.perform_bulk_deletion(call.message, clients_to_delete)
                else:
                    self.bot.edit_message_text(
                        chat_id=call.message.chat.id,
                        message_id=call.message.message_id,
                        text="❌ Данные для удаления не найдены"
                    )
                self.bot.answer_callback_query(call.id)
                
            elif call.data == "bulk_delete_cancel":
                self.bot.edit_message_text(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    text="❌ Массовое удаление отменено"
                )
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
        elif text == "Массовое_создание":
            self.start_bulk_creation(message)
        elif text == "Массовое_удаление":
            self.start_bulk_deletion(message)
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
        """Show list of clients and prompt for deletion"""
        try:
            # Get current configurations
            configs = self.scan_existing_configs()
            
            if not configs:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Нет клиентов для удаления",
                    reply_markup=types.ReplyKeyboardRemove()
                )
                self.show_monitoring_menu(message)
                return
            
            # Create client list message
            clients_msg = "👥 **Список клиентов для удаления:**\n\n"
            
            sorted_configs = sorted(configs.items(), key=lambda x: int(x[1]['octet']))
            for client_name, config_info in sorted_configs:
                escaped_name = self.escape_markdown(client_name)
                clients_msg += f"• **{escaped_name}** - {config_info['ip']} (октет: {config_info['octet']})\n"
            
            clients_msg += f"\n📝 **Способы удаления:**\n"
            clients_msg += f"**По имени:** Введите точное имя клиента\n"
            clients_msg += f"**По IP:** Введите последний октет IP\n\n"
            clients_msg += f"Например: `server1` или `47`"
            
            self.bot.send_message(
                message.chat.id, 
                clients_msg, 
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            
            self.bot.register_next_step_handler(message, self.delete_vpn_config)
            
        except Exception as e:
            logger.error(f"Error showing delete prompt: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при получении списка клиентов")
            self.show_monitoring_menu(message)
    
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
                    escaped_name = self.escape_markdown(client_name)
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
        """Create and send backup configuration as file"""
        try:
            self.bot.send_message(message.chat.id, "📦 Создание резервной копии конфигурации...")
            
            # Create backup using existing script
            result = subprocess.run(['scripts/backup.sh'], capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Backup script failed: {result.stderr}")
                self.bot.send_message(message.chat.id, "❌ Ошибка при создании резервной копии")
                return
            
            # Create comprehensive backup file
            backup_data = self.create_backup_data()
            
            if not backup_data:
                self.bot.send_message(message.chat.id, "❌ Не удалось создать резервную копию")
                return
            
            # Create backup file with timestamp
            from datetime import datetime
            import json
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"wg_backup_{timestamp}.json"
            
            with open(backup_filename, 'w', encoding='utf-8') as f:
                json.dump(backup_data, f, indent=2, ensure_ascii=False)
            
            # Send backup file
            with open(backup_filename, 'rb') as f:
                self.bot.send_document(
                    message.chat.id,
                    f,
                    caption=f"🗄️ Резервная копия WireGuard\n"
                           f"📅 Создана: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
                           f"📊 Клиентов: {len(backup_data.get('clients', {}))}"
                )
            
            # Clean up temp file
            import os
            os.remove(backup_filename)
            
            self.bot.send_message(message.chat.id, "✅ Резервная копия создана и отправлена")
            logger.info("Configuration backed up and sent successfully")
            
        except Exception as e:
            logger.error(f"Error during backup: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при создании резервной копии")

    def create_backup_data(self):
        """Create comprehensive backup data"""
        try:
            backup_data = {
                "version": "1.0",
                "created": datetime.now().isoformat(),
                "server_config": {},
                "clients": {},
                "variables": {}
            }
            
            # Backup server configuration
            server_config_path = Path("/etc/wireguard/wg0.conf")
            if server_config_path.exists():
                with open(server_config_path, 'r', encoding='utf-8') as f:
                    backup_data["server_config"]["wg0.conf"] = f.read()
            
            # Backup server keys
            for key_file in ["privatekey", "publickey"]:
                key_path = Path(f"/etc/wireguard/{key_file}")
                if key_path.exists():
                    with open(key_path, 'r', encoding='utf-8') as f:
                        backup_data["server_config"][key_file] = f.read().strip()
            
            # Backup client configurations
            configs = self.scan_existing_configs()
            for client_name, config_info in configs.items():
                client_data = {
                    "ip": config_info["ip"],
                    "octet": config_info["octet"],
                    "config_content": ""
                }
                
                # Read client config file
                if config_info["file"].exists():
                    with open(config_info["file"], 'r', encoding='utf-8') as f:
                        client_data["config_content"] = f.read()
                
                # Read client keys if they exist
                for key_type in ["privatekey", "publickey"]:
                    key_path = Path(f"/etc/wireguard/{client_name}_{key_type}")
                    if key_path.exists():
                        with open(key_path, 'r', encoding='utf-8') as f:
                            client_data[key_type] = f.read().strip()
                
                backup_data["clients"][client_name] = client_data
            
            # Backup variables
            variables_path = Path("scripts/variables.sh")
            if variables_path.exists():
                with open(variables_path, 'r', encoding='utf-8') as f:
                    backup_data["variables"]["variables.sh"] = f.read()
            
            env_path = Path("scripts/env.sh")
            if env_path.exists():
                with open(env_path, 'r', encoding='utf-8') as f:
                    backup_data["variables"]["env.sh"] = f.read()
            
            return backup_data
            
        except Exception as e:
            logger.error(f"Error creating backup data: {e}")
            return None
    
    def restore_config(self, message):
        """Start import process - ask user to send backup file"""
        try:
            self.bot.send_message(
                message.chat.id, 
                "📤 **Импорт конфигурации из файла**\n\n"
                "Отправьте файл резервной копии WireGuard (JSON файл с расширением .json)\n"
                "Файл должен быть создан функцией резервного копирования этого бота.",
                reply_markup=types.ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            
            # Register handler for file upload
            self.bot.register_next_step_handler(message, self.handle_restore_file)
            
        except Exception as e:
            logger.error(f"Error starting restore: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при запуске импорта")

    def handle_restore_file(self, message):
        """Handle uploaded backup file"""
        if not self.is_authorized(message.chat.id):
            self.send_unauthorized_message(message)
            return
        
        try:
            # Check if file was sent
            if not message.document:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Файл не найден. Отправьте JSON файл с резервной копией."
                )
                self.show_admin_menu(message)
                return
            
            # Check file extension
            if not message.document.file_name.endswith('.json'):
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Неподдерживаемый тип файла. Отправьте JSON файл."
                )
                self.show_admin_menu(message)
                return
            
            # Check file size (max 10MB)
            if message.document.file_size > 10 * 1024 * 1024:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Файл слишком большой. Максимальный размер: 10MB"
                )
                self.show_admin_menu(message)
                return
            
            self.bot.send_message(message.chat.id, "📥 Загрузка файла резервной копии...")
            
            # Download file
            file_info = self.bot.get_file(message.document.file_id)
            downloaded_file = self.bot.download_file(file_info.file_path)
            
            # Save temporarily
            import tempfile
            import json
            
            with tempfile.NamedTemporaryFile(mode='wb', suffix='.json', delete=False) as temp_file:
                temp_file.write(downloaded_file)
                temp_filename = temp_file.name
            
            # Parse and validate backup file
            try:
                with open(temp_filename, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                
                if not self.validate_backup_file(backup_data):
                    self.bot.send_message(
                        message.chat.id, 
                        "❌ Некорректный файл резервной копии"
                    )
                    return
                
                # Show confirmation
                self.show_restore_confirmation(message, backup_data, temp_filename)
                
            except json.JSONDecodeError:
                self.bot.send_message(
                    message.chat.id, 
                    "❌ Ошибка чтения файла. Файл поврежден или имеет неправильный формат."
                )
                import os
                os.unlink(temp_filename)
                self.show_admin_menu(message)
                
        except Exception as e:
            logger.error(f"Error handling restore file: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при обработке файла")
            self.show_admin_menu(message)

    def validate_backup_file(self, backup_data):
        """Validate backup file structure"""
        try:
            required_fields = ["version", "created", "server_config", "clients"]
            for field in required_fields:
                if field not in backup_data:
                    return False
            
            return True
        except:
            return False

    def show_restore_confirmation(self, message, backup_data, temp_filename):
        """Show restore confirmation with backup details"""
        try:
            clients_count = len(backup_data.get('clients', {}))
            created_date = backup_data.get('created', 'Неизвестно')
            
            # Parse date for better display
            try:
                from datetime import datetime
                created_dt = datetime.fromisoformat(created_date.replace('Z', '+00:00'))
                created_str = created_dt.strftime('%d.%m.%Y %H:%M:%S')
            except:
                created_str = created_date
            
            # Create inline keyboard for confirmation
            markup = types.InlineKeyboardMarkup()
            confirm_btn = types.InlineKeyboardButton(
                "✅ Подтвердить импорт", 
                callback_data=f"restore_confirm:{temp_filename}"
            )
            cancel_btn = types.InlineKeyboardButton(
                "❌ Отменить", 
                callback_data="restore_cancel"
            )
            markup.row(confirm_btn)
            markup.row(cancel_btn)
            
            confirmation_msg = (
                f"📋 **Подтверждение импорта**\n\n"
                f"🗄️ **Детали резервной копии:**\n"
                f"📅 Создана: {created_str}\n"
                f"👥 Клиентов: {clients_count}\n"
                f"📝 Версия: {backup_data.get('version', 'Неизвестно')}\n\n"
                f"⚠️ **ВНИМАНИЕ!**\n"
                f"Импорт заменит текущую конфигурацию WireGuard.\n"
                f"Все существующие клиенты будут удалены!\n\n"
                f"Продолжить импорт?"
            )
            
            self.bot.send_message(
                message.chat.id,
                confirmation_msg,
                reply_markup=markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            logger.error(f"Error showing restore confirmation: {e}")
            self.bot.send_message(message.chat.id, "❌ Ошибка при подготовке импорта")
            self.show_admin_menu(message)

    def perform_restore(self, message, temp_filename):
        """Actually perform the restore operation"""
        try:
            # Edit message to show progress
            self.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=message.message_id,
                text="⏳ **Выполняется импорт конфигурации...**\n\nПожалуйста, подождите.",
                parse_mode='Markdown'
            )
            
            # Load backup data
            import json
            with open(temp_filename, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
            
            # Stop WireGuard
            self.bot.send_message(message.chat.id, "🛑 Остановка WireGuard сервиса...")
            subprocess.run(['wg-quick', 'down', 'wg0'], capture_output=True, text=True)
            
            # Backup current configuration (just in case)
            import shutil
            from datetime import datetime
            backup_dir = f"/tmp/wg_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            import os
            os.makedirs(backup_dir, exist_ok=True)
            
            if Path("/etc/wireguard").exists():
                shutil.copytree("/etc/wireguard", f"{backup_dir}/wireguard", dirs_exist_ok=True)
            
            # Clear current configuration
            self.bot.send_message(message.chat.id, "🧹 Очистка текущей конфигурации...")
            subprocess.run(['rm', '-rf', '/etc/wireguard/*'], shell=True, capture_output=True)
            
            # Restore server configuration
            self.bot.send_message(message.chat.id, "🔧 Восстановление конфигурации сервера...")
            
            server_config = backup_data.get('server_config', {})
            
            # Restore main server config
            if 'wg0.conf' in server_config:
                with open('/etc/wireguard/wg0.conf', 'w', encoding='utf-8') as f:
                    f.write(server_config['wg0.conf'])
            
            # Restore server keys
            for key_file in ['privatekey', 'publickey']:
                if key_file in server_config:
                    with open(f'/etc/wireguard/{key_file}', 'w', encoding='utf-8') as f:
                        f.write(server_config[key_file])
                    subprocess.run(['chmod', '600' if key_file == 'privatekey' else '644', f'/etc/wireguard/{key_file}'])
            
            # Restore client configurations
            self.bot.send_message(message.chat.id, "👥 Восстановление клиентских конфигураций...")
            
            clients = backup_data.get('clients', {})
            restored_clients = 0
            
            for client_name, client_data in clients.items():
                try:
                    # Restore client config file
                    if 'config_content' in client_data and client_data['config_content']:
                        with open(f'/etc/wireguard/{client_name}_cl.conf', 'w', encoding='utf-8') as f:
                            f.write(client_data['config_content'])
                    
                    # Restore client keys
                    for key_type in ['privatekey', 'publickey']:
                        if key_type in client_data:
                            with open(f'/etc/wireguard/{client_name}_{key_type}', 'w', encoding='utf-8') as f:
                                f.write(client_data[key_type])
                            subprocess.run(['chmod', '600' if key_type == 'privatekey' else '644', 
                                          f'/etc/wireguard/{client_name}_{key_type}'])
                    
                    restored_clients += 1
                    
                except Exception as e:
                    logger.error(f"Error restoring client {client_name}: {e}")
            
            # Restore variables
            variables = backup_data.get('variables', {})
            if 'variables.sh' in variables:
                with open('scripts/variables.sh', 'w', encoding='utf-8') as f:
                    f.write(variables['variables.sh'])
            
            if 'env.sh' in variables:
                with open('scripts/env.sh', 'w', encoding='utf-8') as f:
                    f.write(variables['env.sh'])
            
            # Start WireGuard
            self.bot.send_message(message.chat.id, "🚀 Запуск WireGuard сервиса...")
            result = subprocess.run(['wg-quick', 'up', 'wg0'], capture_output=True, text=True)
            
            # Clean up temp file
            os.unlink(temp_filename)
            
            # Send final result
            if result.returncode == 0:
                success_msg = (
                    f"✅ **Импорт завершен успешно!**\n\n"
                    f"📊 **Статистика восстановления:**\n"
                    f"👥 Клиентов восстановлено: {restored_clients}\n"
                    f"🟢 WireGuard сервис: Активен\n\n"
                    f"🗄️ Предыдущая конфигурация сохранена в: `{backup_dir}`"
                )
            else:
                success_msg = (
                    f"⚠️ **Импорт выполнен с ошибками**\n\n"
                    f"👥 Клиентов восстановлено: {restored_clients}\n"
                    f"❌ Ошибка запуска WireGuard: {result.stderr[:200]}...\n\n"
                    f"🗄️ Предыдущая конфигурация сохранена в: `{backup_dir}`"
                )
            
            self.bot.send_message(message.chat.id, success_msg, parse_mode='Markdown')
            self.show_admin_menu(message)
            logger.info(f"Configuration restored from backup, {restored_clients} clients restored")
            
        except Exception as e:
            logger.error(f"Error performing restore: {e}")
            self.bot.send_message(
                message.chat.id, 
                f"❌ **Ошибка при импорте:**\n{str(e)[:200]}...\n\n"
                f"Попробуйте восстановить конфигурацию вручную из резервной копии в `{backup_dir if 'backup_dir' in locals() else '/tmp'}`",
                parse_mode='Markdown'
            )
            self.show_admin_menu(message)
            
            # Clean up temp file
            try:
                import os
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
            except:
                pass
    
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
                    escaped_name = self.escape_markdown(client_name)
                    success_msg += f"• {escaped_name}: {config_info['ip']}\n"
                
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
                    escaped_name = self.escape_markdown(client_name)
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
                    escaped_name = self.escape_markdown(client_name)
                    stats_msg += f"• **{escaped_name}** ({config_info['ip']}) - {mod_time.strftime('%d.%m.%Y %H:%M')}\n"
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

