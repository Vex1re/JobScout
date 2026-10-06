# Эксплуатационная документация (Operations Runbook) — JobScout Bot

Настоящий документ предназначен для инженеров сопровождения, SRE и разработчиков. Включает регламенты развёртывания, миграций, резервного копирования, мониторинга и устранения типовых инцидентов.

---

## 1. Режимы работы и окружение

| Параметр | `ENV=dev` (Разработка) | `ENV=prod` (Продакшн) |
| :--- | :--- | :--- |
| **СУБД** | SQLite (`sqlite+aiosqlite:///jobscout.db`, WAL enabled) | PostgreSQL 16 + PgBouncer |
| **Кэш и FSM** | In-Memory (MemoryStorage, SearchResultsCache) | Redis 7 (`REDIS_URL`) |
| **Планировщик** | Встроенный APScheduler в процессе бота | Выделенный сервис `scheduler` + очереди `arq` |
| **Режим бота** | Long Polling (`BOT_USE_WEBHOOK=False`) | Webhook (`BOT_USE_WEBHOOK=True`) или Polling |
| **Миграции** | `alembic upgrade head` | Автоматически через Alembic перед стартом контейнеров |

---

## 2. Локальный запуск (Local Development)

### 2.1. Подготовка окружения
```bash
# Клонирование и переход в директорию
git clone <repo_url>
cd Test1

# Создание виртуального окружения Python 3.11+
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# или .venv\Scripts\activate в Windows PowerShell

# Установка зависимостей
pip install -r requirements.txt
```

### 2.2. Настройка `.env`
Скопируйте пример конфигурации:
```bash
cp .env.example .env
```
Убедитесь, что заполнен `BOT_TOKEN` (полученный в @BotFather) и установлен `ENV=dev`.

### 2.3. Применение миграций и запуск
```bash
# Применение миграций схемы к локальной SQLite БД
alembic upgrade head

# Запуск тестов для проверки окружения
pytest -v

# Запуск бота
python main.py
```

---

## 3. Развёртывание в продакшн (Production Deployment)

### 3.1. Требования к серверу
- **ОС**: Ubuntu 22.04 LTS / Debian 12 / AlmaLinux 9
- **Пакеты**: Docker Engine >= 24.0, Docker Compose >= 2.20
- **Ресурсы**: Минимум 2 vCPU, 4 GB RAM, 20 GB SSD

### 3.2. Архитектура сервисов (Docker Compose)
Продакшн-стек включает 7 изолированных сервисов:
1. `postgres` — PostgreSQL 16 Alpine.
2. `pgbouncer` — Connection pooler (порт 6432, transaction pooling).
3. `redis` — Redis 7 Alpine (кэш, FSM, очередь `arq`).
4. `bot` — Telegram-бот (aiogram 3 + aiohttp web server для webhook, /healthz, /metrics).
5. `scheduler` — APScheduler cron-сервис, планирующий задачи краулинга и рассылок.
6. `worker-crawler` — Воркер `arq`, выполняющий фоновый парсинг внешних площадок и ингестию вакансий.
7. `worker-notifier` — Воркер `arq`, отправляющий уведомления и дайджесты в Telegram.

### 3.3. Команды запуска и обновления
```bash
# 1. Загрузка последних изменений кода
git pull origin main

# 2. Проверка и заполнение боевого .env
nano .env

# 3. Применение миграций БД
docker compose run --rm bot alembic upgrade head

# 4. Сборка и запуск всех сервисов в фоновом режиме
docker compose up -d --build

# 5. Проверка статуса контейнеров
docker compose ps

# 6. Проверка логов запуска
docker compose logs -f --tail=100 bot
```

### 3.4. Масштабирование воркеров
При росте нагрузки на очереди задач воркеры масштабируются горизонтально без изменения конфигурации:
```bash
# Увеличение числа краулеров до 3, а нотификаторов до 2:
docker compose up -d --scale worker-crawler=3 --scale worker-notifier=2
```

---

## 4. Базы данных и миграции (Alembic)

В продакшене вызов `Base.metadata.create_all()` **запрещён**. Все изменения структуры таблиц производятся только через миграции Alembic.

### 4.1. Создание новой миграции
При изменении моделей в `core/database/models.py`:
```bash
alembic revision --autogenerate -m "add_column_name_to_table"
```
Обязательно просмотрите сгенерированный файл в `alembic/versions/` перед коммитом.

### 4.2. Применение и откат миграций
```bash
# Применить все актуальные миграции
alembic upgrade head

# Откатить последнюю миграцию на 1 шаг назад
alembic downgrade -1

# Посмотреть текущую применённую версию
alembic current
```

### 4.3. Резервное копирование PostgreSQL
Настройте ежедневный cron на хост-сервере:
```bash
# Скрипт создания бэкапа
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/var/backups/jobscout"
mkdir -p $BACKUP_DIR

docker compose exec -T postgres pg_dump -U jobscout_user jobscout_prod | gzip > "$BACKUP_DIR/backup_$TIMESTAMP.sql.gz"

# Ротация: удаление бэкапов старше 14 дней
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +14 -delete
```

