"""Reports: the user (or admin) ticks what should be in the report, and gets a visual PDF (charts and diagrams, very little text).
Every generated report is saved so it can be opened again under "Previous reports".

  GET    /api/reports/catalog        what can be put in a report (grouped; admin-only items only for admins)
  POST   /api/reports/generate       {"sections": [ids], "title": "..."}  -> saves the PDF and returns its record
  GET    /api/reports/history        my previous reports
  GET    /api/reports/{id}/download  the PDF (only the owner)
  DELETE /api/reports/{id}
"""
import io, json, os, sqlite3, time
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app import config, db
from app.auth import require_user, now
from app.services import reportviz as V

router = APIRouter(prefix="/api/reports")
REPORT_DIR = os.path.join(config.DATA_DIR, "reports")
MAX_SECTIONS = 30
WEEK = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _init():
    c = db.conn()
    c.executescript("""CREATE TABLE IF NOT EXISTS reports(
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, ts REAL NOT NULL, title TEXT NOT NULL, sections TEXT NOT NULL, bytes INTEGER, pages INTEGER);
        CREATE INDEX IF NOT EXISTS ix_reports_user ON reports(user_id, ts DESC);""")
    c.commit(); c.close()


def _wh():
    if not os.path.exists(config.WAREHOUSE): raise HTTPException(404, "Warehouse not built yet. An admin must run the ETL first.")
    return sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)


_CACHE = {}


def _cached(key, fn):
    m = os.path.getmtime(config.WAREHOUSE) if os.path.exists(config.WAREHOUSE) else 0
    hit = _CACHE.get(key)
    if hit and hit[0] == m: return hit[1]
    v = fn(); _CACHE[key] = (m, v); return v


# ---------------------------------------------------------------- section builders: each returns [(caption, drawing), ...]
def s_kpis(u):
    c = _wh(); posts, likes = c.execute("SELECT SUM(posts), SUM(total_likes) FROM summary_year").fetchone()
    acc = c.execute("SELECT COUNT(*) FROM dim_user").fetchone()[0]; cats = c.execute("SELECT COUNT(*) FROM dim_category").fetchone()[0]
    y0, y1 = c.execute("SELECT MIN(year), MAX(year) FROM dim_date").fetchone()
    return [("", V.tiles([("Posts", V.human(posts)), ("Accounts", V.human(acc)), ("Avg likes / post", f"{likes / posts:.0f}"), ("Categories", cats), ("Years covered", f"{y0}-{y1}")]))]


def s_year(u):
    r = _wh().execute("SELECT year, posts, avg_likes FROM summary_year ORDER BY year").fetchall()
    L = [str(x[0]) for x in r]
    return [("Posts per year", V.bar(L, [x[1] for x in r])), ("Average likes per post, by year", V.line(L, [[x[2] for x in r]]))]


def s_category(u):
    r = _wh().execute("SELECT category_name, posts, avg_likes FROM summary_category ORDER BY avg_likes DESC LIMIT 10").fetchall()
    return [("Average likes by category (top 10)", V.bar([x[0].replace("_", " ") for x in r], [x[2] for x in r], V.PAL[2], horizontal=True))]


def s_tier(u):
    r = _wh().execute("SELECT follower_tier, accounts, avg_likes FROM summary_tier ORDER BY avg_likes").fetchall()
    return [("Average likes by follower tier", V.bar([x[0] for x in r], [x[2] for x in r], V.PAL[1])), ("Share of accounts by tier", V.pie([x[0] for x in r], [x[1] for x in r]))]


def s_hours(u):
    r = _wh().execute("SELECT weekday, hour, avg_likes FROM summary_hour_weekday").fetchall()
    g = [[None] * 24 for _ in range(7)]
    names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    for wd, h, a in r:
        if wd in names and 0 <= h < 24: g[names.index(wd)][h] = a
    return [("Average likes by weekday and hour of posting", V.heat(WEEK, [str(h) for h in range(24)], g, fmt=lambda v: f"{v:.0f}"))]


def s_hashtags(u):
    r = _wh().execute("SELECT hashtag_bin, avg_likes FROM summary_hashtags ORDER BY rowid").fetchall()
    return [("Average likes by number of hashtags", V.bar([("5+" if x[0] == 5 else str(x[0])) for x in r], [x[1] for x in r], V.PAL[3]))]


