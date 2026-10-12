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
    "java core": "Java",
    "core java": "Java",
    "spring": "Spring Boot",
    "spring boot": "Spring Boot",
    "springboot": "Spring Boot",
    "spring data": "Spring Data JPA",
    "spring data jpa": "Spring Data JPA",
    "spring security": "Spring Security",
    "spring mvc": "Spring MVC",
    "hibernate": "Hibernate",
    "jpa": "JPA",
    "maven": "Maven",
    "gradle": "Gradle",
    "javafx": "JavaFX",
    "jdbc": "JDBC",
    "jvm": "JVM",
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
    "vite": "Vite",
    "webpack": "Webpack",
    "html": "HTML5",
    "css": "CSS3",
    "sass": "SASS/SCSS",
    "scss": "SASS/SCSS",

    # Databases & Caches
    "sql": "SQL",
    "sql-transactions": "SQL",
    "sql transactions": "SQL",
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
    "railway": "Railway",

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
    "solid": "SOLID",
    "ооп": "ООП",
    "oop": "ООП",
    "acid": "ACID",
    "mvc": "MVC",
    "dao": "DAO",
    "telegram api": "Telegram API",
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

    SKILLS_BLACKLIST: Set[str] = {
        "ai skills", "ai skill", "ии-агенты", "ии агенты", "ai agents",
        "soft skills", "hard skills", "коммуникабельность", "ответственность",
        "пунктуальность", "стрессоустойчивость", "быстрая обучаемость",
    }

    @classmethod
    def _normalize_token(cls, token: str) -> Optional[str]:
        """Strip leading/trailing punctuation, brackets, and quotes from skill token."""
        cleaned = re.sub(
            r"^[\s\(\[\{\.\,\:\;\-\–\—\"\'\«\»\)]+|[\s\(\[\{\.\,\:\;\-\–\—\"\'\«\»\)]+$",
            "",
            token,
        ).strip()
        if not cleaned or len(cleaned) < 2 or len(cleaned) > 30:
            return None
        return cleaned

    @classmethod
    def _is_garbage_token(cls, low: str) -> bool:
        """Check if token is noise, date, narrative sentence, or irrelevant data."""
        if low in cls.SKILLS_BLACKLIST:
            return True

        # URL / email / domain / repo / package identifiers
        if any(ext in low for ext in [".ru", ".com", ".org", ".net", ".io", ".tech", "@", "http://", "https://", "t.tech"]):
            return True

        # Years (19xx, 20xx) or duration patterns (e.g. 1 месяц, 5 лет)
        if re.search(r"\b(19\d\d|20\d\d)\b", low) or re.search(r"\b(месяц|месяца|месяцев|год|года|лет|month|months|year|years)\b", low):
            return True

        # Month names
        if re.search(r"\b(январ|феврал|март|апрел|ма[ей]|июн|июл|август|сентябр|октябр|ноябр|декабр|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\b", low):
            return True

        # Educational / bio / student indicators
        if re.search(r"\b(студент|курс|курса|курсе|школа|лицей|университет|факультет|бакалавриат|магистратура)\b", low):
            return True

        # Prose verbs / narratives
        if re.search(r"\b(работы|работа|опыт|умею|знаю|владею|понимаю|разработка|разработал|реализовал|проектирование|навыки|компетенции|обо мне|о себе|специализируюсь|направлени)\b", low):
            return True

        # Spoken languages and CEFR levels (e.g. Английский язык: A2)
        if re.search(r"\b(английский|русский|немецкий|французский|китайский|испанский)\s*(?:язык)?\b", low):
            return True
        if re.search(r"\b(a1|a2|b1|b2|c1|c2|native|fluent|intermediate|beginner|advanced)\b", low):
            return True

        return False

    @classmethod
    def _format_custom_skill(cls, cleaned: str) -> str:
        """Format skill that is not present in TECH_SKILLS_MAP."""
        if cleaned.isupper() and len(cleaned) <= 6:
            return cleaned
        if any(c.isupper() for c in cleaned[1:]):
            return cleaned
        return cleaned.title()

    @classmethod
    def extract_skills(cls, text: str) -> List[str]:
        """Extract normalized technical and professional skills found in text."""
        lowered = f" {text.lower()} "
        deduped_skills: Dict[str, str] = {}

        # 1. Match canonical skills from TECH_SKILLS_MAP across the full text
        for key, canonical in TECH_SKILLS_MAP.items():
            pattern = r"(?<![a-zA-Z0-9_#+а-яА-ЯёЁ])" + re.escape(key) + r"(?![a-zA-Z0-9_#+а-яА-ЯёЁ])"
            if re.search(pattern, lowered):
                deduped_skills[canonical.lower()] = canonical

        # 2. Dynamic extraction from explicit skills section if present
        header_pattern = r"(?:ключевые\s+навыки|профессиональные\s+навыки|технические\s+навыки|технологический\s+стек|стек\s+технологий|компетенции|навыки|стек|skills|tech\s+stack)[:\s]*"
        match = re.search(header_pattern, text, re.IGNORECASE)
        if match:
            start_pos = match.end()
            lines = text[start_pos:].split("\n")
            section_lines: List[str] = []
            if lines and lines[0].strip():
                section_lines.append(lines[0].strip())

            stop_section_re = re.compile(
                r"^(?:опыт|образование|обо\s+мне|о\s+себе|контакты|проекты|курсы|сертификаты|языки|дополнительно|"
                r"activities|experience|education|about|contacts|"
                r"telegram|github|email|телефон|местоположение|город|"
                r"я\s+|студент\b|специализируюсь\b|ищу\b|разрабатываю\b|"
                r"\d{4}\b|январ|феврал|март|апрел|ма[ей]|июн|июл|август|сентябр|октябр|ноябр|декабр)",
                re.IGNORECASE,
            )
            narrative_words_re = re.compile(
                r"\b(разработал|создал|реализовал|умею|владею|занимался|занимаюсь|специализируюсь|студент|курса|курсе)\b",
                re.IGNORECASE,
            )

            for raw_line in lines[1:]:
                line = raw_line.strip()
                if not line:
                    if section_lines:
                        break
                    continue

                if stop_section_re.search(line):
                    break

                is_bulleted = line.startswith(("•", "-", "*", "+"))
                if not is_bulleted:
                    if narrative_words_re.search(line) or (len(line.split()) > 8 and "." in line and "," not in line):
                        break

                section_lines.append(line)

            for sec_line in section_lines:
                raw_tokens = re.split(r"[,;•\n\*\t|]+", sec_line)
                for tok in raw_tokens:
                    cleaned = cls._normalize_token(tok)
                    if not cleaned or len(cleaned.split()) > 3:
                        continue
                    low = cleaned.lower()

                    if cls._is_garbage_token(low):
                        continue

                    if low in TECH_SKILLS_MAP:
                        canonical = TECH_SKILLS_MAP[low]
                    else:
                        canonical = cls._format_custom_skill(cleaned)

                    deduped_skills[canonical.lower()] = canonical

        # Sort alphabetically for consistent representation
        return sorted(list(deduped_skills.values()))

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

    IRRELEVANT_ROLES = [
        "\u0431\u0430\u0440\u0438\u0441\u0442\u0430",
        "\u043e\u0444\u0438\u0446\u0438\u0430\u043d\u0442",
        "\u043e\u0444\u0438\u0446\u0438\u0430\u043d\u0442\u043a\u0430",
        "\u043a\u0443\u0440\u044c\u0435\u0440",
        "\u0432\u043e\u0434\u0438\u0442\u0435\u043b\u044c",
        "\u0433\u0440\u0443\u0437\u0447\u0438\u043a",
        "\u043c\u043e\u0439\u0449\u0438\u043a",
        "\u0443\u0431\u043e\u0440\u0449\u0438\u043a",
        "\u0443\u0431\u043e\u0440\u0449\u0438\u0446\u0430",
        "\u0441\u0442\u043e\u0440\u043e\u0436",
        "\u043e\u0445\u0440\u0430\u043d\u043d\u0438\u043a",
        "\u043f\u0440\u043e\u043c\u043e\u0443\u0442\u0435\u0440",
        "\u0440\u0430\u0437\u043d\u043e\u0440\u0430\u0431\u043e\u0447\u0438\u0439",
        "\u0431\u0430\u0440\u043c\u0435\u043d",
        "\u043a\u0430\u0441\u0441\u0438\u0440",
        "\u0444\u0430\u0441\u043e\u0432\u0449\u0438\u043a",
        "\u043c\u0435\u0440\u0447\u0435\u043d\u0434\u0430\u0439\u0437\u0435\u0440",
        "\u0433\u0430\u0440\u0434\u0435\u0440\u043e\u0431\u0449\u0438\u043a",
    ]

    @staticmethod
    def _merge_intervals(intervals: List[Tuple[int, int]]) -> float:
        """Merges overlapping/nested intervals and returns total years."""
        if not intervals:
            return 0.0
        sorted_intervals = sorted(intervals, key=lambda x: x[0])
        merged = []
        for start, end in sorted_intervals:
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
        return round(total_months / 12.0, 1)

    @classmethod
    def _extract_date_intervals_with_context(cls, text: str) -> List[Tuple[int, int, str]]:
        today = datetime.date.today()
        current_year = today.year
        current_month = today.month
        current_coord = current_year * 12 + current_month

        months_map = {
            "\u044f\u043d\u0432": 1, "\u044f\u043d\u0432\u0430\u0440\u044c": 1, "\u044f\u043d\u0432\u0430\u0440\u044f": 1, "jan": 1, "january": 1,
            "\u0444\u0435\u0432": 2, "\u0444\u0435\u0432\u0440\u0430\u043b\u044c": 2, "\u0444\u0435\u0432\u0440\u0430\u043b\u044f": 2, "feb": 2, "february": 2,
            "\u043c\u0430\u0440": 3, "\u043c\u0430\u0440\u0442": 3, "\u043c\u0430\u0440\u0442\u0430": 3, "mar": 3, "march": 3,
            "\u0430\u043f\u0440": 4, "\u0430\u043f\u0440\u0435\u043b\u044c": 4, "\u0430\u043f\u0440\u0435\u043b\u044f": 4, "apr": 4, "april": 4,
            "\u043c\u0430\u0439": 5, "\u043c\u0430\u044f": 5, "may": 5,
            "\u0438\u044e\u043d": 6, "\u0438\u044e\u043d\u044c": 6, "\u0438\u044e\u043d\u044f": 6, "jun": 6, "june": 6,
            "\u0438\u044e\u043b": 7, "\u0438\u044e\u043b\u044c": 7, "\u0438\u044e\u043b\u044f": 7, "jul": 7, "july": 7,
            "\u0430\u0432\u0433": 8, "\u0430\u0432\u0433\u0443\u0441\u0442": 8, "\u0430\u0432\u0433\u0443\u0441\u0442\u0430": 8, "aug": 8, "august": 8,
            "\u0441\u0435\u043d": 9, "\u0441\u0435\u043d\u0442": 9, "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044c": 9, "\u0441\u0435\u043d\u0442\u044f\u0431\u0440\u044f": 9, "sep": 9, "sept": 9, "september": 9,
            "\u043e\u043a\u0442": 10, "\u043e\u043a\u0442\u044f\u0431\u0440\u044c": 10, "\u043e\u043a\u0442\u044f\u0431\u0440\u044f": 10, "oct": 10, "october": 10,
            "\u043d\u043e\u044f": 11, "\u043d\u043e\u044f\u0431\u0440\u044c": 11, "\u043d\u043e\u044f\u0431\u0440\u044f": 11, "nov": 11, "november": 11,
            "\u0434\u0435\u043a": 12, "\u0434\u0435\u043a\u0430\u0431\u0440\u044c": 12, "\u0434\u0435\u043a\u0430\u0431\u0440\u044f": 12, "dec": 12, "december": 12,
        }
        month_names_re = "|".join(re.escape(k) for k in sorted(months_map.keys(), key=len, reverse=True))
        present_re = r"(?:\u043f\u043e\s+)?(?:\u043d\u0430\u0441\u0442\u043e\u044f\u0449\u0435\u0435\s+\u0432\u0440\u0435\u043c\u044f|\u043d\u0430\u0441\u0442\.?\s*\u0432\u0440\u0435\u043c\u044f|\u043d\.?\s*\u0432\.?|\u043f\u043e\s+\u0441\u0435\u0439\s+\u0434\u0435\u043d\u044c|\u0441\u0435\u0433\u043e\u0434\u043d\u044f|\u0441\u0435\u0439\s+\u0434\u0435\u043d\u044c|present|current|now)"
        sep_re = r"(?:\u2014|\u2013|-|\u043f\u043e|to|\u0434\u043e)"

        raw_matches: List[Tuple[int, int, int, int]] = []

        # 1. Month YYYY — Month YYYY
        p1 = rf"({month_names_re})\s+(\d{{4}})\s*{sep_re}\s*({month_names_re})\s+(\d{{4}})"
        for m in re.finditer(p1, text):
            c1 = int(m.group(2)) * 12 + months_map[m.group(1)]
            c2 = int(m.group(4)) * 12 + months_map[m.group(3)] + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 2. Month YYYY — YYYY
        p2 = rf"({month_names_re})\s+(\d{{4}})\s*{sep_re}\s*(19\d\d|20\d\d)(?!\d|\.[0-9]|/[0-9])"
        for m in re.finditer(p2, text):
            c1 = int(m.group(2)) * 12 + months_map[m.group(1)]
            c2 = int(m.group(3)) * 12 + 12
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 3. YYYY — Month YYYY
        p3 = rf"\b(19\d\d|20\d\d)\s*{sep_re}\s*({month_names_re})\s+(\d{{4}})"
        for m in re.finditer(p3, text):
            c1 = int(m.group(1)) * 12 + 1
            c2 = int(m.group(3)) * 12 + months_map[m.group(2)] + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 4. Month YYYY — Present
        p4 = rf"({month_names_re})\s+(\d{{4}})\s*{sep_re}\s*{present_re}(?!\w)"
        for m in re.finditer(p4, text):
            c1 = int(m.group(2)) * 12 + months_map[m.group(1)]
            c2 = current_coord + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 5. MM.YYYY — MM.YYYY
        p5 = rf"\b(0?[1-9]|1[0-2])[./](\d{{4}})\s*{sep_re}\s*(0?[1-9]|1[0-2])[./](\d{{4}})\b"
        for m in re.finditer(p5, text):
            c1 = int(m.group(2)) * 12 + int(m.group(1))
            c2 = int(m.group(4)) * 12 + int(m.group(3)) + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 6. MM.YYYY — YYYY
        p6 = rf"\b(0?[1-9]|1[0-2])[./](\d{{4}})\s*{sep_re}\s*(19\d\d|20\d\d)(?!\d|\.[0-9]|/[0-9])"
        for m in re.finditer(p6, text):
            c1 = int(m.group(2)) * 12 + int(m.group(1))
            c2 = int(m.group(3)) * 12 + 12
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 7. YYYY — MM.YYYY
        p7 = rf"\b(19\d\d|20\d\d)\s*{sep_re}\s*(0?[1-9]|1[0-2])[./](\d{{4}})\b"
        for m in re.finditer(p7, text):
            c1 = int(m.group(1)) * 12 + 1
            c2 = int(m.group(3)) * 12 + int(m.group(2)) + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 8. MM.YYYY — Present
        p8 = rf"\b(0?[1-9]|1[0-2])[./](\d{{4}})\s*{sep_re}\s*{present_re}(?!\w)"
        for m in re.finditer(p8, text):
            c1 = int(m.group(2)) * 12 + int(m.group(1))
            c2 = current_coord + 1
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 9. YYYY — YYYY
        p9 = rf"\b(19\d\d|20\d\d)\s*{sep_re}\s*(19\d\d|20\d\d)\b"
        for m in re.finditer(p9, text):
            c1 = int(m.group(1)) * 12
            c2 = int(m.group(2)) * 12
            raw_matches.append((m.start(), m.end(), c1, c2))

        # 10. YYYY — Present
        p10 = rf"\b(19\d\d|20\d\d)\s*{sep_re}\s*{present_re}(?!\w)"
        for m in re.finditer(p10, text):
            c1 = int(m.group(1)) * 12
            c2 = current_coord
            raw_matches.append((m.start(), m.end(), c1, c2))

        accepted_spans: List[Tuple[int, int]] = []
        results: List[Tuple[int, int, str]] = []

        for s_start, s_end, c1, c2 in raw_matches:
            if any(s_start < end and s_end > start for start, end in accepted_spans):
                continue
            accepted_spans.append((s_start, s_end))
            line_start = text.rfind("\n", 0, s_start)
            line_start = 0 if line_start == -1 else line_start + 1
            line_end = text.find("\n", s_end)
            line_end = len(text) if line_end == -1 else line_end
            context = text[line_start:line_end]
            results.append((c1, c2, context))

        return results

    @classmethod
    def _extract_date_intervals(cls, text: str) -> List[Tuple[int, int]]:
        return [(c1, c2) for c1, c2, _ in cls._extract_date_intervals_with_context(text)]

    @classmethod
    def extract_total_and_relevant_experience(cls, text: str) -> Tuple[float, float]:
        lowered = text.lower()

        # 1. Zero experience detection
        zero_patterns = [
            r"\b\u0431\u0435\u0437\s+\u043e\u043f\u044b\u0442\u0430\b",
            r"\b\u043d\u0435\u0442\s+\u043e\u043f\u044b\u0442\u0430\b",
            r"\b\u043e\u043f\u044b\u0442(?:\u0430)?(?:\s+\u0440\u0430\u0431\u043e\u0442\u044b)?[:\s\-]+0(?:\.0)?\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434|\u0433\u043e\u0434\u0430|\u0433\.|\u043c\u0435\u0441)",
            r"\b0\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434\u0430|\u043c\u0435\u0441\u044f\u0446\u0435\u0432)\s+(?:\u043e\u043f\u044b\u0442\u0430|\u043a\u043e\u043c\u043c\u0435\u0440\u0447\u0435\u0441\u043a\u043e\u0433\u043e)",
            r"\b\u0438\u0449\u0443\s+\u0441\u0442\u0430\u0436\u0438\u0440\u043e\u0432\u043a\u0443\b",
            r"\b(\u0441\u0442\u0430\u0436\u0435\u0440|intern|trainee)\b",
            r"\b\u043d\u0430\u0447\u0438\u043d\u0430\u044e\u0449\u0438\u0439\s+(?:\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u0447\u0438\u043a|\u0441\u043f\u0435\u0446\u0438\u0430\u043b\u0438\u0441\u0442|\u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0438\u0441\u0442)\b",
            r"\bjunior\s+\u0431\u0435\u0437\s+\u043e\u043f\u044b\u0442\u0430\b"
        ]
        if any(re.search(p, lowered) for p in zero_patterns):
            return (0.0, 0.0)

        # 2. Date intervals with context
        intervals_with_ctx = cls._extract_date_intervals_with_context(lowered)
        if intervals_with_ctx:
            total_intervals = [(c1, c2) for c1, c2, _ in intervals_with_ctx]
            total_exp = cls._merge_intervals(total_intervals)

            detected_skills = cls.extract_skills(text)
            target_role = cls.extract_target_role(text, detected_skills).lower()
            is_service_target = any(r in target_role for r in cls.IRRELEVANT_ROLES)

            if is_service_target:
                return (total_exp, total_exp)

            relevant_intervals = []
            for c1, c2, ctx in intervals_with_ctx:
                is_irrelevant_job = any(
                    re.search(rf"\b{re.escape(r)}\b", ctx)
                    for r in cls.IRRELEVANT_ROLES
                )
                if not is_irrelevant_job:
                    relevant_intervals.append((c1, c2))

            relevant_exp = cls._merge_intervals(relevant_intervals)
            return (total_exp, relevant_exp)

        # 3. Compound periods
        compound_patterns = [
            r"(\d+)\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434|\u0433\u043e\u0434\u0430|\u0433\.|years|year|yrs)\s*(?:\u0438\s*)?(\d+)\s*(?:\u043c\u0435\u0441\u044f\u0446\u0435\u0432|\u043c\u0435\u0441\u044f\u0446\u0430|\u043c\u0435\u0441\.|months|month)",
            r"(\d+)\s*(?:\u043c\u0435\u0441\u044f\u0446\u0435\u0432|\u043c\u0435\u0441\u044f\u0446\u0430|\u043c\u0435\u0441\.|months|month)\s*(?:\u0438\s*)?(\d+)\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434|\u0433\u043e\u0434\u0430|\u0433\.|years|year|yrs)"
        ]
        for p in compound_patterns:
            c_match = re.search(p, lowered)
            if c_match:
                if "\u043c\u0435\u0441" in p.split("(")[1] or "month" in p.split("(")[1]:
                    months, years = int(c_match.group(1)), int(c_match.group(2))
                else:
                    years, months = int(c_match.group(1)), int(c_match.group(2))
                val = round(years + (months / 12.0), 1)
                return (val, val)

        # 4. Explicit patterns
        explicit_patterns = [
            r"\u043e\u043f\u044b\u0442(?:\u0430)?(?:\s+\u0440\u0430\u0431\u043e\u0442\u044b)?[:\s\-]+(\d+(?:[.,]\d+)?)\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434|\u0433\u043e\u0434\u0430|\u0433\.|years|year|yrs)",
            r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434|\u0433\u043e\u0434\u0430|\u0433\.|years|year|yrs)\s+(?:\u043e\u043f\u044b\u0442\u0430|\u043a\u043e\u043c\u043c\u0435\u0440\u0447\u0435\u0441\u043a\u043e\u0433\u043e \u043e\u043f\u044b\u0442\u0430)",
            r"(?:\u0431\u043e\u043b\u0435\u0435|\u043e\u0442)\s+(\d+(?:[.,]\d+)?)\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434\u0430)",
            r"(\d+(?:[.,]\d+)?)\s*(?:\+)?\s*(?:\u043b\u0435\u0442|\u0433\u043e\u0434\u0430)\s+\u0432\s+(?:\u0440\u0430\u0437\u0440\u0430\u0431\u043e\u0442\u043a\u0435|it)"
        ]
        for p in explicit_patterns:
            match = re.search(p, lowered)
            if match:
                val = float(match.group(1).replace(",", "."))
                return (val, val)

        month_match = re.search(r"(\d+)\s*(?:\u043c\u0435\u0441\u044f\u0446\u0435\u0432|\u043c\u0435\u0441\u044f\u0446\u0430|\u043c\u0435\u0441\.|months)", lowered)
        if month_match:
            try:
                months = int(month_match.group(1))
                val = round(months / 12.0, 1)
                return (val, val)
            except ValueError:
                pass

        return (0.0, 0.0)

    @classmethod
    def extract_experience_years(cls, text: str) -> float:
        total_exp, relevant_exp = cls.extract_total_and_relevant_experience(text)
        return relevant_exp

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
        total_exp, exp_years = cls.extract_total_and_relevant_experience(text)
        grade = cls.detect_grade(text, exp_years)
        title = cls.extract_target_role(text, skills)
        salary = cls.extract_salary_expectation(text)

        return {
            "title": title,
            "grade": grade,
            "years_of_experience": exp_years,
            "total_years_of_experience": total_exp,
            "skills": skills,
            "salary_expectation": salary,
            "raw_text": text
        }
