"""Creator Income Analyser: organic income for ordinary creators (no sponsorship). Own endpoints under /api/creator."""
import io, json, time
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from typing import Optional
from app import db
from app.auth import audit, require_user
from app.services import creator as C, ocr, pricing

router = APIRouter(prefix="/api/creator")
BIG = 5_000_000_000
MAX_POSTS_PER_USER = 2000


class PostIn(BaseModel):
    followers: int = Field(ge=1, le=BIG)
    likes: int = Field(0, ge=0, le=BIG); comments: int = Field(0, ge=0, le=BIG); saves: int = Field(0, ge=0, le=BIG); shares: int = Field(0, ge=0, le=BIG)
    reach: Optional[int] = Field(None, ge=0, le=BIG)
    post_type: str = "image"; country: str = Field("India", max_length=60); category: str = Field("", max_length=60)
    hashtags: Optional[int] = Field(None, ge=0, le=200); caption_len: Optional[int] = Field(None, ge=0, le=5000)
    offer: str = "affiliate"; price_usd: Optional[float] = Field(None, ge=0, le=1e7); earn_pct: Optional[float] = Field(None, ge=0, le=100)
    link_clicks: Optional[int] = Field(None, ge=0, le=BIG); orders: Optional[int] = Field(None, ge=0, le=BIG)
    label: str = Field("", max_length=80); posted_on: str = Field("", max_length=10); source: str = Field("manual", max_length=12)


class PlanIn(BaseModel):
    followers: int = Field(ge=1, le=BIG)
    posts_per_week: float = Field(3, ge=0, le=40); er_pct: Optional[float] = Field(None, ge=0, le=1000)
    country: str = Field("India", max_length=60); post_type: str = "image"; reach_per_post: Optional[int] = Field(None, ge=0, le=BIG)
    enabled: dict = Field(default_factory=lambda: {"affiliate": True}); prices: dict = Field(default_factory=dict)
    checklist: dict = Field(default_factory=dict); save_share_pct: Optional[float] = Field(None, ge=0, le=100)
    growth_pct: Optional[float] = Field(None, ge=-20, le=50)


def _ready():
    if not C.available(): raise HTTPException(503, "The benchmark data is not available on this server.")


@router.get("/meta")
def meta(u=Depends(require_user)):
    return {"inr_per_usd": pricing.INR_PER_USD, "ocr": ocr.available(), "bands": [b[1] for b in C.BANDS], "post_types": list(C.POST_TYPE_REACH),
            "streams": {k: {"title": v["title"], "how": v["how"]} for k, v in C.STREAMS.items()}, "assumptions": C.ASSUMPTIONS, "benchmarks": C.available(),
            "target_ppw": C.TARGET_PPW}


def _recent(uid, n=10):
    c = db.conn(); r = [dict(x) for x in c.execute("SELECT er_pct FROM creator_posts WHERE user_id=? ORDER BY ts DESC LIMIT ?", (uid, n))]; c.close()
    return [x["er_pct"] for x in r]


@router.post("/analyze")
def analyze(p: PostIn, u=Depends(require_user)):
    _ready(); r = C.analyze_post(p.model_dump())
    rec = _recent(u["id"])
    r["vs_my_average"] = None
    if len(rec) >= 3:
        avg = sum(rec) / len(rec); r["vs_my_average"] = {"avg_er_pct": round(avg, 2), "diff_pct": round(100 * (r["er_pct"] - avg) / avg) if avg else None, "of_posts": len(rec)}
    return r


@router.post("/plan")
def plan(p: PlanIn, u=Depends(require_user)):
    _ready(); return C.plan(p.model_dump())


@router.get("/insights")
def insights(band: str = "", u=Depends(require_user)):
    _ready(); return C.insights(band if band in [b[1] for b in C.BANDS] else None)


# ------------------------------------------------------------------ saved profile (so the plan follows the user across devices)
@router.get("/profile")
def get_profile(u=Depends(require_user)):
    c = db.conn(); r = c.execute("SELECT data FROM creator_profile WHERE user_id=?", (u["id"],)).fetchone(); c.close()
    return json.loads(r["data"]) if r else {}