def s_star(u):
    c = _wh(); n = lambda t: V.human(c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
    dims = [("dim_date", n("dim_date") + " rows"), ("dim_user", n("dim_user") + " rows"), ("dim_category", n("dim_category") + " rows"), ("dim_hashtag", n("dim_hashtag") + " rows")]
    return [("Star schema: one fact table, four dimensions", V.star("fact_posts", n("fact_posts") + " rows", dims))]


def s_snowflake(u):
    c = _wh(); q = lambda s: V.human(c.execute(s).fetchone()[0])
    return [("Snowflake: the date dimension split into a hierarchy", V.hierarchy([("day", q("SELECT COUNT(*) FROM dim_date")), ("month", q("SELECT COUNT(DISTINCT year*100+month) FROM dim_date")),
                                                                              ("quarter", q("SELECT COUNT(DISTINCT year*10+quarter) FROM dim_date")), ("year", q("SELECT COUNT(DISTINCT year) FROM dim_date"))])),
            ("Fact tables and the bridge", V.star("fact_reach", q("SELECT COUNT(*) FROM fact_reach") + " rows", [("fact_posts", q("SELECT COUNT(*) FROM fact_posts") + " rows"),
                                                  ("bridge_reach_hashtag", q("SELECT COUNT(*) FROM bridge_reach_hashtag") + " rows"), ("dim_hashtag", q("SELECT COUNT(*) FROM dim_hashtag") + " rows")], h=190))]


def _cube():
    def go():
        return _wh().execute("""SELECT d.category_name, MIN(f.hashtag_count,5) b, COUNT(*), AVG(f.likes) FROM fact_posts f JOIN dim_category d USING(category_key) GROUP BY 1,2""").fetchall()
    return _cached("cube", go)


def s_cube(u):
    r = _cube(); cats = sorted({x[0] for x in r}); cats = sorted(cats, key=lambda k: -sum(x[2] for x in r if x[0] == k))[:12]
    g = [[next((x[3] for x in r if x[0] == k and x[1] == b), None) for b in range(6)] for k in cats]
    roll = sorted(((k, sum(x[2] for x in r if x[0] == k)) for k in cats), key=lambda t: -t[1])[:8]
    return [("OLAP cube slice: category x hashtags per post (average likes)", V.heat([k.replace("_", " ") for k in cats], ["0", "1", "2", "3", "4", "5+"], g, fmt=lambda v: f"{v:.0f}")),
            ("Roll-up: posts per category", V.bar([k.replace("_", " ") for k, _ in roll], [v for _, v in roll], V.PAL[4], horizontal=True))]


def s_etl(u):
    if not os.path.exists(config.LINEAGE): return [("No ETL run yet", V._empty("No ETL run yet"))]
    d = json.load(open(config.LINEAGE)); ds = d["datasets"]; g = lambda k: V.human(ds.get(k, {}).get("rows") or 0)
    out = [("ETL flow (rows at each stage)", V.flow([("Raw files", "2 datasets", None), ("Clean posts", g("clean_posts"), None), ("Clean reach", g("clean_reach"), None), ("Combined", g("combined"), None), ("Warehouse", "star + snowflake", None)]))]
    ch = d.get("checks", [])
    if ch: out.append((f"Quality checks: {sum(1 for x in ch if x['ok'])} of {len(ch)} passed", V.flow([(x["name"][:26], V.human(x["actual"]), x["ok"]) for x in ch[:5]])))
    return out


def s_models(u):
    from app.services import mining
    r = mining.report()
    if not r: return [("Models are not trained yet", V._empty("Models are not trained yet"))]
    p = r["predictor"]; lk = p["likes"]
    return [("Likes model: fit versus a plain baseline (R2)", V.bar(["Baseline", "Model"], [lk["baseline_r2"], lk["r2"]], V.PAL[0], fmt=lambda v: f"{v:.2f}")),
            ("What drives engagement (importance %)", V.bar([x["label"] for x in p["importance"][:6]], [x["pct"] for x in p["importance"][:6]], V.PAL[1], horizontal=True, unit="%"))]


def s_personas(u):
    from app.services import mining
    r = mining.report()
    if not r: return [("Models are not trained yet", V._empty("Models are not trained yet"))]
    it = r["personas"]["items"]
    return [("Account personas (share of accounts)", V.pie([x["name"] for x in it], [x["accounts"] for x in it])),
            ("Median engagement rate by persona (%)", V.bar([x["name"] for x in it], [x["median_engagement_pct"] for x in it], V.PAL[2], horizontal=True, unit="%"))]


def _dir():
    from app.services import directory
    directory.ensure_seed(); return directory.rows()


def s_reg_country(u):
    import collections
    c = collections.Counter(d["country"] for d in _dir()).most_common(10)
    return [("Influencers in the directory, by country", V.bar([k for k, _ in c], [v for _, v in c], V.PAL[0], horizontal=True))]


def s_reg_state(u):
    import collections
    c = collections.Counter(d["state_or_region"] for d in _dir() if d["country"] == "India" and d["state_or_region"]).most_common(12)
    return [("India: named influencers per state", V.bar([k for k, _ in c], [v for _, v in c], V.PAL[1], horizontal=True))]


def s_reg_earn(u):
    top = sorted(_dir(), key=lambda d: -d["month"])[:10]
    return [("Highest estimated monthly earnings (USD, estimate)", V.bar([d["display_name"] for d in top], [d["month"] for d in top], V.PAL[2], horizontal=True)),
            ("Follower count of the same people", V.bar([d["display_name"] for d in top], [d["followers"] for d in top], V.PAL[3], horizontal=True))]


def s_reg_cat(u):
    import collections
    c = collections.Counter(d["category"].replace("_", " ") for d in _dir()).most_common(8)
    return [("Directory by category", V.pie([k for k, _ in c], [v for _, v in c]))]


def s_history(u):
    c = db.conn(); r = c.execute("SELECT ts, score, income_monthly FROM analyses WHERE user_id=? ORDER BY ts LIMIT 40", (u["id"],)).fetchall(); c.close()
    if not r: return [("You have not analysed an account yet", V._empty("No saved analyses yet"))]
    L = [time.strftime("%d %b", time.localtime(x[0])) for x in r]
    return [("Your account score over time", V.line(L, [[x[1] for x in r]])), ("Estimated monthly income over time (INR, illustrative)", V.bar(L, [x[2] or 0 for x in r], V.PAL[2]))]


def s_progress(u):
    c = db.conn(); r = c.execute("SELECT ts, er_pct, income_mid FROM creator_posts WHERE user_id=? ORDER BY ts LIMIT 40", (u["id"],)).fetchall(); c.close()
    if not r: return [("No analysed posts yet", V._empty("No analysed posts yet"))]
    L = [time.strftime("%d %b", time.localtime(x[0])) for x in r]
    return [("Engagement rate per analysed post (%)", V.line(L, [[x[1] or 0 for x in r]])), ("Estimated income per post (likely)", V.bar(L, [x[2] or 0 for x in r], V.PAL[4]))]


def _days(c, sql, params, n=14):
    got = dict(c.execute(sql, params).fetchall()); out = []
    for i in range(n - 1, -1, -1):
        k = time.strftime("%Y-%m-%d", time.localtime(time.time() - i * 86400)); out.append((k[5:], got.get(k, 0)))
    return out


def s_a_users(u):
    c = db.conn(); t = now(); since = t - 14 * 86400
    sg = _days(c, "SELECT date(created,'unixepoch','localtime'), COUNT(*) FROM users WHERE role='user' AND verified=1 AND created>? GROUP BY 1", (since,))
    lg = _days(c, "SELECT date(ts,'unixepoch','localtime'), COUNT(*) FROM audit WHERE event='login_success' AND ts>? GROUP BY 1", (since,))
    ty = c.execute("SELECT COALESCE(user_type,'unknown'), COUNT(*) FROM users WHERE role='user' AND verified=1 GROUP BY 1 ORDER BY 2 DESC").fetchall()
    tot = c.execute("SELECT COUNT(*) FROM users WHERE role='user' AND verified=1").fetchone()[0]; pend = c.execute("SELECT COUNT(*) FROM users WHERE role='user' AND verified=0").fetchone()[0]
    blk = c.execute("SELECT COUNT(*) FROM users WHERE status='blocked'").fetchone()[0]; c.close()
    return [("", V.tiles([("Verified users", tot), ("Waiting for code", pend), ("Blocked", blk)])),
            ("Sign-ups and sign-ins, last 14 days", V.line([x[0] for x in sg], [[x[1] for x in sg], [x[1] for x in lg]], ["Sign-ups", "Sign-ins"])),
            ("Users by type", V.pie([x[0].replace("_", " ") for x in ty], [x[1] for x in ty]))]


def s_a_usage(u):
    c = db.conn(); t = now()
    pg = c.execute("SELECT name, COUNT(*) FROM events WHERE kind='page' AND ts>? GROUP BY 1 ORDER BY 2 DESC LIMIT 10", (t - 30 * 86400,)).fetchall()
    an = c.execute("SELECT tier, COUNT(*) FROM analyses GROUP BY 1 ORDER BY 2 DESC").fetchall(); c.close()
    return [("Most opened pages, last 30 days", V.bar([x[0] for x in pg], [x[1] for x in pg], V.PAL[0], horizontal=True)), ("Accounts analysed, by follower tier", V.pie([x[0] for x in an], [x[1] for x in an]))]


def s_a_dir(u):
    d = _dir(); import collections
    src = collections.Counter(x["source"].split(" ")[0] for x in d).most_common(8)
    return [("", V.tiles([("Directory rows", len(d)), ("Countries", len({x["country"] for x in d})), ("Indian states", len({x["state_or_region"] for x in d if x["country"] == "India" and x["state_or_region"]}))])),
            ("Where the directory data came from (rows per source site)", V.bar([k for k, _ in src], [v for _, v in src], V.PAL[1], horizontal=True))]


#            id             title                                   group                    admin_only  builder
CATALOG = [
    ("kpis", "Warehouse at a glance", "Dashboard", False, s_kpis),
    ("year", "Posts and likes by year", "Dashboard", False, s_year),
    ("category", "Likes by category", "Dashboard", False, s_category),
    ("tier", "Follower tiers", "Dashboard", False, s_tier),
    ("hours", "Best time to post (weekday x hour)", "Dashboard", False, s_hours),
    ("hashtags", "Hashtags and likes", "Dashboard", False, s_hashtags),
    ("cube", "OLAP cube slice and roll-up", "Warehouse design", False, s_cube),
    ("star", "Star schema", "Warehouse design", False, s_star),
    ("snowflake", "Snowflake schema", "Warehouse design", False, s_snowflake),
    ("etl", "ETL flow and quality checks", "Data", False, s_etl),
    ("models", "Engagement prediction model", "Data mining", False, s_models),
    ("personas", "Account personas", "Data mining", False, s_personas),
    ("reg_country", "Influencers by country", "Region influencers", False, s_reg_country),
    ("reg_state", "Influencers by Indian state", "Region influencers", False, s_reg_state),
    ("reg_earn", "Top estimated earnings", "Region influencers", False, s_reg_earn),
    ("reg_cat", "Directory by category", "Region influencers", False, s_reg_cat),
    ("history", "My account analyses over time", "My data", False, s_history),
    ("progress", "My post progress", "My data", False, s_progress),
    ("a_users", "Users and sign-ins", "Admin only", True, s_a_users),
    ("a_usage", "Page usage and analyses", "Admin only", True, s_a_usage),
    ("a_dir", "Directory sources", "Admin only", True, s_a_dir),
]
BY_ID = {c[0]: c for c in CATALOG}


def _allowed(u):
    return [c for c in CATALOG if not c[3] or u["role"] == "admin"]


@router.get("/catalog")
def catalog(u=Depends(require_user)):
    groups = {}
    for i, t, g, adm, _ in _allowed(u): groups.setdefault(g, []).append({"id": i, "title": t})
    return {"groups": [{"name": k, "items": v} for k, v in groups.items()], "max": MAX_SECTIONS}


class GenIn(BaseModel):
    sections: list[str] = Field(min_length=1, max_length=MAX_SECTIONS)
    title: str = Field(default="", max_length=80)


def build_pdf(u, ids, title):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether, PageBreak
    from xml.sax.saxutils import escape
    ss = getSampleStyleSheet()
    from reportlab.lib import colors as K
    CAP = ParagraphStyle("c", parent=ss["BodyText"], fontSize=9, textColor=V.MUTED, leading=11, spaceBefore=3, spaceAfter=2)
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=16 * mm, title=title, author="InstaWarehouse")
    who = (u["name"] or u["email"]) if "name" in u.keys() else u["email"]
    el = [Spacer(1, 118 * mm), V.cover_chips([(BY_ID[k][1], BY_ID[k][2]) for k in ids]), PageBreak()]
    for n_, k in enumerate(ids, 1):
        _, ttl, grp, _, fn = BY_ID[k]
        try: parts = fn(u)
        except HTTPException as e: parts = [(str(e.detail), V._empty(str(e.detail)))]
        except Exception as e: parts = [("This part could not be drawn: " + type(e).__name__, V._empty("Not available"))]
        head = [V.banner(n_, ttl, grp), Spacer(1, 5)]
        for i, (cap, d) in enumerate(parts):
            blk = (head if i == 0 else []) + ([Paragraph(escape(cap), CAP)] if cap else []) + [V.panel(d), Spacer(1, 8)]
            el.append(KeepTogether(blk))
        el.append(Spacer(1, 4))
    while el and isinstance(el[-1], Spacer): el.pop()
    stamp = f"{who}  |  {time.strftime('%d %b %Y')}"

    def cover(canv, d):
        w, h = A4; canv.saveState(); canv.setFillColor(K.HexColor("#14183a")); canv.rect(0, 0, w, h, stroke=0, fill=1)
        for (x, y, r, c, a) in ((w - 40 * mm, h - 30 * mm, 70 * mm, "#5b5fe0", .55), (20 * mm, h - 95 * mm, 38 * mm, "#e8449a", .5), (w - 25 * mm, h - 120 * mm, 26 * mm, "#ff7a3d", .6), (60 * mm, 5 * mm, 50 * mm, "#14b8a6", .35), (w - 15 * mm, 30 * mm, 30 * mm, "#f5b50a", .45)):
            canv.setFillColor(K.HexColor(c), alpha=a); canv.circle(x, y, r, stroke=0, fill=1)
        canv.setFillAlpha(1); canv.setFillColor(K.white); canv.setFont("Helvetica-Bold", 30); canv.drawString(18 * mm, h - 120 * mm + 55 * mm, title[:34])
        if len(title) > 34: canv.drawString(18 * mm, h - 120 * mm + 44 * mm, title[34:68])
        canv.setFont("Helvetica", 11); canv.setFillColor(K.HexColor("#c9cdf5")); canv.drawString(18 * mm, h - 120 * mm + 30 * mm, "InstaWarehouse  |  data warehouse report")
        canv.drawString(18 * mm, h - 120 * mm + 23 * mm, stamp); canv.restoreState()

    def foot(canv, d):
        canv.saveState(); x = 0
        for c in V.PAL: canv.setFillColor(c); canv.rect(x, A4[1] - 4 * mm, A4[0] / len(V.PAL), 4 * mm, stroke=0, fill=1); x += A4[0] / len(V.PAL)
        canv.setFont("Helvetica", 7.5); canv.setFillColor(V.MUTED); canv.drawString(18 * mm, 9 * mm, "InstaWarehouse report"); canv.drawRightString(A4[0] - 18 * mm, 9 * mm, f"Page {d.page}"); canv.restoreState()
    doc.build(el, onFirstPage=cover, onLaterPages=foot)
    data = buf.getvalue(); pages = data.count(b"/Type /Page") - data.count(b"/Type /Pages")
    return data, max(1, pages)


