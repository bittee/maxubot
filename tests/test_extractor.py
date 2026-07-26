from bot.services.extractor import find_media_links


def test_finds_single_link():
    links = find_media_links("глянь https://www.tiktok.com/@user/video/123456")
    assert len(links) == 1
    assert links[0].platform == "TikTok"


def test_finds_multiple_platforms():
    text = (
        "https://www.instagram.com/p/ABC123/ і ще "
        "https://x.com/user/status/999 та https://youtu.be/dQw4w9WgXcQ"
    )
    platforms = [link.platform for link in find_media_links(text)]
    assert platforms == ["Instagram", "X", "YouTube"]


def test_ignores_unsupported_and_plain_text():
    assert find_media_links("просто текст без лінків") == []
    assert find_media_links("https://example.com/page") == []


def test_strips_trailing_punctuation():
    links = find_media_links("дивись (https://youtu.be/abc123).")
    assert links[0].url == "https://youtu.be/abc123"


def test_no_duplicates():
    url = "https://www.tiktok.com/@u/video/1"
    assert len(find_media_links(f"{url} {url}")) == 1


def test_gallery_capable():
    ig = find_media_links("https://www.instagram.com/p/ABC/")[0]
    yt = find_media_links("https://youtu.be/abc")[0]
    assert ig.gallery_capable
    assert not yt.gallery_capable


def test_subdomain_matching_not_fooled():
    # Хост, що лише містить назву платформи, не повинен матчитись.
    assert find_media_links("https://notinstagram.com.evil.io/x") == []
    assert find_media_links("https://m.tiktok.com/v/123") != []
