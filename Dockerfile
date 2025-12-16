
# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем зависимости для сборки и Ansible
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    sshpass \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта в рабочую директорию
COPY . .

# Открываем порт для API
EXPOSE 8000

# Команда для запуска API сервера и бота
# Используем supervisord или другой процесс-менеджер для запуска нескольких процессов
# Для простоты, здесь будет команда для запуска только API
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

