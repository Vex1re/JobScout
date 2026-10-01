import pytest
import datetime
from core.database.models import User, Resume, Vacancy
from core.database.repository import (
    UserRepository,
    VacancyRepository,
    InteractionRepository
)
from core.database.session import init_db, async_session_factory
from services.resume_analyzer.validator import ResumeValidator
from services.resume_analyzer.extractor import ResumeExtractor
from services.parser.normalizer import CityNormalizer
from services.parser.manager import AggregatorManager


# =====================================================================
# 1. ВАЛИДАЦИЯ РЕЗЮМЕ И АНТИ-СПАМ (ResumeValidator)
# =====================================================================

class TestResumeValidation:
    """
    Тестирование модуля валидации резюме и анти-спам фильтрации (ResumeValidator).
    Проверяет отсечение нерелевантного контента и корректный прием валидных CV.
    """

    def test_recipe_rejection_apple_pie(self):
        """Отклонение рецепта шарлотки / яблочного пирога."""
        pie_recipe = """
        Классический яблочный пирог (Шарлотка).
        Ингредиенты: 300 граммов пшеничной муки, 3 крупных яблока, 1 стакан сахара,
        2 столовая ложка корицы, 3 куриных яйца.
        Рецепт приготовления: нарезать яблоки тонким слоем, замесить тесто в миске,
        выпекать в духовке при температуре 180 градусов в течение 40 минут.
        Посолить по вкусу.
        """
        res = ResumeValidator.validate(pie_recipe, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "recipe"
        assert res.score == 0
        assert "рецепт" in res.error_message.lower()

    def test_recipe_rejection_borsch(self):
        """Отклонение кулинарного рецепта борща."""
        borsch_recipe = """
        Украинский традиционный борщ с пампушками.
        Ингредиенты: 500 граммов мяса на кости, свекла, капуста, картофель, лук, морковь.
        Рецепт: варить говядину в кастрюле 1.5 часа, нарезать свеклу и морковь соломкой,
        обжарить заправку на сковороде с томатной пастой. Посолить по вкусу, варить до готовности.
        """
        res = ResumeValidator.validate(borsch_recipe, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "recipe"
        assert res.score == 0
        assert "рецепт" in res.error_message.lower()

    def test_contract_rejection_lease(self):
        """Отклонение юридического договора аренды коммерческой недвижимости."""
        lease_agreement = """
        ДОГОВОР АРЕНДЫ НЕЖИЛОГО ПОМЕЩЕНИЯ № 45/2024
        Арендодатель в лице генерального директора Петрова А.В. и Арендатор в лице Сидорова Б.Г.
        заключили настоящий договор о нижеследующем.
        Стороны договорились: пункт договора 2.1 устанавливает размер арендной платы 100 000 рублей.
        Ответственность сторон регулируется Гражданским кодексом РФ.
        Акт приема-передачи помещения подписывается уполномоченными лицами.
        За нарушение сроков платежей начисляются штрафные санкции в размере 0.1% в день.
        Банковские реквизиты сторон и подписи.
        """
        res = ResumeValidator.validate(lease_agreement, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "contract"
        assert "договор" in res.error_message.lower()

    def test_contract_rejection_sale_and_purchase(self):
        """Отклонение договора купли-продажи оборудования / имущества."""
        sale_agreement = """
        ДОГОВОР КУПЛИ-ПРОДАЖИ ОБОРУДОВАНИЯ
        Настоящий договор определяет условия сделки.
        Предмет договора: поставка серверов и сетевого оборудования.
        Заказчик обязуется принять и оплатить товар, а Исполнитель обязуется передать документацию.
        Ответственность сторон: стороны несут ответственность согласно законодательству.
        Пункт договора 5.2 регулирует форс-мажорные обстоятельства.
        Паспортные данные и юридический адрес представителей.
        """
        res = ResumeValidator.validate(sale_agreement, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "contract"
        assert "договор" in res.error_message.lower()

    @pytest.mark.parametrize("gibberish", [
        "qwerty12345!@#",
        "qwerty12345!@# asdfghjk zxcvbnm 1234567890 !@#$%^&*()",
        "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "asdfghjk qwertyuiop zxcvbnm asdfghjk qwertyuiop zxcvbnm"
    ])
    def test_random_gibberish_and_symbols_rejection(self, gibberish):
        """Отклонение случайной абракадабры, наборов символов и повторений букв."""
        res = ResumeValidator.validate(gibberish, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type in ["gibberish", "insufficient"]

    @pytest.mark.parametrize("short_text", [
        "Привет",
        "Ищу работу",
        "Резюме разработчика",
        "Junior developer",
        "Хочу работать программистом"
    ])
    def test_short_text_rejection(self, short_text):
        """Отклонение слишком коротких сообщений (< 40 символов или < 6 слов)."""
        res = ResumeValidator.validate(short_text, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "gibberish"
        assert "короткий" in res.error_message.lower()

    def test_non_it_resume_rejected_when_no_tech_skills(self):
        """Отклонение полноценного резюме без единого IT-навыка (напр., менеджер по продажам)."""
        sales_resume = """
        Михаил Сергеев
        Руководитель отдела продаж
        
        Опыт работы:
        Более 7 лет в сфере B2B продаж строительных материалов.
        Управление командой из 15 менеджеров, выполнение квартальных планов на 120%.
        Проведение сложных переговоров с первыми лицами компаний.
        
        Образование:
        Московский государственный университет, Экономический факультет, бакалавр.
        
        Контакты:
        Телефон: +7 (999) 000-11-22, email: sales_leader@example.com
        """
        res = ResumeValidator.validate(sales_resume, tech_skills_count=0)
        assert res.is_valid is False
        assert res.detected_type == "insufficient"
        assert "навык" in res.error_message.lower() or "стек" in res.error_message.lower()

    def test_valid_developer_resume_accepted(self):
        """Успешное принятие корректного резюме разработчика со всеми ключевыми секциями."""
        developer_resume = """
        Евгений Морозов
        Senior Python / Backend Developer
        
        Контакты:
        Telegram: @morozov_dev, Email: morozov@devmail.org, GitHub: github.com/morozov-dev
        
        Опыт работы:
        Более 5 лет коммерческой разработки высоконагруженных сервисов.
        - Проектировал REST API и микросервисы на FastAPI и Django.
        - Оптимизировал сложные аналитические запросы в PostgreSQL, настроил шардирование.
        - Интегрировал брокеры сообщений RabbitMQ и Apache Kafka для асинхронных задач.
        - Развертывал окружения в Docker и Kubernetes, настраивал CI/CD пайплайны в GitLab.
        
        Ключевые навыки:
        Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, RabbitMQ, Kafka, Git, Linux
        
        Образование:
        Санкт-Петербургский политехнический университет Петра Великого (СПбПУ),
        Институт компьютерных наук и технологий, Магистр прикладной информатики, 2020.
        """
        skills = ResumeExtractor.extract_skills(developer_resume)
        assert len(skills) >= 6
        assert "Python" in skills
        assert "FastAPI" in skills

        res = ResumeValidator.validate(developer_resume, tech_skills_count=len(skills))
        assert res.is_valid is True
        assert res.score >= 75
        assert res.error_message is None
        assert res.detected_type == "resume"


# =====================================================================
# 2. ТОЧНОСТЬ РАСЧЕТА СТАЖА И ОПЫТА (ResumeExtractor)
# =====================================================================

class TestExperienceCalculation:
    """
    Тестирование извлечения стажа работы и детекции грейда (ResumeExtractor).
    Проверяет нулевой опыт начинающих, составные периоды, даты и объединение интервалов.
    """

    @pytest.mark.parametrize("beginner_text, expected_grade", [
        ("коммерческого опыта нет, ищу стажировку", "Junior"),
        ("Опыт работы: 0 лет, стажер Python", "Junior"),
        ("Без опыта работы, начинающий разработчик", "Junior"),
        ("Ищу стажировку в IT, коммерческого опыта нет", "Junior"),
        ("Junior без опыта работы, студент последних курсов", "Junior"),
        ("Начинающий специалист по Python, опыта нет", "Junior"),
    ])
    def test_intern_beginner_zero_experience_and_junior_grade(self, beginner_text, expected_grade):
        """Стажер / Начинающий без опыта -> ровно 0.0 лет и грейд 'Junior' (НЕ 1.0 и НЕ Middle!)."""
        exp_years = ResumeExtractor.extract_experience_years(beginner_text)
        assert exp_years == 0.0, f"Expected 0.0 years, got {exp_years} for text: '{beginner_text}'"

        grade = ResumeExtractor.detect_grade(beginner_text, exp_years)
        assert grade == expected_grade, f"Expected '{expected_grade}', got '{grade}'"
        assert grade != "Middle", "Beginner with zero experience MUST NOT be graded as Middle!"
        assert grade != "Senior", "Beginner with zero experience MUST NOT be graded as Senior!"

    @pytest.mark.parametrize("compound_text, expected_years", [
        ("Общий стаж: 2 года 6 месяцев", 2.5),
        ("Опыт работы: 1 год 6 месяцев", 1.5),
        ("Коммерческий опыт: 3 года 8 месяцев", 3.7),
        ("4 года и 6 месяцев в разработке", 4.5),
        ("2 years 6 months of experience", 2.5),
        ("6 месяцев разработки на Python", 0.5),
        ("18 месяцев коммерческого опыта", 1.5),
    ])
    def test_compound_periods_calculation(self, compound_text, expected_years):
        """Расчет составных периодов 'X лет Y месяцев' с переводом в десятичные доли года."""
        result = ResumeExtractor.extract_experience_years(compound_text)
        assert result == expected_years

    @pytest.mark.parametrize("interval_text, expected_years", [
        ("Период работы в компании: 2021 — 2024", 3.0),
        ("Работал в Альфа-Банке: 2018 - 2023", 5.0),
        ("Период: 2020 to 2022", 2.0),
        ("Даты: 01.2020 — 12.2022", 3.0),
    ])
    def test_date_range_intervals(self, interval_text, expected_years):
        """Расчет диапазона дат фиксированных лет (например, '2021 — 2024' -> 3.0 года)."""
        result = ResumeExtractor.extract_experience_years(interval_text)
        assert result == expected_years

    def test_present_period_relative_to_current_year_2026(self):
        """
        Расчет периода по настоящее время 'январь 2024 — по н.в.'
        с учетом текущего системного года (2026).
        Интервал от января 2024 до конца 2026 года должен составлять ~2.8 - 2.9 года.
        """
        current_year = datetime.datetime.now().year
        assert current_year == 2026, "Test environment must be running in 2026"

        text_monthly = "Период работы: январь 2024 — по н.в."
        exp_monthly = ResumeExtractor.extract_experience_years(text_monthly)
        assert 2.7 <= exp_monthly <= 3.0, f"Expected 2.7-3.0 for Jan 2024 - Present in 2026, got {exp_monthly}"

        text_dot = "Опыт: 01.2024 — по настоящее время"
        exp_dot = ResumeExtractor.extract_experience_years(text_dot)
        assert 2.7 <= exp_dot <= 3.0, f"Expected 2.7-3.0 for 01.2024 - Present in 2026, got {exp_dot}"

        text_yearly = "Компания X: 2024 — н.в."
        exp_yearly = ResumeExtractor.extract_experience_years(text_yearly)
        assert 2.5 <= exp_yearly <= 3.0, f"Expected 2.5-3.0 for 2024 - Present in 2026, got {exp_yearly}"

    def test_overlapping_intervals_interval_union(self):
        """
        Перекрывающиеся интервалы работы (Interval Union):
        - 2020-2022 (2 года) и 2021-2023 (2 года) дают ровно 3 года (2020-2023), а НЕ 4.
        - Месячные перекрытия: 01.2021-12.2022 и 06.2022-06.2023 дают 2.5 года (30 мес), а НЕ 3.0.
        - Полное вложение: 2019-2023 и 2020-2022 дают 4 года, а НЕ 6.
        """
        text_years = "Компания A: 2020 — 2022. Компания B: 2021 — 2023."
        exp_years = ResumeExtractor.extract_experience_years(text_years)
        assert exp_years == 3.0, f"Expected 3.0 years via Interval Union, got {exp_years}"

        text_months = "Компания 1: 01.2021 — 12.2022. Компания 2: 06.2022 — 06.2023."
        exp_months = ResumeExtractor.extract_experience_years(text_months)
        assert exp_months == 2.5, f"Expected 2.5 years via Interval Union, got {exp_months}"

        text_nested = "Проект 1: 2019 — 2023. Проект 2: 2020 — 2022."
        exp_nested = ResumeExtractor.extract_experience_years(text_nested)
        assert exp_nested == 4.0, f"Expected 4.0 years for nested intervals, got {exp_nested}"


# =====================================================================
# 3. ФИЛЬТРАЦИЯ ПО ГОРОДУ (CityNormalizer & VacancyRepository)
# =====================================================================

class TestCityFiltering:
    """
    Тестирование фильтрации по городу и нормализации локаций.
    Проверяет доступность удаленки, строгое совпадение офисов и синонимы.
    """

    def test_remote_perm_matches_moscow_user(self):
        """Удаленная вакансия (is_remote=True, город Пермь) подходит соискателю из Москвы."""
        assert CityNormalizer.is_match(
            user_city="Москва",
            vacancy_city="Пермь",
            is_remote=True
        ) is True

    def test_office_perm_strictly_blocked_for_moscow_user(self):
        """Офисная вакансия (is_remote=False, город Пермь) СТРОГО блокируется для соискателя из Москвы."""
        assert CityNormalizer.is_match(
            user_city="Москва",
            vacancy_city="Пермь",
            is_remote=False
        ) is False

    def test_office_moscow_matches_moscow_user(self):
        """Офисная вакансия (is_remote=False, город Москва) подходит соискателю из Москвы."""
        assert CityNormalizer.is_match(
            user_city="Москва",
            vacancy_city="Москва",
            is_remote=False
        ) is True

    @pytest.mark.parametrize("wildcard_city", ["Любой", "все", "любой город", "None", "", None])
    def test_user_with_any_city_sees_all_office_vacancies(self, wildcard_city):
        """Пользователь с городом 'Любой' (или без фильтра) видит офисные вакансии из любых городов."""
        assert CityNormalizer.is_match(user_city=wildcard_city, vacancy_city="Пермь", is_remote=False) is True
        assert CityNormalizer.is_match(user_city=wildcard_city, vacancy_city="Москва", is_remote=False) is True
        assert CityNormalizer.is_match(user_city=wildcard_city, vacancy_city="Казань", is_remote=False) is True
        assert CityNormalizer.is_match(user_city=wildcard_city, vacancy_city="Екатеринбург", is_remote=False) is True

    def test_synonyms_normalization_and_matching(self):
        """Нормализация синонимов: 'мск', 'питер', 'спб', 'г. Москва' корректно приводятся и сопоставляются."""
        assert CityNormalizer.normalize("мск") == "Москва"
        assert CityNormalizer.normalize("г. Москва") == "Москва"
        assert CityNormalizer.normalize("город москва") == "Москва"
        assert CityNormalizer.normalize("Moscow") == "Москва"

        assert CityNormalizer.normalize("питер") == "Санкт-Петербург"
        assert CityNormalizer.normalize("спб") == "Санкт-Петербург"
        assert CityNormalizer.normalize("г. санкт-петербург") == "Санкт-Петербург"
        assert CityNormalizer.normalize("st. petersburg") == "Санкт-Петербург"

        assert CityNormalizer.normalize("екб") == "Екатеринбург"
        assert CityNormalizer.normalize("нск") == "Новосибирск"
        assert CityNormalizer.normalize("Любой") is None

        # Cross-matching с синонимами
        assert CityNormalizer.is_match("мск", "г. Москва", is_remote=False) is True
        assert CityNormalizer.is_match("Москва", "МСК", is_remote=False) is True
        assert CityNormalizer.is_match("питер", "спб", is_remote=False) is True
        assert CityNormalizer.is_match("Санкт-Петербург", "Питер", is_remote=False) is True
        assert CityNormalizer.is_match("мск", "питер", is_remote=False) is False

    @pytest.mark.asyncio
    async def test_db_vacancy_repository_city_filtering_strictness(self):
        """
        Проверка фильтрации на уровне БД (VacancyRepository.get_unhidden_vacancies):
        - Удаленка из Перми доступна москвичу.
        - Офис в Перми СТРОГО отсекается для москвича.
        - Офис в Москве доступен москвичу.
        - Для соискателя с городом 'Любой' доступны все офисные и удаленные вакансии.
        """
        await init_db()
        test_user_id = 999111222

        async with async_session_factory() as session:
            # Upsert distinctive test vacancies
            vacancies = [
                {
                    "id": "qa_vac_perm_remote",
                    "source": "hh",
                    "title": "Python Remote in Perm",
                    "is_remote": True,
                    "city": "Пермь"
                },
                {
                    "id": "qa_vac_perm_office",
                    "source": "hh",
                    "title": "Python Office in Perm",
                    "is_remote": False,
                    "city": "Пермь"
                },
                {
                    "id": "qa_vac_moscow_office",
                    "source": "hh",
                    "title": "Python Office in Moscow",
                    "is_remote": False,
                    "city": "Москва"
                }
            ]
            await VacancyRepository.upsert_vacancies(session, vacancies)

            # 1. Запрос пользователя из Москвы
            moscow_vacs = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=test_user_id,
                user_city="Москва",
                remote_only=False,
                exclude_viewed=False
            )
            moscow_ids = {v.id for v in moscow_vacs}
            assert "qa_vac_perm_remote" in moscow_ids, "Remote vacancy in Perm MUST be visible to Moscow user"
            assert "qa_vac_moscow_office" in moscow_ids, "Office vacancy in Moscow MUST be visible to Moscow user"
            assert "qa_vac_perm_office" not in moscow_ids, "Office vacancy in Perm MUST NOT be visible to Moscow user"

            # 2. Запрос пользователя со значением 'Любой'
            any_city_vacs = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=test_user_id,
                user_city="Любой",
                remote_only=False,
                exclude_viewed=False
            )
            any_city_ids = {v.id for v in any_city_vacs}
            assert "qa_vac_perm_remote" in any_city_ids
            assert "qa_vac_moscow_office" in any_city_ids
            assert "qa_vac_perm_office" in any_city_ids, "Office vacancy in Perm MUST be visible when city is 'Любой'"


# =====================================================================
# 4. ДИНАМИЧЕСКАЯ РОТАЦИЯ И ОТСЛЕЖИВАНИЕ ПРОСМОТРОВ (UserViewed & Manager)
# =====================================================================

class TestDynamicRotationAndViewTracking:
    """
    Тестирование отслеживания просмотренных вакансий (UserViewed),
    сброса истории просмотров (reset_viewed_history) и динамического пула запросов.
    """

    @pytest.mark.asyncio
    async def test_viewed_vacancies_excluded_from_subsequent_fetch(self):
        """Просмотренные пользователем вакансии (UserViewed) исключаются из повторной выдачи."""
        await init_db()
        user_id = 888222333
        vac_id = "qa_vac_view_exclusion_1"

        async with async_session_factory() as session:
            # Сброс для обеспечения изоляции и независимости теста
            await InteractionRepository.reset_viewed_history(session, user_id=user_id)

            await VacancyRepository.upsert_vacancies(session, [{
                "id": vac_id,
                "source": "hh",
                "title": "Rotation Exclusion Test Vacancy",
                "is_remote": True
            }])

            # До просмотра: вакансия должна присутствовать в выборке
            unhidden_before = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=user_id,
                exclude_viewed=True
            )
            assert vac_id in {v.id for v in unhidden_before}

            # Отмечаем как просмотренную
            await InteractionRepository.mark_as_viewed(
                session=session,
                user_id=user_id,
                vacancy_id=vac_id
            )

            # После просмотра: вакансия исключена из выборки
            unhidden_after = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=user_id,
                exclude_viewed=True
            )
            assert vac_id not in {v.id for v in unhidden_after}

    @pytest.mark.asyncio
    async def test_reset_viewed_history_makes_vacancies_available_again(self):
        """Метод reset_viewed_history очищает историю просмотров и снова делает вакансии доступными."""
        await init_db()
        user_id = 888222444
        vac_id = "qa_vac_reset_history_2"

        async with async_session_factory() as session:
            # Сброс для обеспечения изоляции и независимости теста
            await InteractionRepository.reset_viewed_history(session, user_id=user_id)

            await VacancyRepository.upsert_vacancies(session, [{
                "id": vac_id,
                "source": "hh",
                "title": "Reset History Test Vacancy",
                "is_remote": True
            }])

            # Помечаем вакансию просмотренной
            await InteractionRepository.mark_as_viewed(
                session=session,
                user_id=user_id,
                vacancy_id=vac_id
            )

            # Проверяем, что она скрыта из выдачи
            viewed_check = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=user_id,
                exclude_viewed=True
            )
            assert vac_id not in {v.id for v in viewed_check}

            # Сбрасываем историю просмотров
            deleted_count = await InteractionRepository.reset_viewed_history(
                session=session,
                user_id=user_id
            )
            assert deleted_count >= 1

            # Вакансия снова доступна в выдаче
            available_after_reset = await VacancyRepository.get_unhidden_vacancies(
                session=session,
                user_id=user_id,
                exclude_viewed=True
            )
            assert vac_id in {v.id for v in available_after_reset}

    def test_generate_query_pool_produces_diverse_combinations(self):
        """
        Генерация пула запросов (generate_query_pool) строит разнообразные комбинации:
        ролевую позицию, парные сочетания навыков, одиночные ключевые технологии,
        а не только два фиксированных навыка.
        """
        resume = Resume(
            title="Senior Python Backend Developer",
            grade="Senior",
            years_of_experience=5.0,
            skills=["Python", "FastAPI", "PostgreSQL", "Docker", "Redis", "Kafka"]
        )
        pool = AggregatorManager.generate_query_pool(resume)

        # Должен возвращать разнообразный пул
        assert len(pool) >= 5, f"Pool must contain multiple distinct queries, got {len(pool)}"
        assert "Senior Python Backend Developer" in pool
        assert "Python FastAPI" in pool
        assert "Python PostgreSQL" in pool
        assert "FastAPI Docker" in pool
        assert "Python" in pool
        assert "FastAPI" in pool

        # Проверка ротации по индексу
        idx_0_query = pool[0 % len(pool)]
        idx_1_query = pool[1 % len(pool)]
        idx_2_query = pool[2 % len(pool)]
        assert idx_0_query != idx_1_query
        assert idx_1_query != idx_2_query

    @pytest.mark.asyncio
    async def test_search_offsets_incremented_on_search(self):
        """Проверка смещения поисковой пагинации и циклического индекса запросов."""
        await init_db()
        test_id = 999333444

        async with async_session_factory() as session:
            user = await UserRepository.get_or_create_user(
                session=session,
                telegram_id=test_id,
                username="rotation_user"
            )
            initial_page = user.search_page_offset or 0
            initial_query_idx = user.last_query_index or 0

            # Имитация шага поиска
            await UserRepository.increment_search_offsets(
                session=session,
                telegram_id=test_id,
                offset_inc=1,
                query_index_inc=1
            )

            updated_user = await UserRepository.get_or_create_user(
                session=session,
                telegram_id=test_id
            )
            assert updated_user.search_page_offset == initial_page + 1
            assert updated_user.last_query_index == initial_query_idx + 1

    def test_resume_handler_get_onboarding_keyboard_imported(self):
        """Проверка, что get_onboarding_keyboard импортирован и доступен в bot.handlers.resume."""
        import bot.handlers.resume as resume_mod
        assert hasattr(resume_mod, "get_onboarding_keyboard")
        kb = resume_mod.get_onboarding_keyboard()
        assert kb is not None

    def test_fused_conditions_fixed_in_card_formatter(self):
        """Проверка, что слипшиеся строки вида 'Можно удалённоМосква' разделяются точкой в карточке."""
        from bot.formatters.card import format_vacancy_card
        from core.database.models import Vacancy

        vac = Vacancy(
            id="habr_test_123",
            source="habr",
            title="Backend Developer",
            company="Tech Corp",
            url="https://career.habr.com/vacancies/123",
            description="Навыки: Python, FastAPI\nУсловия: Можно удалённоМосква",
            is_remote=True,
            city="Москва",
            risk_level="safe",
            red_flags=[]
        )

        match_info = {
            "score": 90,
            "matched_skills": ["Python"],
            "missing_skills": [],
            "reason": "OK"
        }

        card = format_vacancy_card(vac, match_info)
        assert "удалённоМосква" not in card
        assert "удалённо • Москва" in card

