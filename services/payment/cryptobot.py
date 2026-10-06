import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from services.payment.base import BasePaymentProvider

logger = logging.getLogger(__name__)


class CryptoBotProvider(BasePaymentProvider):
    """
    CryptoBot (@CryptoBot) payment provider stub.
    Disabled by default; activated via ENABLE_CRYPTOBOT=true and CRYPTOBOT_API_TOKEN.
    """

    def __init__(self):
        super().__init__(name="cryptobot")

    def _ensure_enabled(self) -> None:
        if not getattr(settings, "ENABLE_CRYPTOBOT", False):
            raise RuntimeError(
                "CryptoBot provider is currently disabled. "
                "Enable by setting ENABLE_CRYPTOBOT=true and CRYPTOBOT_API_TOKEN in .env."
            )
        if not getattr(settings, "CRYPTOBOT_API_TOKEN", None):
            raise ValueError("CRYPTOBOT_API_TOKEN must be specified.")

    async def create_invoice_payload(
        self,
        user_id: int,
        plan: str,
        amount: Optional[int] = None
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        return {
            "provider": self.name,
            "status": "not_implemented"
        }

    async def confirm_payment(
        self,
        session: AsyncSession,
        user_id: int,
        payload: str,
        amount: int
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        return {
            "provider": self.name,
            "status": "not_implemented"
        }
