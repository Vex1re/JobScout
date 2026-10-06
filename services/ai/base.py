import re
import json
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from core.config import settings

logger = logging.getLogger(__name__)

# Catalog of known prompt injection signatures
PROMPT_INJECTION_PATTERNS = [
    r"(?i)\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b",
    r"(?i)\bdisregard\s+(?:all\s+)?(?:prior|previous|above)\s+instructions\b",
    r"(?i)\bforget\s+(?:all\s+)?(?:previous|prior|everything)\b",
    r"(?i)\bsystem\s+prompt\b",
    r"(?i)\byou\s+are\s+now\s+(?:dan|unrestricted|developer\s+mode)\b",
    r"(?i)\bact\s+as\s+(?:an?\s+)?unrestricted\s+ai\b",
    r"(?i)\breveal\s+(?:your\s+)?(?:system\s+prompt|instructions)\b",
    r"(?i)<\/?(?:system|instruction|prompt|im_start|im_end)>",
    r"(?i)\[\/?(?:inst|sys)\]"
]


def sanitize_llm_input(text: Optional[str], max_chars: int = 15000) -> str:
    """
    Sanitizes user resume or vacancy input prior to sending to external LLM providers:
    1. Removes prompt injection and jailbreak instructions.
    2. Enforces maximum length to prevent context flooding / denial of service.
    3. Strips raw delimiter tags.
    """
    if not text:
        return ""

    sanitized = text
    for pattern in PROMPT_INJECTION_PATTERNS:
        sanitized = re.sub(pattern, "[FILTERED_INSTRUCTION]", sanitized)

    # Trim to safe length
    return sanitized[:max_chars].strip()


class LLMProvider(ABC):
    """Abstract interface for LLM providers (OpenAI, YandexGPT, GigaChat, etc.)."""

    name: str = "base"

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Indicates whether provider is configured and available."""
        pass

    @abstractmethod
    async def extract_resume_data(self, text: str) -> Optional[Dict[str, Any]]:
        """Extracts structured resume data (title, grade, experience, skills, salary)."""
        pass

    @abstractmethod
    async def generate_cover_letter(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        """Generates custom tailored cover letter."""
        pass

    @abstractmethod
    async def explain_match(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        """Explains match score and skill gaps."""
        pass


class NoneLLMProvider(LLMProvider):
    """Fallback provider when LLM integration is disabled or user hasn't given consent."""

    name: str = "none"

    @property
    def is_available(self) -> bool:
        return False

    async def extract_resume_data(self, text: str) -> Optional[Dict[str, Any]]:
        return None

    async def generate_cover_letter(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None

    async def explain_match(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None


class OpenAIProvider(LLMProvider):
    """OpenAI API Provider (GPT-4o-mini, etc.)."""

    name: str = "openai"

    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.base_url = settings.OPENAI_BASE_URL
        self.model = settings.OPENAI_MODEL
        self._client = None
        if self.api_key:
            try:
                from openai import AsyncOpenAI
                self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)
            except ImportError:
                logger.warning("OpenAI library not installed. OpenAIProvider unavailable.")

    @property
    def is_available(self) -> bool:
        return self._client is not None

    async def extract_resume_data(self, text: str) -> Optional[Dict[str, Any]]:
        if not self.is_available:
            return None

        clean_text = sanitize_llm_input(text)
        prompt = f"""
Проанализируй следующее резюме и верни СТРОГО валидный JSON:
{{
  "title": "целевая профессия",
  "grade": "Junior" | "Middle" | "Senior" | "Lead",
  "years_of_experience": float,
  "skills": ["навык1", "навык2"],
  "salary_expectation": integer или null,
  "summary": "краткое резюме"
}}

Текст резюме:
\"\"\"{clean_text}\"\"\"
"""
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты профессиональный HR-аналитик. Отвечай только валидным JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            logger.warning(f"OpenAI resume extraction error: {e}")
            return None

    async def generate_cover_letter(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        if not self.is_available:
            return None

        clean_resume = sanitize_llm_input(resume_text, max_chars=4000)
        clean_vacancy = sanitize_llm_input(vacancy_text, max_chars=4000)

        prompt = f"""
Составь убедительное и вежливое сопроводительное письмо на русском языке на основе резюме кандидата для отклика на вакансию.

Резюме:
{clean_resume}

Вакансия:
{clean_vacancy}
"""
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты эксперт по составлению сопроводительных писем. Пиши четко, без лишней воды."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.4,
                max_tokens=500
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI cover letter generation error: {e}")
            return None

    async def explain_match(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        if not self.is_available:
            return None

        clean_resume = sanitize_llm_input(resume_text, max_chars=3000)
        clean_vacancy = sanitize_llm_input(vacancy_text, max_chars=3000)

        prompt = f"""
Проанализируй соответствие кандидата вакансии. Напиши 2-3 предложения: сильные стороны и зоны роста.

Резюме: {clean_resume}
Вакансия: {clean_vacancy}
"""
        try:
            response = await self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "Ты карьерный консультант."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=200
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            logger.warning(f"OpenAI explain match error: {e}")
            return None


class YandexGPTProvider(LLMProvider):
    """YandexGPT Provider stub."""

    name: str = "yandex"

    def __init__(self):
        self.api_key = settings.YANDEX_API_KEY
        self.folder_id = settings.YANDEX_FOLDER_ID

    @property
    def is_available(self) -> bool:
        return bool(self.api_key and self.folder_id)

    async def extract_resume_data(self, text: str) -> Optional[Dict[str, Any]]:
        if not self.is_available:
            logger.warning("YandexGPT requested but YANDEX_API_KEY or YANDEX_FOLDER_ID not configured.")
            return None
        # Stub implementation
        return None

    async def generate_cover_letter(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None

    async def explain_match(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None


class GigaChatProvider(LLMProvider):
    """Sber GigaChat Provider stub."""

    name: str = "gigachat"

    def __init__(self):
        self.credentials = settings.GIGACHAT_CREDENTIALS

    @property
    def is_available(self) -> bool:
        return bool(self.credentials)

    async def extract_resume_data(self, text: str) -> Optional[Dict[str, Any]]:
        if not self.is_available:
            logger.warning("GigaChat requested but GIGACHAT_CREDENTIALS not configured.")
            return None
        # Stub implementation
        return None

    async def generate_cover_letter(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None

    async def explain_match(self, resume_text: str, vacancy_text: str) -> Optional[str]:
        return None


def get_llm_provider(user_consent: bool = True) -> LLMProvider:
    """
    Factory function returning the active LLM provider.
    Enforces user consent and system configuration flags.
    """
    if not user_consent:
        return NoneLLMProvider()

    prov = (settings.LLM_PROVIDER or "none").lower()

    if prov == "openai" or (prov == "none" and settings.OPENAI_API_KEY):
        return OpenAIProvider()
    elif prov == "yandex":
        return YandexGPTProvider()
    elif prov == "gigachat":
        return GigaChatProvider()

    return NoneLLMProvider()
