from bot.services.downloader import DownloadError, classify_error


def test_classify_auth():
    err = classify_error(Exception("ERROR: Login required to access this content"))
    assert isinstance(err, DownloadError)
    assert err.needs_auth


def test_classify_private():
    err = classify_error(Exception("This account is private"))
    assert "приватний" in str(err)
    assert not err.needs_auth


def test_classify_geo():
    err = classify_error(Exception("Video not available in your country"))
    assert "геоблок" in str(err)


def test_classify_deleted():
    err = classify_error(Exception("Video unavailable: removed by uploader"))
    assert "видалено" in str(err)


def test_classify_generic():
    err = classify_error(Exception("some weird internal thing"))
    assert "Не вдалося" in str(err)


def test_best_height_under_limit():
    from bot.services.downloader import Downloader

    picker = Downloader.__new__(Downloader)  # без __init__ — тестуємо чистий метод

    class Cfg:
        max_file_mb = 50

    picker.config = Cfg()
    info = {
        "duration": 100,
        "formats": [
            {"vcodec": "none", "acodec": "mp4a", "filesize": 2 * 1024 * 1024},
            {"vcodec": "avc1", "acodec": "none", "height": 480,
             "filesize": 20 * 1024 * 1024},
            {"vcodec": "avc1", "acodec": "none", "height": 720,
             "filesize": 40 * 1024 * 1024},
            {"vcodec": "avc1", "acodec": "none", "height": 1080,
             "filesize": 90 * 1024 * 1024},
        ],
    }
    assert picker._best_height_under_limit(info) == 720

    class SmallCfg:
        max_file_mb = 25

    picker.config = SmallCfg()
    assert picker._best_height_under_limit(info) == 480
