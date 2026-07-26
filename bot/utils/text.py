"""Формування підписів до медіа."""
import html

from bot.services.downloader import DownloadResult

CAPTION_LIMIT = 1024  # ліміт Telegram для підпису до медіа


def build_caption(result: DownloadResult) -> str:
    parts: list[str] = []

    title = (result.title or "").strip()
    description = (result.description or "").strip()
    # Часто в TikTok/Instagram title == description — не дублюємо.
    if title and title not in description:
        parts.append(f"<b>{html.escape(title)}</b>")
    if description:
        parts.append(html.escape(description))

    footer: list[str] = []
    if result.uploader:
        footer.append(f"👤 {html.escape(result.uploader)}")
    if result.url:
        footer.append(f'🔗 <a href="{html.escape(result.url, quote=True)}">Джерело</a>')

    body = "\n\n".join(parts)
    tail = "\n\n" + "\n".join(footer) if footer else ""

    if len(body) + len(tail) > CAPTION_LIMIT:
        body = body[: CAPTION_LIMIT - len(tail) - 1].rstrip() + "…"
    return (body + tail).strip()
