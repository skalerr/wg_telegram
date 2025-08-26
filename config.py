import os
from typing import List

# Telegram Bot Configuration
api_tg: str = os.getenv('TELEGRAM_BOT_TOKEN', '')

# Authorized user IDs (can be set via environment variable as comma-separated values)
authorized_users_env = os.getenv('AUTHORIZED_USERS', '')
if authorized_users_env:
    try:
        mainid: List[int] = [int(user_id.strip()) for user_id in authorized_users_env.split(',')]
    except ValueError:
        mainid: List[int] = []
else:
    mainid: List[int] = []

# WireGuard Configuration
wg_local_ip_hint: str = os.getenv('WG_LOCAL_IP_HINT', '10.20.20')

# Validation
if not api_tg:
    print("Warning: TELEGRAM_BOT_TOKEN environment variable not set")

if not mainid:
    print("Warning: AUTHORIZED_USERS environment variable not set or invalid")