#### Восстановление из бэкапа:
```bash
gunzip < /var/backups/jobscout/backup_YYYYMMDD_HHMMSS.sql.gz | docker compose exec -T postgres psql -U jobscout_user jobscout_prod
```

---

## 5. Мониторинг, метрики и алертинг

### 5.1. Эндпоинты наблюдаемости
Приложение поднимает aiohttp HTTP-сервер на порту `8080` (настраивается через `HEALTH_PORT`):
- `GET http://localhost:8080/healthz` — Liveness & Readiness проба:
  - Возвращает JSON `{"status": "ok", "db": "ok", "redis": "ok"}` с кодом `200`.
  - При недоступности БД или Redis возвращает код `503 Service Unavailable`.
- `GET http://localhost:8080/metrics` — Метрики Prometheus в стандартном текстовом формате:
  - `jobscout_vacancies_ingested_total{source="...", grade="..."}` — количество собранных вакансий.
  - `jobscout_parser_errors_total{source="...", error_type="..."}` — счётчик ошибок парсеров.
  - `jobscout_search_latency_seconds` — гистограмма латентности поиска.
  - `jobscout_notifications_sent_total{status="sent|failed"}` — счётчик отправленных сообщений.
  - `jobscout_active_users_total` — Gauge активных пользователей бота.

### 5.2. Настройка Prometheus Scrape Job
Добавьте в ваш `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'jobscout_bot'
    scrape_interval: 15s
    static_configs:
      - targets: ['bot:8080']
```

### 5.3. Канареечный мониторинг парсеров (Canary Checks)
Для проверки доступности и контрактов 9 внешних площадок без нагрузочного парсинга используется скрипт:
```bash
python scripts/canary.py
```
Скрипт проверяет статус каждого парсера, время ответа и процент валидных записей. Рекомендуется запускать каждые 30 минут через Cron/Alertmanager.

---

## 6. Sentry и обработка ошибок

- Для включения Sentry задайте `SENTRY_DSN` в `.env`.
- **Защита персональных данных (PII Redaction)**:
  - Автоматически активен фильтр `core/sentry.py`, который маскирует телефоны РФ (`+7...`), адреса электронной почты и Telegram bot токены во всех сообщениях и breadcrumbs перед отправкой в Sentry.
  - Персональные тексты резюме **не** отправляются во внешние сервисы логирования.

---

## 7. Плейбуки реагирования на инциденты (Incident Playbooks)

### Инцидент A: Ошибки 500 / таймауты от TrudVsem (Работа в России)
**Симптомы**: Логи содержат `TrudVsem endpoint returned 500`.
**Причина**: Периодическая нестабильность шлюза открытых данных trudvsem.ru при высоких оффсетах.
**Действие системы**:
1. Срабатывает встроенный `CircuitBreaker`. После 3 ошибок подряд шлюз переходит в `OPEN` на 60 секунд.
2. Краулер автоматически пропускает источник, не блокируя остальные 8 площадок.
**Действие инженера**: Вмешательство не требуется. Circuit Breaker автоматически перейдёт в `HALF_OPEN` и восстановит опрос, как только API станет доступно.

### Инцидент B: Ошибки 403 / Недействительный токен SuperJob
**Симптомы**: Метрика `jobscout_parser_errors_total{source="superjob"}` растёт, в логах 403 Forbidden.
**Действие инженера**:
1. Запросите новый API-ключ в кабинете разработчика SuperJob.
2. Обновите `SUPERJOB_API_KEY` в `.env`.
3. Перезапустите контейнеры: `docker compose restart bot worker-crawler`.

### Инцидент C: Бот замедлил отправку уведомлений (Telegram 429)
**Симптомы**: Воркер `worker-notifier` пишет `Telegram rate limit hit (429)`.
**Причина**: Превышение лимита Telegram API (30 сообщений в секунду суммарно или 1 сообщение в секунду пользователю).
**Действие системы**:
Встроенный `TelegramRateLimiter` с алгоритмом Token Bucket (лимит 25 msg/sec) защищает бота от глобального бана. Очередь `arq` сохраняет сообщения и отправляет их с экспоненциальной задержкой.
**Действие инженера**: Проверить размер очереди нотификаций в Redis:
```bash
docker compose exec redis redis-cli llen arq:queue
```
Если очередь стабильно растёт — проверить, не настроена ли слишком частая отправка одиночных уведомлений вместо сводных дайджестов (`DIGEST_INTERVAL_HOURS`).

### Инцидент D: Исчерпание соединений PostgreSQL (Too many connections)
**Симптомы**: Ошибки `asyncpg.exceptions.TooManyConnectionsError`.
**Действие инженера**:
1. Убедитесь, что все контейнеры подключены к БД через **PgBouncer** (порт 6432), а не напрямую к порту 5432 PostgreSQL.
2. Проверьте `DB_POOL_SIZE` в `.env` (рекомендуемое значение: 10, `DB_MAX_OVERFLOW=5`).
3. Посмотрите статистику пулера:
```bash
docker compose exec pgbouncer psql -p 6432 -U pgbouncer pgbouncer -c "SHOW POOLS;"
```
