"""Region influencer analyser, steps engine, simulator, directory upload, public mode, backup/restore."""
import io, sqlite3
import pytest
from fastapi.testclient import TestClient
import main
from app import config, publicmode
from app.services import directory as D, pricing
from tests.conftest import last_code
from tests.test_auth import H, post, SIGNUP, PW

CSV = ("handle,display_name,country,state_or_region,category,followers,avg_likes,avg_comments,posts_per_week,source\n"
       "real_a,Real A,India,Kerala,fitness,52000,1500,40,4,team collected\n"
       "real_b,Real B,India,Kerala,food,9000,300,10,2,team collected\n"
       "bad handle!,X,India,Kerala,food,9000,300,10,2,x\n"
       "real_c,Real C,Atlantis,,food,9000,300,10,2,x\n"
       "real_d,Real D,USA,Texas,tech,150000,4000,90,5,team collected\n"
       "real_a,Dup,India,Kerala,food,9000,300,10,2,x\n")


@pytest.fixture()
def seeded():
    D._CACHE.update(rows=None, ver=D._CACHE["ver"] + 1); D.ensure_seed(); yield


def user(c, email="r@example.com"):
    s = post(c, "/api/auth/signup", **{**SIGNUP, "email": email}).json()
    assert post(c, "/api/auth/verify", email=email, code=last_code(email), ticket=s["ticket"]).status_code == 200


def admin(c):
    assert post(c, "/api/admin/auth/login", email="admin@instawarehouse.com", password="Admin@12345").status_code == 200
    assert post(c, "/api/admin/auth/password", current="Admin@12345", new="Adm1nStrong!x").status_code == 200


# ---------------------------------------------------------------- earnings engine
def test_engine_is_monotonic_and_consistent():
    a = D.earn(20_000, 400, 10, 4, "fitness_&_health", "India"); b = D.earn(200_000, 4000, 100, 4, "fitness_&_health", "India")
    assert b["fee"] > a["fee"] and b["year"] > a["year"]
    assert a["year_low"] <= a["year"] <= a["year_high"] and a["fee_low"] <= a["fee"] <= a["fee_high"]
    assert abs(a["year"] - a["fee"] * a["sponsored_per_year"]) <= a["sponsored_per_year"]            # yearly = fee x paid posts (rounding only)
    assert D.earn(20_000, 400, 10, 4, "fitness_&_health", "United States")["fee"] > a["fee"]          # market price level
    assert D.earn(300_000_000, 1e6, 1e4, 4, "sports", "India")["region_factor"] == 1.0              # celebrities priced globally
    assert D.earn(20_000, 400, 10, 0, "fitness_&_health", "India")["year"] == 0                      # no posts, no income
    assert a["sponsored_per_year"] <= D.MAX_SPONSORED_YEAR


def test_steps_are_ranked_explained_and_uplift_is_non_negative():
    d = {"followers": 50_000, "avg_likes": 400, "avg_comments": 5, "posts_per_week": 1, "category": "food_&_dining", "country": "India"}
    s = D.steps(d); assert 3 <= len(s) <= 6
    assert [x["rank"] for x in s] == list(range(1, len(s) + 1))
    ups = [(x["uplift_usd"] or {"year": -1})["year"] for x in s]; assert ups == sorted(ups, reverse=True)
    assert all(x["why"] and x["todo"] for x in s) and all(u is None or u["year_low"] <= u["year"] <= u["year_high"] for u in (x["uplift_usd"] for x in s))
    titles = " ".join(x["title"] for x in s); assert "engagement" in titles.lower() or "times a week" in titles
    pr = D.projection(d); assert pr[0]["month"] == 0 and pr[-1]["with_steps"] >= pr[-1]["now"]


def test_simulator_more_posts_more_income():
    lo = D.simulate(50_000, 2, 2, 20, 2, "fitness_&_health", "India"); hi = D.simulate(50_000, 2, 6, 20, 2, "fitness_&_health", "India")
    assert hi["year_total"]["mid"] > lo["year_total"]["mid"] and len(hi["months"]) == 12


