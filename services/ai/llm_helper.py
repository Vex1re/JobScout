import json
import logging
from typing import Dict, Any, Optional, List
from core.config import settings

logger = logging.getLogger(__name__)

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None


class LLMHelper:
    """
    Optional LLM helper for deep resume analysis, semantic matching,
    and cover letter advice when OPENAI_API_KEY is configured.
    """

    def __init__(self):
        self.client = None
        if settings.OPENAI_API_KEY and AsyncOpenAI:
            self.client = AsyncOpenAI(
                api_key=settings.OPENAI_API_KEY,
                base_url=settings.OPENAI_BASE_URL
            )

    @property
    def is_available(self) -> bool:
        return self.client is not None

    async def analyze_resume_deep(self, resume_text: str) -> Optional[Dict[str, Any]]:
        """Deep analysis of resume using LLM with structured JSON output."""
        if not self.is_available:
            return None

        prompt = f"""
Проанализируй следующее резюме кандидата и верни СТРОГО валидный JSON со следующими полями:
- "title": целевая должность или профессия кандидата (например, "Python Backend Developer", "Интернет-маркетолог", "Главный бухгалтер", "Менеджер по продажам")
- "grade": грейд или уровень квалификации ("Junior", "Middle", "Senior", "Lead")
- "years_of_experience": число полных лет опыта (число с плавающей точкой, например 3.5)
- "skills": список ключевых профессиональных навыков и инструментов (массив строк)
- "salary_expectation": число ожидаемой зарплаты в рублях (или null, если не указано)
- "summary": краткое профессиональное резюме кандидата на 1-2 предложения

Текст резюме:
\"\"\"{resume_text[:4000]}\"\"\"
"""
        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты экспертный HR и карьерный консультант для любых профессиональных сфер. Отвечай только валидным JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            logger.warning(f"LLM deep resume analysis failed: {e}")
            return None

    async def generate_application_tip(
        self,
        candidate_skills: List[str],
        candidate_grade: str,
        vacancy_title: str,
        vacancy_company: str,
        missing_skills: List[str]
    ) -> Optional[str]:
        """Generate a personalized tip or cover letter pitch for applying to this vacancy."""
        if not self.is_available:
            return None

        prompt = f"""
Кандидат уровня {candidate_grade} с навыками ({', '.join(candidate_skills[:8])})
хочет откликнуться на вакансию: "{vacancy_title}" в компанию "{vacancy_company}".
В вакансии упомянуты навыки, которых нет у кандидата: {', '.join(missing_skills[:3]) if missing_skills else 'нет'}.

Напиши 1-2 предложения с конкретным советом: на чем сделать акцент в сопроводительном письме, чтобы выделиться.
"""
        try:
            response = await self.client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": "Ты карьерный консультант. Отвечай кратко, емко, без воды."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=150
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"LLM tip generation failed: {e}")
            return None


llm_helper = LLMHelper()
