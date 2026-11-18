import re
"""Run:  python -m pytest -q   (uses a temporary auth database, never your real one)"""
from fastapi.testclient import TestClient
from tests.conftest import last_code
import main

H = {"X-Requested-With": "fetch"}
PW = "Str0ngPass9"
SIGNUP = dict(name="Test User", email="t@example.com", password=PW, phone="+919876543210", country="India", user_type="creator", handle="@Test_User", interests="food", consent=True)


def post(c, url, **b): return c.post(url, json=b, headers=H)


def signin(c, email, pw):
    """Sign in the way the page does: password first, then the pop-up code when the server asks for it (new device)."""
    r = post(c, "/api/auth/login", email=email, password=pw)
    if r.status_code == 200 and r.json().get("needs_otp"):
        r = post(c, "/api/auth/verify", email=email, code=last_code(email), ticket=r.json()["ticket"])
    return r


def test_everything():
    with TestClient(main.app) as admin, TestClient(main.app) as user:
        # ---- pages and protection
        assert user.get("/").status_code == 200 and user.get("/admin").status_code == 200
        assert user.get("/api/auth/me").status_code == 401 and user.get("/api/admin/overview").status_code == 401
        assert user.post("/api/auth/login", json={}).status_code == 403            # missing header

        # ---- admin portal: first sign-in = password + emailed code (demo shows it) ... default password must be changed
        r = post(admin, "/api/admin/auth/login", email="admin@instawarehouse.com", password="Admin@12345").json()
        assert r["step"] == "done" and r["user"]["must_change"]                      # first run: skips code, forces new password
        assert admin.get("/api/admin/overview").status_code == 403                   # blocked until password changed
        assert post(admin, "/api/admin/auth/password", current="Admin@12345", new="short").status_code == 400
        assert post(admin, "/api/admin/auth/password", current="Wrong", new="Adm1nStrong!x").status_code == 400
        assert post(admin, "/api/admin/auth/password", current="Admin@12345", new="Adm1nStrong!x").status_code == 200
        assert admin.get("/api/admin/overview").status_code == 200
        admin.post("/api/admin/auth/logout", headers=H); assert admin.get("/api/admin/overview").status_code == 401
        # second sign-in needs the code
        r = post(admin, "/api/admin/auth/login", email="admin@instawarehouse.com", password="Adm1nStrong!x").json()
        assert r["step"] == "code" and "demo_otp" not in r and r["ticket"] and not re.search(r"\b\d{6}\b", str(r))
        assert admin.get("/api/admin/overview").status_code == 401
        assert post(admin, "/api/admin/auth/verify", email="admin@instawarehouse.com", code="000000", ticket=r["ticket"]).status_code == 400
        assert post(admin, "/api/admin/auth/verify", email="admin@instawarehouse.com", code=last_code("admin@instawarehouse.com"), ticket=r["ticket"]).status_code == 200
        assert admin.get("/api/admin/auth/me").json()["role"] == "admin"

        # ---- portals are separate
        assert post(user, "/api/auth/login", email="admin@instawarehouse.com", password="Adm1nStrong!x").status_code == 403     # admin on user portal
        assert user.get("/api/admin/overview").status_code == 401
        assert admin.get("/api/auth/me").status_code == 401                                      # admin cookie is not a user session

        # ---- user sign-up validation
        bad = lambda **k: post(user, "/api/auth/signup", **{**SIGNUP, **k}).status_code
        assert bad(password="abc") == 400 and bad(password="Password123") == 400 and bad(password="Test1234x") == 400   # weak / common / contains email name
        assert bad(email="x@mailinator.com") == 400 and bad(email="nope") == 400
        assert bad(phone="12ab") == 400 and bad(country="") == 400 and bad(user_type="alien") == 400 and bad(handle="bad handle!") == 400
        assert bad(consent=False) == 400
        s = post(user, "/api/auth/signup", **SIGNUP).json(); assert s["ok"] and "demo_otp" not in s and s["ticket"] and s["ttl"] == 300
        assert user.get("/api/auth/me").status_code == 401
        r = post(user, "/api/auth/login", email="t@example.com", password=PW).json(); assert r["needs_verification"]      # unverified -> new code
        assert post(user, "/api/auth/verify", email="t@example.com", code="111111", ticket=r["ticket"]).status_code == 400
        v = post(user, "/api/auth/verify", email="t@example.com", code=last_code("t@example.com"), ticket=r["ticket"]); assert v.status_code == 200 and v.json()["user"]["role"] == "user"
        assert user.get("/api/auth/me").json()["email"] == "t@example.com"
        assert post(user, "/api/auth/signup", **SIGNUP).status_code == 409

        # ---- role separation
        for u in ("/api/admin/overview", "/api/admin/users", "/api/admin/audit", "/api/admin/analyses", "/api/data/combined"):
            assert user.get(u).status_code in (401, 403), u
        assert post(user, "/api/etl/run").status_code in (401, 403)
        assert user.get("/api/data/sample").status_code == 200 and len(user.get("/api/data/sample").json()["rows"]) == 100

        # ---- analyser saves history, what-if does not
        a = dict(handle="@mine", followers=5000, category="arts & culture", account_type="personal", avg_likes=80, avg_comments=3, hashtags_per_post=8, posts_per_week=3)
        cats = user.get("/api/meta/categories").json(); a["category"] = cats[0]
        assert post(user, "/api/analyse", **a).status_code == 200
        assert post(user, "/api/analyse", **a, save=False).status_code == 200
        h = user.get("/api/account/history").json(); assert len(h) == 1 and h[0]["handle"] == "@mine"
        # ---- data mining (models are trained once and reused)
        from app.services import mining
        if not mining.available(): mining.train(lambda m: None)          # about a minute the first time
        an = post(user, "/api/analyse", **a, save=False).json()
        assert an["prediction"]["next_likes"] > 0 and an["persona"]["name"] and an["fee"]["usd"]["mid"] > 0 and an["fee"]["inr"]["high"] > an["fee"]["inr"]["low"]
        assert post(user, "/api/caption/check", caption="What is your favourite pizza topping? Tell us below").json()["score"] >= 0
        inf = dict(name="Test Celeb", kind="celebrity", followers=30_000_000, category="sports", avg_likes=2_500_000, avg_comments=20_000, caption="Game day! #win #team", hour=18, weekday=5, post_likes=3_000_000, post_comments=25_000)
        r = post(user, "/api/influencer/analyse", **inf); assert r.status_code == 200, r.text
        j = r.json(); assert j["fee_next"]["celebrity_reference"] and not j["fee_next"]["extrapolated"] and j["this_post"]["fee"]["usd"]["mid"] > 100_000 and j["model_in_range"] is not None
        assert post(user, "/api/influencer/analyse", **{**inf, "category": "nonsense"}).status_code == 400
        # famous accounts typed with followers only (engagement unknown) must still work and land near public rate estimates
        for nm, fol, cat, lo, hi in [("Cristiano Ronaldo", 679_000_000, "sports", 2_500_000, 7_000_000), ("Virat Kohli", 271_000_000, "sports", 1_000_000, 2_500_000),
                                     ("Rafael Nadal", 18_000_000, "sports", 60_000, 200_000)]:
            c = post(user, "/api/influencer/analyse", name=nm, kind="athlete", followers=fol, category=cat, save=False)
            assert c.status_code == 200, c.text; cj = c.json()
            assert cj["engagement_assumed"] and lo < cj["fee_next"]["usd"]["mid"] < hi, (nm, cj["fee_next"]["usd"])
            assert cj["fee_next"]["usd"]["low"] < cj["fee_next"]["usd"]["mid"] < cj["fee_next"]["usd"]["high"] and cj["prediction"]["next_likes"] > 0
        assert user.get("/api/mining/report").status_code == 200 and "items" not in user.get("/api/mining/report").json()["breakouts"]
        assert user.get("/api/admin/mining/breakouts").status_code in (401, 403) and post(user, "/api/admin/mining/train").status_code in (401, 403)
        assert post(user, "/api/track", page="analyser").status_code == 200
        post(user, "/api/account/feedback", rating=5, topic="analyser", message="Nice tool")
        assert user.get("/api/account/export").json()["profile"]["email"] == "t@example.com"

        # ---- profile, password change, devices
        p = user.put("/api/account/profile", json=dict(name="Test U", phone="", country="India", user_type="business", handle="x_y", interests=""), headers=H); assert p.status_code == 200 and p.json()["handle"] == "@x_y"
        assert len(user.get("/api/account/sessions").json()) == 1
        with TestClient(main.app) as phone:                                     # second device
            nd = post(phone, "/api/auth/login", email="t@example.com", password=PW).json(); assert nd["needs_otp"] and phone.get("/api/auth/me").status_code == 401   # new device: code first
            assert signin(phone, "t@example.com", PW).status_code == 200 and phone.get("/api/auth/me").status_code == 200
            assert len(user.get("/api/account/sessions").json()) == 2
            assert post(user, "/api/account/password", current=PW, new="NewPassw0rdZ").status_code == 200
            assert phone.get("/api/auth/me").status_code == 401                 # other device signed out by the change
        assert user.get("/api/auth/me").status_code == 200
        user.post("/api/auth/logout", headers=H); assert user.get("/api/auth/me").status_code == 401

        # ---- forgot / reset password (pop-up checks the code, then a second step sets the new password)
        g = post(user, "/api/auth/forgot", email="nobody@example.com").json(); assert g["ticket"] and "demo_otp" not in g          # same answer, no account guessing
        f = post(user, "/api/auth/forgot", email="t@example.com").json(); assert f["ticket"] and "demo_otp" not in f
        assert post(user, "/api/auth/reset", email="t@example.com", ticket=f["ticket"], password="Another1Pass").status_code == 400    # code not entered yet
        assert post(user, "/api/auth/reset/verify", email="t@example.com", code="000000", ticket=f["ticket"]).status_code == 400
        assert post(user, "/api/auth/reset/verify", email="t@example.com", code=last_code("t@example.com"), ticket="wrong-ticket").status_code == 400
        assert post(user, "/api/auth/reset/verify", email="t@example.com", code=last_code("t@example.com"), ticket=f["ticket"]).status_code == 200
        assert post(user, "/api/auth/reset", email="t@example.com", ticket=f["ticket"], password="weak").status_code == 400
        assert post(user, "/api/auth/reset", email="t@example.com", ticket=f["ticket"], password="Another1Pass").status_code == 200
        assert post(user, "/api/auth/reset", email="t@example.com", ticket=f["ticket"], password="Another1Pass2").status_code == 400    # one use only
        assert post(user, "/api/auth/login", email="t@example.com", password="NewPassw0rdZ").status_code == 401
        assert signin(user, "t@example.com", "Another1Pass").status_code == 200                # reset forgot every trusted device: code again

        # ---- admin sees the collected data
        ov = admin.get("/api/admin/overview").json(); k = ov["kpi"]
        assert k["users"] == 1 and k["analyses"] == 1 and k["feedback"] == 1 and ov["dist"]["country"][0][0] == "India"
        us = admin.get("/api/admin/users").json(); uid = us[0]["id"]; assert us[0]["analyses"] == 1
        d = admin.get(f"/api/admin/users/{uid}").json(); assert d["profile"]["phone"] is None and d["analyses"][0]["handle"] == "@mine"
        assert admin.get("/api/admin/analyses").json()["agg"]["total"] == 1
        assert "t@example.com" in admin.get("/api/admin/users.csv").text and "@mine" in admin.get("/api/admin/analyses.csv").text
        assert len(admin.get("/api/admin/feedback").json()) == 1
        assert len(admin.get("/api/admin/mining/breakouts").json()["items"]) == 100 and len(admin.get("/api/admin/lookups").json()) == 1

        # ---- block / force logout / delete
        assert post(admin, f"/api/admin/users/{uid}/block", reason="x").status_code == 400
        assert post(admin, f"/api/admin/users/{uid}/logout").json()["closed"] >= 1
        assert user.get("/api/auth/me").status_code == 401
        signin(user, "t@example.com", "Another1Pass")
        assert post(admin, f"/api/admin/users/{uid}/block", reason="spam posting").status_code == 200
        assert user.get("/api/auth/me").status_code == 401
        m = post(user, "/api/auth/login", email="t@example.com", password="Another1Pass"); assert m.status_code == 403 and "spam posting" in m.json()["detail"]
        assert post(admin, f"/api/admin/users/{uid}/unblock").status_code == 200
        assert signin(user, "t@example.com", "Another1Pass").status_code == 200
        assert post(admin, f"/api/admin/users/{uid}/delete", reason="policy breach").status_code == 200
        assert post(user, "/api/auth/login", email="t@example.com", password="Another1Pass").status_code == 403
        assert post(admin, "/api/admin/users/1/block", reason="no way").status_code == 400                # admins are protected

        # ---- admin accounts
        assert post(admin, "/api/admin/admins", name="Second Admin", email="a2@example.com", password="Zx9Qr7!mnop").status_code == 200
        with TestClient(main.app) as a2:
            r = post(a2, "/api/admin/auth/login", email="a2@example.com", password="Zx9Qr7!mnop").json(); assert r["step"] == "done" and r["user"]["must_change"]

        # ---- lockout + alerts
        with TestClient(main.app) as x:
            for _ in range(5): post(x, "/api/auth/login", email="victim@example.com", password="bad")
            assert post(x, "/api/auth/login", email="victim@example.com", password="bad").status_code == 429
        assert any(a["type"] == "Many failed logins" for a in admin.get("/api/admin/alerts").json())
        assert any(o["email"] == "admin@instawarehouse.com" for o in admin.get("/api/admin/online").json())
        assert "login_success" in admin.get("/api/admin/audit.csv").text
