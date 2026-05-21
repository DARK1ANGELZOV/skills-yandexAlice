# Alice Skill Backend (FastAPI)

Минимальный production-ready backend для webhook навыка Яндекс Алисы.

## Финальная структура

```text
.
├── app.py
├── requirements.txt
├── Dockerfile
├── .env.example
└── README.md
```

## Что реализовано

- `POST /alice` - webhook для Яндекс Диалогов.
- `GET /health` - healthcheck.
- Стабильная обработка пустых/битых запросов без падений.
- Fallback-ответ при любой внутренней ошибке.
- Логирование всех входящих запросов.
- Формат ответа Алисы строго:

```json
{
  "response": {
    "text": "...",
    "end_session": false
  },
  "version": "1.0"
}
```

## Локальный запуск

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8080
```

Проверка:

```bash
curl http://localhost:8080/health
```

## Docker

```bash
docker build -t alice-skill:local .
docker run --rm -p 8080:8080 alice-skill:local
```

## Deploy в Yandex Cloud Serverless Containers

Замените:
- `<folder-id>` - ID папки
- `<registry-id>` - ID Container Registry (например `crp...`)

### 1) Подготовка окружения

```bash
yc config set folder-id <folder-id>
yc container registry configure-docker
```

### 2) Создание registry (если еще нет)

```bash
yc container registry create --name alice-registry
yc container registry list
```

### 3) Сборка и публикация образа

```bash
docker build -t cr.yandex/<registry-id>/alice-skill:latest .
docker push cr.yandex/<registry-id>/alice-skill:latest
```

### 4) Создание Serverless Container (если еще не создан)

```bash
yc serverless container create --name alice-skill
```

### 5) Деплой ревизии

```bash
yc serverless container revision deploy \
  --container-name alice-skill \
  --image cr.yandex/<registry-id>/alice-skill:latest \
  --cores 1 \
  --memory 512MB \
  --execution-timeout 10s \
  --concurrency 10 \
  --environment LOG_LEVEL=INFO
```

Если образ приватный и нужен service account для pull:

```bash
yc serverless container revision deploy \
  --container-name alice-skill \
  --image cr.yandex/<registry-id>/alice-skill:latest \
  --service-account-id <service-account-id> \
  --cores 1 \
  --memory 512MB \
  --execution-timeout 10s \
  --concurrency 10
```

### 6) Открыть публичный доступ для webhook

```bash
yc serverless container allow-unauthenticated-invoke alice-skill
```

### 7) Получить URL контейнера

```bash
yc serverless container get alice-skill
```

В ответе возьмите поле `url`, затем webhook для Dialogs:

```text
https://<container-url>/alice
```

Healthcheck URL:

```text
https://<container-url>/health
```

## Тестовый curl для Алисы

```bash
curl -X POST http://localhost:8080/alice \
  -H "Content-Type: application/json" \
  -d '{
    "meta": {"locale": "ru-RU", "timezone": "Asia/Yekaterinburg"},
    "session": {
      "message_id": 0,
      "session_id": "test-session-id",
      "skill_id": "test-skill-id",
      "user_id": "test-user-id",
      "new": true
    },
    "request": {
      "command": "привет",
      "original_utterance": "привет",
      "type": "SimpleUtterance"
    },
    "version": "1.0"
  }'
```

## Подключение в dialogs.yandex.ru

1. Откройте навыки в [dialogs.yandex.ru](https://dialogs.yandex.ru/).
2. В настройках endpoint укажите `https://<container-url>/alice`.
3. Сохраните и запустите проверку навыка.

## Полезные ссылки (официальная документация)

- Serverless Containers quickstart: https://yandex.cloud/en/docs/serverless-containers/quickstart/container
- Container revision deploy (CLI): https://yandex.cloud/en/docs/cli/cli-ref/serverless/cli-ref/v0/container/revision/deploy
- Allow unauthenticated invoke (CLI): https://yandex.cloud/en/docs/cli/cli-ref/serverless/cli-ref/container/allow-unauthenticated-invoke
- Container Registry quickstart: https://yandex.cloud/en/docs/container-registry/quickstart/
- Invocation link: https://yandex.cloud/en/docs/serverless-containers/operations/invocation-link
