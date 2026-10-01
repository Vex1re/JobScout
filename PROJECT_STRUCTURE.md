# 🏗️ Архитектура и структура проекта JobScout Bot

В данном документе детально описана архитектура системы, назначение модулей и потоки данных при взаимодействии пользователя с ботом.

---

## 📁 Структура каталогов и файлов

```
Test1/
├── bot/                                # Слой Telegram-бота (Aiogram 3.x)
│   ├── formatters/                     # Визуальные форматеры сообщений
│   │   ├── __init__.py
│   │   └── card.py                     # Форматирование красивых карточек вакансий и профиля
│   ├── handlers/                       # Обработчики команд, сообщений и callback-кнопок
│   │   ├── __init__.py                 # Регистрация всех роутеров
│   │   ├── start.py                    # /start, /help и первичный онбординг
│   │   ├── resume.py                   # Загрузка резюме (PDF/DOCX/текст), валидация, редактирование стека
│   │   ├── vacancies.py                # Поиск, мульти-запросы, карточки, пагинация, скрытие, AI-советы
│   │   ├── favorites.py                # Просмотр и удаление из избранного
│   │   └── settings.py                 # Фильтры (город, удаленка, минимальная ЗП, Kwork, уведомления)
│   ├── keyboards/                      # Клавиатуры бота
│   │   ├── __init__.py
│   │   ├── reply.py                    # Постоянное нижнее меню (Reply)
│   │   └── inline.py                   # Инлайн-кнопки (карточки вакансий, выбор города, пагинация)
│   ├── middlewares/                    # Промежуточные слои Aiogram
│   │   └── db.py                       # Внедрение асинхронной сессии БД (AsyncSession) в хэндлеры
│   └── states/                         # FSM-состояния конечного автомата
│       ├── __init__.py
│       └── profile.py                  # Состояния загрузки резюме, ввода навыков, выбора города
├── core/                               # Ядро приложения и инфраструктура
│   ├── database/                       # Слой базы данных (SQLAlchemy 2.0 Async)
│   │   ├── __init__.py
│   │   ├── models.py                   # ORM-модели (User, Resume, Vacancy, Favorite, Match, UserViewed)
│   │   ├── session.py                  # Создание движка create_async_engine и init_db()
│   │   └── repository.py               # Репозитории CRUD операций (лимит расширен до 500)
│   ├── config.py                       # Настройки через Pydantic-Settings и чтение .env
│   └── scheduler.py                    # Фоновый планировщик APScheduler для пуш-уведомлений
├── services/                           # Бизнес-логика, парсеры и анализ
│   ├── ai/                             # Интеграция с языковыми моделями (LLM)
│   │   └── llm_helper.py               # Опциональный вызов OpenAI/LLM для генерации советов
│   ├── parser/                         # Модуль парсинга 9 агрегаторов вакансий и фриланса
│   │   ├── __init__.py
│   │   ├── base.py                     # Базовый абстрактный класс BaseVacanciesParser
│   │   ├── hh.py                       # Клиент официального REST API HeadHunter (многостраничный)
│   │   ├── habr.py                     # Парсер вакансий Хабр Карьеры (аккуратный разбор мета-тегов)
│   │   ├── trudvsem.py                 # Официальное открытое REST API Работа России (без капчи)
│   │   ├── superjob.py                 # Парсер SuperJob (REST API и веб-поиск)
│   │   ├── remoteok.py                 # Клиент международного API удаленки RemoteOK (USD)
│   │   ├── kwork.py                    # Парсер freelance-проектов биржи Kwork
│   │   ├── fl_ru.py                    # RSS-парсер заказов фриланс-биржи FL.ru (IT/сайты)
│   │   ├── habr_freelance.py           # RSS-парсер IT-заказов Хабр Фриланс
│   │   ├── rabota.py                   # Парсер вакансий Работа.ру
│   │   ├── normalizer.py               # CityNormalizer (нормализация синонимов городов и правил офиса)
│   │   └── manager.py                  # AggregatorManager (мульти-запросный параллельный сбор)
│   └── resume_analyzer/                # Анализ резюме, скоринг и фильтрация ред-флагов
│       ├── __init__.py
│       ├── validator.py                # ResumeValidator (защита от рецептов, договоров и мусора)
│       ├── extractor.py                # Извлечение стека (300+ скиллов), стажа (Interval Union)
│       ├── matcher.py                  # Взвешенный алгоритм скоринга резюме vs вакансия
│       └── red_flags.py                # Детектор мошенников, залогов, серой ЗП и токсичных условий
├── tests/                              # Автоматические тесты (pytest — 102 теста, 100% pass)
│   ├── test_extractor.py               # Тесты извлечения стека, стажа (Interval Union, 0.0 лет)
│   ├── test_features.py                # Тесты валидации, городов, пула запросов и БД
│   ├── test_matcher.py                 # Тесты алгоритма совместимости
│   ├── test_parsers.py                 # Тесты унификации вакансий и парсинга 9 агрегаторов
│   ├── test_qa_suite.py                # Независимый комплексный QA-сьют на все граничные кейсы
│   ├── test_red_flags.py               # Тесты блокировки скама и выявления предупреждений
│   ├── test_search_optimization.py     # Тесты мульти-запросов, снятия лимитов и адаптивного скоринга
│   └── test_source_selection.py        # Тесты выбора и переключения агрегаторов в настройках
├── .env.example                        # Пример файла конфигурации с описанием параметров
├── .gitignore                          # Исключения для Git
├── docker-compose.yml                  # Оркестрация контейнера и volume для данных
├── Dockerfile                          # Multi-stage сборка Docker-образа
├── main.py                             # Точка входа в приложение
├── pytest.ini                          # Конфигурация для запуска тестов
├── requirements.txt                    # Список зависимостей Python
├── PROJECT_STRUCTURE.md                # Настоящий документ с описанием архитектуры
└── ROADMAP.md                          # План дальнейшего развития
```

