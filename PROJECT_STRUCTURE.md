# 🏗️ Архитектура и структура проекта JobScout Bot

В данном документе детально описана полная структура каталогов, назначение всех модулей, сущностей базы данных и потоков данных в системе JobScout Bot.

---

## 📁 Структура каталогов и файлов

```
Test1/
├── alembic/                             # Управление миграциями схемы БД (Alembic)
│   ├── env.py                          # Конфигурация асинхронного запуска миграций
│   ├── script.py.mako                  # Шаблон новых миграций
│   └── versions/                       # Версионированные файлы миграций
│       ├── d98b492d0c53_initial_schema.py             # Базовые таблицы пользователей и вакансий
│       ├── 1f2a3b4c5d6e_phase5_user_interactions.py  # Аналитика кликов и взаимодействий
│       └── 2b3c4d5e6f7a_phase7_monetization_and_tracker.py # Подписки, права и трекер откликов
│
├── bot/                                # Слой Telegram-интерфейса (Aiogram 3.x)
│   ├── formatters/                     # Форматирование текстовых сообщений
│   │   ├── __init__.py
│   │   └── card.py                     # Разметка карточек вакансий, грейдов, опыта и трекера
│   ├── handlers/                       # Роутеры команд и интерактивных callback-кнопок
│   │   ├── __init__.py                 # Регистрация всех роутеров
│   │   ├── start.py                    # /start, /help, онбординг
│   │   ├── resume.py                   # Загрузка резюме (PDF/DOCX/текст), валидация, редактирование стека
│   │   ├── vacancies.py                # Поиск вакансий, пагинация, скрытие, добавление в избранное
│   │   ├── favorites.py                # Просмотр и управление избранным
│   │   ├── tracker.py                  # /tracker: Канбан-трекер откликов, AI сопроводительные и Gap-анализ
│   │   ├── premium.py                  # /premium: Подписки Telegram Stars (XTR), покупка, обработка платежей
│   │   └── settings.py                 # Выбор городов, удалёнки, агрегаторов и удаление данных (/delete_me)
│   ├── keyboards/                      # Разметка клавиатур
│   │   ├── __init__.py
│   │   ├── reply.py                    # Постоянное нижнее меню (ReplyKeyboard)
│   │   └── inline.py                   # Инлайн-кнопки карточек, трекера, тарифов и фильтров
│   ├── middlewares/                    # Промежуточные слои обработки апдейтов
│   │   ├── __init__.py
│   │   ├── db.py                       # Внедрение сессии AsyncSession в каждый хэндлер
│   │   └── throttling.py               # Rate limiting: Redis (атомарный Lua) + In-Memory fallback
│   └── states/                         # FSM-состояния конечного автомата
│       ├── __init__.py
│       └── profile.py                  # Состояния редактирования стека, загрузки файлов, выбора города
│
├── core/                               # Системное ядро и инфраструктура
│   ├── database/                       # Слой ORM (SQLAlchemy 2.0 Async)
│   │   ├── __init__.py
│   │   ├── models.py                   # ORM-модели (User, Resume, Vacancy, Favorite, Interaction, Subscription, Entitlement, JobApplicationTracker)
│   │   ├── session.py                  # Движок БД (PostgreSQL asyncpg / SQLite WAL), connection pooling
│   │   └── repository.py               # Репозитории CRUD, дедупликации, трекера и подписок
│   ├── config.py                       # Типизированная конфигурация через Pydantic-Settings
│   ├── scheduler.py                    # APScheduler: планировщик фоновых задач и очередей
│   ├── health.py                       # HTTP эндпоинт проверки здоровья системы /healthz
│   ├── metrics.py                      # Prometheus метрики и HTTP эндпоинт /metrics
│   └── sentry.py                       # Интеграция Sentry с маскированием персональных данных (PII Redaction)
│
├── data/                               # Справочники и статические данные
│   └── cities.json                     # Каталог 165 городов РФ (население > 100k, регионы, синонимы)
│
├── docs/                               # Проектная и архитектурная документация
│   ├── ARCHITECTURE_DECISIONS.md       # ADR 001-005 (arq, PgBouncer, Ingestion, Hybrid Parser, Stars)
│   └── OPERATIONS.md                   # Руководство по эксплуатации, миграциям, бэкапам и инцидентам
│
├── scripts/                            # Утилиты проверки и тестирования
│   ├── canary.py                       # Канареечный мониторинг доступности внешних парсеров
│   └── eval_matcher.py                 # Оценка точности ранжирования на Golden Dataset
│
├── services/                           # Бизнес-логика, парсеры и интеграции
│   ├── ai/                             # Гибридный парсинг резюме и генерация текстов
│   │   ├── __init__.py
│   │   ├── base.py                     # Интерфейс LLMProvider, санитизация Prompt Injection
│   │   ├── openai_provider.py          # Провайдер OpenAI (GPT-4o-mini / GPT-4o)
│   │   ├── yandex_provider.py          # Провайдер YandexGPT
│   │   ├── gigachat_provider.py        # Провайдер Сбер GigaChat
│   │   └── llm_helper.py               # AI-советы по резюме и сопроводительным письмам
│   ├── parser/                         # Агрегаторы вакансий и отказоустойчивость
│   │   ├── __init__.py
│   │   ├── base.py                     # Базовый абстрактный класс BaseVacanciesParser
│   │   ├── deduplicator.py             # 64-битный SimHash и расчёт Canonical ID
│   │   ├── resilience.py               # TokenBucket rate limiter и CircuitBreaker
│   │   ├── normalizer.py               # CityNormalizer: нормализация городов и синонимов
│   │   ├── hh.py                       # HeadHunter REST API клиент
│   │   ├── habr.py                     # Хабр Карьера HTML-парсер
│   │   ├── trudvsem.py                 # Работа России (ТрудВсем) открытое REST API
│   │   ├── superjob.py                 # SuperJob REST API клиент
│   │   ├── remoteok.py                 # RemoteOK международное API
│   │   ├── kwork.py                    # Kwork биржа микроуслуг
│   │   ├── fl_ru.py                    # FL.ru RSS/HTML парсер
│   │   ├── freelance_ru.py             # Freelance.ru парсер проектов
│   │   ├── rabota.py                   # Работа.ру парсер с поддержкой PROXY
│   │   ├── freelancehunt.py            # Freelancehunt API v2 (feature-flagged)
│   │   └── manager.py                  # AggregatorManager: параллельный опрос и фильтрация
│   ├── payment/                        # Модуль монетизации и платёжных шлюзов
│   │   ├── __init__.py
│   │   ├── base.py                     # Интерфейс BasePaymentProvider, тарифы FREE/PRO/TEAM
│   │   ├── stars.py                    # Telegram Stars (валюта XTR)
│   │   ├── yookassa.py                 # ЮKassa (feature-flagged)
│   │   └── cryptobot.py                # CryptoBot (feature-flagged)
│   └── resume_analyzer/                # Анализ резюме, матчинг и фильтрация
│       ├── __init__.py
│       ├── validator.py                # ResumeValidator: строгая проверка на спам, рецепты и договоры
│       ├── extractor.py                # Извлечение 192+ канонических скиллов, Interval Union стажа
│       ├── vacancy_extractor.py        # VacancyExperienceExtractor и VacancyGradeDetector
│       ├── matcher.py                  # Взвешенный скоринг, грейд-пенальти, time decay
│       └── red_flags.py                # Детектор мошенников, залогов, серой ЗП и штрафов
│
├── tests/                              # Автоматические тесты (181 тест, 100% pass)
│   ├── golden/                         # Эталонный набор для оценки ранжирования
│   │   └── matcher_golden.json         # 20 эталонных сценариев для разных отраслей
│   ├── snapshots/                      # Снепшоты ответов внешних агрегаторов
│   │   ├── hh_response.json
│   │   ├── trudvsem_response.json
│   │   ├── superjob_response.json
│   │   ├── remoteok_response.json
│   │   ├── kwork_response.json
│   │   ├── fl_ru_feed.xml
│   │   ├── habr_career_page.html
│   │   ├── freelance_ru_page.html
│   │   └── rabota_ru_response.json
│   ├── test_aggregator_contracts.py    # Тесты контрактов 9 агрегаторов по снепшотам
│   ├── test_ai_parsing.py              # Тесты гибридного парсера, LLM fallback, дат
│   ├── test_crawler_ingestion.py       # Тесты фонового сбора и сохранения вакансий
│   ├── test_deduplication.py           # Тесты SimHash и хэммингова расстояния
│   ├── test_extractor.py               # Тесты извлечения стека и стажа
│   ├── test_features.py                # Тесты валидации, городов, пула запросов
│   ├── test_freelancehunt.py           # Тесты интеграции с Freelancehunt API v2
│   ├── test_matcher.py                 # Базовые тесты матчинга и скоринга
│   ├── test_matcher_quality.py         # Тесты взвешенных коэффициентов и fresh-decay
│   ├── test_monetization_and_tracker.py# Тесты Stars, Entitlements и Kanban-трекера
│   ├── test_notifier.py                # Тесты Telegram rate limiting и дайджестов
│   ├── test_observability.py           # Тесты /healthz, /metrics, PII маскирования
│   ├── test_parsers.py                 # Тесты унификации вакансий парсерами
│   ├── test_prod_stability.py          # Тесты троттлинга, удаления профиля, сессий
│   ├── test_qa_suite.py                # Комплексный QA сьют граничных случаев
│   ├── test_red_flags.py               # Тесты детектора скама и ред-флагов
│   ├── test_resilience.py              # Тесты TokenBucket и Circuit Breaker
│   ├── test_source_selection.py        # Тесты включения/отключения источников
│   └── test_universal_professions.py   # Тесты не-IT профессий (маркетинг, финансы, HR)
│
├── workers/                            # Фоновые воркеры arq
│   ├── __init__.py
│   ├── crawler.py                      # Воркер периодического сбора вакансий
│   └── notifier.py                     # Воркер отправки уведомлений и дайджестов
│
├── .env.example                        # Эталонный файл переменных окружения
├── docker-compose.yml                  # Оркестрация 7 сервисов (bot, scheduler, workers, postgres, pgbouncer, redis)
├── Dockerfile                          # Multi-stage production сборка контейнера
├── main.py                             # Точка входа бота
├── pytest.ini                          # Настройки pytest
└── requirements.txt                    # Зависимости проекта
```

