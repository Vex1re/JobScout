from typing import Callable, Dict, Any, Awaitable, Optional
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TelegramUser
from core.database.session import async_session_factory
from core.database.repository import UserRepository


class DatabaseMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with async_session_factory() as session:
            data["session"] = session
            telegram_user: Optional[TelegramUser] = data.get("event_from_user")
            if not telegram_user and hasattr(event, "from_user"):
                telegram_user = getattr(event, "from_user")

            if telegram_user:
                try:
                    data["user"] = await UserRepository.get_or_create_user(
                        session=session,
                        telegram_id=telegram_user.id,
                        username=telegram_user.username,
                        first_name=telegram_user.first_name
                    )
                except Exception:
                    pass

            return await handler(event, data)