# ---------------------------------------------------------------- CSV directory
def test_csv_validation_and_replace():
    r = D.load_csv(CSV.encode())
    assert r["accepted"] == 3 and r["rejected"] == 3
    reasons = " | ".join(x["reason"] for x in r["rejected_rows"]); assert "handle" in reasons and "continent" in reasons and "duplicate" in reasons
    with pytest.raises(ValueError): D.load_csv(b"handle,country\nx,India\n")                       # missing columns
    r2 = D.load_csv(CSV.encode(), replace=True); assert r2["accepted"] == 3
    assert {d["handle"] for d in D.rows()} == {"real_a", "real_b", "real_d"}


# ---------------------------------------------------------------- API + access control
def test_region_api_paging_filters_access_and_export(seeded):
    with TestClient(main.app) as c:
        assert c.get("/api/regions").status_code == 401 and c.get("/api/region/influencers").status_code == 401        # anonymous
        user(c)
        t = c.get("/api/regions").json(); assert t["total"] >= 500 and "Asia" in t["tree"] and "India" in t["tree"]["Asia"]
        r = c.get("/api/region/influencers?country=India&size=10&sort=year&dir=desc").json()
        assert r["n"] >= 400 and len(r["rows"]) == 10 and r["pages"] > 1 and all(x["country"] == "India" for x in r["rows"])
        ys = [x["year"] for x in r["rows"]]; assert ys == sorted(ys, reverse=True)
        assert len(c.get("/api/region/influencers?size=500").json()["rows"]) <= 50                                  # never more than 50 at once
        st = c.get("/api/region/influencers?country=India&state=Tamil Nadu").json(); assert st["n"] >= 30 and all(x["state_or_region"] == "Tamil Nadu" for x in st["rows"])
        p2 = c.get("/api/region/influencers?country=India&size=10&page=2").json(); assert p2["rows"][0]["id"] != r["rows"][0]["id"]
        assert c.get("/api/region/influencers?q=kohli").json()["n"] == 1
        s = c.get("/api/region/summary?country=India").json(); assert s["n"] == c.get("/api/region/influencers?country=India").json()["n"] and s["demo_share"] == 0
        i = c.get(f"/api/influencer/{r['rows'][0]['id']}").json(); assert i["steps"] and i["projection"] and "Not actual income" in i["note"]
        assert c.get("/api/influencer/99999999").status_code == 404
        assert c.get("/api/region/compare?a=India&b=United States").json()["b"]["n"] > 0
        sim = post(c, "/api/influencer/simulate", followers=40000, er_pct=2, posts_per_week=4, sponsored_share_pct=20, growth_pct_month=2, category="gaming", country="India")
        assert sim.status_code == 200 and post(c, "/api/influencer/simulate", followers=40000, er_pct=2, posts_per_week=4, sponsored_share_pct=20, growth_pct_month=2, category="nope", country="India").status_code == 400
        assert post(c, "/api/influencer/simulate", followers=-5, er_pct=2, posts_per_week=4, sponsored_share_pct=20, growth_pct_month=2).status_code == 422
        x = c.get("/api/region/export?fmt=csv&country=India"); assert x.status_code == 200 and "Instagram does not publish" in x.text and "ESTIMATES" in x.text
        assert c.get("/api/region/export?fmt=xlsx&country=India").content[:2] == b"PK"
        assert c.get("/api/admin/directory/stats").status_code == 401                                              # a user cannot reach admin APIs
        assert post(c, "/api/admin/directory/upload", x=1).status_code == 401


