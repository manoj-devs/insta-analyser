import os, sqlite3, threading
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from app import config
from app.deps import require_user
from app.auth import require_portal_user, now
from app import db as authdb

router = APIRouter(prefix="/api")
TIERS = [(1000, "Nano (<1K)"), (10000, "Micro (1K-10K)"), (100000, "Mid (10K-100K)"), (1000000, "Macro (100K-1M)"), (float("inf"), "Mega (1M+)")]
# ILLUSTRATIVE assumption (INR per 1,000 followers per sponsored post). The dataset has no real earnings.
RATES = {"Nano (<1K)": 300, "Micro (1K-10K)": 600, "Mid (10K-100K)": 1200, "Macro (100K-1M)": 2500, "Mega (1M+)": 4000}


def _db():
    if not os.path.exists(config.WAREHOUSE):
        raise HTTPException(404, "Warehouse not built yet. An admin must run the ETL first.")
    return sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)


def tier_of(f):
    for lim, name in TIERS:
        if f < lim: return name


@router.get("/overview")
def overview(_=Depends(require_user)):
    c = _db(); q = lambda s: c.execute(s).fetchone()[0]
    likes, n = c.execute("SELECT SUM(total_likes), SUM(posts) FROM summary_year").fetchone()
    return {"posts": q("SELECT COUNT(*) FROM combined_posts"), "avg_likes": round(likes / n, 1), "accounts": q("SELECT COUNT(*) FROM dim_user"),
            "categories": q("SELECT COUNT(*) FROM dim_category"), "years": [q("SELECT MIN(year) FROM dim_date"), q("SELECT MAX(year) FROM dim_date")]}


@router.get("/meta/categories")
def categories(_=Depends(require_user)):
    return [r[0] for r in _db().execute("SELECT category_name FROM dim_category ORDER BY 1")]


_CUBE = {"mtime": None, "data": None}
_LOCK = threading.Lock()


def cube_payload():
    """Cached: rebuilt only when the warehouse file changes (the full pass over 600k posts takes a few seconds)."""
    m = os.path.getmtime(config.WAREHOUSE) if os.path.exists(config.WAREHOUSE) else None
    with _LOCK:
        if m is None: raise HTTPException(404, "Warehouse not built yet. An admin must run the ETL first.")
        if _CUBE["mtime"] != m:
            _CUBE.update(data=_build_cube(), mtime=m)
        return _CUBE["data"]


@router.get("/cube/data")
def cube_data(_=Depends(require_user)):
    return cube_payload()


def _build_cube():
    """Base cuboid for the 3D cube: topic x hashtag bin x text-length bin x source."""
    import re
    c = _db()
    rows = c.execute("SELECT text, hashtag_count, text_length, source, likes, comments FROM combined_posts")   # streamed, not loaded all at once (keeps memory low on small hosts)
    names = ["Food & Drink", "Fitness & Health", "Fashion & Beauty", "Travel & Places", "Art & Photography", "General"]
    pats = [re.compile(p) for p in [
        r"(?<![a-z0-9])#?(?:food|yum|delicious|vegan|coffee|brunch|dinner|lunch|breakfast|pizza|burger|cake|dessert|wine|beer|cocktail|restaurant|recipe|cook|bak(?:e|ing)|chocolate|tea\b)",
        r"(?<![a-z0-9])#?(?:fitness|gym|workout|yoga|health|running|crossfit|training|bodybuilding|marathon|fitfam|motivation|exercise)",
        r"(?<![a-z0-9])#?(?:fashion|beauty|style|ootd|makeup|model|outfit|hair|nails|jewel|shoes|dress)",
        r"(?<![a-z0-9])#?(?:travel|wanderlust|london|nyc|newyork|manhattan|brooklyn|scotland|england|beach|holiday|vacation|adventure|paris|trip|sunset|mountain|city\b|uk\b)",
        r"(?<![a-z0-9])#?(?:photo|art\b|artist|artwork|design|architecture|landscape|nature|music|painting|drawing)"]]
    edges = [14, 36, 75, 141, 275]
    agg = {}
    for text, hc, tl, src, lk, cm in rows:
        t = text.lower(); topic = 5
        for i, p in enumerate(pats):
            if p.search(t): topic = i; break
        lb = sum(tl > e for e in edges)
        k = (topic, min(hc, 5), lb, 1 if src == "reach_dataset" else 0)
        a = agg.setdefault(k, [0, 0, 0]); a[0] += 1; a[1] += lk; a[2] += cm
    return {"dims": [names, ["0", "1", "2", "3", "4", "5+"], ["1–14 chars", "15–36", "37–75", "76–141", "142–275", "276+"]],
            "short": [["Food", "Fitness", "Fashion", "Travel", "Art", "General"], ["0", "1", "2", "3", "4", "5+"], ["≤14", "15–36", "37–75", "76–141", "142–275", "276+"]],
            "srcs": ["Posts dataset", "Reach dataset"], "rows": [list(k) + v for k, v in sorted(agg.items())]}


