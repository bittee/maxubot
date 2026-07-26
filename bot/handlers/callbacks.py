"""Обробка інлайн-кнопок: музика з відео та вибір якості."""
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery

from bot.handlers.links import run_download
from bot.services.cache import MediaCache, cache_key
from bot.services.downloader import Downloader, DownloadError
from bot.services.extractor import find_media_links
from bot.services.sender import send_cached, send_result
from bot.services.stats import Stats
from bot.utils.tokens import token_store

log = logging.getLogger(__name__)
router = Router(name="callbacks")


@router.callback_query(F.data.startswith("audio:"))
async def on_audio_button(query: CallbackQuery, bot: Bot, downloader: Downloader,
                          cache: MediaCache, stats: Stats) -> None:
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
            stats.record_cache_hit()
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
            stats.record_audio()
        finally:
            result.cleanup()
    except DownloadError as e:
        await bot.send_message(message.chat.id, f"❌ {e}")
    except Exception:
        log.exception("Помилка аудіо-кнопки: %s", url)
        await bot.send_message(message.chat.id, "❌ Не вдалося витягти музику.")


@router.callback_query(F.data.startswith("q:"))
async def on_quality_button(query: CallbackQuery, bot: Bot, downloader: Downloader,
                            cache: MediaCache, stats: Stats) -> None:
    # Формат: q:<token>:<висота>, 0 = максимальна якість.
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer()
        return
    url = token_store.get(parts[1])
    if not url:
        await query.answer("Посилання застаріло — надішли його ще раз.", show_alert=True)
        return
    try:
        height = int(parts[2]) or None
    except ValueError:
        await query.answer()
        return

    message = query.message
    if message is None:
        await query.answer()
        return

    links = find_media_links(url)
    if not links:
        await query.answer("Не можу обробити це посилання.", show_alert=True)
        return

    quality_label = f"{height}p" if height else "максимальній якості"
    await query.answer(f"⏳ Завантажую в {quality_label}…")

    # Відповіді чіпляємо до оригінального повідомлення юзера з лінком,
    # а повідомлення з кнопками прибираємо.
    target = message.reply_to_message
    if target:
        try:
            await message.delete()
        except Exception:
            pass
    else:
        target = message

    await run_download(target, bot, downloader, cache, stats, links[0],
                       height_cap=height)
