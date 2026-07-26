"""Обробка посилань у приватних і групових чатах + команда /audio."""
import asyncio
import logging
import time
from collections import defaultdict

from aiogram import Bot, F, Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.services.cache import InflightRegistry, MediaCache, cache_key
from bot.services.downloader import Downloader, DownloadError
from bot.services.extractor import MediaLink, find_media_links
from bot.services.sender import send_cached, send_result
from bot.services.stats import Stats
from bot.utils.tokens import token_store

log = logging.getLogger(__name__)
router = Router(name="links")

MAX_LINKS_PER_MESSAGE = 3
INFLIGHT_WAIT_TIMEOUT = 600  # с — скільки чекати чуже завантаження того ж URL
QUALITY_CHOICE_MIN_DURATION = 15 * 60  # довші відео — питаємо якість
QUALITY_OPTIONS = (480, 720, 1080)

# Один чат — одне активне завантаження, щоб ніхто не зайняв усі воркери.
_chat_locks: dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def _message_text(message: Message) -> str:
    return message.text or message.caption or ""


def quality_keyboard(token: str) -> InlineKeyboardMarkup:
    row = [InlineKeyboardButton(text=f"{h}p", callback_data=f"q:{token}:{h}")
           for h in QUALITY_OPTIONS]
    row.append(InlineKeyboardButton(text="⭐ Макс", callback_data=f"q:{token}:0"))
    return InlineKeyboardMarkup(inline_keyboard=[row])


@router.message(Command("audio"))
async def cmd_audio(message: Message, bot: Bot, downloader: Downloader,
                    cache: MediaCache, stats: Stats) -> None:
    links = find_media_links(_message_text(message))
    if not links:
        await message.reply(
            "Надішли посилання разом з командою:\n<code>/audio https://…</code>"
        )
        return
    await process_audio(message, bot, downloader, cache, stats, links[0].url)


@router.message(F.text | F.caption)
async def handle_links(message: Message, bot: Bot, downloader: Downloader,
                       cache: MediaCache, inflight: InflightRegistry,
                       stats: Stats) -> None:
    links = find_media_links(_message_text(message))
    if not links:
        # У приваті підказуємо; у групах мовчимо, щоб не спамити.
        if message.chat.type == "private" and message.text:
            await message.reply(
                "Це не схоже на підтримуване посилання. Надішли лінк на пост "
                "або відео (TikTok, Instagram, YouTube, X…). /help — довідка."
            )
        return

    async with _chat_locks[message.chat.id]:
        for link in links[:MAX_LINKS_PER_MESSAGE]:
            await _process_link(message, bot, downloader, cache, inflight, stats, link)


async def _process_link(message: Message, bot: Bot, downloader: Downloader,
                        cache: MediaCache, inflight: InflightRegistry,
                        stats: Stats, link: MediaLink) -> None:
    key = cache_key(link.url)

    # 1. Кеш: той самий лінк уже завантажували — віддаємо миттєво.
    if await _try_send_cached(message, bot, cache, stats, key, link.url):
        return

    # 2. Дедуплікація: той самий URL уже качається для іншого чату — чекаємо.
    waiter = inflight.claim(key)
    if waiter is not None:
        try:
            await asyncio.wait_for(asyncio.shield(waiter), INFLIGHT_WAIT_TIMEOUT)
        except (TimeoutError, Exception):
            pass
        if await _try_send_cached(message, bot, cache, stats, key, link.url):
            return
        # Перший запит провалився — пробуємо самі (без повторного claim).

    try:
        # 3. Для довгих YouTube-відео — метадані й вибір якості кнопками.
        probed = None
        if link.platform == "YouTube":
            probed = await downloader.probe(link.url)
            if probed and (probed.get("duration") or 0) >= QUALITY_CHOICE_MIN_DURATION:
                token = token_store.put(link.url)
                mins = int(probed["duration"] // 60)
                await message.reply(
                    f"🎬 <b>{probed.get('title', 'Відео')}</b> — {mins} хв.\n"
                    f"Обери якість:",
                    reply_markup=quality_keyboard(token),
                )
                return

        # 4. Завантажуємо самі.
        await run_download(message, bot, downloader, cache, stats, link,
                           probed=probed)
    finally:
        inflight.release(key)


async def run_download(message: Message, bot: Bot, downloader: Downloader,
                       cache: MediaCache, stats: Stats, link: MediaLink,
                       height_cap: int | None = None,
                       probed: dict | None = None) -> None:
    """Завантаження + відправка + кешування. Викликається і з quality-кнопок."""
    variant = f"h{height_cap}" if height_cap else ""
    key = cache_key(link.url, variant)
    if await _try_send_cached(message, bot, cache, stats, key, link.url):
        return

    status = await message.reply(f"⏳ Завантажую з {link.platform}…")
    loop = asyncio.get_running_loop()

    def progress(text: str) -> None:
        asyncio.run_coroutine_threadsafe(_edit_silently(status, text), loop)

    started = time.monotonic()
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VIDEO)
        result = await downloader.download(link, progress=progress,
                                           height_cap=height_cap, probed=probed)
        token = token_store.put(link.url) if result.audio_available else None
        try:
            await _edit_silently(status, "📤 Надсилаю…")
            entry = await send_result(bot, message, result, audio_token=token)
            if entry:
                await cache.put(key, entry)
            stats.record_ok(link.platform, time.monotonic() - started)
        finally:
            result.cleanup()
    except DownloadError as e:
        log.info("DownloadError %s: %s", link.url, e)
        stats.record_err(link.platform)
        await message.reply(f"❌ {e}")
    except Exception:
        log.exception("Неочікувана помилка: %s", link.url)
        stats.record_err(link.platform)
        await message.reply("❌ Щось пішло не так. Спробуй ще раз пізніше.")
    finally:
        await _delete_silently(status)


async def process_audio(message: Message, bot: Bot, downloader: Downloader,
                        cache: MediaCache, stats: Stats, url: str) -> None:
    key = cache_key(url, "audio")
    if await _try_send_cached(message, bot, cache, stats, key, url):
        return

    status = await message.reply("🎵 Витягую музику…")
    try:
        await bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_VOICE)
        result = await downloader.download_audio(url)
        try:
            entry = await send_result(bot, message, result)
            if entry:
                await cache.put(key, entry)
            stats.record_audio()
        finally:
            result.cleanup()
    except DownloadError as e:
        await message.reply(f"❌ {e}")
    except Exception:
        log.exception("Помилка при витягуванні аудіо: %s", url)
        await message.reply("❌ Щось пішло не так. Спробуй ще раз пізніше.")
    finally:
        await _delete_silently(status)


async def _try_send_cached(message: Message, bot: Bot, cache: MediaCache,
                           stats: Stats, key: str, url: str) -> bool:
    entry = await cache.get(key)
    if not entry:
        return False
    token = token_store.put(url) if entry.audio_available else None
    try:
        await send_cached(bot, message, entry, audio_token=token)
        stats.record_cache_hit()
        log.info("Кеш-хіт: %s", url)
        return True
    except TelegramBadRequest as e:
        # file_id протух (напр., після зміни Bot API сервера) — перекачуємо.
        log.info("Кешований file_id недійсний (%s), інвалідую: %s", e, url)
        await cache.invalidate(key)
        return False


async def _edit_silently(message: Message, text: str) -> None:
    try:
        await message.edit_text(text)
    except Exception:  # "message is not modified", флуд-ліміт тощо
        pass


async def _delete_silently(message: Message) -> None:
    try:
        await message.delete()
    except Exception:  # немає прав на видалення в групі — не страшно
        pass
