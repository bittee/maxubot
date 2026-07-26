"""Точка входу: запуск бота (long polling або webhook)."""
import asyncio
import hashlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.types import BotCommand
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.config import Config, load_config
from bot.handlers import callbacks, commands, links
from bot.services.cache import InflightRegistry, MediaCache
from bot.services.downloader import Downloader
from bot.services.stats import Stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook"


def _install_uvloop() -> None:
    try:
        import uvloop
        uvloop.install()
        log.info("uvloop увімкнено.")
    except ImportError:
        pass


def _build_bot(config: Config) -> Bot:
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
    return Bot(
        token=config.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _setup(config: Config, bot: Bot) -> Dispatcher:
    cache = MediaCache(config.redis_url)
    await cache.connect()

    dp = Dispatcher()
    # Сервіси прокидаються в хендлери через DI aiogram.
    dp["config"] = config
    dp["downloader"] = Downloader(config)
    dp["cache"] = cache
    dp["inflight"] = InflightRegistry()
    dp["stats"] = Stats()

    dp.include_router(commands.router)
    dp.include_router(callbacks.router)
    dp.include_router(links.router)  # останній — ловить решту повідомлень

    await bot.set_my_commands([
        BotCommand(command="start", description="Почати"),
        BotCommand(command="help", description="Довідка"),
        BotCommand(command="audio", description="Витягти музику з посилання"),
    ])
    return dp


async def _run_polling(config: Config, bot: Bot, dp: Dispatcher) -> None:
    me = await bot.get_me()
    log.info("Бот запущено (polling): @%s", me.username)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def _run_webhook(config: Config, bot: Bot, dp: Dispatcher) -> None:
    # Секрет захищає ендпоінт від сторонніх запитів.
    secret = hashlib.sha256(config.bot_token.encode()).hexdigest()[:32]
    url = config.webhook_url + WEBHOOK_PATH
    await bot.set_webhook(url, secret_token=secret, drop_pending_updates=True)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=secret) \
        .register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    me = await bot.get_me()
    log.info("Бот запущено (webhook %s): @%s", url, me.username)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", config.webhook_port)
    await site.start()
    await asyncio.Event().wait()  # працюємо, поки процес не зупинять


async def main() -> None:
    config = load_config()
    bot = _build_bot(config)
    dp = await _setup(config, bot)
    if config.webhook_url:
        await _run_webhook(config, bot, dp)
    else:
        await _run_polling(config, bot, dp)


if __name__ == "__main__":
    _install_uvloop()
    asyncio.run(main())
