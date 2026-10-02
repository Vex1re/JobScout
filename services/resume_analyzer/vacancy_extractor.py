import re
from typing import Optional, Tuple


class VacancyExperienceExtractor:
    """
    Extracts required years of experience from vacancy text or API metadata.
    Returns (min_years, max_years).
    """

    HH_API_EXPERIENCE_MAP = {
        "noexperience": (0.0, 0.0),
        "between1and3": (1.0, 3.0),
        "between3and6": (3.0, 6.0),
        "morethan6": (6.0, None),
    }

    @classmethod
    def extract_required_experience(
        cls,
        text: str,
        api_experience_id: Optional[str] = None
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Extracts minimum and maximum required experience in years.
        
        Returns:
            Tuple[Optional[float], Optional[float]]: (min_experience, max_experience)
        """
        if not text:
            text = ""
        lowered = text.lower()

        # 1. Zero experience / internship patterns
        zero_patterns = [
            r"\b(не\s+требуется|без\s+опыта|опыт\s+не\s+требуется|можно\s+без\s+опыта|стажировка|стаж[её]р|internship|no\s+experience)\b",
            r"\bопыт(?:а)?(?:\s+работы)?[:\s\-]+0\s*(?:лет|год|года|г\.|мес)",
            r"\bот\s+0\s*(?:лет|года|г\.)\b"
        ]
        for p in zero_patterns:
            if re.search(p, lowered):
                return 0.0, 0.0

        # 2. Ranges: "от 1 до 3 лет", "1-3 года", "3 - 6 лет", "от 3 до 5 лет"
        range_patterns = [
            # "от 1 до 3 лет", "от 1.5 до 3 лет"
            r"(?:опыт(?:а)?(?:\s+работы)?[:\s\-]+)?от\s+(\d+(?:[.,]\d+)?)\s*(?:до|-|—|–)\s*(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "1-3 года", "3-6 лет", "2 — 4 года"
            r"(?:опыт(?:а)?(?:\s+работы)?[:\s\-]+)?\b(\d+(?:[.,]\d+)?)\s*(?:-|—|–|to)\s*(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "от 1 года до 3 лет"
            r"от\s+(\d+(?:[.,]\d+)?)\s*(?:года|лет|г\.)\s*до\s*(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.)"
        ]
        for p in range_patterns:
            m = re.search(p, lowered)
            if m:
                try:
                    min_val = float(m.group(1).replace(",", "."))
                    max_val = float(m.group(2).replace(",", "."))
                    if min_val <= max_val:
                        return min_val, max_val
                    return max_val, min_val
                except ValueError:
                    pass

        # 3. Minimum experience patterns: "от 4 лет", "более 5 лет", "4+ года", "не менее 3 лет"
        min_patterns = [
            # "от 4 лет", "опыт от 3 лет"
            r"\b(?:опыт(?:а)?(?:\s+работы)?[:\s\-]+)?от\s+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "более 5 лет", "свыше 3 лет"
            r"\b(?:более|свыше)\s+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "не менее 3 лет"
            r"\bне\s+менее\s+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "4+ года", "5+ лет", "3+ years"
            r"\b(\d+(?:[.,]\d+)?)\s*\+\s*(?:лет|год|года|г\.|years|year|yrs)",
            # "опыт работы: 3 года", "коммерческий опыт: 4 года"
            r"(?:коммерческий\s+)?опыт(?:а)?(?:\s+работы)?[:\s\-]+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)"
        ]
        for p in min_patterns:
            m = re.search(p, lowered)
            if m:
                try:
                    min_val = float(m.group(1).replace(",", "."))
                    return min_val, None
                except ValueError:
                    pass

        # Months range: "от 6 месяцев" -> 0.5
        month_min = re.search(r"\bот\s+(\d+)\s*(?:месяцев|месяца|мес\.)", lowered)
        if month_min:
            try:
                months = int(month_min.group(1))
                return round(months / 12.0, 1), None
            except ValueError:
                pass

        # 4. Maximum experience patterns: "до 1 года", "до 3 лет", "менее 2 лет"
        max_patterns = [
            r"\b(?:до|менее)\s+(\d+(?:[.,]\d+)?)\s*(?:лет|год|года|г\.|years|year|yrs)",
            r"\bдо\s+(\d+)\s*(?:месяцев|месяца|мес\.)"
        ]
        for p in max_patterns:
            m = re.search(p, lowered)
            if m:
                try:
                    val = float(m.group(1).replace(",", "."))
                    if "мес" in m.group(0):
                        val = round(val / 12.0, 1)
                    return None, val
                except ValueError:
                    pass

        # 5. Fallback from aggregator API metadata (e.g. HH experience code)
        if api_experience_id:
            clean_id = api_experience_id.lower().replace("_", "").replace("-", "")
            if clean_id in cls.HH_API_EXPERIENCE_MAP:
                return cls.HH_API_EXPERIENCE_MAP[clean_id]

        return None, None

    extract_experience_years = extract_required_experience


class VacancyGradeDetector:
    """
    Detects target seniority grade for a vacancy based on role title,
    description text and minimum required experience.
    """

    @classmethod
    def detect_vacancy_grade(
        cls,
        title: str,
        description: str = "",
        min_experience: Optional[float] = None
    ) -> str:
        """
        Determines vacancy seniority grade: 'Junior', 'Middle', 'Senior', or 'Lead'.
        """
        title_lower = (title or "").lower()

        # 1. High priority: Title keywords
        # Lead / Architect / Team Lead
        if re.search(
            r"\b(lead|team\s*lead|tech\s*lead|principal|staff|architect|архитектор|руководитель|главный\s+(?:разработчик|инженер|программист)|тимлид|техлид)\b",
            title_lower
        ):
            return "Lead"

        # Senior / Ведущий
        if re.search(
            r"\b(senior|сеньор|сеньер|синиор|ведущий\s+(?:разработчик|программист|инженер)|старший\s+(?:разработчик|программист|инженер)|senior\+)\b",
            title_lower
        ):
            return "Senior"

        # Junior / Intern
        if re.search(
            r"\b(junior|джуниор|джун|стаж[её]р|intern|trainee|junior\+)\b",
            title_lower
        ):
            return "Junior"

        # Middle
        if re.search(
            r"\b(middle\+|мидл\+|миддл\+|middle|мидл|миддл)\b",
            title_lower
        ):
            return "Middle"

        # 2. Medium priority: Infer from required minimum experience
        if min_experience is not None:
            if min_experience >= 6.0:
                return "Lead"
            elif min_experience >= 3.5:
                return "Senior"
            elif min_experience >= 1.5:
                return "Middle"
            elif min_experience < 1.5:
                return "Junior"

        # 3. Check description keywords
        desc_lower = (description or "").lower()
        if re.search(r"\b(lead|тимлид|архитектор)\b", desc_lower):
            return "Lead"
        elif re.search(r"\b(senior|сеньор|ведущий разработчик)\b", desc_lower):
            return "Senior"
        elif re.search(r"\b(junior|стаж[её]р|без опыта)\b", desc_lower):
            return "Junior"

        # Default fallback
        return "Middle"

    detect_grade = detect_vacancy_grade
