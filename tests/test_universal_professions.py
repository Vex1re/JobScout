import pytest
from core.database.models import Resume, User
from services.resume_analyzer.extractor import ResumeExtractor
from services.resume_analyzer.validator import ResumeValidator
from services.resume_analyzer.matcher import VacancyMatcher
from services.parser.manager import AggregatorManager


class TestUniversalProfessions:
    """
    Verifies support for non-IT professions across parsing, validation,
    scoring, matching, and query pool generation.
    """

    def test_marketing_specialist_lifecycle(self):
        cv = """
        Анна Ковалева
        Интернет-маркетолог / SMM-специалист
        
        Контакты:
        Telegram: @anna_marketing, Email: anna@mktg.ru, Телефон: +7 (999) 111-22-33
        
        Опыт работы:
        Более 3 лет ведения рекламных кампаний для e-commerce и онлайн-школ.
        - Настройка таргетированной рекламы и контекстной рекламы в Яндекс.Директ.
        - Ведение SMM и создание контент-стратегий, копирайтинг.
        - Аналитика конверсий через Яндекс.Метрика и Google Analytics, расчет юнит-экономики.
        
        Ключевые навыки:
        SMM, Таргетированная реклама, Яндекс.Директ, Google Analytics, Яндекс.Метрика, Копирайтинг, Лидогенерация
        
        Образование:
        Санкт-Петербургский государственный университет, Факультет журналистики и PR, 2021.
        """
        # 1. Extraction
        parsed = ResumeExtractor.parse_full_resume(cv)
        assert parsed["title"] in ["Интернет-маркетолог", "Маркетолог", "SMM-специалист"]
        assert "SMM" in parsed["skills"]
        assert "Яндекс.Директ" in parsed["skills"]
        assert "Google Analytics" in parsed["skills"]
        assert parsed["years_of_experience"] >= 3.0

        # 2. Validation
        val = ResumeValidator.validate(cv, tech_skills_count=len(parsed["skills"]))
        assert val.is_valid is True
        assert val.detected_type == "resume"

        # 3. Query generation
        resume_model = Resume(
            title=parsed["title"],
            grade=parsed["grade"],
            years_of_experience=parsed["years_of_experience"],
            skills=parsed["skills"]
        )
        pool = AggregatorManager.generate_query_pool(resume_model)
        assert any("маркетолог" in q.lower() or "smm" in q.lower() for q in pool)
        # MUST NOT contain developer/programming terms
        assert not any("developer" in q.lower() for q in pool)
        assert not any("разработчик" in q.lower() for q in pool)
        assert not any("python" in q.lower() for q in pool)

        # 4. Matching against marketing vacancy
        match_res = VacancyMatcher.match(
            candidate_skills=parsed["skills"],
            candidate_grade=parsed["grade"],
            candidate_role=parsed["title"],
            candidate_experience=parsed["years_of_experience"],
            vacancy_title="Ведущий интернет-маркетолог (SMM, трафик)",
            vacancy_description="Требуется специалист по интернет-маркетингу. Стек: SMM, Яндекс.Директ, Google Analytics",
            vacancy_requirements=["SMM", "Яндекс.Директ", "Google Analytics"]
        )
        assert match_res["score"] >= 80
        assert "SMM" in match_res["matched_skills"]
        assert "Яндекс.Директ" in match_res["matched_skills"]

    def test_accountant_lifecycle(self):
        cv = """
        Елена Васильева
        Главный бухгалтер
        
        Контакты:
        Телефон: +7 (916) 555-44-33, Email: elena.buh@mail.ru
        
        Опыт работы:
        5 лет ведения бухгалтерского и налогового учета в производственных компаниях.
        - Полное ведение ООО и ИП на ОСНО и УСН.
        - Первичная документация, акты, сверки, банк-клиент.
        - Расчет заработной платы, сдача налоговой отчетности.
        
        Профессиональные навыки:
        1С:Бухгалтерия, 1С:ЗУП, Бухгалтерский учет, Налоговый учет, Первичная документация, MS Excel, Банк-Клиент
        
        Образование:
        РЭУ им. Г.В. Плеханова, Факультет финансов и налогообложения, Специалист, 2019.
        """
        parsed = ResumeExtractor.parse_full_resume(cv)
        assert "бухгалтер" in parsed["title"].lower()
        assert any("1С" in s for s in parsed["skills"])
        assert "Бухгалтерский учет" in parsed["skills"]

        val = ResumeValidator.validate(cv, tech_skills_count=len(parsed["skills"]))
        assert val.is_valid is True

        resume_model = Resume(
            title=parsed["title"],
            grade=parsed["grade"],
            years_of_experience=parsed["years_of_experience"],
            skills=parsed["skills"]
        )
        pool = AggregatorManager.generate_query_pool(resume_model)
        assert any("бухгалтер" in q.lower() for q in pool)
        assert not any("developer" in q.lower() for q in pool)
        assert not any("docker" in q.lower() for q in pool)

        match_res = VacancyMatcher.match(
            candidate_skills=parsed["skills"],
            candidate_grade=parsed["grade"],
            candidate_role=parsed["title"],
            candidate_experience=parsed["years_of_experience"],
            vacancy_title="Бухгалтер на первичную документацию",
            vacancy_description="Обязанности: ведение первичной документации, знание 1С:Бухгалтерия и Excel",
            vacancy_requirements=["1С:Бухгалтерия", "Первичная документация", "MS Excel"]
        )
        assert match_res["score"] >= 75
        assert "1С:Бухгалтерия" in match_res["matched_skills"]

    def test_designer_lifecycle(self):
        cv = """
        Дмитрий Орлов
        Графический дизайнер / UI/UX дизайнер
        
        Контакты:
        Telegram: @orlov_design, Behance: behance.net/orlov
        
        Опыт работы:
        4 года проектирования интерфейсов мобильных приложений и веб-сервисов.
        - Создание дизайн-систем, UI-китов и интерактивных прототипов в Figma.
        - Подготовка полиграфии и баннеров в Adobe Photoshop и Illustrator.
        - Анимация микро-взаимодействий в After Effects.
        
        Ключевые навыки:
        Figma, UI/UX, Adobe Photoshop, Adobe Illustrator, After Effects, Веб-дизайн, Типографика
        
        Образование:
        Британская высшая школа дизайна (БВШД), Графический дизайн, 2021.
        """
        parsed = ResumeExtractor.parse_full_resume(cv)
        assert "дизайнер" in parsed["title"].lower()
        assert "Figma" in parsed["skills"]
        assert "UI/UX" in parsed["skills"]

        val = ResumeValidator.validate(cv, tech_skills_count=len(parsed["skills"]))
        assert val.is_valid is True

        resume_model = Resume(
            title=parsed["title"],
            grade=parsed["grade"],
            years_of_experience=parsed["years_of_experience"],
            skills=parsed["skills"]
        )
        pool = AggregatorManager.generate_query_pool(resume_model)
        assert any("дизайн" in q.lower() for q in pool)
        assert not any("backend" in q.lower() for q in pool)

        match_res = VacancyMatcher.match(
            candidate_skills=parsed["skills"],
            candidate_grade=parsed["grade"],
            candidate_role=parsed["title"],
            candidate_experience=parsed["years_of_experience"],
            vacancy_title="Product Designer / UI/UX Дизайнер",
            vacancy_description="Разработка интерфейсов веб-сервиса в Figma, подготовка иллюстраций",
            vacancy_requirements=["Figma", "UI/UX"]
        )
        assert match_res["score"] >= 80
        assert "Figma" in match_res["matched_skills"]

    def test_sales_manager_lifecycle(self):
        cv = """
        Сергей Смирнов
        Менеджер по продажам
        
        Контакты:
        Телефон: +7 (903) 777-88-99, Telegram: @smirnov_sales
        
        Опыт:
        3 года работы в B2B продажах IT-решений и SaaS продуктов.
        - Проведение сложных переговоров с ЛПР, заключение контрактов.
        - Работа с воронкой продаж в amoCRM и Битрикс24.
        - Холодные звонки и теплые лиды, перевыполнение KPI на 130%.
        
        Навыки:
        B2B продажи, amoCRM, Битрикс24, Холодные звонки, Переговоры, Воронка продаж
        
        Образование:
        Высшая школа экономики, Менеджмент, Бакалавр, 2022.
        """
        parsed = ResumeExtractor.parse_full_resume(cv)
        assert "продаж" in parsed["title"].lower()
        assert "B2B продажи" in parsed["skills"]
        assert "amoCRM" in parsed["skills"]

        val = ResumeValidator.validate(cv, tech_skills_count=len(parsed["skills"]))
        assert val.is_valid is True

        resume_model = Resume(
            title=parsed["title"],
            grade=parsed["grade"],
            years_of_experience=parsed["years_of_experience"],
            skills=parsed["skills"]
        )
        pool = AggregatorManager.generate_query_pool(resume_model)
        assert any("продаж" in q.lower() for q in pool)
        assert not any("developer" in q.lower() for q in pool)
