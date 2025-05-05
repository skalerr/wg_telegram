#!/bin/bash
source variables.sh
source scripts/env.sh

SERVICE_NAME="wg0.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

# Проверка на запуск от root
# if [[ $EUID -ne 0 ]]; then
#   echo "Этот скрипт нужно запускать от root или через sudo."
#   exit 1
# fi


cat > "${SERVICE_PATH}" << 'EOF'
[Unit]
Description=WireGuard interface wg0
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/wg-quick up wg0
ExecStop=/usr/bin/wg-quick down wg0
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
EOF

echo "Файл ${SERVICE_PATH} создан."

# Перезагружаем конфигурацию systemd
systemctl daemon-reload
echo "systemd: daemon-reload выполнен."

# Включаем автозапуск при загрузке
systemctl enable "${SERVICE_NAME}"
echo "systemd: сервис ${SERVICE_NAME} включён."

# Запускаем сервис прямо сейчас
systemctl start "${SERVICE_NAME}"
echo "systemd: сервис ${SERVICE_NAME} запущен."

# Выводим статус
systemctl status "${SERVICE_NAME}" --no-pager