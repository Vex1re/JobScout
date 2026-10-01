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
│   │   ├── resume.py                   # Загрузка резюме (PDF/DOCX/текст), редактирование стека
│   │   ├── vacancies.py                # Поиск, карточки, пагинация, скрытие, AI-советы
│   │   ├── favorites.py                # Просмотр и удаление из избранного
│   │   └── settings.py                 # Фильтры (удаленка, минимальная ЗП, Kwork, уведомления)
│   ├── keyboards/                      # Клавиатуры бота
│   │   ├── __init__.py
│   │   ├── reply.py                    # Постоянное нижнее меню (Reply)
│   │   └── inline.py                   # Инлайн-кнопки (карточки вакансий, пагинация, настройки)
│   ├── middlewares/                    # Промежуточные слои Aiogram
│   │   └── db.py                       # Внедрение асинхронной сессии БД (AsyncSession) в хэндлеры
│   └── states/                         # FSM-состояния конечного автомата
│       ├── __init__.py
│       └── profile.py                  # Состояния загрузки резюме, ввода навыков, настроек
├── core/                               # Ядро приложения и инфраструктура
│   ├── database/                       # Слой базы данных (SQLAlchemy 2.0 Async)
│   │   ├── __init__.py
│   │   ├── models.py                   # ORM-модели (User, Resume, Vacancy, Favorite, Match)
│   │   ├── session.py                  # Создание движка create_async_engine и init_db()
│   │   └── repository.py               # Репозитории CRUD операций
│   ├── config.py                       # Настройки через Pydantic-Settings и чтение .env
│   └── scheduler.py                    # Фоновый планировщик APScheduler для пуш-уведомлений
├── services/                           # Бизнес-логика, парсеры и анализ
│   ├── ai/                             # Интеграция с языковыми моделями (LLM)
│   │   └── llm_helper.py               # Опциональный вызов OpenAI/LLM для генерации советов
│   ├── parser/                         # Модуль парсинга агрегаторов вакансий и бирж фриланса
│   │   ├── __init__.py
│   │   ├── base.py                     # Базовый абстрактный класс BaseVacanciesParser
│   │   ├── hh.py                       # Клиент официального REST API HeadHunter
│   │   ├── habr.py                     # Парсер вакансий Хабр Карьеры
│   │   ├── trudvsem.py                 # Официальное открытое REST API Работа России
│   │   ├── superjob.py                 # Парсер SuperJob (REST API и веб-поиск)
│   │   ├── remoteok.py                 # Клиент международного API удаленки RemoteOK (USD)
│   │   ├── kwork.py                    # Парсер freelance-проектов биржи Kwork
│   │   ├── fl_ru.py                    # RSS-парсер заказов фриланс-биржи FL.ru (IT/сайты)
│   │   ├── habr_freelance.py           # RSS-парсер IT-заказов Хабр Фриланс
│   │   ├── rabota.py                   # Парсер вакансий Работа.ру
│   │   └── manager.py                  # AggregatorManager (параллельный опрос всех 9 парсеров)
│   └── resume_analyzer/                # Анализ резюме, скоринг и фильтрация ред-флагов
│       ├── __init__.py
│       ├── extractor.py                # Извлечение текста (PDF/DOCX), стека (300+ скиллов), грейда
│       ├── matcher.py                  # Взвешенный алгоритм скоринга резюме vs вакансия
│       └── red_flags.py                # Детектор мошенников, залогов, серой ЗП и токсичных условий
├── tests/                              # Автоматические тесты (pytest)
│   ├── test_extractor.py               # Тесты извлечения стека и грейдов
│   ├── test_red_flags.py               # Тесты блокировки скама и выявления предупреждений
│   ├── test_matcher.py                 # Тесты алгоритма совместимости
│   └── test_parsers.py                 # Тесты унификации вакансий и парсинга зарплат
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
      ├──► [services.resume_analyzer.extractor] (Нормализация навыков, грейд, стаж)
      └──► [services.ai.llm_helper] (Опциональное улучшение через LLM)
      │
      ▼
[core.database.repository] ──► Сохранение профиля в БД (SQLite/PostgreSQL)

      │
      ▼ (Пользователь нажал "Найти вакансии" или фоновый триггер scheduler)
[services.parser.manager]
      │
      ├──► [HeadHunterParser] (API)
      ├──► [HabrCareerParser] (Scraper)
      ├──► [KworkParser]      (Scraper freelance)
      └──► [RabotaRuParser]   (Scraper)
      │
      ▼
[services.resume_analyzer.red_flags] ──► Отсеивание скама (BLOCKED / WARNING)
      │
      ▼
[services.resume_analyzer.matcher]   ──► Расчет совпадения (0 - 100%)
      │
      ▼
[bot.formatters.card]                ──► Генерация Telegram HTML карточки с кнопками
      │
      ▼
[Telegram Чат пользователя]
```

---

## 🧩 Руководство по расширению: Добавление нового агрегатора

Архитектура построена по принципу открытости/закрытости (Open-Closed Principle). Чтобы добавить новый источник (например, SuperJob или FL.ru):

1. Создайте файл `services/parser/superjob.py`:
   ```python
   from services.parser.base import BaseVacanciesParser

   class SuperJobParser(BaseVacanciesParser):
       def __init__(self):
           super().__init__(name="superjob")

       async def fetch_vacancies(self, query: str, limit: int = 30, remote_only: bool = False):
           # Реализация HTTP-запроса через httpx
           # ...
           return [self.standardize_vacancy(...)]
   ```

2. Зарегистрируйте новый парсер в `services/parser/manager.py`:
   ```python
   from services.parser.superjob import SuperJobParser

   class AggregatorManager:
       def __init__(self):
           self.parsers = [
               HeadHunterParser(),
               HabrCareerParser(),
               KworkParser(),
               RabotaRuParser(),
               SuperJobParser() # Новый парсер
           ]
   ```
3. Готово! Новый агрегатор автоматически подключен к поисковому конвейеру, проверке на ред-флаги, скорингу и фоновым уведомлениям.