---

## 🔄 Потоки данных (Data Flows)

### 1. Ingestion Pipeline (Фоновый сбор вакансий)
```
[scheduler]
     │
     ▼ (Каждые N минут ставит задачу crawl_category в очередь arq)
[worker-crawler]
     │
     ├──► [AggregatorManager] ──► [TokenBucket / CircuitBreaker] ──► Внешние API (9 платформ)
     │
     ▼ (Сбор сырых вакансий)
[services.parser.deduplicator]
     │
     ├──► Canonical ID (MD5 компании + заголовка + города + зарплаты)
     └──► SimHash 64-bit (отпечаток текста описания)
     │
     ▼ (Проверка дублей в БД)
[core.database.repository.VacancyRepository.upsert_bulk]
     │
     ▼ (Сохранение в таблицу vacancies с индексами)
[PostgreSQL]
```

### 2. Search & Matching Pipeline (Поиск вакансий пользователем)
```
[Пользователь] ──► Команда /search
     │
     ▼
[bot.handlers.vacancies]
     │
     ├──► [VacancyRepository.search_by_profile] (Быстрый поиск по локальной базе)
     │
     ├──► Найдено < 15 вакансий?
     │         ├── ДА ──► [AggregatorManager.search_all] (On-demand догрузка)
     │         └── НЕТ ──► Использование локальной базы
     │
     ▼
[services.resume_analyzer.matcher.VacancyMatcher.calculate_match]
     │
     ├── 45% Стек технологий (Must-have vs Nice-to-have)
     ├── 25% Целевая роль
     ├── 30% Грейд и опыт
     ├── Soft Penalty (-12% при grade_confidence < 0.7)
     └── Freshness Time Decay (-12% за 14 дней, -30% за 30 дней)
     │
     ▼
[bot.formatters.card.format_vacancy_card] ──► Выдача карточек в Telegram
```

