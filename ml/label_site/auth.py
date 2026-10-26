"""Logins for the labelling site (python -m label_site). Standard library only.

The site is reachable from the internet (Tailscale Funnel), so:
  - passwords are stored only as PBKDF2-SHA256 hashes with a per-user salt (users.json);
  - a login is a signed cookie (user, expiry, HMAC with a secret kept beside users.json), so a restart
    doesn't log everyone out and nothing about sessions is stored;
  - every POST needs a CSRF token tied to the session, sent in a header;
  - a name is locked for LOCK_S after MAX_FAILS wrong passwords, and all logins slow down when many fail at once.

    python -m label_site users nina sunny patti ... [--admin nina]    # users.json, secret and passwords.txt
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from pathlib import Path

ITERATIONS = 310_000  # OWASP 2023 figure for PBKDF2-SHA256; ~0.3 s per check on a Pi 5
SESSION_S = 14 * 24 * 3600
MAX_FAILS = 5
LOCK_S = 15 * 60
GLOBAL_FAILS_PER_MIN = 30
COOKIE = "labels_session"


def hash_password(password: str, salt: bytes | None = None, iterations: int = ITERATIONS) -> dict:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": iterations}


def check_password(password: str, rec: dict) -> bool:
    got = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(rec["salt"]), int(rec["iterations"]))
    return hmac.compare_digest(got.hex(), rec["hash"])


def new_password() -> str:
    """Four groups of five letters and digits (~100 bits), easy to read out or paste."""
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"  # no 0/o, 1/l/i
    return "-".join("".join(secrets.choice(alphabet) for _ in range(5)) for _ in range(4))


class Auth:
    def __init__(self, users_path: Path, secret_path: Path):
        self.users_path = users_path
        self.users: dict[str, dict] = json.loads(users_path.read_text())
        self.secret = bytes.fromhex(secret_path.read_text().strip())
        self.lock = threading.Lock()
        self.fails: dict[str, list[float]] = {}
        self.recent_fails: list[float] = []
        # Checked when the name is unknown too, so a wrong name takes as long as a wrong password.
        self._dummy = hash_password(secrets.token_hex(8))

    def is_admin(self, name: str) -> bool:
        return bool(self.users.get(name, {}).get("admin"))

    # -- passwords and lockout
    def locked(self, name: str, now: float | None = None) -> bool:
        now = now or time.time()
        with self.lock:
            recent = [t for t in self.fails.get(name, []) if now - t < LOCK_S]
            self.fails[name] = recent
            return len(recent) >= MAX_FAILS

    def login(self, name: str, password: str, now: float | None = None) -> str | None:
        """The user's name if the password is right, else None. Records failures."""
        now = now or time.time()
        name = name.strip().lower()
        if self.locked(name, now):
            return None
        with self.lock:
            self.recent_fails = [t for t in self.recent_fails if now - t < 60]
            busy = len(self.recent_fails) >= GLOBAL_FAILS_PER_MIN
        if busy:
            time.sleep(2)  # someone is guessing: slow every attempt down
        ok = check_password(password, self.users.get(name, self._dummy)) and name in self.users
        if ok:
            with self.lock:
                self.fails.pop(name, None)
            return name
        with self.lock:
            self.fails.setdefault(name, []).append(now)
            self.recent_fails.append(now)
        return None

    # -- sessions
    def _sign(self, msg: str) -> str:
        return hmac.new(self.secret, msg.encode(), hashlib.sha256).hexdigest()

    def make_cookie(self, name: str, now: float | None = None) -> str:
        exp = int((now or time.time()) + SESSION_S)
        msg = f"{name}|{exp}"
        return f"{msg}|{self._sign(msg)}"

    def user_of(self, cookie_value: str | None, now: float | None = None) -> str | None:
        if not cookie_value or cookie_value.count("|") != 2:
            return None
        name, exp, sig = cookie_value.split("|")
        if not hmac.compare_digest(sig, self._sign(f"{name}|{exp}")):
            return None
        if not exp.isdigit() or int(exp) < (now or time.time()) or name not in self.users:
            return None
        return name

    def csrf(self, cookie_value: str) -> str:
        return self._sign("csrf|" + cookie_value)

    def csrf_ok(self, cookie_value: str | None, token: str | None) -> bool:
        return bool(cookie_value and token) and hmac.compare_digest(self.csrf(cookie_value), token)  # type: ignore[arg-type]


def read_cookie(header: str | None, name: str = COOKIE) -> str | None:
    for part in (header or "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == name:
            return v
    return None
