"""Обробка посилань у приватних і групових чатах + команда /audio."""
import logging

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.downloader import Downloader, DownloadError
from bot.services.extractor import find_media_links
from bot.services.sender import send_result
from bot.utils.tokens import token_store

log = logging.getLogger(__name__)
router = Router(name="links")

MAX_LINKS_PER_MESSAGE = 3


def _message_text(message: Message) -> str:
    return message.text or message.caption or ""


@router.message(Command("audio"))
async def cmd_audio(message: Message, bot: Bot, downloader: Downloader) -> None:
    links = find_media_links(_message_text(message))
    if not links:
        await message.reply(
            "Надішли посилання разом з командою:\n<code>/audio https://…</code>"
        )
        return
    status = await message.reply("🎵 Витягую музику…")
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)
        result = await downloader.download_audio(links[0].url)
        try:
            await send_result(bot, message, result)
        finally:
            result.cleanup()
    except DownloadError as e:
        await message.reply(f"❌ {e}")
    except Exception:
        log.exception("Помилка при витягуванні аудіо: %s", links[0].url)
        await message.reply("❌ Щось пішло не так. Спробуй ще раз пізніше.")
    finally:
        await _delete_silently(status)


@router.message(F.text | F.caption)
async def handle_links(message: Message, bot: Bot, downloader: Downloader) -> None:
    links = find_media_links(_message_text(message))
    if not links:
        # У приваті підказуємо; у групах мовчимо, щоб не спамити.
        if message.chat.type == "private" and message.text:
            await message.reply(
                "Це не схоже на підтримуване посилання. Надішли лінк на пост "
                "або відео (TikTok, Instagram, YouTube, X…). /help — довідка."
            )
        return

    for link in links[:MAX_LINKS_PER_MESSAGE]:
        status = await message.reply(f"⏳ Завантажую з {link.platform}…")
        try:
            await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
            result = await downloader.download(link)
            token = token_store.put(link.url) if result.audio_available else None
            try:
                await send_result(bot, message, result, audio_token=token)
            finally:
                result.cleanup()
        except DownloadError as e:
            log.info("DownloadError %s: %s", link.url, e)
            await message.reply(
                f"❌ Не вдалося завантажити з {link.platform}.\n"
                f"Можливо, пост приватний, видалений або потрібна авторизація."
            )
        except Exception:
            log.exception("Неочікувана помилка: %s", link.url)
            await message.reply("❌ Щось пішло не так. Спробуй ще раз пізніше.")
        finally:
            await _delete_silently(status)


async def _delete_silently(message: Message) -> None:
    try:
        await message.delete()
    except Exception:  # немає прав на видалення в групі — не страшно
        pass
