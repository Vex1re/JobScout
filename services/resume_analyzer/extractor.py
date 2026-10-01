import io
import re
from typing import List, Dict, Any, Optional, Set
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
    "postman": "Postman"
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
        """Extract normalized technical skills found in text."""
        lowered = f" {text.lower()} "
        found_skills: Set[str] = set()

        for key, canonical in TECH_SKILLS_MAP.items():
            # Match whole words or boundary patterns
            pattern = r"(?<![a-zA-Z0-9_#+])" + re.escape(key) + r"(?![a-zA-Z0-9_#+])"
            if re.search(pattern, lowered):
                found_skills.add(canonical)

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
        """Extract years of experience from resume text."""
        lowered = text.lower()

        # Look for explicit patterns like "опыт работы: 3 года", "опыт: 5 лет", "4 года опыта", "6+ years"
        patterns = [
            r"опыт(?:а)?(?:\s+работы)?[:\s\-]+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            r"(\d+(?:[.,]\d+)?)\s*\+?\s*(?:лет|год|года|г\.|years|year|yrs)\s+(?:опыта|коммерческого опыта)",
            r"(?:более|от)\s+(\d+)\s*(?:лет|года)",
            r"(\d+)\s*(?:\+)?\s*(?:лет|года)\s+в\s+(?:разработке|it)"
        ]

        for p in patterns:
            match = re.search(p, lowered)
            if match:
                val = match.group(1).replace(",", ".")
                try:
                    return float(val)
                except ValueError:
                    pass

        # Check for months: "18 месяцев"
        month_match = re.search(r"(\d+)\s*(?:месяцев|месяца|мес\.|months)", lowered)
        if month_match:
            try:
                months = int(month_match.group(1))
                return round(months / 12.0, 1)
            except ValueError:
                pass

        return 1.0 # Default conservative fallback

    @classmethod
    def extract_target_role(cls, text: str, detected_skills: List[str]) -> str:
        """Extract or infer target job title."""
        lowered = text.lower()
        role_patterns = [
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
        ]

        for pattern, role in role_patterns:
            if re.search(pattern, lowered):
                return role

        # Infer from skills
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

        return "Software Developer"

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
