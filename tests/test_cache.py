import asyncio

from bot.services.cache import (
    CachedMedia,
    MediaCache,
    cache_key,
    normalize_url,
)


def test_normalize_strips_tracking_params():
    a = normalize_url("https://www.tiktok.com/@u/video/1?is_from_webapp=1&sender_device=pc")
    b = normalize_url("https://tiktok.com/@u/video/1")
    assert a == b


def test_normalize_utm_and_igsh():
    a = normalize_url("https://www.instagram.com/p/ABC/?igsh=xyz&utm_source=share")
    b = normalize_url("https://instagram.com/p/ABC")
    assert a == b


def test_normalize_twitter_to_x():
    a = normalize_url("https://twitter.com/user/status/123?s=20&t=abc")
    b = normalize_url("https://x.com/user/status/123")
    assert a == b


def test_normalize_mobile_hosts():
    a = normalize_url("https://m.tiktok.com/v/1")
    b = normalize_url("https://tiktok.com/v/1")
    assert a == b


def test_meaningful_params_kept():
    a = normalize_url("https://youtube.com/watch?v=abc")
    b = normalize_url("https://youtube.com/watch?v=def")
    assert a != b


def test_cache_key_variants_differ():
    url = "https://youtu.be/abc"
    assert cache_key(url) != cache_key(url, "audio")


def test_cached_media_roundtrip():
    entry = CachedMedia(
        kind="images",
        items=[("photo", "id1"), ("video", "id2")],
        caption="<b>test</b>",
        audio_available=True,
    )
    restored = CachedMedia.from_json(entry.to_json())
    assert restored == entry


def test_memory_cache_put_get_invalidate():
    async def run():
        cache = MediaCache(redis_url=None)
        await cache.connect()
        key = cache_key("https://youtu.be/abc")
        assert await cache.get(key) is None
        entry = CachedMedia(kind="video", items=[("video", "fid")])
        await cache.put(key, entry)
        assert await cache.get(key) == entry
        await cache.invalidate(key)
        assert await cache.get(key) is None

    asyncio.run(run())