@router.post("/generate")
def generate(b: GenIn, u=Depends(require_user)):
    _init(); ok = {c[0] for c in _allowed(u)}; ids = []
    for k in b.sections:
        if k not in ok: raise HTTPException(400, f"Unknown or not allowed report part: {k}")
        if k not in ids: ids.append(k)
    title = (b.title or "").strip() or "InstaWarehouse report"
    data, pages = build_pdf(u, ids, title)
    c = db.conn(); cur = c.execute("INSERT INTO reports(user_id,ts,title,sections,bytes,pages) VALUES(?,?,?,?,?,?)", (u["id"], now(), title, json.dumps(ids), len(data), pages))
    rid = cur.lastrowid; c.commit(); c.close()
    d = os.path.join(REPORT_DIR, str(u["id"])); os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, f"{rid}.pdf"), "wb") as f: f.write(data)
    return {"id": rid, "title": title, "sections": ids, "bytes": len(data), "pages": pages}


@router.get("/history")
def history(u=Depends(require_user)):
    _init(); c = db.conn(); r = c.execute("SELECT id, ts, title, sections, bytes, pages FROM reports WHERE user_id=? ORDER BY ts DESC LIMIT 100", (u["id"],)).fetchall(); c.close()
    return [{"id": x[0], "ts": x[1], "title": x[2], "sections": [BY_ID[k][1] for k in json.loads(x[3]) if k in BY_ID], "bytes": x[4], "pages": x[5]} for x in r]


def _own(u, rid):
    _init(); c = db.conn(); r = c.execute("SELECT id, title FROM reports WHERE id=? AND user_id=?", (rid, u["id"])).fetchone(); c.close()
    if not r: raise HTTPException(404, "Report not found.")
    return r, os.path.join(REPORT_DIR, str(u["id"]), f"{rid}.pdf")


@router.get("/{rid}/download")
def download(rid: int, u=Depends(require_user)):
    r, p = _own(u, rid)
    if not os.path.exists(p): raise HTTPException(404, "The file is no longer on this server (it was removed when the server restarted). Please generate it again.")
    safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in r["title"])[:40].strip() or "report"
    return FileResponse(p, media_type="application/pdf", filename=f"{safe}.pdf")


@router.delete("/{rid}")
def delete(rid: int, u=Depends(require_user)):
    r, p = _own(u, rid)
    c = db.conn(); c.execute("DELETE FROM reports WHERE id=? AND user_id=?", (rid, u["id"])); c.commit(); c.close()
    try: os.remove(p)
    except OSError: pass
    return {"ok": True}
