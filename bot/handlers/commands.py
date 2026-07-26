"""Команди /start та /help."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router(name="commands")

HELP_TEXT = (
    "👋 Привіт! Я — <b>бот-завантажувач</b>.\n\n"
    "Просто надішли мені посилання (або додай мене в груповий чат) — "
    "я завантажу контент і надішлю його сюди:\n\n"
    "🎬 <b>Відео</b> — TikTok, Instagram Reels, YouTube Shorts, X (Twitter), "
    "Facebook, Reddit, Pinterest та багато інших\n"
    "🖼 <b>Фото та каруселі</b> — Instagram, X, Threads, Pinterest\n"
    "📝 <b>Опис поста</b> — додаю до медіа\n"
    "🎵 <b>Музика</b> — кнопка «Музика» під відео витягне аудіодоріжку в mp3\n\n"
    "<b>Команди:</b>\n"
    "/audio &lt;посилання&gt; — одразу отримати тільки музику (mp3)\n"
    "/help — ця довідка\n\n"
    "У групах я реагую тільки на повідомлення з підтримуваними посиланнями."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(HELP_TEXT)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)
