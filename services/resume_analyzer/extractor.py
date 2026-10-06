import io
import re
import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
import pypdf
import docx


# Normalized catalog of tech skills and synonyms
TECH_SKILLS_MAP: Dict[str, str] = {
    # Backend / Languages
    "python": "Python",
    "python3": "Python",
    "golang": "Go",
    "go": "Go",
    "java": "Java",
    "kotlin": "Kotlin",
    "scala": "Scala",
    "rust": "Rust",
    "c++": "C++",
    "cpp": "C++",
    "c#": "C#",
    "csharp": "C#",
    ".net": ".NET",
    "dotnet": ".NET",
    "php": "PHP",
    "ruby": "Ruby",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "node": "Node.js",
    "typescript": "TypeScript",
    "ts": "TypeScript",
    "javascript": "JavaScript",
    "js": "JavaScript",

    # Python frameworks & libs
    "django": "Django",
    "fastapi": "FastAPI",
    "fast api": "FastAPI",
    "flask": "Flask",
    "aiohttp": "aiohttp",
    "asyncio": "asyncio",
    "celery": "Celery",
    "sqlalchemy": "SQLAlchemy",
    "pydantic": "Pydantic",
    "pytest": "Pytest",
    "aiogram": "aiogram",
    "telebot": "pyTelegramBotAPI",

    # Frontend
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "angular": "Angular",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "nuxt": "Nuxt.js",
    "redux": "Redux",
    "mobx": "MobX",
    "tailwind": "Tailwind CSS",
    "html": "HTML5",
    "css": "CSS3",
    "sass": "SASS/SCSS",
    "scss": "SASS/SCSS",

    # Databases & Caches
    "postgresql": "PostgreSQL",
    "postgres": "PostgreSQL",
    "psql": "PostgreSQL",
    "mysql": "MySQL",
    "mariadb": "MariaDB",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "clickhouse": "ClickHouse",
    "elasticsearch": "Elasticsearch",
    "elastic": "Elasticsearch",
    "opensearch": "OpenSearch",
    "cassandra": "Cassandra",
    "neo4j": "Neo4j",

    # Message Brokers & Queues
    "kafka": "Apache Kafka",
    "apache kafka": "Apache Kafka",
    "rabbitmq": "RabbitMQ",
    "rabbit": "RabbitMQ",
    "sqs": "AWS SQS",

    # DevOps & Infrastructure
    "docker": "Docker",
    "docker-compose": "Docker Compose",
    "compose": "Docker Compose",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "helm": "Helm",
    "ansible": "Ansible",
    "terraform": "Terraform",
    "ci/cd": "CI/CD",
    "cicd": "CI/CD",
    "gitlab ci": "GitLab CI",
    "github actions": "GitHub Actions",
    "jenkins": "Jenkins",
    "linux": "Linux",
    "bash": "Bash",
    "nginx": "Nginx",

    # Cloud
    "aws": "AWS",
    "gcp": "Google Cloud",
    "azure": "Azure",
    "yandex cloud": "Yandex Cloud",

    # Architecture & API
    "rest": "REST API",
    "rest api": "REST API",
    "grpc": "gRPC",
    "graphql": "GraphQL",
    "websocket": "WebSocket",
    "websockets": "WebSocket",
    "microservices": "Microservices",
    "микросервисы": "Microservices",
    "git": "Git",

    # Data Science / ML / AI
    "pandas": "Pandas",
    "numpy": "NumPy",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "scikit-learn": "Scikit-Learn",
    "sklearn": "Scikit-Learn",
    "opencv": "OpenCV",
    "llm": "LLM",
    "nlp": "NLP",
    "langchain": "LangChain",
    "rag": "RAG",

    # Mobile
    "flutter": "Flutter",
    "react native": "React Native",
    "swift": "Swift",
    "swiftui": "SwiftUI",

    # QA
    "selenium": "Selenium",
    "playwright": "Playwright",
    "cypress": "Cypress",
    "allure": "Allure",
    "postman": "Postman",

    # Marketing & Digital
    "smm": "SMM",
    "seo": "SEO",
    "контекстная реклама": "Контекстная реклама",
    "яндекс директ": "Яндекс.Директ",
    "яндекс.директ": "Яндекс.Директ",
    "директ": "Яндекс.Директ",
    "google ads": "Google Ads",
    "таргетинг": "Таргетированная реклама",
    "таргетированная реклама": "Таргетированная реклама",
    "копирайтинг": "Копирайтинг",
    "контент-маркетинг": "Контент-маркетинг",
    "email маркетинг": "Email-маркетинг",
    "e-mail маркетинг": "Email-маркетинг",
    "яндекс метрика": "Яндекс.Метрика",
    "яндекс.метрика": "Яндекс.Метрика",
    "google analytics": "Google Analytics",
    "лидогенерация": "Лидогенерация",
    "медиапланирование": "Медиапланирование",
    "pr": "PR",

    # Design & Creative
    "figma": "Figma",
    "photoshop": "Adobe Photoshop",
    "adobe photoshop": "Adobe Photoshop",
    "illustrator": "Adobe Illustrator",
    "adobe illustrator": "Adobe Illustrator",
    "after effects": "After Effects",
    "coreldraw": "CorelDRAW",
    "corel draw": "CorelDRAW",
    "ui/ux": "UI/UX",
    "ux/ui": "UI/UX",
    "web-дизайн": "Веб-дизайн",
    "веб дизайн": "Веб-дизайн",
    "графический дизайн": "Графический дизайн",
    "3d max": "3ds Max",
    "3ds max": "3ds Max",
    "blender": "Blender",
    "indesign": "InDesign",
    "motion design": "Motion Design",
    "моушн дизайн": "Motion Design",
    "типографика": "Типографика",
    "sketch": "Sketch",

    # Sales & Commerce
    "b2b": "B2B продажи",
    "b2b продажи": "B2B продажи",
    "b2c": "B2C продажи",
    "b2c продажи": "B2C продажи",
    "amocrm": "amoCRM",
    "amo crm": "amoCRM",
    "битрикс24": "Битрикс24",
    "битрикс 24": "Битрикс24",
    "bitrix24": "Битрикс24",
    "холодные звонки": "Холодные звонки",
    "переговоры": "Переговоры",
    "деловые переговоры": "Переговоры",
    "воронка продаж": "Воронка продаж",
    "работа с возражениями": "Работа с возражениями",
    "клиентский сервис": "Клиентский сервис",
    "управление продажами": "Управление продажами",
    "прямые продажи": "Прямые продажи",
    "тендеры": "Тендеры",
    "госзакупки": "Госзакупки",
    "44-фз": "44-ФЗ",
    "223-фз": "223-ФЗ",

    # Finance & Accounting
    "1с": "1С:Предприятие",
    "1с:бухгалтерия": "1С:Бухгалтерия",
    "1с бухгалтерия": "1С:Бухгалтерия",
    "1с:зуп": "1С:ЗУП",
    "1с зуп": "1С:ЗУП",
    "бухгалтерский учет": "Бухгалтерский учет",
    "бухучет": "Бухгалтерский учет",
    "налоговый учет": "Налоговый учет",
    "первичная документация": "Первичная документация",
    "первичка": "Первичная документация",
    "excel": "MS Excel",
    "ms excel": "MS Excel",
    "финансовый анализ": "Финансовый анализ",
    "мсфо": "МСФО",
    "банк-клиент": "Банк-Клиент",
    "расчет заработной платы": "Расчет заработной платы",
    "расчет зарплаты": "Расчет заработной платы",
    "налоговая отчетность": "Налоговая отчетность",
    "аудит": "Аудит",
    "управленческий учет": "Управленческий учет",

    # HR & Recruitment
    "рекрутинг": "Рекрутинг",
    "подбор персонала": "Подбор персонала",
    "адаптация персонала": "Адаптация персонала",
    "кадровое делопроизводство": "Кадровое делопроизводство",
    "кдп": "Кадровое делопроизводство",
    "хедхантинг": "Хедхантинг",
    "оценка персонала": "Оценка персонала",
    "мотивация персонала": "Мотивация персонала",
    "проведение собеседований": "Проведение собеседований",

    # Legal
    "договорное право": "Договорное право",
    "составление договоров": "Договорное право",
    "претензионная работа": "Претензионная работа",
    "корпоративное право": "Корпоративное право",
    "арбитраж": "Арбитраж",
    "судебная практика": "Судебная практика",
    "юридическое сопровождение": "Юридическое сопровождение",

    # Management & Operations
    "scrum": "Scrum",
    "agile": "Agile",
    "kanban": "Kanban",
    "jira": "Jira",
    "confluence": "Confluence",
    "управление проектами": "Управление проектами",
    "project management": "Project Management",
    "product management": "Product Management",
    "управление командой": "Управление командой",
    "custdev": "CustDev",
    "юнит-экономика": "Unit-экономика",
    "бизнес-процессы": "Бизнес-процессы",

    # Logistics & Supply
    "логистика": "Логистика",
    "вэд": "ВЭД",
    "управление складом": "Складской учет",
    "складской учет": "Складской учет",
    "закупки": "Закупки",
    "снабжение": "Снабжение",
    "транспортная логистика": "Транспортная логистика",

    # Office & General
    "деловая переписка": "Деловая переписка",
    "документооборот": "Документооборот",
    "эдо": "ЭДО",
    "ms office": "MS Office",
    "powerpoint": "PowerPoint",
    "английский язык": "Английский язык",

    # Engineering & Technical
    "autocad": "AutoCAD",
    "автокад": "AutoCAD",
    "solidworks": "SolidWorks",
    "компас-3d": "Компас-3D",
    "проектирование": "Проектирование",
    "чпу": "ЧПУ"
}


