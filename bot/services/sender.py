"""Відправлення медіа в чат: свіжозавантаженого або з кешу file_id."""
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from bot.services.cache import CachedMedia
from bot.services.downloader import VIDEO_EXT, DownloadResult
from bot.utils.text import build_caption

log = logging.getLogger(__name__)

ALBUM_LIMIT = 10  # максимум елементів у media group Telegram


def audio_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎵 Музика", callback_data=f"audio:{token}")
    ]])


def _is_video(f: Path) -> bool:
    return f.suffix.lower() in VIDEO_EXT


async def send_result(bot: Bot, message: Message, result: DownloadResult,
                      audio_token: str | None = None) -> CachedMedia | None:
    """Надсилає завантажене медіа; повертає CachedMedia з file_id для кешу."""
    caption = build_caption(result)
    keyboard = audio_keyboard(audio_token) if (audio_token and result.audio_available) else None
    items: list[tuple[str, str]] = []

    if result.kind == "audio":
        sent = await bot.send_audio(
            chat_id=message.chat.id,
            audio=FSInputFile(result.files[0]),
            caption=caption or None,
            title=result.title or None,
            performer=result.uploader or None,
            reply_to_message_id=message.message_id,
        )
        if sent.audio:
            items.append(("audio", sent.audio.file_id))
        return _entry(result, caption, items)

    media_files = list(result.files) + list(result.extra_videos)

    if result.kind == "video" and len(media_files) == 1:
        sent = await bot.send_video(
            chat_id=message.chat.id,
            video=FSInputFile(media_files[0]),
            caption=caption or None,
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
            supports_streaming=True,
        )
        if sent.video:
            items.append(("video", sent.video.file_id))
        return _entry(result, caption, items)

    # Фото/карусель або кілька відео — шлемо альбомами по 10.
    for start in range(0, len(media_files), ALBUM_LIMIT):
        chunk = media_files[start:start + ALBUM_LIMIT]
        cap = caption if start == 0 else None
        if len(chunk) == 1:
            items.extend(await _send_single(bot, message, chunk[0], cap, keyboard))
            continue
        group = []
        for i, f in enumerate(chunk):
            item_cap = cap if i == 0 else None
            if _is_video(f):
                group.append(InputMediaVideo(media=FSInputFile(f), caption=item_cap,
                                             supports_streaming=True))
            else:
                group.append(InputMediaPhoto(media=FSInputFile(f), caption=item_cap))
        sent_msgs = await bot.send_media_group(
            chat_id=message.chat.id, media=group,
            reply_to_message_id=message.message_id,
        )
        items.extend(_ids_from(sent_msgs))

    # Альбоми не підтримують інлайн-кнопки — шлемо кнопку окремо.
    if keyboard and len(media_files) > 1:
        await bot.send_message(
            chat_id=message.chat.id,
            text="🎵 Витягнути музику з відео?",
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
        )
    return _entry(result, caption, items)


async def send_cached(bot: Bot, message: Message, entry: CachedMedia,
                      audio_token: str | None = None) -> None:
    """Миттєва відправка через file_id — без завантаження."""
    keyboard = audio_keyboard(audio_token) if (audio_token and entry.audio_available) else None
    caption = entry.caption or None

    if entry.kind == "audio":
        await bot.send_audio(
            chat_id=message.chat.id, audio=entry.items[0][1],
            caption=caption, title=entry.title or None,
            performer=entry.uploader or None,
            reply_to_message_id=message.message_id,
        )
        return

    if len(entry.items) == 1:
        media_type, file_id = entry.items[0]
        if media_type == "video":
            await bot.send_video(
                chat_id=message.chat.id, video=file_id, caption=caption,
                reply_markup=keyboard, reply_to_message_id=message.message_id,
                supports_streaming=True,
            )
        else:
            await bot.send_photo(
                chat_id=message.chat.id, photo=file_id, caption=caption,
                reply_to_message_id=message.message_id,
            )
        return

    for start in range(0, len(entry.items), ALBUM_LIMIT):
        chunk = entry.items[start:start + ALBUM_LIMIT]
        group = []
        for i, (media_type, file_id) in enumerate(chunk):
            item_cap = caption if (start == 0 and i == 0) else None
            if media_type == "video":
                group.append(InputMediaVideo(media=file_id, caption=item_cap,
                                             supports_streaming=True))
            else:
                group.append(InputMediaPhoto(media=file_id, caption=item_cap))
        await bot.send_media_group(
            chat_id=message.chat.id, media=group,
            reply_to_message_id=message.message_id,
        )

    if keyboard:
        await bot.send_message(
            chat_id=message.chat.id,
            text="🎵 Витягнути музику з відео?",
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
        )


# ---------- допоміжне ----------

async def _send_single(bot: Bot, message: Message, f: Path, caption: str | None,
                       keyboard: InlineKeyboardMarkup | None) -> list[tuple[str, str]]:
    if _is_video(f):
        sent = await bot.send_video(
            chat_id=message.chat.id, video=FSInputFile(f), caption=caption,
            reply_markup=keyboard, reply_to_message_id=message.message_id,
            supports_streaming=True,
        )
    else:
        sent = await bot.send_photo(
            chat_id=message.chat.id, photo=FSInputFile(f), caption=caption,
            reply_to_message_id=message.message_id,
        )
    return _ids_from([sent])


def _ids_from(messages: list[Message]) -> list[tuple[str, str]]:
    ids: list[tuple[str, str]] = []
    for m in messages:
        if m.video:
            ids.append(("video", m.video.file_id))
        elif m.photo:
            ids.append(("photo", m.photo[-1].file_id))
        elif m.audio:
            ids.append(("audio", m.audio.file_id))
    return ids


def _entry(result: DownloadResult, caption: str,
           items: list[tuple[str, str]]) -> CachedMedia | None:
    if not items:
        return None
    return CachedMedia(
        kind=result.kind,
        items=items,
        caption=caption,
        title=result.title,
        uploader=result.uploader,
        audio_available=result.audio_available,
    )
