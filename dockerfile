FROM python:3.13-slim

WORKDIR /app

# Копируем зависимости (предположим, requirements.txt рядом с Dockerfile)
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходники и assets
COPY src/ ./src/
COPY assets/ ./assets/

# Устанавливаем рабочую директорию в /app/src для запуска бота
WORKDIR /app/src

# Запуск бота
CMD ["python", "bot.py"]
