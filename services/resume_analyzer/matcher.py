import re
from typing import List, Dict, Any, Set, Tuple
from services.resume_analyzer.extractor import ResumeExtractor


class VacancyMatcher:
    """
    Intelligent matching engine between a candidate's resume and job postings / freelance orders.
    Calculates weighted compatibility scores and skill gap analysis.
    """

    GRADE_RANKS = {
        "Junior": 1,
        "Middle": 2,
        "Senior": 3,
        "Lead": 4
    }

    ROLE_KEYWORDS = {
        "python": {"python", "django", "fastapi", "flask", "aiohttp"},
        "backend": {"backend", "бэкенд", "бэкэнд", "серверный"},
        "frontend": {"frontend", "фронтенд", "фронтэнд", "react", "vue", "angular", "next.js"},
        "fullstack": {"fullstack", "фуллстек", "фулстек"},
        "devops": {"devops", "девопс", "sre", "инфраструктура", "sysadmin", "системный администратор"},
        "qa": {"qa", "тестировщик", "тестирование", "quality assurance", "автотест", "automation"},
        "data": {"data scientist", "дата саентист", "ml", "machine learning", "аналитик данных", "data engineer"},
        "mobile": {"mobile", "мобильный", "android", "ios", "flutter", "react native", "swift", "kotlin"},
        "go": {"go", "golang"},
        "java": {"java", "spring"},
        "php": {"php", "laravel", "symfony", "1с-битрикс"}
    }

    @classmethod
    def match(
        cls,
        candidate_skills: List[str],
        candidate_grade: str,
        candidate_role: str,
        candidate_experience: float,
        vacancy_title: str,
        vacancy_description: str,
        vacancy_requirements: List[str],
        risk_level: str = "safe"
    ) -> Dict[str, Any]:
        """
        Calculates compatibility between candidate profile and vacancy.
        
        Returns:
            dict containing:
                - score: int (0 to 100)
                - matched_skills: List[str]
                - missing_skills: List[str]
                - grade_compatibility: str ('exact' | 'higher' | 'lower' | 'unspecified')
                - reason: str (short explanation)
        """
        # If vacancy is completely blocked for scam, return score 0
        if risk_level == "blocked":
            return {
                "score": 0,
                "matched_skills": [],
                "missing_skills": [],
                "grade_compatibility": "blocked",
                "reason": "⛔ Вакансия заблокирована алгоритмом защиты от мошенничества"
            }

        cand_skills_set = set(candidate_skills)

        # 1. Determine vacancy required skills
        vac_text = f"{vacancy_title}\n{vacancy_description}"
        vac_skills = set(vacancy_requirements)
        if not vac_skills:
            # Extract skills directly from vacancy text
            vac_skills = set(ResumeExtractor.extract_skills(vac_text))

        # Skill overlap calculation
        matched_skills = sorted(list(cand_skills_set.intersection(vac_skills)))
        missing_skills = sorted(list(vac_skills - cand_skills_set))

        if vac_skills:
            skill_score = (len(matched_skills) / len(vac_skills)) * 100
        else:
            # If vacancy has no identifiable tech skills, fall back to title token matching
            skill_score = 50.0

        # Cap and scale skill score
        skill_score = min(100.0, max(0.0, skill_score))

        # 2. Role / Title compatibility
        role_score = cls._calculate_role_score(candidate_role, vacancy_title)

        # 3. Grade / Seniority compatibility
        vac_grade = ResumeExtractor.detect_grade(vacancy_title + " " + vacancy_description, 2.0)
        grade_score, grade_comp = cls._calculate_grade_score(candidate_grade, vac_grade, candidate_experience)

        # 4. Weighted total score calculation
        # Weights: 50% hard skills, 30% role title match, 20% grade match
        total_score = (skill_score * 0.50) + (role_score * 0.30) + (grade_score * 0.20)

        # Apply slight penalty for warnings
        if risk_level == "warning":
            total_score = max(10.0, total_score - 15.0)

        final_score = int(round(total_score))
        final_score = min(100, max(0, final_score))

        # Formulate human-friendly reason summary
        reason = cls._generate_reason(final_score, matched_skills, missing_skills, grade_comp, vac_grade)

        return {
            "score": final_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "grade_compatibility": grade_comp,
            "vacancy_grade": vac_grade,
            "reason": reason
        }

    @classmethod
    def _calculate_role_score(cls, cand_role: str, vac_title: str) -> float:
        cand_role_lower = cand_role.lower()
        vac_title_lower = vac_title.lower()

        # Check keyword clusters
        cand_clusters: Set[str] = set()
        for cluster_name, kws in cls.ROLE_KEYWORDS.items():
            if any(kw in cand_role_lower for kw in kws):
                cand_clusters.add(cluster_name)

        vac_clusters: Set[str] = set()
        for cluster_name, kws in cls.ROLE_KEYWORDS.items():
            if any(kw in vac_title_lower for kw in kws):
                vac_clusters.add(cluster_name)

        # If both belong to the same domain cluster (e.g. 'python' or 'backend')
        common = cand_clusters.intersection(vac_clusters)
        if common:
            # Perfect role alignment
            return 100.0

        # Substring token check
        cand_tokens = set(re.findall(r"\w+", cand_role_lower))
        vac_tokens = set(re.findall(r"\w+", vac_title_lower))
        overlap = cand_tokens.intersection(vac_tokens)
        if overlap:
            return 75.0

        # Freelance orders or generic orders often have descriptive titles like "Сделать сайт"
        if any(term in vac_title_lower for term in ["скрипт", "бот", "парсер", "сайт", "разработка", "доработка", "api"]):
            return 60.0

        # Role mismatch (e.g. Python Backend vs 1C or iOS)
        return 20.0

    @classmethod
    def _calculate_grade_score(cls, cand_grade: str, vac_grade: str, cand_years: float) -> Tuple[float, str]:
        c_rank = cls.GRADE_RANKS.get(cand_grade, 2)
        v_rank = cls.GRADE_RANKS.get(vac_grade, 2)

        diff = v_rank - c_rank

        if diff == 0:
            return 100.0, "exact"
        elif diff == 1:
            # Candidate is Junior, vacancy is Middle (or Middle looking at Senior)
            return 75.0, "growth_opportunity"
        elif diff == -1:
            # Candidate is Senior, vacancy is Middle
            return 85.0, "comfortable"
        elif diff >= 2:
            # Junior looking at Senior/Lead
            return 25.0, "significantly_higher"
        else: # diff <= -2
            # Lead looking at Junior
            return 60.0, "overqualified"

    @classmethod
    def _generate_reason(
        cls,
        score: int,
        matched: List[str],
        missing: List[str],
        grade_comp: str,
        vac_grade: str
    ) -> str:
        parts = []
        if matched:
            parts.append(f"✅ Совпало: {', '.join(matched[:4])}")
        if missing:
            parts.append(f"⚡ Требуется подтянуть: {', '.join(missing[:3])}")
        if grade_comp == "growth_opportunity":
            parts.append(f"📈 Позиция {vac_grade} — отличная зона роста")
        elif grade_comp == "significantly_higher":
            parts.append(f"⚠️ Требуется более высокий грейд ({vac_grade})")

        return " | ".join(parts) if parts else "Соответствие по ключевым навыкам"
