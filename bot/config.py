"""Конфігурація бота з змінних оточення."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    download_dir: Path
    cookies_file: str | None
    max_file_mb: int
    max_concurrent_downloads: int


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN не задано. Створіть .env на основі .env.example "
            "і вставте токен від @BotFather."
        )

    download_dir = Path(os.getenv("DOWNLOAD_DIR", "downloads")).resolve()
    download_dir.mkdir(parents=True, exist_ok=True)

    cookies = os.getenv("COOKIES_FILE", "").strip() or None
    if cookies and not Path(cookies).exists():
        cookies = None

    return Config(
        bot_token=token,
        download_dir=download_dir,
        cookies_file=cookies,
        max_file_mb=int(os.getenv("MAX_FILE_MB", "49")),
        max_concurrent_downloads=int(os.getenv("MAX_CONCURRENT_DOWNLOADS", "3")),
    )
