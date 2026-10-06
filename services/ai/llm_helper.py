import json
import logging
from typing import Dict, Any, Optional, List
from core.config import settings
from services.ai.base import get_llm_provider, sanitize_llm_input

logger = logging.getLogger(__name__)


class LLMHelper:
    """
    LLM helper for deep resume analysis, semantic matching,
    and cover letter advice, delegating to active LLMProvider.
    Respects user consent and configuration flags.
    """

    def __init__(self):
        pass

    @property
    def is_available(self) -> bool:
        provider = get_llm_provider(user_consent=True)
        return provider.is_available

    async def analyze_resume_deep(self, resume_text: str, user_consent: bool = True) -> Optional[Dict[str, Any]]:
        """Deep analysis of resume using active LLM provider with structured JSON output."""
        provider = get_llm_provider(user_consent=user_consent)
        if not provider.is_available:
            return None
        return await provider.extract_resume_data(resume_text)

    async def generate_application_tip(
        self,
        candidate_skills: List[str],
        candidate_grade: str,
        vacancy_title: str,
        vacancy_company: str,
        missing_skills: List[str],
        user_consent: bool = True
    ) -> Optional[str]:
        """Generate a personalized tip or cover letter pitch for applying to this vacancy."""
        provider = get_llm_provider(user_consent=user_consent)
        if not provider.is_available:
            return None

        clean_skills = sanitize_llm_input(', '.join(candidate_skills[:8]))
        clean_title = sanitize_llm_input(vacancy_title)
        clean_comp = sanitize_llm_input(vacancy_company)
        clean_missing = sanitize_llm_input(', '.join(missing_skills[:3]) if missing_skills else 'нет')

        prompt = f"""
Кандидат уровня {candidate_grade} с навыками ({clean_skills})
хочет откликнуться на вакансию: "{clean_title}" в компанию "{clean_comp}".
В вакансии упомянуты навыки, которых нет у кандидата: {clean_missing}.

Напиши 1-2 предложения с конкретным советом: на чем сделать акцент в сопроводительном письме, чтобы выделиться.
"""
        return await provider.generate_cover_letter(clean_skills, prompt)


llm_helper = LLMHelper()
