"""Відправлення завантаженого медіа в чат."""
import logging

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    Message,
)

from bot.services.downloader import DownloadResult
from bot.utils.text import build_caption

log = logging.getLogger(__name__)

ALBUM_LIMIT = 10  # максимум елементів у media group Telegram


def audio_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🎵 Музика", callback_data=f"audio:{token}")
    ]])


async def send_result(bot: Bot, message: Message, result: DownloadResult,
                      audio_token: str | None = None) -> None:
    caption = build_caption(result)
    keyboard = audio_keyboard(audio_token) if (audio_token and result.audio_available) else None

    if result.kind == "audio":
        await bot.send_audio(
            chat_id=message.chat.id,
            audio=FSInputFile(result.files[0]),
            caption=caption or None,
            title=result.title or None,
            performer=result.uploader or None,
            reply_to_message_id=message.message_id,
        )
        return

    if result.kind == "video" and len(result.files) == 1:
        await bot.send_video(
            chat_id=message.chat.id,
            video=FSInputFile(result.files[0]),
            caption=caption or None,
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
            supports_streaming=True,
        )
        return

    # Фото/карусель або кілька відео — шлемо альбомами по 10.
    media_files = list(result.files) + list(result.extra_videos)
    for start in range(0, len(media_files), ALBUM_LIMIT):
        chunk = media_files[start:start + ALBUM_LIMIT]
        if len(chunk) == 1:
            f = chunk[0]
            if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}:
                await bot.send_video(
                    chat_id=message.chat.id, video=FSInputFile(f),
                    caption=caption if start == 0 else None,
                    reply_markup=keyboard,
                    reply_to_message_id=message.message_id,
                    supports_streaming=True,
                )
            else:
                await bot.send_photo(
                    chat_id=message.chat.id, photo=FSInputFile(f),
                    caption=caption if start == 0 else None,
                    reply_to_message_id=message.message_id,
                )
            continue

        group = []
        for i, f in enumerate(chunk):
            cap = caption if (start == 0 and i == 0 and caption) else None
            if f.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".m4v"}:
                group.append(InputMediaVideo(media=FSInputFile(f), caption=cap,
                                             supports_streaming=True))
            else:
                group.append(InputMediaPhoto(media=FSInputFile(f), caption=cap))
        await bot.send_media_group(
            chat_id=message.chat.id, media=group,
            reply_to_message_id=message.message_id,
        )

    # Альбоми не підтримують інлайн-кнопки — шлемо кнопку окремо.
    if keyboard and len(media_files) > 1:
        await bot.send_message(
            chat_id=message.chat.id,
            text="🎵 Витягнути музику з відео?",
            reply_markup=keyboard,
            reply_to_message_id=message.message_id,
        )
