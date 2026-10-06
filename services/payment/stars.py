import time
import logging
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database.repository import SubscriptionRepository
from services.payment.base import BasePaymentProvider

logger = logging.getLogger(__name__)


class TelegramStarsProvider(BasePaymentProvider):
    """
    Official Telegram Stars (XTR) payment provider.
    Native to Telegram, no corporate legal entity required to receive Stars.
    """

    CURRENCY = "XTR"

    PLAN_PRICES = {
        "pro": getattr(settings, "STARS_PRICE_PRO", 150),
        "team": getattr(settings, "STARS_PRICE_TEAM", 400),
    }

    def __init__(self):
        super().__init__(name="telegram_stars")

    async def create_invoice_payload(
        self,
        user_id: int,
        plan: str,
        amount: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Prepares parameters for bot.send_invoice using Telegram Stars (XTR).
        For Telegram Stars, provider_token must be empty string.
        """
        plan_lower = plan.lower()
        price_stars = amount or self.PLAN_PRICES.get(plan_lower, 150)
        timestamp = int(time.time())
        invoice_payload = f"sub:{plan_lower}:{user_id}:{timestamp}"

        title = f"⭐ Подписка JobScout {plan_lower.upper()}"
        description = (
            f"Доступ ко всем фичам плана {plan_lower.upper()} на 30 дней: "
            f"AI-сопроводительные письма, Gap-анализ, канбан-трекер, мгновенные уведомления."
        )

        return {
            "title": title,
            "description": description,
            "payload": invoice_payload,
            "currency": self.CURRENCY,
            "prices": [{"label": f"{plan_lower.upper()} (30 дней)", "amount": price_stars}],
            "provider_token": "",  # Empty for Telegram Stars
            "start_parameter": f"sub-{plan_lower}",
        }

    async def confirm_payment(
        self,
        session: AsyncSession,
        user_id: int,
        payload: str,
        amount: int
    ) -> Dict[str, Any]:
        """
        Validates the invoice payload and activates the subscription in DB.
        """
        parts = payload.split(":")
        if len(parts) >= 2 and parts[0] == "sub":
            plan = parts[1]
        else:
            plan = "pro"

        logger.info("Confirming Telegram Stars payment: user=%d, plan=%s, amount=%d XTR", user_id, plan, amount)
        sub = await SubscriptionRepository.create_or_update_subscription(
            session=session,
            user_id=user_id,
            plan=plan,
            duration_days=30
        )

        return {
            "success": True,
            "user_id": user_id,
            "plan": sub.plan,
            "expires_at": sub.expires_at,
            "provider": self.name,
            "amount_xtr": amount
        }
