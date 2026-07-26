"""Конфігурація бота з змінних оточення."""
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    download_dir: Path
    cookies_files: tuple[str, ...]  # кілька профілів — ротація при відмовах
    max_file_mb: int
    max_concurrent_downloads: int
    bot_api_url: str | None   # самохостнутий telegram-bot-api (--local), до 2 ГБ
    redis_url: str | None     # кеш file_id; без Redis — in-memory
    admin_ids: frozenset[int] = field(default_factory=frozenset)  # доступ до /stats
    webhook_url: str | None = None   # публічний URL; без нього — long polling
    webhook_port: int = 8080


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задано. Створіть .env на основі .env.example "
            "і вставте токен від @BotFather."
        )

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads")).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    cookies = tuple(
        p for p in (c.strip() for c in os.getenv("COOKIES_FILE", "").split(","))
        if p and Path(p).exists()
    )

    bot_api_url = os.getenv("BOT_API_URL", "").strip().rstrip("/") or None
    # З локальним Bot API ліміт — 2 ГБ; з хмарним — 50 МБ.
    default_limit = "1950" if bot_api_url else "49"

    admin_ids = frozenset(
        int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",")
        if x.lstrip("-").isdigit()
    )

    return Config(
        bot_token=token,
        download_dir=download_dir,
        cookies_files=cookies,
        max_file_mb=int(os.getenv("MAX_FILE_MB", default_limit)),
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "4")),
        bot_api_url=bot_api_url,
        redis_url=os.getenv("REDIS_URL", "").strip() or None,
        admin_ids=admin_ids,
        webhook_url=os.getenv("WEBHOOK_URL", "").strip().rstrip("/") or None,
        # Хостинги (Railway, Render тощо) призначають порт через PORT.
        webhook_port=int(os.getenv("WEBHOOK_PORT") or os.getenv("PORT") or "8080"),
    )
