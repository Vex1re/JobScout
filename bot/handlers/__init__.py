from aiogram import Dispatcher
from bot.handlers.start import router as start_router
from bot.handlers.resume import router as resume_router
from bot.handlers.vacancies import router as vacancies_router
from bot.handlers.favorites import router as favorites_router
from bot.handlers.settings import router as settings_router
from bot.middlewares.db import DatabaseMiddleware
from bot.middlewares.throttling import ThrottlingMiddleware


def register_handlers(dp: Dispatcher) -> None:
    """Register all routers and middlewares on the Dispatcher."""
    dp.update.middleware(DatabaseMiddleware())
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(start_router)
    dp.include_router(resume_router)
    dp.include_router(vacancies_router)
    dp.include_router(favorites_router)
    dp.include_router(settings_router)
