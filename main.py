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

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

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

    storage = MemoryStorage()
    if settings.REDIS_URL:
        try:
            from aiogram.fsm.storage.redis import RedisStorage
            storage = RedisStorage.from_url(settings.REDIS_URL)
            logger.info("Using RedisStorage for FSM.")
        except Exception as e:
            logger.warning(f"Could not initialize RedisStorage ({e}), falling back to MemoryStorage.")

    dp = Dispatcher(storage=storage)

    # 3. Register handlers and middlewares
    register_handlers(dp)

    # 4. Start background scheduler in dev mode if enabled
    scheduler = None
    if settings.ENV == "dev" and settings.ENABLE_AUTO_NOTIFICATIONS:
        logger.info(f"Starting in-process scheduler for dev environment (interval: {settings.AUTO_SEARCH_INTERVAL_MINUTES}m)...")
        scheduler = setup_scheduler(bot)
        scheduler.start()
    elif settings.ENV == "prod":
        logger.info("Running in production mode. Scheduler is managed by dedicated scheduler service.")

    try:
        if settings.BOT_MODE == "webhook":
            if not settings.WEBHOOK_URL:
                raise ValueError("WEBHOOK_URL must be specified when BOT_MODE='webhook'")

            from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
            from aiohttp import web

            webhook_url = f"{settings.WEBHOOK_URL.rstrip('/')}{settings.WEBHOOK_PATH}"
            await bot.set_webhook(
                url=webhook_url,
                secret_token=settings.WEBHOOK_SECRET,
                drop_pending_updates=True
            )
            logger.info(f"Configured Telegram webhook at {webhook_url}")

            app = web.Application()

            async def healthz(request):
                return web.Response(text="OK", status=200)

            app.router.add_get("/healthz", healthz)

            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=settings.WEBHOOK_SECRET,
            )
            webhook_requests_handler.register(app, path=settings.WEBHOOK_PATH)
            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, host=settings.WEBHOOK_HOST, port=settings.WEBHOOK_PORT)
            await site.start()
            logger.info(f"Webhook server running on {settings.WEBHOOK_HOST}:{settings.WEBHOOK_PORT}")

            # Keep server running until signal
            while True:
                await asyncio.sleep(3600)

        else:
            # Polling mode (dev / default)
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Bot is polling for updates...")
            await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"Fatal error in bot execution: {e}", exc_info=True)
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user.")