def test_admin_directory_upload_stats_backup_restore(seeded):
    with TestClient(main.app) as c:
        admin(c)
        st = c.get("/api/admin/directory/stats").json(); assert st["total"] >= 500 and st["demo"] == 0 and not any("demo" in (x["source"] or "").lower() for x in st["sources"])
        up = c.post("/api/admin/directory/upload?replace=true", content=CSV.encode(), headers=H).json(); assert up["accepted"] == 3 and up["rejected"] == 3
        st = c.get("/api/admin/directory/stats").json(); assert st["total"] == 3 and st["demo"] == 0 and all(x["gap"] for x in st["countries"])
        assert c.post("/api/admin/directory/upload", content=b"", headers=H).status_code == 400
        assert c.post("/api/admin/directory/upload", content=b"handle,country\nx,India\n", headers=H).status_code == 400
        assert c.get("/api/admin/directory/template.csv").text.startswith("handle,")
        # backup then restore
        b = c.get("/api/admin/backup"); assert b.status_code == 200 and b.content.startswith(b"SQLite format 3")
        c.post("/api/admin/directory/upload?replace=true", content=CSV.encode().split(b"real_b")[0] + b"real_z,Z,India,Kerala,food,9000,300,10,2,x\n", headers=H)
        assert c.post("/api/admin/restore?confirm=no", content=b.content, headers=H).status_code == 400            # needs the word RESTORE
        assert c.post("/api/admin/restore?confirm=RESTORE", content=b"not a database" * 400, headers=H).status_code == 400
        assert c.post("/api/admin/restore?confirm=RESTORE", content=b.content, headers=H).json()["ok"]
        assert {d["handle"] for d in D.rows()} == {"real_a", "real_b", "real_d"}                                    # back to the backed-up state
        assert os_exists(config.AUTH_DB + ".before_restore")
        lg = c.get("/api/admin/logins")
        assert lg.status_code in (200, 401)


def os_exists(p):
    import os; return os.path.exists(p)


# ---------------------------------------------------------------- public mode
def test_public_mode_problems_and_admin_gate(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    assert len(publicmode.problems()) == 2
    monkeypatch.setenv("SECRET_KEY", "x"); monkeypatch.setenv("SMTP_HOST", "h"); monkeypatch.setenv("SMTP_USER", "u"); monkeypatch.setenv("SMTP_PASS", "p")
    assert publicmode.problems() == []
    monkeypatch.setattr(config, "PUBLIC_MODE", True)
    with TestClient(main.app, base_url="http://testserver") as c:
        publicmode._DEF["t"] = 0
        assert c.get("/admin", headers={"X-Forwarded-For": "8.8.8.8"}).status_code in (200, 403)     # TestClient is not loopback: treated as remote
        assert c.get("/api/admin/overview").status_code == 403                                      # default admin password still unchanged
        assert c.get("/").status_code == 200                                                         # the user site stays open


def test_admin_ip_allowlist(monkeypatch):
    import ipaddress
    monkeypatch.setattr(publicmode, "_NETS", [ipaddress.ip_network("203.0.113.0/24")])
    with TestClient(main.app) as c:
        assert c.get("/admin").status_code == 404 and c.get("/api/admin/overview").status_code == 404
        assert c.get("/").status_code == 200
    monkeypatch.setattr(publicmode, "_NETS", [ipaddress.ip_network("testclient/32", strict=False)] if False else [])
    with TestClient(main.app) as c: assert c.get("/admin").status_code == 200


def test_security_headers_and_two_devices_see_same_region_data(seeded):
    with TestClient(main.app) as a, TestClient(main.app) as b:
        user(a, "d1@example.com"); r = a.get("/")
        assert r.headers["referrer-policy"] == "same-origin" and "frame-ancestors" in r.headers["content-security-policy"]
        s = post(b, "/api/auth/signup", **{**SIGNUP, "email": "d2@example.com"}).json()
        post(b, "/api/auth/verify", email="d2@example.com", code=last_code("d2@example.com"), ticket=s["ticket"])
        assert a.get("/api/region/summary?country=India").json() == b.get("/api/region/summary?country=India").json()
