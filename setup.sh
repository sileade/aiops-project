#!/bin/bash

# Скрипт для интерактивной настройки проекта AIOps

set -e

ENV_FILE=".env"

if [ -f "$ENV_FILE" ]; then
    read -p "Файл .env уже существует. Хотите его перезаписать? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Настройка отменена."
        exit 0
    fi
fi

echo "--- Настройка AIOps Проекта ---"

# API Сервер
read -p "Введите хост API сервера (по умолчанию: 0.0.0.0): " API_HOST
API_HOST=${API_HOST:-0.0.0.0}

read -p "Введите порт API сервера (по умолчанию: 8000): " API_PORT
API_PORT=${API_PORT:-8000}

# Telegram Бот
read -p "Введите токен вашего Telegram бота: " TELEGRAM_BOT_TOKEN

# AI Модель (Qwen)
read -p "Введите URL для API Qwen модели (например, http://host.docker.internal:11434): " QWEN_API_URL

# MikroTik
read -p "Введите хост MikroTik: " MIKROTIK_HOST
read -p "Введите порт MikroTik (по умолчанию: 8728): " MIKROTIK_PORT
MIKROTIK_PORT=${MIKROTIK_PORT:-8728}
read -p "Введите пользователя MikroTik: " MIKROTIK_USER
read -s -p "Введите пароль MikroTik: " MIKROTIK_PASSWORD
echo

# UniFi
read -p "Введите хост UniFi Controller: " UNIFI_HOST
read -p "Введите порт UniFi Controller (по умолчанию: 8443): " UNIFI_PORT
UNIFI_PORT=${UNIFI_PORT:-8443}
read -p "Введите сайт UniFi (по умолчанию: default): " UNIFI_SITE
UNIFI_SITE=${UNIFI_SITE:-default}
read -p "Введите пользователя UniFi: " UNIFI_USER
read -s -p "Введите пароль UniFi: " UNIFI_PASSWORD
echo

# n8n
read -p "Введите домен для n8n (например, n8n.yourdomain.com): " N8N_DOMAIN

# Создание .env файла
cat > $ENV_FILE << EOL
# --- API Сервер ---
API_HOST=$API_HOST
API_PORT=$API_PORT

# --- Telegram Бот ---
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN

# --- AI Модель ---
QWEN_API_URL=$QWEN_API_URL

# --- MikroTik ---
MIKROTIK_HOST=$MIKROTIK_HOST
MIKROTIK_PORT=$MIKROTIK_PORT
MIKROTIK_USER=$MIKROTIK_USER
MIKROTIK_PASSWORD=$MIKROTIK_PASSWORD

# --- UniFi ---
UNIFI_HOST=$UNIFI_HOST
UNIFI_PORT=$UNIFI_PORT
UNIFI_SITE=$UNIFI_SITE
UNIFI_USER=$UNIFI_USER
UNIFI_PASSWORD=$UNIFI_PASSWORD

# --- n8n ---
N8N_DOMAIN=$N8N_DOMAIN
EOL

echo -e "\n✅ Файл .env успешно создан!"
echo "Теперь вы можете запустить проект с помощью 'docker-compose up -d'"
