import re
import datetime
from typing import List, Dict, Any, Set, Tuple, Optional
from core.config import settings
from services.resume_analyzer.extractor import ResumeExtractor
from services.resume_analyzer.vacancy_extractor import VacancyExperienceExtractor, VacancyGradeDetector


class VacancyMatcher:
    """
    Intelligent matching engine between a candidate's resume and job postings / freelance orders.
    Calculates weighted compatibility scores, grade & experience mismatch penalties, and skill gap analysis.
    """

    GRADE_RANKS = {
        "Junior": 1,
        "Middle": 2,
        "Senior": 3,
        "Lead": 4
    }

    ROLE_KEYWORDS = {
        # Tech & Engineering
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
        "php": {"php", "laravel", "symfony", "1с-битрикс"},

        # Marketing & Advertising
        "marketing": {"маркетинг", "маркетолог", "smm", "seo", "таргетолог", "копирайтер", "контент", "pr", "трафик", "лидогенерация"},

        # Sales & Commerce
        "sales": {"продажи", "менеджер по продажам", "b2b", "b2c", "торговый представитель", "работа с клиентами", "аккаунт", "продавец", "телемаркетинг"},

        # Design & Media
        "design": {"дизайнер", "дизайн", "ui/ux", "figma", "графический дизайнер", "моушн", "веб-дизайнер", "иллюстратор", "3d", "art director"},

        # Finance & Accounting
        "finance": {"бухгалтер", "бухгалтерия", "главный бухгалтер", "экономист", "финансист", "аудит", "1с", "налоги", "расчет зарплаты"},

        # HR & Recruiting
        "hr": {"hr", "рекрутер", "подбор персонала", "специалист по кадрам", "human resources", "кадровик", "recruiter"},

        # Legal
        "legal": {"юрист", "юрисконсульт", "юриспруденция", "адвокат", "договорное право"},

        # Logistics & Supply
        "logistics": {"логист", "логистика", "закупки", "снабжение", "склад", "водитель", "экспедитор", "курьер", "кладовщик"},

        # Management & Operations
        "management": {"project manager", "product manager", "руководитель", "директор", "управляющий", "менеджер проектов", "тимлид"},

        # Engineering & Technical
        "engineering": {"инженер", "проектировщик", "техник", "технолог", "конструктор", "механик"},

        # Support & Office
        "support": {"поддержка", "оператор", "call-центр", "диспетчер", "консультант", "секретарь", "ассистент", "офис-менеджер"}
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
        risk_level: str = "safe",
        vacancy_min_exp: Optional[float] = None,
        vacancy_max_exp: Optional[float] = None,
        vacancy_grade: Optional[str] = None,
        grade_confidence: float = 1.0,
        published_at: Optional[datetime.datetime] = None
    ) -> Dict[str, Any]:
        """
        Calculates compatibility between candidate profile and vacancy.
        
        Returns:
            dict containing:
                - score: int (0 to 100)
                - matched_skills: List[str]
                - missing_skills: List[str]
                - grade_compatibility: str ('exact' | 'growth_opportunity' | 'comfortable' | 'significantly_higher' | 'overqualified' | 'disqualified' | 'blocked')
                - vacancy_grade: str
                - vacancy_min_exp: Optional[float]
                - vacancy_max_exp: Optional[float]
                - candidate_grade: str
                - candidate_experience: float
                - exp_diff: Optional[float]
                - is_disqualified: bool
                - is_growth_opportunity: bool
                - grade_confidence: float
                - time_decay_factor: float
                - reason: str
        """
        # If vacancy is completely blocked for scam, return score 0
        if risk_level == "blocked":
            return {
                "score": 0,
                "matched_skills": [],
                "missing_skills": [],
                "grade_compatibility": "blocked",
                "vacancy_grade": vacancy_grade or "Middle",
                "vacancy_min_exp": vacancy_min_exp,
                "vacancy_max_exp": vacancy_max_exp,
                "candidate_grade": candidate_grade,
                "candidate_experience": candidate_experience,
                "exp_diff": None,
                "is_disqualified": True,
                "is_growth_opportunity": False,
                "grade_confidence": grade_confidence,
                "time_decay_factor": 1.0,
                "reason": "⛔ Вакансия заблокирована алгоритмом защиты от мошенничества"
            }

        cand_skills_set = set(candidate_skills)
        vac_text = f"{vacancy_title}\n{vacancy_description}"

        # 1. Determine vacancy required skills
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

        # 3. Extract vacancy required experience and grade if not supplied
        if vacancy_min_exp is None and vacancy_max_exp is None:
            vac_min_exp, vac_max_exp = VacancyExperienceExtractor.extract_required_experience(vac_text)
        else:
            vac_min_exp, vac_max_exp = vacancy_min_exp, vacancy_max_exp

        if vacancy_grade is None:
            vac_grade = VacancyGradeDetector.detect_vacancy_grade(
                title=vacancy_title,
                description=vacancy_description,
                min_experience=vac_min_exp
            )
        else:
            vac_grade = vacancy_grade

        c_rank = cls.GRADE_RANKS.get(candidate_grade, 1 if candidate_grade == "Junior" else 2)
        v_rank = cls.GRADE_RANKS.get(vac_grade, 2)
        grade_diff = v_rank - c_rank

        exp_diff = (candidate_experience - vac_min_exp) if vac_min_exp is not None else None

        # 4. HARD CUTOFF RULE vs SOFT PENALTY (Grade Confidence)
        # If grade_confidence < 0.7: apply soft penalty (10-15%) instead of hard cutoff
        is_disqualified = False
        soft_grade_penalty = 0.0

        if grade_confidence < 0.7:
            soft_grade_penalty = 12.0
        else:
            if candidate_grade == "Junior" and (grade_diff >= 2 or v_rank >= 3):
                is_disqualified = True
            elif vac_min_exp is not None and vac_min_exp >= 3.5 and exp_diff is not None and exp_diff <= -2.0:
                is_disqualified = True

        # 5. GROWTH OPPORTUNITY & EXPERIENCE GAP PENALTY
        is_growth_opportunity = False
        penalty = soft_grade_penalty

        if not is_disqualified:
            if candidate_grade == "Junior" and vac_grade == "Middle":
                if vac_min_exp is None or vac_min_exp <= 2.5:
                    is_growth_opportunity = True
                    if exp_diff is not None and exp_diff < 0:
                        penalty += 5.0 * abs(exp_diff)

            if not is_growth_opportunity and exp_diff is not None and exp_diff < 0:
                deficit = abs(exp_diff)
                if deficit < 1.5:
                    penalty += 15.0 * deficit
                else:
                    penalty += 35.0 + 20.0 * (deficit - 1.5)

        # 6. Weighted total score calculation
        grade_score, base_grade_comp = cls._calculate_grade_score(candidate_grade, vac_grade, candidate_experience)
        grade_comp = "growth_opportunity" if is_growth_opportunity else base_grade_comp

        # Configurable weights from core.config (default: skills 45%, grade 25%, experience 30%)
        w_skills = getattr(settings, "SCORE_WEIGHT_SKILLS", 0.45)
        w_grade = getattr(settings, "SCORE_WEIGHT_GRADE", 0.25)
        w_exp = getattr(settings, "SCORE_WEIGHT_EXPERIENCE", 0.30)

        # Experience score component (0..100)
        if vac_min_exp is None or exp_diff is None or exp_diff >= 0:
            exp_score = 100.0
        else:
            exp_score = max(0.0, 100.0 - (abs(exp_diff) * 25.0))

        # Skills component: combines hard skills (70%) and role title match (30%)
        skills_component = (skill_score * 0.70) + (role_score * 0.30)

        total_score = (skills_component * w_skills) + (grade_score * w_grade) + (exp_score * w_exp)

        # Apply slight penalty for warnings
        if risk_level == "warning":
            total_score = max(10.0, total_score - 15.0)

        # 7. Apply disqualification or penalty
        time_decay_factor = 1.0
        if is_disqualified:
            final_score = min(int(round(total_score * 0.15)), 18)
            grade_comp = "disqualified"
        else:
            penalized_score = max(0.0, total_score - penalty)

            # 8. Time decay for freshness (piecewise linear decay)
            if published_at is not None:
                now = datetime.datetime.now(datetime.timezone.utc)
                pub_tz = published_at if published_at.tzinfo is not None else published_at.replace(tzinfo=datetime.timezone.utc)
                days_old = max(0, (now - pub_tz).days)
                if days_old >= 30:
                    time_decay_factor = 0.70  # 30% penalty for > 30 days
                elif days_old >= 14:
                    # Decay from 0.88 down to 0.70
                    time_decay_factor = 0.88 - 0.18 * ((days_old - 14) / 16.0)
                elif days_old >= 7:
                    time_decay_factor = 0.95

            penalized_score = penalized_score * time_decay_factor
            final_score = int(round(penalized_score))
            final_score = min(100, max(0, final_score))

        # Formulate human-friendly reason summary
        reason = cls._generate_reason(
            score=final_score,
            matched=matched_skills,
            missing=missing_skills,
            grade_comp=grade_comp,
            vac_grade=vac_grade,
            vac_min_exp=vac_min_exp,
            exp_diff=exp_diff,
            is_disqualified=is_disqualified,
            is_growth_opportunity=is_growth_opportunity
        )

        return {
            "score": final_score,
            "matched_skills": matched_skills,
            "missing_skills": missing_skills,
            "grade_compatibility": grade_comp,
            "vacancy_grade": vac_grade,
            "vacancy_min_exp": vac_min_exp,
            "vacancy_max_exp": vac_max_exp,
            "candidate_grade": candidate_grade,
            "candidate_experience": candidate_experience,
            "exp_diff": round(exp_diff, 1) if exp_diff is not None else None,
            "is_disqualified": is_disqualified,
            "is_growth_opportunity": is_growth_opportunity,
            "grade_confidence": grade_confidence,
            "time_decay_factor": round(time_decay_factor, 2),
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

        # Freelance orders or generic project tasks often have descriptive titles
        generic_tasks = [
            "скрипт", "бот", "парсер", "сайт", "разработка", "доработка", "api",
            "дизайн", "макет", "логотип", "баннер", "презентация",
            "текст", "статья", "копирайтинг", "перевод", "рерайт",
            "настройка", "реклама", "трафик", "таблица", "отчет"
        ]
        if any(term in vac_title_lower for term in generic_tasks):
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
        vac_grade: str,
        vac_min_exp: Optional[float] = None,
        exp_diff: Optional[float] = None,
        is_disqualified: bool = False,
        is_growth_opportunity: bool = False
    ) -> str:
        parts = []
        if is_disqualified:
            exp_str = f" (требуется от {vac_min_exp:.1f} л.)" if vac_min_exp is not None else ""
            parts.append(f"⛔ Недостаточно опыта/грейда для позиции {vac_grade.upper()}{exp_str}")
        elif is_growth_opportunity:
            parts.append(f"🌱 Отличная зона роста ({vac_grade})")
        elif grade_comp == "significantly_higher":
            parts.append(f"⚠️ Требуется более высокий грейд ({vac_grade})")
        elif grade_comp == "overqualified":
            parts.append(f"ℹ️ Оверквалифицирован для позиции ({vac_grade})")
        elif exp_diff is not None and exp_diff < -0.5:
            parts.append(f"⚠️ Нехватка опыта: {abs(exp_diff):.1f} г.")

        if matched:
            parts.append(f"✅ Совпало: {', '.join(matched[:4])}")
        if missing:
            parts.append(f"⚡ Требуется подтянуть: {', '.join(missing[:3])}")

        return " | ".join(parts) if parts else "Соответствие по ключевым навыкам"
