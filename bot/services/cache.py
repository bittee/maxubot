"""Кеш file_id: повторний лінк відправляється миттєво, без завантаження.

Telegram після першого аплоаду повертає file_id, який можна пересилати
в будь-який чат без повторного завантаження. Ключ — нормалізований URL
(без трекінг-параметрів), сховище — Redis або in-memory фолбек.
"""
import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

log = logging.getLogger(__name__)

CACHE_TTL = 30 * 24 * 3600  # 30 днів

# Параметри, що не впливають на контент — лише трекінг/шеринг.
TRACKING_PARAMS = {
    "si", "igsh", "igshid", "fbclid", "gclid", "feature", "ref", "ref_src",
    "ref_url", "share_id", "sender_web_id", "web_id", "mibextid", "rdid",
    "s", "t", "is_from_webapp", "sender_device", "_r", "share_app_id",
    "checksum", "sec_user_id", "tt_from", "u_code", "ug_btm", "app",
}


def normalize_url(url: str) -> str:
    """Канонізує URL, щоб один і той самий пост давав один ключ кешу."""
    p = urlparse(url.strip())
    host = (p.hostname or "").lower()
    for prefix in ("www.", "m.", "mobile."):
        host = host.removeprefix(prefix)
    if host == "twitter.com":
        host = "x.com"

    path = re.sub(r"/+$", "", p.path) or "/"
    query = [(k, v) for k, v in parse_qsl(p.query)
             if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    query.sort()
    return urlunparse(("https", host, path, "", urlencode(query), ""))


def cache_key(url: str, variant: str = "") -> str:
    """Ключ кешу для URL; variant — напр. 'audio' для витягнутої музики."""
    digest = hashlib.sha256(normalize_url(url).encode()).hexdigest()[:32]
    return f"media:{digest}:{variant}" if variant else f"media:{digest}"


@dataclass
class CachedMedia:
    kind: str                       # video | images | audio
    items: list[tuple[str, str]]    # (тип: video|photo|audio, file_id)
    caption: str = ""
    title: str = ""
    uploader: str = ""
    audio_available: bool = False

    def to_json(self) -> str:
        return json.dumps({
            "kind": self.kind, "items": self.items, "caption": self.caption,
            "title": self.title, "uploader": self.uploader,
            "audio_available": self.audio_available,
        })

    @classmethod
    def from_json(cls, raw: str) -> "CachedMedia":
        d = json.loads(raw)
        return cls(
            kind=d["kind"],
            items=[tuple(i) for i in d["items"]],
            caption=d.get("caption", ""),
            title=d.get("title", ""),
            uploader=d.get("uploader", ""),
            audio_available=d.get("audio_available", False),
        )


class MediaCache:
    """Redis-кеш з in-memory фолбеком (для запуску без Redis)."""

    def __init__(self, redis_url: str | None):
        self._redis_url = redis_url
        self._redis = None
        self._memory: dict[str, str] = {}

    async def connect(self) -> None:
        if not self._redis_url:
            log.info("REDIS_URL не задано — кеш file_id працює in-memory.")
            return
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url, decode_responses=True, socket_timeout=5,
            )
            await self._redis.ping()
            log.info("Кеш file_id: Redis підключено (%s).", self._redis_url)
        except Exception as e:
            log.warning("Redis недоступний (%s) — кеш працює in-memory.", e)
            self._redis = None

    async def get(self, key: str) -> CachedMedia | None:
        try:
            raw = (await self._redis.get(key)) if self._redis else self._memory.get(key)
        except Exception as e:
            log.warning("Помилка читання кешу: %s", e)
            return None
        return CachedMedia.from_json(raw) if raw else None

    async def put(self, key: str, entry: CachedMedia) -> None:
        try:
            if self._redis:
                await self._redis.set(key, entry.to_json(), ex=CACHE_TTL)
            else:
                self._memory[key] = entry.to_json()
                if len(self._memory) > 5000:
                    self._memory.pop(next(iter(self._memory)))
        except Exception as e:
            log.warning("Помилка запису кешу: %s", e)

    async def invalidate(self, key: str) -> None:
        try:
            if self._redis:
                await self._redis.delete(key)
            self._memory.pop(key, None)
        except Exception as e:
            log.warning("Помилка інвалідації кешу: %s", e)


@dataclass
class InflightRegistry:
    """Дедуплікація завантажень у польоті.

    Якщо той самий URL уже завантажується (інший чат скинув той самий лінк),
    другий запит чекає завершення першого і бере результат з кешу,
    замість того щоб качати повторно.
    """
    _futures: dict[str, asyncio.Future] = field(default_factory=dict)

    def claim(self, key: str) -> asyncio.Future | None:
        """Повертає future для очікування, або None — якщо ми перші (власник)."""
        existing = self._futures.get(key)
        if existing is not None:
            return existing
        self._futures[key] = asyncio.get_running_loop().create_future()
        return None

    def release(self, key: str) -> None:
        fut = self._futures.pop(key, None)
        if fut and not fut.done():
            fut.set_result(None)
