import sentry_sdk

from sentinel_server import monitoring


def test_off_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: (_ for _ in ()).throw(AssertionError("init called")))
    assert monitoring.init_sentry("test") is False


def test_on_with_dsn_sends_no_pii(monkeypatch):
    seen = {}
    monkeypatch.setenv("SENTRY_DSN", "https://key@o0.ingest.sentry.io/0")
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: seen.update(kw))
    monkeypatch.setattr(sentry_sdk, "set_tag", lambda k, v: seen.update({k: v}))
    assert monitoring.init_sentry("test") is True
    assert seen["send_default_pii"] is False and seen["component"] == "test"
