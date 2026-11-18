"""Region-wise influencer analyser: region tree, paged influencer list, estimated earnings, steps to earn more, what-if simulator, export, admin directory."""
import csv, io
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from app import db
from app.auth import audit, require_admin, require_user
from app.services import directory as D, pricing

router = APIRouter(prefix="/api")
NOTE = "Estimated from followers, engagement and category. Not actual income."
SORTS = {"handle": "handle", "followers": "followers", "er": "er_pct", "fee": "fee", "month": "month", "year": "year", "country": "country", "category": "category"}


def _sel(continent, country, state, category, tier, q):
    return D.select(continent, country, state, category, tier, q)


@router.get("/regions")
def regions(u=Depends(require_user)):
    t = D.tree()
    return {"tree": t, "total": sum(c["n"] for ct in t.values() for c in ct.values()), "inr_per_usd": pricing.INR_PER_USD, "note": NOTE,
            "categories": D.CATS, "tiers": ["Nano", "Micro", "Mid-tier", "Macro", "Mega", "Celebrity"],
            "assumptions": {"sponsored_share_pct": round(D.SPONSORED_SHARE * 100), "growth_pct_month": D.GROWTH_PCT_MONTH, "other_streams_pct": D.OTHER_STREAMS_PCT,
                            "region_factor": D.REGION_FACTOR}}


def _slim(d):
    keys = ("id", "handle", "display_name", "continent", "country", "state_or_region", "city", "category", "account_type", "verified", "followers", "er_pct", "bench_pct", "ratio",
            "tier", "posts_per_week", "fee_low", "fee", "fee_high", "month", "year_low", "year", "year_high", "er_known", "source", "as_of")
    return {k: d[k] for k in keys}


