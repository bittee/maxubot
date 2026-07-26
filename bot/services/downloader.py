"""Завантаження медіа: yt-dlp для відео/аудіо, gallery-dl для фото-каруселей."""
import asyncio
import logging
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yt_dlp

from bot.config import Config
from bot.services.extractor import MediaLink

log = logging.getLogger(__name__)

VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AUDIO_EXT = {".mp3", ".m4a", ".ogg", ".opus", ".flac", ".wav"}


class DownloadError(Exception):
    """Не вдалося завантажити медіа за посиланням."""


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

    # ---------- публічний API ----------

    async def download(self, link: MediaLink) -> DownloadResult:
        """Завантажує контент за посиланням: спершу yt-dlp, потім gallery-dl."""
        async with self._sem:
            workdir = self._new_workdir()
            try:
                return await asyncio.to_thread(self._download_sync, link, workdir)
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

    def _base_opts(self, workdir: Path) -> dict:
        opts = {
            "outtmpl": str(workdir / "%(title).80B [%(id)s].%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "noplaylist": False,
            "playlist_items": "1-10",
            "restrictfilenames": False,
            "socket_timeout": 30,
            "retries": 3,
            "concurrent_fragment_downloads": 4,
        }
        if self.config.cookies_file:
            opts["cookiefile"] = self.config.cookies_file
        return opts

    def _download_sync(self, link: MediaLink, workdir: Path) -> DownloadResult:
        limit = self.config.max_file_mb
        # Від найкращої якості, що влазить у ліміт, до найгіршої.
        format_ladder = [
            f"bv*[filesize<{limit}M]+ba[filesize<10M]/b[filesize<{limit}M]",
            "bv*[height<=720]+ba/b[height<=720]",
            "bv*[height<=480]+ba/b[height<=480]",
            "b",
        ]
        info: dict | None = None
        last_err: Exception | None = None

        for fmt in format_ladder:
            self._clear_dir(workdir)
            opts = self._base_opts(workdir) | {
                "format": fmt,
                "merge_output_format": "mp4",
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link.url, download=True)
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
            raise DownloadError(
                f"Файл завеликий для Telegram (ліміт {limit} МБ)."
            )
        raise DownloadError(str(last_err) if last_err else "Не знайшов медіа за посиланням.")

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
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Не вдалося витягти аудіо: {e}") from e

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
        if self.config.cookies_file:
            cmd[1:1] = ["--cookies", self.config.cookies_file]
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
        d = Path(tempfile.mkdtemp(prefix=f"dl-{uuid.uuid4().hex[:8]}-",
                                  dir=self.config.download_dir))
        return d

    @staticmethod
    def _clear_dir(d: Path) -> None:
        for f in d.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
            else:
                shutil.rmtree(f, ignore_errors=True)

    @staticmethod
    def _collect_files(workdir: Path) -> list[Path]:
        files = [f for f in sorted(workdir.rglob("*"))
                 if f.is_file() and f.suffix.lower() in VIDEO_EXT | IMAGE_EXT | AUDIO_EXT]
        return files

    @staticmethod
    def _size_mb(f: Path) -> float:
        return f.stat().st_size / (1024 * 1024)
