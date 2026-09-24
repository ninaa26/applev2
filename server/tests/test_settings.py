from sentinel_server.settings import _load_dotenv


def test_dotenv_strips_inline_comments_and_quotes(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# full-line comment\n"
        "SENTINEL_T_A=data                  # database + photos\n"
        "SENTINEL_T_B=\"has # hash\"  # comment\n"
        "SENTINEL_T_C=http://host:8000/#frag\n"
    )
    for k in ("SENTINEL_T_A", "SENTINEL_T_B", "SENTINEL_T_C"):
        monkeypatch.delenv(k, raising=False)
    _load_dotenv(env)
    import os

    assert os.environ["SENTINEL_T_A"] == "data"
    assert os.environ["SENTINEL_T_B"] == "has # hash"
    assert os.environ["SENTINEL_T_C"] == "http://host:8000/#frag"
    for k in ("SENTINEL_T_A", "SENTINEL_T_B", "SENTINEL_T_C"):
        monkeypatch.delenv(k)
