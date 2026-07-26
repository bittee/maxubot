"""Точка входу: запуск бота в режимі long polling."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import load_config
from bot.handlers import callbacks, commands, links
from bot.services.cache import InflightRegistry, MediaCache
from bot.services.downloader import Downloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def _install_uvloop() -> None:
    try:
        import uvloop
        uvloop.install()
        log.info("uvloop увімкнено.")
    except ImportError:
        pass


async def main() -> None:
    config = load_config()

    session = None
    if config.bot_api_url:
        # Самохостнутий telegram-bot-api: файли до 2 ГБ.
        # Великі аплоади потребують довшого таймауту.
        session = AiohttpSession(
            api=TelegramAPIServer.from_base(config.bot_api_url, is_local=True),
            timeout=600,
        )
        log.info("Локальний Bot API: %s (ліміт %d МБ)",
                 config.bot_api_url, config.max_file_mb)
    else:
        log.info("Хмарний Bot API (ліміт %d МБ). Для файлів до 2 ГБ "
                 "запусти telegram-bot-api і задай BOT_API_URL.",
                 config.max_file_mb)

    bot = Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    cache = MediaCache(config.redis_url)
    await cache.connect()

    dp = Dispatcher()
    # Сервіси прокидаються в хендлери через DI aiogram.
    dp["downloader"] = Downloader(config)
    dp["cache"] = cache
    dp["inflight"] = InflightRegistry()

    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(links.router)  # останній — ловить решту повідомлень

    await bot.set_my_commands([
        BotCommand(command="start", description="Почати"),
        BotCommand(command="help", description="Довідка"),
        BotCommand(command="audio", description="Витягти музику з посилання"),
    ])

    me = await bot.get_me()
    log.info("Бот запущено: @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    _install_uvloop()
    asyncio.run(main())
