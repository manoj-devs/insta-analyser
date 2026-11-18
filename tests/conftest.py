import os, re, sys, tempfile
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import config

_TMP = tempfile.mkdtemp()
config.UPLOAD_DIR = os.path.join(_TMP, "uploads"); os.makedirs(config.UPLOAD_DIR, exist_ok=True)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
import main                                                  # noqa: E402  (after the environment is prepared)
from app import db, otp                                      # noqa: E402


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    """Every test gets its own empty auth database, an empty development inbox and the normal OTP settings."""
    n = len(os.listdir(_TMP))
    monkeypatch.setattr(config, "AUTH_DB", os.path.join(_TMP, f"auth_{n}.db"))
    db.init(); otp.OUTBOX.clear(); main.HITS.clear()
    from app.services import directory; directory._CACHE.update(rows=None, ver=directory._CACHE['ver'] + 1)   # the directory cache belongs to one database
    for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASS", "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(otp, "COOLDOWN", 0); monkeypatch.setattr(otp, "MAX_SENDS", 1000)
    yield


def last_code(email):
    """The newest code sent to this address, read from the in-memory development inbox (the page never receives it)."""
    for m in otp.OUTBOX:
        if m["to"] == email.lower(): return re.search(r"\b(\d{6})\b", m["body"]).group(1)
    raise AssertionError("no message for " + email)