@router.get("/schema/counts")
def schema_counts(_=Depends(require_user)):
    c = _db(); out = {}
    for t in ["fact_posts", "fact_reach", "dim_date", "dim_category", "dim_user", "dim_hashtag", "bridge_reach_hashtag"]:
        out[t] = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    out["dim_month"] = c.execute("SELECT COUNT(DISTINCT year*100+month) FROM dim_date").fetchone()[0]
    out["dim_quarter"] = c.execute("SELECT COUNT(DISTINCT year*10+quarter) FROM dim_date").fetchone()[0]
    out["dim_year"] = c.execute("SELECT COUNT(DISTINCT year) FROM dim_date").fetchone()[0]
    out["dim_follower_tier"] = len(TIERS)
    return out


class AnalyseIn(BaseModel):
    handle: str = Field(min_length=1, max_length=40)
    followers: int = Field(ge=0, le=2_000_000_000)
    category: str
    account_type: str = "personal"
    avg_likes: float = Field(ge=0)
    avg_comments: float = Field(ge=0)
    hashtags_per_post: int = Field(ge=0, le=30)
    posts_per_week: float = Field(ge=0, le=50)
    save: bool = True            # False for slider what-ifs, True when the user presses Analyse
    following: int | None = Field(default=None, ge=0, le=2_000_000_000)
    num_posts: int | None = Field(default=None, ge=0, le=10_000_000)
    sponsored_per_month: int = Field(default=4, ge=0, le=60)
    # the NEXT post being planned (defaults = a typical post)
    planned_hashtags: int | None = Field(default=None, ge=0, le=30)
    mentions: int = Field(default=0, ge=0, le=20)
    caption_len: int | None = Field(default=None, ge=0, le=2200)
    hour: int | None = Field(default=None, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)


