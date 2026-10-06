from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession


class BasePaymentProvider(ABC):
    """
    Abstract interface for payment providers.
    """

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def create_invoice_payload(
        self,
        user_id: int,
        plan: str,
        amount: int
    ) -> Dict[str, Any]:
        """Creates invoice parameters for Telegram bot or payment gateway."""
        pass

    @abstractmethod
    async def confirm_payment(
        self,
        session: AsyncSession,
        user_id: int,
        payload: str,
        amount: int
    ) -> Dict[str, Any]:
        """Confirms successful payment and activates subscription."""
        pass
