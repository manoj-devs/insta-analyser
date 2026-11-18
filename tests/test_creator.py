"""Creator Income Analyser: organic income engine, percentile, readiness, steps, history, screenshot reader, PDF, separation from sponsorship."""
import io, os
import pytest
from fastapi.testclient import TestClient
import main
from PIL import Image, ImageDraw, ImageFont
from app.services import creator as C, ocr
from tests.test_auth import H, post
from tests.test_region import user

POST = dict(followers=2400, likes=180, comments=12, saves=20, shares=9, reach=900, post_type="reel", country="India", hashtags=5, caption_len=120)
PLAN = dict(followers=2400, posts_per_week=3, country="India", enabled={"affiliate": True})


def font(size):
    import glob
    return ImageFont.truetype(glob.glob("/usr/share/fonts/**/DejaVuSans.ttf", recursive=True)[0], size)


def shot(rows, w=1080, dark=False, fmt="PNG", quality=90):
    bg, fg = ((20, 20, 20), (240, 240, 240)) if dark else ((255, 255, 255), (20, 20, 20))
    im = Image.new("RGB", (w, 160 + 120 * len(rows)), bg); d = ImageDraw.Draw(im)
    for i, (a, b) in enumerate(rows):
        d.text((60, 100 + 120 * i), a, font=font(40), fill=fg); d.text((w - 200, 100 + 120 * i), b, font=font(40), fill=fg)
    buf = io.BytesIO(); im.save(buf, fmt, quality=quality); return buf.getvalue()


# ---------------------------------------------------------------- engine
def test_benchmarks_load_and_percentile_is_monotonic():
    assert C.available()
    ps = [C.percentile(e, "Micro (1K-10K)") for e in (0.5, 3, 6, 12, 40)]
    assert ps == sorted(ps) and ps[0] < 20 and ps[-1] > 90


def test_post_analysis_is_consistent():
    r = C.analyze_post(POST)
    assert r["band"].startswith("Micro") and 0 <= r["percentile"] <= 100
    assert r["income_usd"]["low"] <= r["income_usd"]["mid"] <= r["income_usd"]["high"]
    assert abs(r["er_pct"] - (180 + 12) / 2400 * 100) < .01
    assert C.analyze_post({**POST, "link_clicks": 80, "orders": 6})["basis"].endswith("your orders")


def test_no_sponsorship_logic_is_used():
    import ast, inspect
    tree = ast.parse(inspect.getsource(C))
    names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not names & {"pricing", "curve_usd", "SPONSORED_SHARE", "MAX_SPONSORED_YEAR", "OTHER_STREAMS_PCT", "CATEGORY_FACTOR"}      # never touches the brand-deal fee engine
    imported = [(n.module, [a.name for a in n.names]) for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("app.services")]
    assert imported == [("app.services", ["directory"])] and "region_factor" in names                                                    # the only shared item: the country price level
    assert "NOT included" in C.ASSUMPTIONS["sponsorship"]


def test_more_followers_or_posts_raise_income_and_zero_streams_give_zero():
    a = C.monthly({**PLAN})["total_usd"]["mid"]
    assert C.monthly({**PLAN, "followers": 24000})["total_usd"]["mid"] > a
    assert C.monthly({**PLAN, "posts_per_week": 6})["total_usd"]["mid"] > a
    assert C.monthly({**PLAN, "enabled": {}})["total_usd"]["mid"] == 0
    t = C.monthly({**PLAN, "enabled": {"affiliate": True, "product": True, "service": True, "membership": True}})["total_usd"]
    assert t["low"] <= t["mid"] <= t["high"]


def test_steps_are_the_same_model_with_one_change():
    pl = C.plan({**PLAN, "posts_per_week": 1})
    s = [x for x in pl["steps"] if x["title"].startswith("Post 4")][0]
    again = C.monthly({**PLAN, "posts_per_week": 4})["total_usd"]["mid"] - pl["model"]["total_usd"]["mid"]
    assert abs(s["extra_usd_month"] - again) < .02
    assert all(x["extra_usd_month"] > 0 for x in pl["steps"]) and pl["steps"] == sorted(pl["steps"], key=lambda x: -x["extra_usd_month"])


def test_readiness_is_bounded_and_rewards_setup():
    lo = C.readiness({"followers": 300, "posts_per_week": 0})["score"]
    hi = C.readiness({"followers": 50000, "posts_per_week": 5, "er_pct": 30, "save_share_pct": 3, "checklist": dict(link=1, niche=1, business=1, contact=1)})["score"]
    assert 0 <= lo < hi <= 100


def test_projection_grows_with_positive_growth():
    pr = C.projection(PLAN, 5)
    assert pr["rows"][-1]["followers"] > 2400 and pr["rows"][-1]["mid"] >= pr["rows"][0]["mid"]
    assert pr["rows"][-1]["cumulative_mid"] >= pr["rows"][-1]["mid"]