class ResumeExtractor:
    @staticmethod
    def extract_text_from_pdf(file_bytes: bytes) -> str:
        """Extract text content from PDF bytes."""
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text = "\n".join([page.extract_text() or "" for page in reader.pages])
            return text.strip()
        except Exception as e:
            return ""

    @staticmethod
    def extract_text_from_docx(file_bytes: bytes) -> str:
        """Extract text content from DOCX bytes."""
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
            text = "\n".join([p.text for p in doc.paragraphs])
            return text.strip()
        except Exception as e:
            return ""

    @classmethod
    def extract_skills(cls, text: str) -> List[str]:
        """Extract normalized technical and professional skills found in text."""
        lowered = f" {text.lower()} "
        found_skills: Set[str] = set()

        for key, canonical in TECH_SKILLS_MAP.items():
            pattern = r"(?<![a-zA-Z0-9_#+а-яА-ЯёЁ])" + re.escape(key) + r"(?![a-zA-Z0-9_#+а-яА-ЯёЁ])"
            if re.search(pattern, lowered):
                found_skills.add(canonical)

        # Dynamic extraction from explicit skills section if present
        section_pattern = r"(?:ключевые\s+навыки|профессиональные\s+навыки|навыки|компетенции|стек|skills)[:\s\n]+([^\n\r]+(?:\n[•\-\*\s]+[^\n\r]+|\n[^\n\r]+){0,10})"
        sec_match = re.search(section_pattern, text, re.IGNORECASE)
        if sec_match:
            sec_text = sec_match.group(1)
            raw_tokens = re.split(r"[,;•\n\*\t]+", sec_text)
            for token in raw_tokens:
                cleaned = token.strip().strip("-").strip()
                if 2 <= len(cleaned) <= 35 and not any(kw in cleaned.lower() for kw in ["опыт", "образование", "контакт", "телефон", "email", "город"]):
                    if len(cleaned.split()) <= 4:
                        found_skills.add(cleaned.strip().capitalize())

        # Sort alphabetically for consistent representation
        return sorted(list(found_skills))

    @classmethod
    def detect_grade(cls, text: str, years: float) -> str:
        """Detect seniority grade from resume text and years of experience."""
        lowered = text.lower()

        if re.search(r"\b(lead|тимлид|руководитель|главный разработчик|staff|principal|architect|архитектор)\b", lowered):
            return "Lead"
        elif re.search(r"\b(senior|сеньор|сеньер|синиор|ведущий разработчик|старший)\b", lowered):
            return "Senior"
        elif re.search(r"\b(middle\+|мидл\+|миддл\+|middle|мидл|миддл)\b", lowered):
            return "Middle"
        elif re.search(r"\b(junior\+|джуниор\+|junior|джуниор|джун|стажер|intern|trainee)\b", lowered):
            return "Junior"

        # Fallback to experience years
        if years >= 5.0:
            return "Senior"
        elif years >= 2.0:
            return "Middle"
        elif years >= 0.5:
            return "Junior"
        return "Junior"

    @classmethod
    def extract_experience_years(cls, text: str) -> float:
        """
        Extract years of experience from resume text:
        - Accurately identifies zero experience (0.0 years) for interns and beginners
        - Parses compound periods (e.g. '3 года 8 месяцев' -> 3.7)
        - Extracts date intervals and applies Interval Union algorithm for overlapping periods
        - Fallback default is 0.0
        """
        lowered = text.lower()

        # 1. Zero experience detection for interns / beginners
        zero_patterns = [
            r"\bбез\s+опыта\b",
            r"\bнет\s+опыта\b",
            r"\bопыт(?:а)?(?:\s+работы)?[:\s\-]+0(?:\.0)?\s*(?:лет|год|года|г\.|мес)",
            r"\b0\s*(?:лет|года|месяцев)\s+(?:опыта|коммерческого)",
            r"\bищу\s+стажировку\b",
            r"\b(стажер|intern|trainee)\b",
            r"\bначинающий\s+(?:разработчик|специалист|программист)\b",
            r"\bjunior\s+без\s+опыта\b"
        ]
        has_zero_experience = any(re.search(p, lowered) for p in zero_patterns)

        # 2. Compound periods like "3 года 8 месяцев", "1 год и 2 месяца"
        compound_patterns = [
            r"(\d+)\s*(?:лет|год|года|г\.|years|year|yrs)\s*(?:и\s*)?(\d+)\s*(?:месяцев|месяца|мес\.|months|month)",
            r"(\d+)\s*(?:месяцев|месяца|мес\.|months|month)\s*(?:и\s*)?(\d+)\s*(?:лет|год|года|г\.|years|year|yrs)"
        ]
        for p in compound_patterns:
            c_match = re.search(p, lowered)
            if c_match:
                if "мес" in p.split("(")[1] or "month" in p.split("(")[1]:
                    months, years = int(c_match.group(1)), int(c_match.group(2))
                else:
                    years, months = int(c_match.group(1)), int(c_match.group(2))
                return round(years + (months / 12.0), 1)

        # 3. Explicit patterns: "опыт работы: 4 года", "более 5 лет", "4 года опыта"
        explicit_patterns = [
            r"опыт(?:а)?(?:\s+работы)?[:\s\-]+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:лет|год|года|г\.|years|year|yrs)\s+(?:опыта|коммерческого опыта)",
            r"(?:более|от)\s+(\d+(?:[.,]\d+)?)\s*(?:лет|года)",
            r"(\d+(?:[.,]\d+)?)\s*(?:\+)?\s*(?:лет|года)\s+в\s+(?:разработке|it)"
        ]
        for p in explicit_patterns:
            match = re.search(p, lowered)
            if match:
                val = match.group(1).replace(",", ".")
                try:
                    return float(val)
                except ValueError:
                    pass

        # Explicit months: "18 месяцев коммерческого опыта"
        month_match = re.search(r"(\d+)\s*(?:месяцев|месяца|мес\.|months)", lowered)
        if month_match:
            try:
                months = int(month_match.group(1))
                return round(months / 12.0, 1)
            except ValueError:
                pass

        # 4. Date intervals with Interval Union (e.g. '2021 — 2024', 'январь 2024 — по настоящее время')
        intervals = cls._extract_date_intervals(lowered)
        if intervals:
            # Sort intervals by start timestamp
            intervals.sort(key=lambda x: x[0])
            merged = []
            for start, end in intervals:
                if start > end:
                    start, end = end, start
                if not merged:
                    merged.append([start, end])
                else:
                    prev = merged[-1]
                    if start <= prev[1]:
                        prev[1] = max(prev[1], end)
                    else:
                        merged.append([start, end])

            total_months = sum(end - start for start, end in merged)
            if total_months > 0:
                return round(total_months / 12.0, 1)

        # If zero experience pattern was found and no positive intervals
        if has_zero_experience:
            return 0.0

        # Fallback default is 0.0 (NOT 1.0)
        return 0.0

    @classmethod
    def _extract_date_intervals(cls, text: str) -> List[Tuple[int, int]]:
        """
        Extracts start and end month coordinate pairs (start_coord, end_coord)
        from date intervals in the text.
        Coord = year * 12 + month.
        """
        today = datetime.date.today()
        current_year = today.year
        current_month = today.month
        current_coord = current_year * 12 + current_month

        months_map = {
            "янв": 1, "январь": 1, "января": 1, "jan": 1, "january": 1,
            "фев": 2, "февраль": 2, "февраля": 2, "feb": 2, "february": 2,
            "мар": 3, "март": 3, "марта": 3, "mar": 3, "march": 3,
            "апр": 4, "апрель": 4, "апреля": 4, "apr": 4, "april": 4,
            "май": 5, "мая": 5, "may": 5,
            "июн": 6, "июнь": 6, "июня": 6, "jun": 6, "june": 6,
            "июл": 7, "июль": 7, "июля": 7, "jul": 7, "july": 7,
            "авг": 8, "август": 8, "августа": 8, "aug": 8, "august": 8,
            "сен": 9, "сент": 9, "сентябрь": 9, "сентября": 9, "sep": 9, "sept": 9, "september": 9,
            "окт": 10, "октябрь": 10, "октября": 10, "oct": 10, "october": 10,
            "ноя": 11, "ноябрь": 11, "ноября": 11, "nov": 11, "november": 11,
            "дек": 12, "декабрь": 12, "декабря": 12, "dec": 12, "december": 12,
        }
        month_names_re = "|".join(re.escape(k) for k in sorted(months_map.keys(), key=len, reverse=True))

        present_re = r"(?:по\s+)?(?:настоящее\s+время|наст\.?\s*время|н\.?\s*в\.?|сегодня|present|current|now)"
        intervals: List[Tuple[int, int]] = []

        # 1. Month YYYY — Month YYYY
        p1 = rf"({month_names_re})\s+(\d{{4}})\s*(?:—|–|-|по|to)\s*({month_names_re})\s+(\d{{4}})"
        for m in re.finditer(p1, text):
            m1_name, y1_str, m2_name, y2_str = m.group(1), m.group(2), m.group(3), m.group(4)
            c1 = int(y1_str) * 12 + months_map[m1_name]
            c2 = int(y2_str) * 12 + months_map[m2_name] + 1
            intervals.append((c1, c2))

        # 2. Month YYYY — Present
        p2 = rf"({month_names_re})\s+(\d{{4}})\s*(?:—|–|-|по|to)\s*{present_re}"
        for m in re.finditer(p2, text):
            m1_name, y1_str = m.group(1), m.group(2)
            c1 = int(y1_str) * 12 + months_map[m1_name]
            intervals.append((c1, current_coord + 1))

        # 3. MM.YYYY — MM.YYYY
        p3 = r"\b(0?[1-9]|1[0-2])[./](\d{4})\s*(?:—|–|-|по|to)\s*(0?[1-9]|1[0-2])[./](\d{4})\b"
        for m in re.finditer(p3, text):
            m1, y1, m2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            intervals.append((y1 * 12 + m1, y2 * 12 + m2 + 1))

        # 4. MM.YYYY — Present
        p4 = rf"\b(0?[1-9]|1[0-2])[./](\d{{4}})\s*(?:—|–|-|по|to)\s*{present_re}\b"
        for m in re.finditer(p4, text):
            m1, y1 = int(m.group(1)), int(m.group(2))
            intervals.append((y1 * 12 + m1, current_coord + 1))

        # 5. YYYY — YYYY (Year only, e.g. "2021 — 2024")
        p5 = r"\b(19\d\d|20\d\d)\s*(?:—|–|-|по|to)\s*(19\d\d|20\d\d)\b"
        for m in re.finditer(p5, text):
            y1, y2 = int(m.group(1)), int(m.group(2))
            # avoid duplicate matches if already captured as part of MM.YYYY
            start_pos = m.start()
            if start_pos > 0 and text[start_pos - 1] in "./":
                continue
            intervals.append((y1 * 12, y2 * 12))

        # 6. YYYY — Present
        p6 = rf"\b(19\d\d|20\d\d)\s*(?:—|–|-|по|to)\s*{present_re}\b"
        for m in re.finditer(p6, text):
            y1 = int(m.group(1))
            start_pos = m.start()
            if start_pos > 0 and text[start_pos - 1] in "./":
                continue
            intervals.append((y1 * 12, current_coord))

        return intervals

    @classmethod
    def extract_target_role(cls, text: str, detected_skills: List[str]) -> str:
        """Extract or infer target job title across all professions."""
        lowered = text.lower()
        role_patterns = [
            # IT & Software (High priority)
            (r"(python\s+(?:developer|разработчик|backend|программист))", "Python Backend Developer"),
            (r"(backend\s+(?:developer|разработчик|инженер))", "Backend Developer"),
            (r"(frontend\s+(?:developer|разработчик))", "Frontend Developer"),
            (r"(fullstack\s+(?:developer|разработчик)|фуллстек)", "Fullstack Developer"),
            (r"(devops(?:\s+engineer|\s+инженер)?)", "DevOps Engineer"),
            (r"(data\s+scientist|дата\s+саентист|ml\s+engineer)", "Data Scientist / ML Engineer"),
            (r"(qa(?:\s+engineer|\s+автоматизатор|\s+тестировщик)?|тестировщик)", "QA Engineer"),
            (r"(go\s+developer|golang\s+разработчик)", "Go Developer"),
            (r"(java\s+developer|java\s+разработчик)", "Java Developer"),
            (r"(android\s+developer|ios\s+developer|мобильный\s+разработчик)", "Mobile Developer"),

            # Sales & Commerce
            (r"(руководитель\s+отдела\s+продаж)", "Руководитель отдела продаж"),
            (r"(менеджер\s+по\s+продажам|b2b\s+продажи|менеджер\s+по\s+работе\s+с\s+клиентами|аккаунт-менеджер)", "Менеджер по продажам"),
            (r"(торговый\s+представитель|продавец-консультант|продавец)", "Менеджер по продажам"),

            # Finance & Accounting
            (r"(главный\s+бухгалтер)", "Главный бухгалтер"),
            (r"(бухгалтер|бухгалтерия)", "Бухгалтер"),
            (r"(финансовый\s+аналитик|экономист|финансист)", "Финансовый аналитик"),
            (r"(аудитор)", "Аудитор"),

            # Marketing & Media
            (r"(интернет-маркетолог|диджитал-маркетолог)", "Интернет-маркетолог"),
            (r"(таргетолог|smm-специалист|smm-менеджер|smm)", "SMM-специалист"),
            (r"(seo-специалист|seo)", "SEO-специалист"),
            (r"(копирайтер|контент-менеджер)", "Копирайтер"),
            (r"(маркетолог|специалист\s+по\s+маркетингу)", "Маркетолог"),

            # Design & Creative
            (r"(ui/ux\s+дизайнер|веб-дизайнер|web-дизайнер)", "UI/UX Дизайнер"),
            (r"(графический\s+дизайнер|моушн-дизайнер|моушн\s+дизайнер)", "Графический дизайнер"),
            (r"(дизайнер)", "Дизайнер"),

            # HR & Recruitment
            (r"(hr-менеджер|рекрутер|менеджер\s+по\s+персоналу|специалист\s+по\s+кадрам)", "HR-менеджер"),

            # Legal
            (r"(юрист|юрисконсульт|адвокат)", "Юрист"),

            # Management & Operations
            (r"(project\s+manager|руководитель\s+проектов|менеджер\s+проектов)", "Project Manager"),
            (r"(product\s+manager|продакт-менеджер|менеджер\s+продукта)", "Product Manager"),
            (r"(бизнес-аналитик)", "Бизнес-аналитик"),

            # Logistics & Supply
            (r"(менеджер\s+по\s+логистике|логист)", "Менеджер по логистике"),
            (r"(водитель-экспедитор|водитель)", "Водитель-экспедитор"),
            (r"(кладовщик)", "Кладовщик"),

            # Engineering & Production
            (r"(инженер-конструктор|инженер-проектировщик|инженер)", "Инженер"),

            # Service & Hospitality
            (r"(повар|шеф-повар)", "Повар"),
            (r"(администратор)", "Администратор"),

            # Education
            (r"(преподаватель|учитель|репетитор)", "Преподаватель"),
            (r"(переводчик)", "Переводчик")
        ]

        for pattern, role in role_patterns:
            if re.search(pattern, lowered):
                return role

        # Explicit role heading in text (e.g. "Должность: Графический дизайнер")
        role_label_match = re.search(r"(?:желаемая\s+)?(?:должность|позиция|специальность)[:\s]+([^\n\r,]+)", text, re.IGNORECASE)
        if role_label_match:
            candidate = role_label_match.group(1).strip()
            if 3 <= len(candidate) <= 50:
                return candidate.title()

        # Infer from detected skills
        if "Python" in detected_skills:
            return "Python Developer"
        elif "React" in detected_skills or "Vue.js" in detected_skills:
            return "Frontend Developer"
        elif "Go" in detected_skills:
            return "Go Developer"
        elif "Java" in detected_skills:
            return "Java Developer"
        elif "Docker" in detected_skills and "Kubernetes" in detected_skills:
            return "DevOps Engineer"
        elif any(s in detected_skills for s in ["1С:Бухгалтерия", "Бухгалтерский учет", "Первичная документация"]):
            return "Бухгалтер"
        elif any(s in detected_skills for s in ["Figma", "UI/UX", "Adobe Photoshop"]):
            return "Дизайнер"
        elif any(s in detected_skills for s in ["SMM", "SEO", "Яндекс.Директ", "Таргетированная реклама"]):
            return "Маркетолог"
        elif any(s in detected_skills for s in ["B2B продажи", "amoCRM", "Битрикс24", "Холодные звонки"]):
            return "Менеджер по продажам"
        elif any(s in detected_skills for s in ["Рекрутинг", "Подбор персонала", "Кадровое делопроизводство"]):
            return "HR-менеджер"
        elif any(s in detected_skills for s in ["Договорное право", "Претензионная работа"]):
            return "Юрист"

        # Check the first non-empty lines for role title
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        for line in lines[:3]:
            if 3 <= len(line) <= 40 and not any(kw in line.lower() for kw in ["@", "+7", "тел", "резюме", "обо мне", "опыт"]):
                if not re.search(r"\d", line):
                    return line.title()

        return "Специалист"

    @classmethod
    def extract_salary_expectation(cls, text: str) -> Optional[int]:
        """Extract expected salary if mentioned."""
        patterns = [
            r"(?:желаемая\s+)?з(?:арплата)?(?:\s+от|\s*:|\s*=\s*)?\s*(\d[\d\s]{2,8})\s*(?:руб|рубл|₽|rub)",
            r"(?:от|около)\s*(\d[\d\s]{2,8})\s*(?:руб|рубл|₽|rub)",
            r"(\d[\d\s]{2,8})\s*(?:руб|рубл|₽|rub)"
        ]
        for p in patterns:
            match = re.search(p, text.lower())
            if match:
                clean_num = re.sub(r"\s+", "", match.group(1))
                try:
                    val = int(clean_num)
                    if 15000 <= val <= 2000000:
                        return val
                except ValueError:
                    pass
        return None

    @classmethod
    def parse_full_resume(cls, text: str) -> Dict[str, Any]:
        """Analyze full resume text and return structured profile dictionary."""
        skills = cls.extract_skills(text)
        exp_years = cls.extract_experience_years(text)
        grade = cls.detect_grade(text, exp_years)
        title = cls.extract_target_role(text, skills)
        salary = cls.extract_salary_expectation(text)

        return {
            "title": title,
            "grade": grade,
            "years_of_experience": exp_years,
            "skills": skills,
            "salary_expectation": salary,
            "raw_text": text
        }