---

## 🔄 Архитектура потока данных (Data Flow)

```
[Пользователь]
      │
      ▼ (Отправка PDF / DOCX / Текста)
[bot.handlers.resume]
      │
      ├──► [services.resume_analyzer.validator] (Проверка на спам, рецепты, договоры, мусор)
      │         │
      │         ├── Невалидно ──► Сообщение об ошибке с перечнем недостающих секций
      │         ▼ Валидно
      ├──► [services.resume_analyzer.extractor] (Interval Union стажа, грейд, каталог 300+ скиллов)
      └──► [services.ai.llm_helper] (Опциональное улучшение через LLM)
      │
      ▼
[core.database.repository] ──► Сохранение профиля в БД (SQLite/PostgreSQL)

      │
      ▼ (Пользователь нажал "Найти вакансии" или фоновый триггер scheduler)
[services.parser.manager]
      │
      ├──► Генерация Query Permutation Pool (роль eng/ru, ядро стека, связки фреймворков)
      ├──► Параллельный опрос пачки из 3-5 запросов одновременно (asyncio.gather)
      ├──► Многостраничный сбор (scan_pages=2: страницы page и page + 1)
      │
      ├──► [HeadHunterParser]   (API)
      ├──► [HabrCareerParser]   (Scraper)
      ├──► [TrudVsemParser]     (Открытое REST API Работа России)
      ├──► [SuperJobParser]     (REST API / Web)
      ├──► [RemoteOKParser]     (REST API World Remote USD)
      ├──► [KworkParser]        (Scraper микро-задач)
      ├──► [FLRuParser]         (RSS биржа фриланса №1)
      ├──► [HabrFreelanceParser](RSS профильные IT-заказы)
      └──► [RabotaRuParser]     (Scraper)
      │
      ▼
[services.resume_analyzer.red_flags] ──► Отсеивание скама (BLOCKED / WARNING)
      │
      ▼
[services.parser.normalizer]         ──► Фильтрация по городу (удаленка всем, чужие офисы блок)
      │
      ▼
[services.resume_analyzer.matcher]   ──► Скоринг + Адаптивный fallback (мягкий порог 35% при нехватке)
      │
      ▼
[core.database.repository]          ──► Исключение UserViewed (уже просмотренных), лимит до 500
      │
      ▼
[bot.formatters.card]                ──► Генерация HTML карточки: формат, город, бейджи, кнопки
      │
      ▼
[Telegram Чат пользователя] ──► Пагинация, "В избранное", "Скрыть", "🔄 Обновить подборку"
```

---

## 🧩 Руководство по расширению: Добавление нового агрегатора

Архитектура построена по принципу открытости/закрытости (Open-Closed Principle). Чтобы добавить новый источник (например, Getmatch или Freelancehunt):

1. Создайте файл `services/parser/getmatch.py`:
   ```python
   from services.parser.base import BaseVacanciesParser

   class GetmatchParser(BaseVacanciesParser):
       def __init__(self):
           super().__init__(name="getmatch")

       async def fetch_vacancies(self, query: str, limit: int = 50, remote_only: bool = False, page: int = 0):
           # Реализация HTTP-запроса через httpx
           # ...
           return [self.standardize_vacancy(...)]
   ```

2. Зарегистрируйте новый парсер в `services/parser/manager.py`:
   ```python
   from services.parser.getmatch import GetmatchParser

   class AggregatorManager:
       def __init__(self):
           self.parsers = [
               HeadHunterParser(),
               HabrCareerParser(),
               TrudVsemParser(),
               SuperJobParser(),
               RemoteOKParser(),
               KworkParser(),
               FLRuParser(),
               HabrFreelanceParser(),
               RabotaRuParser(),
               GetmatchParser() # Новый парсер
           ]
   ```
3. Готово! Новый агрегатор автоматически подключен к параллельному конвейеру, проверке на ред-флаги, фильтрации по городам, адаптивному скорингу и фоновым уведомлениям.
