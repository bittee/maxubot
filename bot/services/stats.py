"""Проста статистика роботи бота для /stats (в памʼяті процесу)."""
import time
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Stats:
    started_at: float = field(default_factory=time.monotonic)
    downloads_ok: Counter = field(default_factory=Counter)     # платформа → к-сть
    downloads_err: Counter = field(default_factory=Counter)    # платформа → к-сть
    cache_hits: int = 0
    audio_extracted: int = 0
    total_download_seconds: float = 0.0

    def record_ok(self, platform: str, seconds: float) -> None:
        self.downloads_ok[platform] += 1
        self.total_download_seconds += seconds

    def record_err(self, platform: str) -> None:
        self.downloads_err[platform] += 1

    def record_cache_hit(self) -> None:
        self.cache_hits += 1

    def record_audio(self) -> None:
        self.audio_extracted += 1

    def render(self) -> str:
        ok = sum(self.downloads_ok.values())
        err = sum(self.downloads_err.values())
        uptime_h = (time.monotonic() - self.started_at) / 3600
        avg = self.total_download_seconds / ok if ok else 0

        lines = [
            "📊 <b>Статистика</b>",
            f"⏱ Аптайм: {uptime_h:.1f} год",
            f"✅ Завантажень: {ok} (середній час {avg:.1f} с)",
            f"⚡ Кеш-хітів: {self.cache_hits}",
            f"🎵 Аудіо витягнуто: {self.audio_extracted}",
            f"❌ Помилок: {err}",
        ]
        if self.downloads_ok:
            top = ", ".join(f"{p}: {n}" for p, n in self.downloads_ok.most_common(5))
            lines.append(f"🏆 Платформи: {top}")
        if self.downloads_err:
            top = ", ".join(f"{p}: {n}" for p, n in self.downloads_err.most_common(3))
            lines.append(f"⚠️ Помилки за платформами: {top}")
        return "\n".join(lines)
