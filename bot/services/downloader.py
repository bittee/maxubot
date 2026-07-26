"""Завантаження медіа: yt-dlp для відео/аудіо, gallery-dl для фото-каруселей."""
import asyncio
import itertools
import logging
import shutil
import subprocess
import tempfile
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp

from bot.config import Config
from bot.services.extractor import MediaLink

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav"}

ProgressCallback = Callable[[str], None]


class DownloadError(Exception):
    """Не вдалося завантажити медіа. Текст — зрозуміле повідомлення для юзера."""

    def __init__(self, message: str, *, needs_auth: bool = False):
        super().__init__(message)
        self.needs_auth = needs_auth


def classify_error(err: Exception) -> DownloadError:
    """Перетворює помилку yt-dlp на зрозуміле повідомлення."""
    text = str(err).lower()
    if any(m in text for m in ("login required", "sign in", "cookies", "authentication",
                               "not logged in", "requested content is not available",
                               "rate-limit reached")):
        return DownloadError(
            "Потрібна авторизація — пост доступний лише залогіненим користувачам. "
            "Адмін може додати cookies (див. README).", needs_auth=True,
        )
    if "private" in text:
        return DownloadError("Пост приватний — я не маю до нього доступу.")
    if any(m in text for m in ("geo", "not available in your country", "region")):
        return DownloadError("Контент недоступний у регіоні сервера (геоблок).")
    if any(m in text for m in ("age", "18 years")):
        return DownloadError("Контент з віковим обмеженням — потрібні cookies акаунта.")
    if any(m in text for m in ("removed", "deleted", "no longer available",
                               "video unavailable", "404")):
        return DownloadError("Пост видалено або він більше недоступний.")
    if any(m in text for m in ("timed out", "timeout", "connection", "temporary")):
        return DownloadError("Джерело не відповідає. Спробуй ще раз за хвилину.")
    return DownloadError("Не вдалося завантажити за цим посиланням.")


def _is_transient(err: Exception) -> bool:
    text = str(err).lower()
    return any(m in text for m in ("timed out", "timeout", "connection reset",
                                   "connection aborted", "temporary failure",
                                   "503", "502", "500"))


@dataclass
class DownloadResult:
    kind: str  # "video" | "images" | "audio"
    files: list[Path]
    title: str = ""
    description: str = ""
    uploader: str = ""
    url: str = ""
    workdir: Path | None = None
    audio_available: bool = False
    extra_videos: list[Path] = field(default_factory=list)

    def cleanup(self) -> None:
        if self.workdir and self.workdir.exists():
            shutil.rmtree(self.workdir, ignore_errors=True)


