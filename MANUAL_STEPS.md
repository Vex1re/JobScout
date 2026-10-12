# 📋 Руководство по ручной настройке (MANUAL_STEPS.md)

В данном файле перечислены действия и настройки, требующие участия человека (регистрация во внешних сервисах, получение токенов, настройка Telegram BotFather и инфраструктуры).

---

## 1. Настройка Telegram-бота (@BotFather)

### 1.1. Создание бота и получение токена
1. Откройте диалог с официальным ботом [@BotFather](https://t.me/BotFather) в Telegram.
2. Отправьте команду `/newbot` и следуйте инструкциям.
3. Скопируйте выданный токен в переменную `BOT_TOKEN` в файле `.env`.

### 1.2. Регистрация команд бота (Menu Commands)
Отправьте боту [@BotFather](https://t.me/BotFather) команду `/setcommands`, выберите вашего бота и отправьте следующий список:
```text
start - Запустить бота и настроить профиль
search - Найти подходящие вакансии и заказы
tracker - Карьерный канбан-трекер откликов
favorites - Избранные вакансии
settings - Фильтры, города и выбор источников
premium - Тарифы Pro и Telegram Stars
delete_me - Полное удаление профиля и данных
```

### 1.3. Включение Telegram Stars для монетизации
1. В диалоге с [@BotFather](https://t.me/BotFather) отправьте команду `/mybots`.
2. Выберите вашего бота.
3. Перейдите в **Payments** ➔ выберите **Telegram Stars** (XTR).
4. Подтвердите условия использования. После этого бот сможет выставлять счета за звёзды через команду `/premium`.

---

## 2. Получение внешних API-ключей

### 2.1. SuperJob API Key (Рекомендуется)
- **Зачем**: Прямой доступ к API SuperJob без ограничений и капчи.
- **Где получить**: Зарегистрируйтесь на [api.superjob.ru](https://api.superjob.ru/), создайте приложение и скопируйте `Secret key`.
- **Куда прописать**: Переменная `SUPERJOB_API_KEY` в `.env`.
- *Примечание*: Если ключ не указан, модуль SuperJob использует резервный веб-поиск (Fallback).

### 2.2. Мониторинг Sentry (Рекомендуется для продакшна)
- **Зачем**: Сбор и группировка исключений во всех 7 сервисах с автоматической маскировкой персональных данных (телефоны РФ, email, токены).
- **Где получить**: Создайте бесплатный проект Python на [sentry.io](https://sentry.io/).
- **Куда прописать**: Переменная `SENTRY_DSN` в `.env`.

### 2.3. LLM-провайдеры (Опционально)
По умолчанию бот использует **100% бесплатный и локальный rule-based парсер резюме** (Regex + Interval Union). Для включения продвинутой генерации сопроводительных писем и LLM fallback:
- **OpenAI**: Установите `LLM_PROVIDER=openai` и укажите `OPENAI_API_KEY` с платформы OpenAI.
- **YandexGPT**: Установите `LLM_PROVIDER=yandex`, укажите `YANDEX_API_KEY` и `YANDEX_FOLDER_ID`.
- **GigaChat**: Установите `LLM_PROVIDER=gigachat` и укажите `GIGACHAT_CREDENTIALS`.

### 2.4. Альтернативные платёжные шлюзы (Опционально)
- **ЮKassa**: Задайте `YOOKASSA_ENABLED=True`, `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` (требуется договор с ЮKassa).
- **CryptoBot**: Задайте `CRYPTOBOT_ENABLED=True` и `CRYPTOBOT_API_TOKEN` от [@CryptoBot](https://t.me/CryptoBot).
- **Freelancehunt**: Задайте `FREELANCEHUNT_API_TOKEN` для включения украинской биржи фриланса.

---

## 3. Настройка Production Webhook и SSL

Если бот запускается в режиме `BOT_USE_WEBHOOK=True`:
1. Обеспечьте наличие публичного домена с SSL-сертификатом (например, через Let's Encrypt / Certbot).
2. Настройте обратный прокси (Nginx, Traefik или Caddy) для проксирования запросов на порт сервиса бота:
```nginx
server {
    server_name bot.yourdomain.com;

    location /webhook {
        proxy_pass http://127.0.0.1:8080/webhook;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8080/healthz;
    }
}
```
3. Укажите в `.env`:
```env
BOT_USE_WEBHOOK=True
WEBHOOK_URL=https://bot.yourdomain.com/webhook
```

---

## 4. Первый запуск и миграции базы данных

Перед запуском контейнеров в продакшне примените миграции схемы:
```bash
# 1. Применить все миграции Alembic к PostgreSQL
docker compose run --rm bot alembic upgrade head

# 2. Поднять все сервисы
docker compose up -d --build

# 3. Убедиться, что все 7 контейнеров в статусе 'Up' или 'running'
docker compose ps

# 4. Проверить эндпоинт здоровья
curl http://localhost:8080/healthz
```
Ожидаемый ответ:
```json
{"status": "ok", "db": "ok", "redis": "ok"}
```
