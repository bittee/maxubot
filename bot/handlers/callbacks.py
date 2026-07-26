"""Обробка інлайн-кнопок (витягування музики з відео)."""
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery

from bot.services.cache import MediaCache, cache_key
from bot.services.downloader import Downloader, DownloadError
from bot.services.sender import send_cached, send_result
from bot.utils.tokens import token_store

log = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data.startswith("audio:"))
async def on_audio_button(query: CallbackQuery, bot: Bot, downloader: Downloader,
                          cache: MediaCache) -> None:
    token = (query.data or "").removeprefix("audio:")
    url = token_store.get(token)
    if not url:
        await query.answer("Посилання застаріло — надішли його ще раз.", show_alert=True)
        return

    message = query.message
    if message is None:
        await query.answer()
        return

    key = cache_key(url, "audio")
    entry = await cache.get(key)
    if entry:
        try:
            await send_cached(bot, message, entry)
            await query.answer("🎵 Готово!")
            return
        except Exception:
            await cache.invalidate(key)

    await query.answer("🎵 Витягую музику…")
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)
        result = await downloader.download_audio(url)
        try:
            new_entry = await send_result(bot, message, result)
            if new_entry:
                await cache.put(key, new_entry)
        finally:
            result.cleanup()
    except DownloadError as e:
        await bot.send_message(message.chat.id, f"❌ {e}")
    except Exception:
        log.exception("Помилка аудіо-кнопки: %s", url)
        await bot.send_message(message.chat.id, "❌ Не вдалося витягти музику.")
