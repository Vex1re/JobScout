import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from core.config import settings
from core.database.session import init_db
from core.scheduler import setup_scheduler
from bot.handlers import register_handlers

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("JobScoutBot")


async def main():
    logger.info("Initializing JobScout Bot...")

    if not settings.BOT_TOKEN or settings.BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        logger.error(
            "❌ ОШИБКА: BOT_TOKEN не указан в файле .env!\n"
            "Пожалуйста, скопируйте .env.example в .env и укажите ваш токен от @BotFather.\n"
            "Пример: BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
        )
        return

    # 1. Initialize database tables
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized successfully.")

    # 2. Initialize Telegram Bot and Dispatcher
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # 3. Register handlers and middlewares
    register_handlers(dp)

    # 4. Start background scheduler
    if settings.ENABLE_AUTO_NOTIFICATIONS:
        logger.info(f"Starting scheduler (interval: {settings.AUTO_SEARCH_INTERVAL_MINUTES}m)...")
        scheduler = setup_scheduler(bot)
        scheduler.start()

    logger.info("Bot is polling for updates...")

    try:
        # Delete webhook to prevent conflicts with long polling
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Fatal error while polling: {e}", exc_info=True)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