@router.put("/profile")
def put_profile(p: PlanIn, u=Depends(require_user)):
    c = db.conn(); c.execute("INSERT INTO creator_profile(user_id,data,updated) VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                             (u["id"], json.dumps(p.model_dump()), time.time())); c.commit(); c.close()
    return {"ok": True}


# ------------------------------------------------------------------ progress tracker
@router.post("/posts")
def save_post(p: PostIn, request: Request, u=Depends(require_user)):
    _ready(); r = C.analyze_post(p.model_dump()); c = db.conn()
    n = c.execute("SELECT COUNT(*) FROM creator_posts WHERE user_id=?", (u["id"],)).fetchone()[0]
    if n >= MAX_POSTS_PER_USER: c.close(); raise HTTPException(400, "You have saved the maximum number of posts. Please delete some old ones.")
    inc = r["income_usd"]
    cur = c.execute("INSERT INTO creator_posts(user_id,ts,label,post_type,posted_on,followers,likes,comments,saves,shares,reach,er_pct,percentile,income_low,income_mid,income_high,source) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (u["id"], time.time(), p.label.strip()[:80], r["post_type"], p.posted_on, p.followers, p.likes, p.comments, p.saves, p.shares, r["reach"], r["er_pct"],
                     r["percentile"], round(inc["low"] * 100), round(inc["mid"] * 100), round(inc["high"] * 100), "screenshot" if p.source == "screenshot" else "manual"))
    c.commit(); pid = cur.lastrowid; c.close()
    return {"id": pid, "result": r}


@router.get("/posts")
def list_posts(u=Depends(require_user)):
    c = db.conn(); rows = [dict(x) for x in c.execute("SELECT * FROM creator_posts WHERE user_id=? ORDER BY ts DESC LIMIT 500", (u["id"],))]; c.close()
    for r in rows:
        for k in ("income_low", "income_mid", "income_high"): r[k] = r[k] / 100
    summ = None
    if rows:
        ers = [r["er_pct"] for r in rows]; last = ers[:5]; prev = ers[5:10]
        summ = {"posts": len(rows), "avg_er_pct": round(sum(ers) / len(ers), 2), "avg_percentile": round(sum(r["percentile"] for r in rows) / len(rows)),
                "best": max(rows, key=lambda r: r["er_pct"])["id"], "total_income_mid_usd": round(sum(r["income_mid"] for r in rows), 2),
                "trend": None if len(prev) < 3 else ("up" if sum(last) / len(last) > sum(prev) / len(prev) * 1.05 else "down" if sum(last) / len(last) < sum(prev) / len(prev) * .95 else "steady")}
    return {"rows": rows, "summary": summ}


@router.delete("/posts/{pid}")
def delete_post(pid: int, u=Depends(require_user)):
    c = db.conn(); c.execute("DELETE FROM creator_posts WHERE id=? AND user_id=?", (pid, u["id"])); c.commit(); c.close()
    return {"ok": True}


# ------------------------------------------------------------------ screenshot reader (the picture is never stored)
@router.post("/ocr")
async def read_screenshot(request: Request, u=Depends(require_user)):
    if not ocr.available(): raise HTTPException(503, "Screenshot reading is not set up on this server. Please type the numbers instead.")
    data = await request.body()
    if not data: raise HTTPException(400, "Please choose a screenshot.")
    if len(data) > ocr.MAX_BYTES: raise HTTPException(413, "The picture is bigger than 6 MB. Please crop it or send a smaller one.")
    try: r = await run_in_threadpool(ocr.read, data)
    except ValueError as e: raise HTTPException(400, str(e))
    audit("creator_screenshot", u["id"], u["email"], request, f"{r['found']} numbers found")      # only the count is logged
    return r


# ------------------------------------------------------------------ one-page PDF report card (recomputed here, not trusted from the browser)
def money_txt(usd, cur, rate):
    v = usd * rate if cur == "INR" else usd
    return ("INR " if cur == "INR" else "USD ") + f"{v:,.0f}"