### 3. Payment & Entitlements Pipeline (Оплата и права доступа)
```
[Пользователь] ──► Команда /premium ──► Выбор тарифа Pro / Team
     │
     ▼
[bot.handlers.premium.process_buy_subscription]
     │
     ▼ (Отправка инвойса в валюте XTR - Telegram Stars)
[bot.send_invoice] ──► Пользователь оплачивает звёздами
     │
     ├──► PreCheckoutQuery ──► [SubscriptionRepository.get_plan] ──► Одобрение
     └──► SuccessfulPayment
               │
               ▼
          [SubscriptionRepository.create_subscription]
               │
               ▼
          Активация прав (AI Cover Letter, Gap Analysis, Kanban Tracker)
```

### 4. Application Tracker Pipeline (Трекер откликов)
```
[Карточка вакансии] ──► Кнопка "📌 В трекер"
     │
     ▼
[bot.handlers.tracker.track_vacancy_callback]
     │
     ▼ (Создание записи со статусом 'saved')
[core.database.repository.TrackerRepository.add_application]
     │
     ▼
[Команда /tracker] ──► Просмотр канбан-доски и переключение статусов:
     │                 'saved' ➔ 'applied' ➔ 'interview' ➔ 'offer' / 'rejected'
     │
     ├──► Кнопка "✍️ AI письмо" ──► Генерация персонализированного сопроводительного
     └──► Кнопка "🔍 Gap анализ" ──► Анализ недостающих навыков соискателя
```
