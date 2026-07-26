"""Пошук і класифікація посилань на медіа в тексті повідомлень."""
import re
from dataclasses import dataclass
from urllib.parse import urlparse

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# Платформи, які бот обробляє. Ключ — підрядок хоста, значення — назва.
PLATFORMS: dict[str, str] = {
    "instagram.com": "Instagram",
    "instagr.am": "Instagram",
    "tiktok.com": "TikTok",
    "x.com": "X",
    "twitter.com": "X",
    "youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "facebook.com": "Facebook",
    "fb.watch": "Facebook",
    "reddit.com": "Reddit",
    "redd.it": "Reddit",
    "pinterest.com": "Pinterest",
    "pin.it": "Pinterest",
    "vimeo.com": "Vimeo",
    "twitch.tv": "Twitch",
    "soundcloud.com": "SoundCloud",
    "threads.net": "Threads",
    "threads.com": "Threads",
    "vk.com": "VK",
    "dailymotion.com": "Dailymotion",
    "likee.video": "Likee",
    "snapchat.com": "Snapchat",
}

# Хости, де карусель/фото краще тягнути через gallery-dl.
GALLERY_HOSTS = ("instagram.com", "instagr.am", "x.com", "twitter.com",
                 "pinterest.com", "pin.it", "threads.net", "threads.com")


@dataclass(frozen=True)
class MediaLink:
    url: str
    platform: str
    host: str

    @property
    def gallery_capable(self) -> bool:
        return any(h in self.host for h in GALLERY_HOSTS)


def _host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def find_media_links(text: str) -> list[MediaLink]:
    """Повертає всі підтримувані медіа-посилання з тексту (без дублів)."""
    links: list[MediaLink] = []
    seen: set[str] = set()
    for raw in URL_RE.findall(text or ""):
        url = raw.rstrip(").,!?»”'\"")
        if url in seen:
            continue
        host = _host_of(url)
        if not host:
            continue
        for key, name in PLATFORMS.items():
            if host == key or host.endswith("." + key):
                seen.add(url)
                links.append(MediaLink(url=url, platform=name, host=host))
                break
    return links
