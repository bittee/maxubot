"""Обробка інлайн-кнопок (витягування музики з відео)."""
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery

from bot.services.downloader import Downloader, DownloadError
from bot.services.sender import send_result
from bot.utils.tokens import token_store

log = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data.startswith("audio:"))
async def on_audio_button(query: CallbackQuery, bot: Bot, downloader: Downloader) -> None:
    token = (query.data or "").removeprefix("audio:")
    url = token_store.get(token)
    if not url:
        await query.answer("Посилання застаріло — надішли його ще раз.", show_alert=True)
        return

    await query.answer("🎵 Витягую музику…")
    message = query.message
    if message is None:
        return
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)
        result = await downloader.download_audio(url)
        try:
            await send_result(bot, message, result)
        finally:
            result.cleanup()
    except DownloadError as e:
        await bot.send_message(message.chat.id, f"❌ {e}")
    except Exception:
        log.exception("Помилка аудіо-кнопки: %s", url)
        await bot.send_message(message.chat.id, "❌ Не вдалося витягти музику.")
