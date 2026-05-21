# Alice Office Skill — навык Яндекс Алисы для вызова сотрудников

Система позволяет вызывать сотрудников в офисе через голосовые команды Яндекс Алисы.

Пример:

> «Алиса, позови Ивана в бухгалтерию»

Навык:

1. Принимает запрос от Алисы
2. Определяет сотрудника и кабинет
3. Отправляет уведомление в notify-сервис
4. Возвращает голосовой ответ

---

# Возможности

* Вызов сотрудников голосом
* Поиск сотрудника по имени
* Привязка сотрудников к кабинетам
* REST API
* SQLite база данных
* Docker и Docker Compose
* Готово для деплоя
* Поддержка webhook Яндекс Алисы
* Локальный notify-agent для тестов

---

# Архитектура

```text
Яндекс Алиса
       ↓
Webhook (/alice)
       ↓
FastAPI backend
       ↓
Notify API
       ↓
Оповещение кабинета / колонки
```

---

# Структура проекта

```text
alice-office-skill/
├── app.py
├── notify_agent.py
├── requirements.txt
├── Dockerfile
├── Dockerfile.notify
├── docker-compose.yml
├── .env.example
└── README.md
```

---

# Технологии

* Python 3.11
* FastAPI
* SQLite
* Docker
* Docker Compose
* Requests
* Yandex Dialogs API

---

# Установка

## 1. Клонировать репозиторий

```bash
git clone https://github.com/USERNAME/alice-office-skill.git

cd alice-office-skill
```

---

# Локальный запуск без Docker

## 1. Установить зависимости

```bash
pip install -r requirements.txt
```

---

## 2. Создать .env

Скопируй:

```bash
cp .env.example .env
```

---

## 3. Запустить notify-agent

```bash
uvicorn notify_agent:app --host 0.0.0.0 --port 8001
```

---

## 4. Запустить backend навыка

В новом терминале:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

---

# Проверка работы

## Health check backend

```text
http://127.0.0.1:8000/health
```

---

## Health check notify-agent

```text
http://127.0.0.1:8001/health
```

---

# Тест навыка через PowerShell

```powershell
$body = @{
  session = @{
    new = $true
    session_id = "test-session"
    message_id = 1
    user_id = "test-user"
  }

  request = @{
    command = "позови ивана в бухгалтерию"
    original_utterance = "позови ивана в бухгалтерию"
    type = "SimpleUtterance"
  }

  version = "1.0"
} | ConvertTo-Json -Depth 10

Invoke-WebRequest `
  -Uri "http://127.0.0.1:8000/alice" `
  -Method POST `
  -Body $body `
  -ContentType "application/json"
```

---

# Пример ответа

```json
{
  "response": {
    "text": "Запрос принят. Я позову Ивана в Бухгалтерия.",
    "tts": "Запрос принят. Я позову Ивана в Бухгалтерия.",
    "end_session": false
  },
  "version": "1.0"
}
```

---

# Локальное уведомление

Notify-agent выводит сообщение в консоль:

```text
=== OFFICE NOTIFY ===
target: room:бухгалтерия
message: Иван, вас зовет босс. Подойдите, пожалуйста.
=====================
```

---

# Запуск через Docker

## Сборка и запуск

```bash
docker compose up --build
```

---

# Порты

| Сервис        | Порт |
| ------------- | ---- |
| Alice backend | 8000 |
| Notify agent  | 8001 |

---

# Подключение к Яндекс Алисе

## 1. Открыть

```text
https://dialogs.yandex.ru
```

---

## 2. Создать навык

Тип:

```text
Навык для Алисы
```

---

## 3. Указать Backend

Backend → Webhook URL

---

## 4. Вставить URL

Например:

```text
https://YOUR_DOMAIN/alice
```

---

# Для локального тестирования

Используй ngrok.

---

## Установка ngrok

Сайт:

```text
https://ngrok.com
```

---

## Запуск

```bash
ngrok http 8000
```

---

## Получишь URL

```text
https://abc123.ngrok-free.app
```

---

## Вставить в Алису

```text
https://abc123.ngrok-free.app/alice
```

---

# База данных

Используется SQLite:

```text
office_calls.db
```

---

# Таблицы

## rooms

Кабинеты офиса

---

## employees

Сотрудники

---

## calls

История вызовов

---

# Примеры команд

## Вызов сотрудника

```text
Позови Ивана в бухгалтерию
```

---

## Поиск сотрудника

```text
Где сейчас Анна
```

---

## Помощь

```text
Помощь
```

---

# Переменные окружения

## .env

```env
DB_PATH=office_calls.db

OFFICE_NOTIFY_API_URL=http://127.0.0.1:8001/speak

OFFICE_NOTIFY_API_KEY=local-test-key

LOG_LEVEL=INFO
```

---

# Production deploy

Можно развернуть:

* Render
* Railway
* VPS
* Docker
* Yandex Cloud
* Kubernetes

---

# Render deploy

## Build command

```bash
pip install -r requirements.txt
```

---

## Start command

```bash
uvicorn app:app --host 0.0.0.0 --port 10000
```

---

# Безопасность

Рекомендуется:

* добавить API authentication
* ограничить IP
* вынести SQLite в PostgreSQL
* хранить секреты через ENV
* использовать HTTPS

---

# Roadmap

Планируемые функции:

* TTS в колонки
* WebSocket уведомления
* Telegram интеграция
* Панель администратора
* Авторизация
* История вызовов
* Push уведомления
* AI маршрутизация сотрудников
