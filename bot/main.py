"""Точка входу: запуск бота в режимі long polling."""
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from bot.config import load_config
from bot.handlers import callbacks, commands, links
from bot.services.downloader import Downloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


async def main() -> None:
    config = load_config()
    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    # Downloader прокидається в хендлери через DI aiogram.
    dp["downloader"] = Downloader(config)

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
    asyncio.run(main())