# ---------------------------------------------------------------- screenshot reader
def test_ocr_reads_insights_light_and_dark_and_jpeg():
    if not ocr.available(): pytest.skip("tesseract not installed")
    rows = [("Accounts reached", "1,482"), ("Likes", "234"), ("Comments", "18"), ("Shares", "9"), ("Saves", "41")]
    for data in (shot(rows), shot(rows, dark=True), shot(rows, fmt="JPEG", quality=45), shot(rows, w=720)):
        f = ocr.read(data)["fields"]
        assert (f["reach"]["value"], f["likes"]["value"], f["comments"]["value"], f["shares"]["value"], f["saves"]["value"]) == (1482, 234, 18, 9, 41)


def test_number_parsing():
    assert [ocr.parse_number(x) for x in ("1,234", "12.3K", "1.2M", "1.234", "4.5", "x", "850")] == [1234, 12300, 1200000, 1234, None, None, 850]


def test_ocr_rejects_bad_files():
    with pytest.raises(ValueError): ocr.read(b"not a picture")
    with pytest.raises(ValueError): ocr.read(b"x" * (ocr.MAX_BYTES + 1))
    buf = io.BytesIO(); Image.new("RGB", (50, 50)).save(buf, "GIF")
    with pytest.raises(ValueError): ocr.read(buf.getvalue())


# ---------------------------------------------------------------- API
def test_api_needs_sign_in_and_checks_input():
    c = TestClient(main.app)
    assert c.post("/api/creator/analyze", json=POST, headers=H).status_code == 401
    user(c)
    assert c.post("/api/creator/analyze", json={**POST, "followers": 0}, headers=H).status_code == 422
    assert c.post("/api/creator/analyze", json={**POST, "likes": -5}, headers=H).status_code == 422
    assert c.post("/api/creator/plan", json={**PLAN, "posts_per_week": 500}, headers=H).status_code == 422
    assert c.post("/api/creator/analyze", json=POST).status_code in (400, 403)          # missing X-Requested-With header
    r = c.post("/api/creator/analyze", json=POST, headers=H); assert r.status_code == 200 and r.json()["verdict"]
    m = c.get("/api/creator/meta").json(); assert "assumptions" in m and "ocr" in m


def test_history_is_private_per_user_and_deletable():
    a, b = TestClient(main.app), TestClient(main.app)
    user(a, "a1@example.com"); user(b, "b1@example.com")
    ids = [a.post("/api/creator/posts", json={**POST, "label": f"p{i}"}, headers=H).json()["id"] for i in range(4)]
    assert len(a.get("/api/creator/posts").json()["rows"]) == 4 and b.get("/api/creator/posts").json()["rows"] == []
    assert b.delete(f"/api/creator/posts/{ids[0]}", headers=H).status_code == 200              # someone else's id: nothing is deleted
    assert len(a.get("/api/creator/posts").json()["rows"]) == 4
    assert a.delete(f"/api/creator/posts/{ids[0]}", headers=H).status_code == 200 and len(a.get("/api/creator/posts").json()["rows"]) == 3
    r = a.post("/api/creator/analyze", json=POST, headers=H).json(); assert r["vs_my_average"]["of_posts"] == 3


def test_profile_round_trip():
    c = TestClient(main.app); user(c)
    assert c.get("/api/creator/profile").json() == {}
    assert c.put("/api/creator/profile", json={**PLAN, "posts_per_week": 5}, headers=H).status_code == 200
    assert c.get("/api/creator/profile").json()["posts_per_week"] == 5


def test_screenshot_endpoint_reads_and_stores_nothing():
    if not ocr.available(): pytest.skip("tesseract not installed")
    from app import config
    c = TestClient(main.app); user(c)
    before = set(os.listdir(config.UPLOAD_DIR))
    h = {**H, "Content-Type": "image/png"}
    r = c.post("/api/creator/ocr", content=shot([("Likes", "234"), ("Comments", "18")]), headers=h)
    assert r.status_code == 200 and r.json()["fields"]["likes"]["value"] == 234 and "text" not in r.json()
    assert set(os.listdir(config.UPLOAD_DIR)) == before
    assert c.post("/api/creator/ocr", content=b"junk", headers=h).status_code == 400
    assert c.post("/api/creator/ocr", content=b"", headers=h).status_code == 400
    assert TestClient(main.app).post("/api/creator/ocr", content=b"x", headers=h).status_code == 401


def test_pdf_report_card():
    c = TestClient(main.app); user(c)
    r = c.post("/api/creator/report?cur=INR&handle=my_handle", json=PLAN, headers=H)
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content[:5] == b"%PDF-" and len(r.content) > 2000
    assert c.post("/api/creator/report?cur=USD", json=PLAN, headers=H).status_code == 200


def test_insights():
    c = TestClient(main.app); user(c)
    r = c.get("/api/creator/insights?band=Micro%20(1K-10K)").json()
    assert r["hashtags"] and r["weekday"] and "2019" in r["note"]
