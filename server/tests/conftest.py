import pytest

from sentinel_server import db as db_mod, settings as settings_mod


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("SENTINEL_DATABASE_URL", raising=False)
    monkeypatch.setenv("SENTINEL_DETECTOR", "baseline")
    monkeypatch.setenv("SENTINEL_CLASSIFIER", "none")
    monkeypatch.chdir(tmp_path)
    settings_mod.reset_settings()
    db_mod.reset_engine()
    db_mod.init_db()
    yield
    db_mod.reset_engine()
    settings_mod.reset_settings()