class Downloader:
    def __init__(self, config: Config):
        self.config = config
        self._sem = asyncio.Semaphore(config.max_concurrent_downloads)
        self._aria2c = shutil.which("aria2c") is not None
        self._cookie_cycle = itertools.cycle(config.cookies_files) \
            if config.cookies_files else None
        if self._aria2c:
            log.info("aria2c знайдено — багатопотокове завантаження увімкнено.")
        if len(config.cookies_files) > 1:
            log.info("Ротація cookies: %d профілів.", len(config.cookies_files))

    # ---------- публічний API ----------

    async def probe(self, url: str) -> dict | None:
        """Швидко тягне метадані (без завантаження): тривалість, формати, назву."""
        async with self._sem:
            try:
                return await asyncio.to_thread(self._probe_sync, url)
            except Exception as e:
                log.info("Проба метаданих не вдалася (%s): %s", url, e)
                return None

    async def download(self, link: MediaLink,
                       progress: ProgressCallback | None = None,
                       height_cap: int | None = None,
                       probed: dict | None = None) -> DownloadResult:
        """Завантажує контент за посиланням: спершу yt-dlp, потім gallery-dl."""
        async with self._sem:
            workdir = self._new_workdir()
            try:
                return await asyncio.to_thread(
                    self._download_sync, link, workdir, progress, height_cap, probed
                )
            except Exception:
                shutil.rmtree(workdir, ignore_errors=True)
                raise

    async def download_audio(self, url: str) -> DownloadResult:
        """Витягує аудіодоріжку (музику) у mp3."""
        async with self._sem:
            workdir = self._new_workdir()
            try:
                return await asyncio.to_thread(self._download_audio_sync, url, workdir)
            except Exception:
                shutil.rmtree(workdir, ignore_errors=True)
                raise

    # ---------- yt-dlp ----------

    def _next_cookiefile(self) -> str | None:
        return next(self._cookie_cycle) if self._cookie_cycle else None

    def _base_opts(self, workdir: Path, cookiefile: str | None = None) -> dict:
        opts = {
            "outtmpl": str(workdir / "%(title).80B [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "playlist_items": "1-10",
            "restrictfilenames": False,
            "socket_timeout": 30,
            "retries": 3,
            "concurrent_fragment_downloads": 8,
        }
        cookiefile = cookiefile or self._next_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
        # aria2c: багатопотокове скачування прямих URL (для HLS/DASH-фрагментів
        # yt-dlp сам обирає нативний завантажувач).
        if self._aria2c:
            opts["external_downloader"] = {"default": "aria2c"}
            opts["external_downloader_args"] = {
                "aria2c": ["-x8", "-s8", "-k1M", "--summary-interval=0"],
            }
        return opts

    def _probe_sync(self, url: str) -> dict:
        opts = {
            "quiet": True, "no_warnings": True, "socket_timeout": 20,
            "playlist_items": "1", "extract_flat": False,
        }
        cookiefile = self._next_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return self._flatten_info(info or {})

    @staticmethod
    def _progress_hook(progress: ProgressCallback):
        """Хук yt-dlp: тротлений прогрес для статусного повідомлення."""
        last_call = [0.0]

        def hook(d: dict) -> None:
            if d.get("status") != "downloading":
                return
            now = time.monotonic()
            if now - last_call[0] < 2.5:
                return
            last_call[0] = now
            done = d.get("downloaded_bytes") or 0
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed = d.get("speed") or 0
            mb = 1024 * 1024
            if total:
                text = (f"⏳ Завантажую… {done * 100 // total}% "
                        f"({done / mb:.0f}/{total / mb:.0f} МБ · {speed / mb:.1f} МБ/с)")
            else:
                text = f"⏳ Завантажую… {done / mb:.0f} МБ · {speed / mb:.1f} МБ/с"
            try:
                progress(text)
            except Exception:
                pass

        return hook

    def _format_ladder(self, height_cap: int | None,
                       probed: dict | None) -> list[str]:
        """Селектори форматів: перший — розрахований за метаданими, далі фолбеки."""
        limit = self.config.max_file_mb
        cap = f"[height<={height_cap}]" if height_cap else ""
        ladder = []

        # Якщо є метадані з розмірами — обираємо висоту одразу, без перебору.
        best_h = self._best_height_under_limit(probed) if probed else None
        if best_h and (not height_cap or best_h <= height_cap):
            ladder.append(f"bv*[height<={best_h}]+ba/b[height<={best_h}]")

        ladder += [
            f"bv*{cap}[filesize<{limit}M]+ba/b{cap}[filesize<{limit}M]/bv*{cap}+ba/b{cap}",
            "bv*[height<=720]+ba/b[height<=720]",
            "bv*[height<=480]+ba/b[height<=480]",
            "b",
        ]
        return ladder

    def _best_height_under_limit(self, info: dict) -> int | None:
        """За реальними розмірами форматів знаходить максимальну висоту,
        сумарний розмір якої влазить у ліміт."""
        formats = info.get("formats") or []
        duration = info.get("duration") or 0
        limit_bytes = self.config.max_file_mb * 1024 * 1024 * 0.95

        def est_size(f: dict) -> float | None:
            size = f.get("filesize") or f.get("filesize_approx")
            if size:
                return float(size)
            tbr = f.get("tbr")  # кбіт/с
            if tbr and duration:
                return tbr * 1000 / 8 * duration
            return None

        audio_sizes = [est_size(f) for f in formats
                       if f.get("acodec") not in (None, "none")
                       and f.get("vcodec") in (None, "none")]
        audio_size = min((s for s in audio_sizes if s), default=0)

        best = None
        for f in formats:
            if f.get("vcodec") in (None, "none") or not f.get("height"):
                continue
            size = est_size(f)
            if size is None:
                continue
            total = size + (0 if f.get("acodec") not in (None, "none") else audio_size)
            if total <= limit_bytes:
                best = max(best or 0, f["height"])
        return best

    def _download_sync(self, link: MediaLink, workdir: Path,
                       progress: ProgressCallback | None = None,
                       height_cap: int | None = None,
                       probed: dict | None = None) -> DownloadResult:
        limit = self.config.max_file_mb
        info: dict | None = None
        last_err: Exception | None = None

        for fmt in self._format_ladder(height_cap, probed):
            self._clear_dir(workdir)
            opts = self._base_opts(workdir) | {
                "format": fmt,
                "merge_output_format": "mp4",
            }
            if progress:
                opts["progress_hooks"] = [self._progress_hook(progress)]
            try:
                info = self._extract_with_retry(link.url, opts)
            except yt_dlp.utils.DownloadError as e:
                last_err = e
                log.info("yt-dlp (%s) не впорався: %s", fmt, e)
                continue

            files = self._collect_files(workdir)
            if not files:
                continue
            if all(self._size_mb(f) <= limit for f in files):
                return self._build_result(link, info, files, workdir)
            # Файл завеликий — пробуємо нижчу якість.
            log.info("Файл >%d МБ, знижуємо якість (%s)", limit, fmt)

        # Відео не вийшло — можливо, це фото-пост/карусель.
        if link.gallery_capable:
            result = self._gallery_dl(link, workdir, info)
            if result:
                return result

        files = self._collect_files(workdir)
        if files:  # останній формат дав файл, хай і великий — віддамо помилку розміру
            raise DownloadError(f"Файл завеликий для Telegram (ліміт {limit} МБ).")
        if last_err:
            raise classify_error(last_err)
        raise DownloadError("Не знайшов медіа за посиланням.")

    def _extract_with_retry(self, url: str, opts: dict) -> dict:
        """Одна спроба + повтор при мережевому збої або з іншим cookies-профілем."""
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            retry_opts = None
            if _is_transient(e):
                time.sleep(2)
                retry_opts = opts
            elif (classify_error(e).needs_auth
                  and len(self.config.cookies_files) > 1):
                retry_opts = opts | {"cookiefile": self._next_cookiefile()}
            if retry_opts is None:
                raise
            with yt_dlp.YoutubeDL(retry_opts) as ydl:
                return ydl.extract_info(url, download=True)

    def _download_audio_sync(self, url: str, workdir: Path) -> DownloadResult:
        opts = self._base_opts(workdir) | {
            "format": "bestaudio/best",
            "playlist_items": "1",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
        }
        try:
            info = self._extract_with_retry(url, opts)
        except yt_dlp.utils.DownloadError as e:
            raise classify_error(e) from e

        files = [f for f in self._collect_files(workdir) if f.suffix.lower() in AUDIO_EXT]
        if not files:
            raise DownloadError("Аудіодоріжку не знайдено.")
        info = self._flatten_info(info)
        return DownloadResult(
            kind="audio",
            files=files[:1],
            title=info.get("title") or "audio",
            uploader=info.get("uploader") or info.get("channel") or "",
            url=url,
            workdir=workdir,
        )

    # ---------- gallery-dl (каруселі, фото-пости) ----------

    def _gallery_dl(self, link: MediaLink, workdir: Path,
                    info: dict | None) -> DownloadResult | None:
        self._clear_dir(workdir)
        cmd = ["gallery-dl", "--directory", str(workdir), "--range", "1-10", link.url]
        cookiefile = self._next_cookiefile()
        if cookiefile:
            cmd[1:1] = ["--cookies", cookiefile]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=180, check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            log.warning("gallery-dl не запустився: %s", e)
            return None
        if proc.returncode != 0:
            log.info("gallery-dl exit=%s: %s", proc.returncode, proc.stderr[-500:])

        files = self._collect_files(workdir)
        images = [f for f in files if f.suffix.lower() in IMAGE_EXT]
        videos = [f for f in files if f.suffix.lower() in VIDEO_EXT
                  and self._size_mb(f) <= self.config.max_file_mb]
        if not images and not videos:
            return None

        result = self._build_result(link, info, images or videos, workdir)
        if images:
            result.kind = "images"
            result.extra_videos = videos
            result.audio_available = bool(videos)
        return result

    # ---------- допоміжне ----------

    def _build_result(self, link: MediaLink, info: dict | None,
                      files: list[Path], workdir: Path) -> DownloadResult:
        info = self._flatten_info(info or {})
        kind = "video" if files[0].suffix.lower() in VIDEO_EXT else "images"
        return DownloadResult(
            kind=kind,
            files=files,
            title=info.get("title") or "",
            description=info.get("description") or "",
            uploader=info.get("uploader") or info.get("channel")
                     or info.get("uploader_id") or "",
            url=link.url,
            workdir=workdir,
            audio_available=(kind == "video"),
        )

    @staticmethod
    def _flatten_info(info: dict) -> dict:
        """Для плейлистів бере метадані першого елемента як доповнення."""
        if info.get("entries"):
            first = next((e for e in info["entries"] if e), {})
            merged = dict(first)
            for k, v in info.items():
                if k != "entries" and v and not merged.get(k):
                    merged[k] = v
            return merged
        return info

    def _new_workdir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix=f"dl-{uuid.uuid4().hex[:8]}-",
                                     dir=self.config.download_dir))

    @staticmethod
    def _clear_dir(d: Path) -> None:
        for f in d.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
            else:
                shutil.rmtree(f, ignore_errors=True)

    @staticmethod
    def _collect_files(workdir: Path) -> list[Path]:
        return [f for f in sorted(workdir.rglob("*"))
                if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT | AUDIO_EXT]

    @staticmethod
    def _size_mb(f: Path) -> float:
        return f.stat().st_size / (1024 * 1024)