@router.get("/region/influencers")
def influencers(continent: str = "", country: str = "", state: str = "", category: str = "", tier: str = "", q: str = "", sort: str = "year", dir: str = "desc",
                page: int = 1, size: int = 25, u=Depends(require_user)):
    size = min(max(size, 5), 50); page = max(int(page), 1)
    sel = _sel(continent, country, state, category, tier, q)
    key = SORTS.get(sort, "year"); sel.sort(key=lambda d: (d[key] is None, d[key]), reverse=(dir != "asc"))
    n = len(sel); lo = (page - 1) * size
    return {"n": n, "page": page, "size": size, "pages": max(1, -(-n // size)), "rows": [_slim(d) for d in sel[lo:lo + size]], "note": NOTE, "inr_per_usd": pricing.INR_PER_USD}


@router.get("/region/summary")
def summ(continent: str = "", country: str = "", state: str = "", category: str = "", tier: str = "", q: str = "", u=Depends(require_user)):
    return {**D.summary(_sel(continent, country, state, category, tier, q)), "inr_per_usd": pricing.INR_PER_USD, "note": NOTE}


@router.get("/region/compare")
def compare(a: str, b: str, u=Depends(require_user)):
    """a and b look like 'India' or 'India|Tamil Nadu'"""
    def one(x):
        co, _, st = x.partition("|"); s = D.summary(D.select(country=co, state=st)); s["label"] = co + (f" / {st}" if st else ""); return s
    return {"a": one(a), "b": one(b), "inr_per_usd": pricing.INR_PER_USD, "note": NOTE}


@router.get("/influencer/{iid}")
def one(iid: int, u=Depends(require_user)):
    p = D.profile(iid)
    if not p: raise HTTPException(404, "That influencer is not in the directory.")
    p.pop("added", None)
    return {**p, "inr_per_usd": pricing.INR_PER_USD, "note": NOTE,
            "assumptions": {"sponsored_share_pct": round(D.SPONSORED_SHARE * 100), "growth_pct_month": D.GROWTH_PCT_MONTH, "projection_note": "A projection under stated assumptions, not a promise."}}


class SimIn(BaseModel):
    followers: int = Field(ge=100, le=2_000_000_000)
    er_pct: float = Field(ge=0, le=60)
    posts_per_week: float = Field(ge=0, le=60)
    sponsored_share_pct: float = Field(ge=0, le=100)
    growth_pct_month: float = Field(ge=-10, le=30)
    category: str = "diaries_&_daily_life"
    country: str = "India"


@router.post("/influencer/simulate")
def simulate(b: SimIn, u=Depends(require_user)):
    if b.category not in pricing.CATEGORY_FACTOR: raise HTTPException(400, "Unknown category.")
    return {**D.simulate(b.followers, b.er_pct, b.posts_per_week, b.sponsored_share_pct, b.growth_pct_month, b.category, b.country), "inr_per_usd": pricing.INR_PER_USD, "note": NOTE}


@router.get("/region/export")
def export(request: Request, fmt: str = "csv", continent: str = "", country: str = "", state: str = "", category: str = "", tier: str = "", q: str = "", u=Depends(require_user)):
    sel = _sel(continent, country, state, category, tier, q)[:20_000]
    head = ["handle", "name", "country", "state_or_region", "category", "tier", "followers", "engagement_pct", "posts_per_week", "fee_per_post_usd", "monthly_usd", "yearly_low_usd",
            "yearly_mid_usd", "yearly_high_usd", "yearly_mid_inr", "source"]
    rows = [[d["handle"], d["display_name"], d["country"], d["state_or_region"] or "", d["category"], d["tier"], d["followers"], d["er_pct"], d["posts_per_week"], d["fee"], d["month"],
             d["year_low"], d["year"], d["year_high"], round(d["year"] * pricing.INR_PER_USD), d["source"]] for d in sel]
    audit("region_export", u["id"], u["email"], request, f"{fmt}, {len(rows)} rows")
    note = ["Earnings are ESTIMATES. " + NOTE, "Follower counts come from the public page named in the source column, as of the date shown. Instagram does not publish anyone's income."]
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.title = "Influencers"; ws.append(head); [ws.append(r) for r in rows]; ws.append([]); [ws.append([x]) for x in note]
        for col, w in zip("ABCDEFGHIJKLMNOP", [22, 22, 16, 18, 22, 10, 12, 12, 10, 12, 12, 12, 12, 12, 14, 18]): ws.column_dimensions[col].width = w
        bio = io.BytesIO(); wb.save(bio)
        return Response(bio.getvalue(), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": 'attachment; filename="region_influencers.xlsx"'})
    s = io.StringIO(); w = csv.writer(s); w.writerow(head); w.writerows(rows); [w.writerow([x]) for x in note]
    return Response("﻿" + s.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="region_influencers.csv"'})


# ---------------------------------------------------------------- admin: the directory data
LAST_UPLOAD = {}


@router.post("/admin/directory/upload")
async def upload(request: Request, replace: bool = False, u=Depends(require_admin)):
    data = await request.body()
    if not data: raise HTTPException(400, "Please choose a CSV file.")
    if len(data) > 8_000_000: raise HTTPException(400, "The file is bigger than 8 MB.")
    try: r = D.load_csv(data, replace=replace)
    except ValueError as e: raise HTTPException(400, str(e))
    LAST_UPLOAD.clear(); LAST_UPLOAD.update(r)
    audit("directory_upload", u["id"], u["email"], request, f"{r['accepted']} accepted, {r['rejected']} rejected, replace={replace}")
    return r


@router.get("/admin/directory/stats")
def stats(u=Depends(require_admin)):
    c = db.conn()
    per = [dict(r) for r in c.execute("SELECT country, continent, COUNT(*) n, ROUND(AVG(followers)) avg_followers, MAX(as_of) as_of FROM directory GROUP BY country ORDER BY n DESC")]
    src = [dict(r) for r in c.execute("SELECT source, COUNT(*) n FROM directory GROUP BY source ORDER BY n DESC")]
    users = [dict(r) for r in c.execute("SELECT country, COUNT(*) n FROM users WHERE role='user' AND country IS NOT NULL AND country!='' GROUP BY country ORDER BY n DESC LIMIT 30")]
    total = c.execute("SELECT COUNT(*) FROM directory").fetchone()[0]; demo = c.execute("SELECT COUNT(*) FROM directory WHERE LOWER(source) LIKE '%demo%'").fetchone()[0]
    c.close()
    for p in per: p["gap"] = p["n"] < 10
    return {"total": total, "demo": demo, "countries": per, "sources": src, "users_by_country": users, "last_upload": LAST_UPLOAD or None, "min_per_region": 10}


@router.get("/admin/directory/template.csv")
def template(u=Depends(require_admin)):
    s = io.StringIO(); w = csv.writer(s); w.writerow(D.TEMPLATE_HEADER)
    w.writerow(["example_handle", "Example Name", "Asia", "India", "Tamil Nadu", "Chennai", "fitness_&_health", "creator", "0", "52000", "1500", "40", "4", "2026-11-01", "public profile (team collected)"])
    return Response(s.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="influencer_directory_template.csv"'})
