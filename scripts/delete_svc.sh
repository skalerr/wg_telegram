#!/bin/bash
source variables.sh
source scripts/env.sh

SERVICE_NAME="wg0.service"
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}"

# # Проверка на запуск от root
# if [[ $EUID -ne 0 ]]; then
#   echo "Этот скрипт нужно запускать от root или через sudo."
#   exit 1
# fi

#Останавливаем сервис, если он запущен
if systemctl is-active --quiet "${SERVICE_NAME}"; then
  systemctl stop "${SERVICE_NAME}"
  echo "systemd: сервис ${SERVICE_NAME} остановлен."
else
  echo "systemd: сервис ${SERVICE_NAME} уже не запущен."
fi

# Отключаем автозапуск
if systemctl is-enabled --quiet "${SERVICE_NAME}"; then
  systemctl disable "${SERVICE_NAME}"
  echo "systemd: автозапуск для ${SERVICE_NAME} отключён."
else
  echo "systemd: автозапуск для ${SERVICE_NAME} уже отключён."
fi

# Удаляем unit-файл
if [[ -f "${SERVICE_PATH}" ]]; then
  rm -f "${SERVICE_PATH}"
  echo "Файл ${SERVICE_PATH} удалён."
else
  echo "Файл ${SERVICE_PATH} не найден."
fi

# Перезагружаем конфигурацию systemd
systemctl daemon-reload
echo "systemd: daemon-reload выполнен."

# Сбрасываем статус неудачных сервисов
systemctl reset-failed
echo "systemd: сброс статусов неудачных сервисов."

# Проверяем статус (ожидаем ошибку, если сервис удалён)
echo "Пробуем получить статус ${SERVICE_NAME}:"
systemctl status "${SERVICE_NAME}" --no-pager || true