@router.post("/analyse")
def analyse(b: AnalyseIn, u=Depends(require_portal_user)):
    c = _db(); tier = tier_of(b.followers)
    cat = c.execute("SELECT category_key FROM dim_category WHERE category_name=?", (b.category,)).fetchone()
    if not cat: raise HTTPException(400, "Unknown category.")
    base = "FROM fact_posts f JOIN dim_user u USING(user_key) WHERE u.follower_tier=?"
    t_n, t_l, t_c = c.execute(f"SELECT COUNT(*), AVG(f.likes), AVG(f.comments) {base}", (tier,)).fetchone()
    k_n, k_l, k_c = c.execute(f"SELECT COUNT(*), AVG(f.likes), AVG(f.comments) {base} AND f.category_key=?", (tier, cat[0])).fetchone()
    if k_n >= 30: n, bl, bc, level = k_n, k_l, k_c, "your category and follower tier"
    elif t_n >= 30: n, bl, bc, level = t_n, t_l, t_c, "your follower tier (the category has too few posts)"
    else: raise HTTPException(422, "Not enough similar posts in the warehouse to benchmark this account.")
    bins = c.execute(f"SELECT MIN(f.hashtag_count,5) b, COUNT(*) n, AVG(f.likes) l {base} GROUP BY b HAVING n>=30", (tier,)).fetchall()
    hours = c.execute(f"SELECT f.post_hour h, COUNT(*) n, AVG(f.likes) l {base} GROUP BY h HAVING n>=30 ORDER BY l DESC LIMIT 1", (tier,)).fetchone()
    biz = {r[0]: (r[1], r[2]) for r in c.execute(f"SELECT u.is_business_account, COUNT(*), AVG(f.likes) {base} GROUP BY 1", (tier,))}
    best = max(bins, key=lambda r: r[2]) if bins else None
    mine = min(b.hashtags_per_post, 5); cur = next((r for r in bins if r[0] == mine), None)
    lr, cr = (b.avg_likes / bl if bl else 0), (b.avg_comments / bc if bc else 0)
    s1 = min(lr, 1.5) / 1.5 * 50; s2 = min(cr, 1.5) / 1.5 * 20
    s3 = 15 * (1 - min(abs(mine - best[0]), 5) / 5) if best else 7.5
    ppw = b.posts_per_week; dist = 0 if 3 <= ppw <= 7 else min(abs(ppw - 3), abs(ppw - 7))
    s4 = 15 * max(0, 1 - dist / 7); score = round(s1 + s2 + s3 + s4)
    tips = []
    if best and mine != best[0]:
        lab = "5 or more" if best[0] == 5 else str(best[0])
        tips.append({"title": ("Try using no hashtags" if best[0] == 0 else f"Try about {lab} hashtags per post"), "text": f"Accounts in your tier average {best[2]:.1f} likes with {lab} hashtags" + (f", versus {cur[2]:.1f} with {'5+' if mine == 5 else mine}." if cur else "."), "evidence": f"Based on {best[1]:,} posts"})
    if hours:
        tips.append({"title": f"Post around {hours[0]:02d}:00", "text": f"Posts at {hours[0]:02d}:00 get the highest average likes ({hours[2]:.1f}) in your follower tier.", "evidence": f"Based on {hours[1]:,} posts"})
    if ppw < 3: tips.append({"title": "Post at least 3 times a week", "text": "Steady posting keeps the audience engaged; you currently post less than 3 times a week.", "evidence": "Rule of thumb, not from the data"})
    elif ppw > 7: tips.append({"title": "Consider fewer, stronger posts", "text": "Posting more than 7 times a week can dilute engagement per post.", "evidence": "Rule of thumb, not from the data"})
    if lr < 0.8: tips.append({"title": "Your likes are below the benchmark", "text": f"Your average likes are {lr*100:.0f}% of the benchmark ({bl:.1f}) for {level}.", "evidence": f"Benchmark from {n:,} posts"})
    elif lr > 1.2: tips.append({"title": "Strong likes performance", "text": f"You are at {lr*100:.0f}% of the benchmark ({bl:.1f}) for {level}. Keep your current content style.", "evidence": f"Benchmark from {n:,} posts"})
    if cr < 0.8: tips.append({"title": "Raise comments with questions", "text": f"Your comments are {cr*100:.0f}% of the benchmark ({bc:.2f}). Ending captions with a question usually invites replies.", "evidence": f"Benchmark from {n:,} posts"})
    if 1 in biz and 0 in biz and biz[1][1] > biz[0][1] * 1.1 and b.account_type == "personal":
        tips.append({"title": "Business accounts do better in your tier", "text": f"Business accounts average {biz[1][1]:.1f} likes versus {biz[0][1]:.1f} for personal accounts in your tier.", "evidence": f"Based on {biz[1][0]+biz[0][0]:,} posts"})
    from app.services import mining, pricing
    pred = persona = None; ratio_now = ratio_better = (b.avg_likes + b.avg_comments) / (bl + bc) if (bl + bc) else 1.0
    if mining.available():
        t = mining.bundle()["typical"]
        acct = {"followers": b.followers, "category": b.category, "business": b.account_type == "business", "following": b.following, "num_posts": b.num_posts}
        post = {"hashtags": b.hashtags_per_post if b.planned_hashtags is None else b.planned_hashtags, "mentions": b.mentions,
                "caption_len": t["caption_len"] if b.caption_len is None else b.caption_len, "hour": t["hour"] if b.hour is None else b.hour,
                "weekday": t["weekday"] if b.weekday is None else b.weekday}
        pred = mining.analyse_post(acct, post, b.avg_likes, b.avg_comments, habit_hashtags=b.hashtags_per_post)
        persona = mining.match_persona(b.followers, (b.avg_likes + b.avg_comments) / max(b.followers, 1) * 100, b.hashtags_per_post)
        ter = max(mining.tier_er(b.followers), 1e-6); f1 = max(b.followers, 1)
        ratio_now = (pred["next_likes"] + pred["next_comments"]) / f1 / ter
        g = 1 + pred["combined_gain_pct"] / 100
        ratio_better = (pred["next_likes"] + pred["next_comments"]) * g / f1 / ter
    fee_now = pricing.fee(b.followers, ratio_now, b.category, b.sponsored_per_month)
    fee_better = pricing.fee(b.followers, ratio_better, b.category, b.sponsored_per_month)
    per = fee_now["inr"]["mid"]
    if b.save:                                   # collected data: every submitted account is stored with the user's history
        ac = authdb.conn()
        ac.execute("INSERT INTO analyses(ts,user_id,handle,followers,tier,category,account_type,avg_likes,avg_comments,hashtags,posts_per_week,score,income_per_post,income_monthly,best_hashtags,pred_likes,persona,fee_mid_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (now(), u["id"], b.handle.strip()[:40], b.followers, tier, b.category, b.account_type, b.avg_likes, b.avg_comments,
                    b.hashtags_per_post, b.posts_per_week, score, per, fee_now["monthly_inr"], None if not best else ("5+" if best[0] == 5 else str(best[0])),
                    pred["next_likes"] if pred else None, persona["name"] if persona else None, fee_now["usd"]["mid"]))
        ac.commit(); ac.close()
    return {"handle": b.handle, "tier": tier, "score": score, "level": level, "sample": n,
            "benchmark": {"likes": round(bl, 1), "comments": round(bc, 2)}, "ratios": {"likes": round(lr, 2), "comments": round(cr, 2)},
            "suggestions": tips, "low_confidence": n < 100, "prediction": pred, "persona": persona, "fee": fee_now, "fee_improved": fee_better,
            "income": {"per_post": per, "low": fee_now["inr"]["low"], "high": fee_now["inr"]["high"], "monthly": fee_now["monthly_inr"]},
            "disclaimer": "The fee is an ESTIMATE: the dataset has no real earnings, so it combines published planning benchmarks for sponsored posts with the model's engagement forecast. Real fees depend on negotiation, usage rights and the brand."}


@router.get("/mining/typical")
def typical(_=Depends(require_user)):
    from app.services import mining
    b = mining.bundle()
    return {"trained": b is not None, "typical": b["typical"] if b else None}
