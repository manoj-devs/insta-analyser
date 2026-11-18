import time, sqlite3
from fastapi.testclient import TestClient
import main
from app import otp, config
from tests.conftest import last_code
from tests.test_auth import H, post, SIGNUP, PW


def start(c, email="o@example.com"):
    r = post(c, "/api/auth/signup", **{**SIGNUP, "email": email}); assert r.status_code == 200, r.text
    return r.json()


def test_wrong_then_right_and_never_on_screen():
    with TestClient(main.app) as c:
        s = start(c); assert "demo_otp" not in s and s["ticket"]
        r = post(c, "/api/auth/verify", email="o@example.com", code="000000", ticket=s["ticket"])
        assert r.status_code == 400 and r.headers["X-Otp-State"] == "wrong"
        assert post(c, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket="bad").status_code == 400  # ticket needed
        assert post(c, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket=s["ticket"]).status_code == 200


def test_expired(monkeypatch):
    with TestClient(main.app) as c:
        s = start(c); code = last_code("o@example.com")
        con = sqlite3.connect(config.AUTH_DB); con.execute("UPDATE users SET otp_exp=?", (time.time() - 5,)); con.commit(); con.close()
        r = post(c, "/api/auth/verify", email="o@example.com", code=code, ticket=s["ticket"])
        assert r.status_code == 400 and r.headers["X-Otp-State"] == "expired"


def test_resend_cancels_old_code():
    with TestClient(main.app) as c:
        s = start(c); old = last_code("o@example.com")
        for _ in range(20):
            r = post(c, "/api/auth/resend", email="o@example.com", ticket=s["ticket"]); assert r.status_code == 200, r.text
            s = r.json(); new = last_code("o@example.com")
            if new != old: break
        assert new != old
        assert post(c, "/api/auth/verify", email="o@example.com", code=old, ticket=s["ticket"]).status_code == 400
        assert post(c, "/api/auth/verify", email="o@example.com", code=new, ticket=s["ticket"]).status_code == 200


def test_lock_after_five_wrong():
    with TestClient(main.app) as c:
        s = start(c); good = last_code("o@example.com")
        for i in range(5): r = post(c, "/api/auth/verify", email="o@example.com", code="000001", ticket=s["ticket"])
        r = post(c, "/api/auth/verify", email="o@example.com", code=good, ticket=s["ticket"])
        assert r.status_code in (400, 429) and r.headers["X-Otp-State"] in ("locked", "expired")   # even the right code is refused now


def test_cooldown_and_hourly_limit(monkeypatch):
    monkeypatch.setattr(otp, "COOLDOWN", 30)
    with TestClient(main.app) as c:
        s = start(c)
        r = post(c, "/api/auth/resend", email="o@example.com", ticket=s["ticket"])
        assert r.status_code == 429 and r.headers["X-Otp-State"] == "cooldown" and int(r.headers["Retry-After"]) > 0
    monkeypatch.setattr(otp, "COOLDOWN", 0); monkeypatch.setattr(otp, "MAX_SENDS", 2)
    with TestClient(main.app) as c:
        s = start(c, "p@example.com"); s = post(c, "/api/auth/resend", email="p@example.com", ticket=s["ticket"]).json()
        r = post(c, "/api/auth/resend", email="p@example.com", ticket=s["ticket"])
        assert r.status_code == 429 and r.headers["X-Otp-State"] == "limit"


def test_two_devices_and_trusted_device():
    with TestClient(main.app) as a:
        s = start(a); post(a, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket=s["ticket"])
        a.post("/api/auth/logout", headers=H)
        r = post(a, "/api/auth/login", email="o@example.com", password=PW).json()
        assert not r.get("needs_otp")                                    # this device was trusted at registration
    with TestClient(main.app) as phone:                                  # a different device
        r = post(phone, "/api/auth/login", email="o@example.com", password=PW).json()
        assert r["needs_otp"] and phone.get("/api/auth/me").status_code == 401
        assert post(phone, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket=r["ticket"]).status_code == 200
        assert phone.get("/api/auth/me").status_code == 200


def test_avatar_and_devices_across_two_browsers():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 50
    with TestClient(main.app) as a:
        s = start(a); post(a, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket=s["ticket"])
        assert a.post("/api/account/avatar", content=b"not an image", headers=H).status_code == 400
        assert a.post("/api/account/avatar", content=png, headers=H).status_code == 200
        d = a.get("/api/account/devices").json(); assert len(d) == 1 and d[0]["current"]
        a.post("/api/auth/logout", headers=H)
    with TestClient(main.app) as b:                                      # another device signs in and sees the same picture
        r = post(b, "/api/auth/login", email="o@example.com", password=PW).json()
        post(b, "/api/auth/verify", email="o@example.com", code=last_code("o@example.com"), ticket=r["ticket"])
        got = b.get("/api/account/avatar"); assert got.status_code == 200 and got.content == png
        assert len(b.get("/api/account/devices").json()) == 2
        other = [x for x in b.get("/api/account/devices").json() if not x["current"]][0]
        assert b.delete(f"/api/account/devices/{other['id']}", headers=H).status_code == 200
        assert b.get("/api/account/avatar").headers["x-content-type-options"] == "nosniff"
