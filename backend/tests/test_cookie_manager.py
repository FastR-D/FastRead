from app.services.cookie_manager import CookieConfigManager


def test_cookie_status_treats_mstoken_as_warning(tmp_path):
    manager = CookieConfigManager(str(tmp_path / "downloader.json"))
    manager.set("douyin", "ttwid=abc; sessionid=def")

    status = manager.status("douyin")

    assert status["configured"] is True
    assert status["valid_looking"] is True
    assert status["missing_keys"] == []
    assert status["warning_keys"] == ["msToken"]
    assert "不绝对影响使用" in status["warning_message"]


def test_cookie_status_still_requires_ttwid(tmp_path):
    manager = CookieConfigManager(str(tmp_path / "downloader.json"))
    manager.set("douyin", "sessionid=def; msToken=ghi")

    status = manager.status("douyin")

    assert status["configured"] is True
    assert status["valid_looking"] is False
    assert status["missing_keys"] == ["ttwid"]
