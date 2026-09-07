# API-Gateway

> Шлюз для микросервисной части проекта. Принимает внешние HTTP-запросы и проксирует их в соответствующие сервисы

## Назначение

- Единая точка входа для клиентов
- Версионирование публичного API через префикс `/api/v1`
- Маршрутизация запросов к **AuthService** и **FileService**
- Агрегированная проверка состояния сервисов через `GET /health`

## Структура

```
API-Gateway/
├── cmd/api-gateway/     # Точка входа
├── internal/
│   ├── api/             # HTTP-роутер, reverse proxy, handlers
│   └── config/          # Загрузка конфигурации из env
└── dev/deployment/      # Dockerfile
```

## Конфигурация

Переменные окружения:
| Переменная       | Описание                          | Значение по умолчанию |
|------------------|-----------------------------------|-----------------------|
| `HTTP_PORT`      | Порт, на котором слушает шлюз     | `8000`                |
| `AUTH_HOST`      | Хост `AuthService`                | `localhost`           |
| `AUTH_PORT`      | Порт `AuthService`                | `8001`                |
| `JWT_SECRET`     | Секрет для JWT                    | `dev-secret`          |

> Шлюз явно проксирует `/api/v1/auth/*`, ... в соответствующие сервисы

## Роутинг
| Метод | Путь                    | Описание                                                           |
|-------|-------------------------|--------------------------------------------------------------------|
| `*`   | `/api/v1/auth/*`        | Проксирует запросы на `AuthService` с удалённым префиксом `/api/v1/auth` |

Примеры:

```bash
# health-check
curl http://localhost:8000/health
```
```bash
# register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"name":"test","email":"test@example.com","password":"password123"}'
```

## Локальный запуск

```bash
cd API-Gateway

go mod tidy
go run ./cmd/api-gateway
```

По умолчанию шлюз стартует на localhost:8000 и обращается к сервисам на localhost:8001 (auth), localhost:8002 (file)

## Запуск через Docker Compose

Шлюз добавлен в корневой docker-compose.yaml. Для запуска всего стека из корня проекта:

```bash
cp compose.dev.env.example compose.dev.env
# Отредактировать compose.dev.env при необходимости

docker compose --env-file compose.dev.env up --build
```

Проверка:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/auth/health
```

## Health check

`GET /health` возвращает JSON с состоянием шлюза и каждого сервиса:

```json
{
  "API-Gateway": "running",
  "AuthService": "running"
}
```

Если сервис недоступен, в поле будет описание ошибки или HTTP-статус

## Зависимости
- [go-chi/chi/v5](https://github.com/go-chi/chi) - HTTP-роутер и middleware
- [kelseyhightower/envconfig](https://github.com/kelseyhightower/envconfig) - загрузка конфигурации из переменных окружения