@router.post("/report")
def report(p: PlanIn, cur: str = "INR", handle: str = "", u=Depends(require_user)):
    _ready()
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.graphics.shapes import Drawing, Rect, String
    from xml.sax.saxutils import escape
    cur = "USD" if cur == "USD" else "INR"; rate = pricing.INR_PER_USD
    pl = C.plan(p.model_dump()); m = pl["model"]; rd = pl["readiness"]
    ss = getSampleStyleSheet(); H = ParagraphStyle("h", parent=ss["Title"], fontSize=20, spaceAfter=2, textColor=colors.HexColor("#1b2a52"))
    H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4, textColor=colors.HexColor("#1b2a52"))
    B = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13); S = ParagraphStyle("s", parent=B, fontSize=8, textColor=colors.HexColor("#555555"))
    buf = io.BytesIO(); doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
                                                title="Creator report card", author="InstaWarehouse")
    el = [Paragraph("Creator Income Report Card", H), Paragraph(escape(f"{handle[:40] or 'Your account'}  |  {m['band']}  |  {int(p.followers):,} followers  |  {time.strftime('%d %b %Y')}"), S), Spacer(1, 6)]
    d = Drawing(170 * mm, 18); d.add(Rect(0, 4, 170 * mm, 10, fillColor=colors.HexColor("#e6e9f5"), strokeColor=None))
    d.add(Rect(0, 4, 170 * mm * rd["score"] / 100, 10, fillColor=colors.HexColor("#5b6cff"), strokeColor=None)); d.add(String(0, -6, f"Readiness {rd['score']}/100 - {rd['label']}", fontSize=9))
    el += [d, Spacer(1, 12), Paragraph("Estimated monthly income from your own content", H2)]
    t = Table([["", "Low", "Likely", "High"]] + [[v["title"] + ("" if v["enabled"] else " (off)")] + [money_txt(v["usd"][s], cur, rate) for s in ("low", "mid", "high")] for v in m["streams"].values()] +
              [["Total of streams switched on"] + [money_txt(m["total_usd"][s], cur, rate) for s in ("low", "mid", "high")]], colWidths=[84 * mm, 28 * mm, 28 * mm, 28 * mm])
    t.setStyle(TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b2a52")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                           ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"), ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#c8cde0")),
                           ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f4f6fd")])]))
    el += [t, Spacer(1, 4), Paragraph("Organic income only: no sponsorship or brand deals. These are estimates, not actual earnings.", S),
           Paragraph("Where you stand", H2), Paragraph(escape(f"Your engagement of {m['er_pct']}% is ahead of {rd['percentile']}% of posts in your size band ({rd['percentile']}th percentile)."), B)]
    for i in rd["items"]: el.append(Paragraph(escape(f"{i['name']}: {i['got']}/{i['of']} - {i['note']}"), B))
    el.append(Paragraph("Top steps to earn more", H2))
    for i, s in enumerate(pl["steps"][:3], 1):
        el.append(Paragraph(escape(f"{i}. {s['title']} (about +{money_txt(s['extra_usd_month'], cur, rate)} a month)  -  {s['todo']}"), B))
    ms = pl["projection"]["milestones"]
    el += [Paragraph("Where this could go", H2), Paragraph(escape(f"At {pl['projection']['growth_pct_month']}% follower growth a month, likely monthly income: " +
           ", ".join(f"month {k}: {money_txt(v['mid'], cur, rate)}" for k, v in ms.items()) + "."), B), Spacer(1, 10),
           Paragraph("How this is calculated: engagement benchmarks come from 605,563 posts in the project warehouse (posts up to August 2019); conversion rates, prices and reach "
                     "rates are planning assumptions listed in the app under 'How the numbers are made'. Platform bonuses and brand deals are not included.", S)]
    doc.build(el); audit("creator_report", u["id"], u["email"], None, "")
    return Response(buf.getvalue(), media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="creator_report_card.pdf"'})
