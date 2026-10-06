import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class ValidationResult:
    is_valid: bool
    error_message: Optional[str] = None
    score: int = 0
    missing_sections: List[str] = field(default_factory=list)
    detected_type: str = "resume"
    confidence: str = "high"  # "high", "medium", "low"

    def __bool__(self) -> bool:
        return self.is_valid


class ResumeValidator:
    """
    Validates uploaded resumes:
    - Detects junk / non-resume texts (culinary recipes, legal contracts, fiction, random gibberish)
    - Scores structural completeness across key sections: Experience, Skills, Education, Contacts
    - Produces informative, constructive feedback explaining what is missing.
    """

    # Anti-pattern keyword catalogs
    RECIPE_KEYWORDS = [
        "ингредиенты", "граммов", "нарезать", "столовая ложка", "чайная ложка",
        "рецепт", "выпекать", "посолить", "духовка", "тесто", "варить", "жарить",
        "по вкусу", "фарш", "сковорода", "кастрюля", "запекать", "кипятить", "блендер"
    ]

    CONTRACT_KEYWORDS = [
        "договор", "арендатор", "арендодатель", "стороны договорились", "настоящий договор",
        "пункт договора", "ответственность сторон", "реквизиты сторон", "акт приема-передачи",
        "штрафные санкции", "юридический адрес", "предмет договора", "заказчик обязуется",
        "исполнитель обязуется", "настоящего соглашения", "паспортные данные", "банковские реквизиты"
    ]

    FICTION_KEYWORDS = [
        "сказал он", "ответила она", "роман", "повесть", "вдруг он почувствовал",
        "ночь опустилась", "шаги за дверью", "с улыбкой произнес", "тишина наполнила комнату",
        "с легкой грустью", "сердце бешено колотилось", "взглянула в окно"
    ]

    # Section markers
    SECTION_MARKERS = {
        "experience": [
            "опыт", "опыт работы", "коммерческий опыт", "проекты", "пет-проект",
            "разработка", "стажировка", "практика", "работал", "участвовал",
            "обязанности", "достижения", "место работы", "должность", "компания",
            "experience", "work history", "projects"
        ],
        "skills": [
            "навыки", "стек", "технологии", "ключевые навыки", "инструменты",
            "компетенции", "профессиональные навыки", "знания", "умения",
            "hard skills", "skills", "tech stack", "technologies"
        ],
        "education": [
            "образование", "вуз", "университет", "институт", "колледж",
            "курсы", "сертификат", "факультет", "бакалавр", "магистр",
            "education", "courses", "university", "студент"
        ],
        "contacts": [
            "контакты", "телефон", "email", "@", "telegram", "тг", "почта",
            "github", "gitlab", "linkedin", "связаться", "обо мне", "о себе"
        ]
    }

    @classmethod
    def check_anti_patterns(cls, text: str) -> Optional[tuple[str, str]]:
        """
        Scans text for junk patterns: recipes, legal agreements, literature, gibberish.
        Returns (detected_type, error_message) if text is invalid, else None.
        """
        lowered = text.lower()
        words = re.findall(r"\b[a-zA-Zа-яА-ЯёЁ0-9_#+-]+\b", lowered)

        # 1. Text length and gibberish check
        if len(text.strip()) < 40 or len(words) < 6:
            return (
                "gibberish",
                "⚠️ Текст слишком короткий для полноценного резюме. Пожалуйста, укажите ваш опыт, ключевые навыки и желаемую должность."
            )

        # Repetition of characters (e.g. aaaaa, asdfasdf)
        if re.search(r"(\w)\1{7,}", text):
            return (
                "gibberish",
                "⚠️ Обнаружен бессмысленный повторяющийся текст или поврежденный файл."
            )

        # High density of culinary words
        recipe_matches = [kw for kw in cls.RECIPE_KEYWORDS if kw in lowered]
        if len(recipe_matches) >= 3:
            return (
                "recipe",
                "⚠️ Текст похож на кулинарный рецепт, а не резюме специалиста. "
                "Пожалуйста, отправьте документ с описанием профессионального опыта и ключевых навыков."
            )

        # High density of legal contract phrases
        contract_matches = [kw for kw in cls.CONTRACT_KEYWORDS if kw in lowered]
        if len(contract_matches) >= 3:
            return (
                "contract",
                "⚠️ Загруженный документ похож на юридический договор или соглашение, а не резюме. "
                "Пожалуйста, загрузите резюме соискателя."
            )

        # High density of fiction / narrative phrases
        fiction_matches = [kw for kw in cls.FICTION_KEYWORDS if kw in lowered]
        if len(fiction_matches) >= 2:
            return (
                "fiction",
                "⚠️ Текст содержит художественное произведение или рассказ. "
                "Пожалуйста, отправьте ваше профессиональное резюме."
            )

        return None

    @classmethod
    def validate(cls, text: str, tech_skills_count: int = 0) -> ValidationResult:
        """
        Validates resume text and returns ValidationResult.
        """
        # 1. Check for junk / anti-patterns
        anti_pattern = cls.check_anti_patterns(text)
        if anti_pattern:
            det_type, err_msg = anti_pattern
            return ValidationResult(
                is_valid=False,
                error_message=err_msg,
                score=0,
                detected_type=det_type,
                confidence="low"
            )

        lowered = text.lower()

        # 2. Structural scoring
        present_sections: List[str] = []
        missing_sections: List[str] = []

        # Experience check
        has_experience = any(kw in lowered for kw in cls.SECTION_MARKERS["experience"])
        if has_experience:
            present_sections.append("experience")
        else:
            missing_sections.append("Опыт работы / выполненные проекты")

        # Skills check
        has_skills_section = any(kw in lowered for kw in cls.SECTION_MARKERS["skills"])
        has_skills = has_skills_section or tech_skills_count >= 1
        if has_skills:
            present_sections.append("skills")
        else:
            missing_sections.append("Профессиональные навыки и инструменты")

        # Education check
        has_education = any(kw in lowered for kw in cls.SECTION_MARKERS["education"])
        if has_education:
            present_sections.append("education")
        else:
            missing_sections.append("Образование / профильные курсы")

        # Contacts check
        has_contacts = any(kw in lowered for kw in cls.SECTION_MARKERS["contacts"]) or ("@" in text)
        if has_contacts:
            present_sections.append("contacts")
        else:
            missing_sections.append("Контактная информация (Telegram, email, телефон)")

        score = int((len(present_sections) / 4.0) * 100)

        # 3. Decision threshold:
        # A valid resume must have at least professional skills identified OR a skills section,
        # plus at least one other structural block (or total score >= 50).
        if not has_skills and tech_skills_count == 0:
            missing_text = "\n• ".join(missing_sections)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    "⚠️ В резюме не обнаружено ключевых навыков или специализации.\n\n"
                    "Для точного подбора вакансий укажите ваши ключевые навыки и инструменты "
                    "(например: B2B продажи, Переговоры, или Figma, или 1С, или Python, Docker).\n\n"
                    f"<b>Не хватает разделов:</b>\n• {missing_text}"
                ),
                score=score,
                missing_sections=missing_sections,
                detected_type="insufficient",
                confidence="low"
            )

        if len(present_sections) < 2 and tech_skills_count < 2:
            missing_text = "\n• ".join(missing_sections)
            return ValidationResult(
                is_valid=False,
                error_message=(
                    "⚠️ Текст содержит недостаточно структурированной информации для резюме.\n\n"
                    f"<b>Рекомендуем добавить:</b>\n• {missing_text}"
                ),
                score=score,
                missing_sections=missing_sections,
                detected_type="insufficient",
                confidence="low"
            )

        conf = "high" if score >= 75 else "medium"
        return ValidationResult(
            is_valid=True,
            error_message=None,
            score=score,
            missing_sections=missing_sections,
            detected_type="resume",
            confidence=conf
        )
