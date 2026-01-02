FROM python:3.13-slim AS builder

# Устанавливаем uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости в виртуальное окружение, но внутри системы (т.к. это контейнер)
RUN uv sync --frozen --no-install-project

# Этап 2: Финальный образ (максимально легкий)
FROM python:3.13-slim

WORKDIR /app

# Копируем установленные пакеты из первого этапа
COPY --from=builder /app/.venv /app/.venv

# Копируем код проекта
COPY src/ ./src/

# Добавляем venv в PATH
ENV PATH="/app/.venv/bin:$PATH"

# Переменные окружения (Дефолтные, но их перезапишем в docker-compose)
ENV PYTHONPATH=/app

# Команда запуска
CMD ["python", "-m", "src.main"]