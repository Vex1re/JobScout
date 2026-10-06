import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from services.payment.base import BasePaymentProvider

logger = logging.getLogger(__name__)


class YooKassaProvider(BasePaymentProvider):
    """
    YooKassa payment provider stub.
    Disabled by default; activated via ENABLE_YOOKASSA=true.
    """

    def __init__(self):
        super().__init__(name="yookassa")

    def _ensure_enabled(self) -> None:
        if not getattr(settings, "ENABLE_YOOKASSA", False):
            raise RuntimeError(
                "YooKassa provider is currently disabled. "
                "Enable by setting ENABLE_YOOKASSA=true, YOOKASSA_SHOP_ID, and YOOKASSA_SECRET_KEY in .env."
            )
        if not getattr(settings, "YOOKASSA_SHOP_ID", None) or not getattr(settings, "YOOKASSA_SECRET_KEY", None):
            raise ValueError("YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY must be provided.")

    async def create_invoice_payload(
        self,
        user_id: int,
        plan: str,
        amount: Optional[int] = None
    ) -> Dict[str, Any]:
        self._ensure_enabled()
        # Stub for live YooKassa API checkout session
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
