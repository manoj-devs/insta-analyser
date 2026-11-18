"""Influencer directory: loading, region tree, ESTIMATED earnings and the 'steps to earn more' engine.

Everything money-related is an estimate built from the transparent fee model in pricing.py plus the assumptions in the CONFIG block below.
The directory only holds the influencers that were loaded into it; it is not every influencer in the world.
"""
import csv, io, math, os, re, time
from app import db
from app.services import pricing

# ---------------------------------------------------------------- CONFIG (assumptions, shown on screen)
SPONSORED_SHARE = float(os.getenv("SPONSORED_SHARE", "0.20"))     # share of all posts that are paid brand posts
MAX_SPONSORED_YEAR = int(os.getenv("MAX_SPONSORED_YEAR", "120"))  # nobody sells more than this many paid posts a year
GROWTH_PCT_MONTH = float(os.getenv("GROWTH_PCT_MONTH", "2.0"))    # follower growth per month used for projections
OTHER_STREAMS_PCT = float(os.getenv("OTHER_STREAMS_PCT", "12"))   # affiliate / product / bonus income as % of sponsored income (optional step)
# price level of a market compared with the global (USA/UK style) benchmark curve. An ASSUMPTION, editable. Celebrities (10M+) are priced globally.
REGION_FACTOR = {"United States": 1.0, "United Kingdom": .95, "Canada": .95, "Australia": .95, "Germany": .9, "France": .9, "United Arab Emirates": .9,
                 "Singapore": .85, "Japan": .8, "South Korea": .8, "Brazil": .55, "Mexico": .55, "Turkey": .5, "Indonesia": .4, "Philippines": .4,
                 "Nigeria": .35, "South Africa": .45, "India": .45, "Pakistan": .35}
TARGET_PPW = {"Nano": 4, "Micro": 4, "Mid-tier": 5, "Macro": 5, "Mega": 5, "Celebrity": 4}   # posts per week that work well for the size (assumption)
ADJACENT = {"food_&_dining": "fitness_&_health", "gaming": "science_&_technology", "music": "film_tv_&_video", "family": "fitness_&_health",
            "arts_&_culture": "fashion_&_style", "diaries_&_daily_life": "travel_&_adventure", "youth_&_student_life": "learning_&_educational",
            "other_hobbies": "science_&_technology", "relationships": "fashion_&_style", "news_&_social_concern": "business_&_entrepreneurs"}
CATS = list(pricing.CATEGORY_FACTOR)
CONTINENT = {"India": "Asia", "Pakistan": "Asia", "Bangladesh": "Asia", "Sri Lanka": "Asia", "Nepal": "Asia", "Indonesia": "Asia", "Philippines": "Asia", "Japan": "Asia",
             "South Korea": "Asia", "Singapore": "Asia", "Malaysia": "Asia", "Thailand": "Asia", "Vietnam": "Asia", "United Arab Emirates": "Asia", "Saudi Arabia": "Asia",
             "Turkey": "Asia", "United States": "North America", "Canada": "North America", "Mexico": "North America", "United Kingdom": "Europe", "Germany": "Europe",
             "France": "Europe", "Spain": "Europe", "Italy": "Europe", "Netherlands": "Europe", "Brazil": "South America", "Argentina": "South America",
             "Colombia": "South America", "Nigeria": "Africa", "South Africa": "Africa", "Egypt": "Africa", "Kenya": "Africa", "Australia": "Oceania", "New Zealand": "Oceania"}
COUNTRY_ALIAS = {"usa": "United States", "us": "United States", "u.s.": "United States", "united states of america": "United States", "uk": "United Kingdom",
                 "england": "United Kingdom", "uae": "United Arab Emirates", "korea": "South Korea", "republic of korea": "South Korea"}
CAT_ALIAS = {"fashion": "fashion_&_style", "style": "fashion_&_style", "fitness": "fitness_&_health", "health": "fitness_&_health", "food": "food_&_dining",
             "travel": "travel_&_adventure", "tech": "science_&_technology", "technology": "science_&_technology", "business": "business_&_entrepreneurs",
             "comedy": "film_tv_&_video", "movies": "film_tv_&_video", "education": "learning_&_educational", "lifestyle": "diaries_&_daily_life",
             "beauty": "fashion_&_style", "sports": "sports", "music": "music", "gaming": "gaming", "art": "arts_&_culture", "news": "news_&_social_concern"}
HANDLE_RE = re.compile(r"^[a-z0-9._]{1,30}$")
TEMPLATE_HEADER = ["handle", "display_name", "continent", "country", "state_or_region", "city", "category", "account_type", "verified",
                   "followers", "avg_likes", "avg_comments", "posts_per_week", "as_of", "source"]
_CACHE = {"ver": 0, "rows": None, "ver_built": -1}


def short_tier(f):
    return pricing.market_tier(f).split(" ")[0]


def region_factor(country, followers):
    f = REGION_FACTOR.get(country, .6)
    return f + (1 - f) * min(1.0, followers / 10_000_000)       # the very biggest accounts are priced worldwide


def bench_er(followers):
    """typical engagement rate (a fraction) for an audience this size, from the trained mining model, with a plain fallback"""
    try:
        from app.services import mining
        if mining.available(): return max(mining.tier_er(followers), 1e-6)
    except Exception: pass
    return 0.06 if followers < 1_000 else .035 if followers < 10_000 else .02 if followers < 100_000 else .012 if followers < 1_000_000 else .008


def earn(followers, avg_likes, avg_comments, ppw, category, country, share=None, ratio=None, factor_override=None):
    """ESTIMATED income of one influencer. Returns USD numbers (the page converts to INR)."""
    share = SPONSORED_SHARE if share is None else share
    bench = bench_er(followers)
    er = (avg_likes + avg_comments) / max(followers, 1) if (avg_likes or 0) + (avg_comments or 0) > 0 else bench       # engagement not published: use the typical rate for the size
    ratio = er / bench if ratio is None else ratio
    f = pricing.fee(followers, ratio, category, 4)
    rf = region_factor(country, followers) if factor_override is None else factor_override
    fee = {k: v * rf for k, v in f["usd"].items()}
    n = min(max(ppw, 0) * 52 * share, MAX_SPONSORED_YEAR)
    return {"er_pct": round(er * 100, 3), "bench_pct": round(bench * 100, 3), "ratio": round(ratio, 2), "tier": short_tier(followers), "region_factor": round(rf, 2),
            "fee_low": round(fee["low"]), "fee": round(fee["mid"]), "fee_high": round(fee["high"]), "sponsored_per_year": round(n, 1),
            "year_low": round(fee["low"] * n), "year": round(fee["mid"] * n), "year_high": round(fee["high"] * n), "month": round(fee["mid"] * n / 12)}


# ---------------------------------------------------------------- loading and validating a CSV
def _num(v, name, lo=0, hi=None):
    try: x = float(str(v).replace(",", "").strip())
    except ValueError: raise ValueError(f"{name} must be a number")
    if x < lo or (hi is not None and x > hi): raise ValueError(f"{name} is out of range")
    return x


def clean_row(r):
    """validate one CSV row; returns a dict ready for the table or raises ValueError with a plain reason"""
    g = lambda k: (r.get(k) or "").strip()
    h = g("handle").lstrip("@").lower()
    if not HANDLE_RE.match(h): raise ValueError("handle may have letters, numbers, dots and underscores only (max 30)")
    c = g("country"); c = COUNTRY_ALIAS.get(c.lower(), c.title() if c.islower() or c.isupper() else c)
    if len(c) < 2: raise ValueError("country is required")
    cont = g("continent") or CONTINENT.get(c, "")
    if not cont: raise ValueError(f"country '{c}' is new: add a continent value")
    cat = g("category").lower(); cat = cat if cat in pricing.CATEGORY_FACTOR else CAT_ALIAS.get(cat)
    if not cat: raise ValueError("category is not one of: " + ", ".join(CATS))
    fol = int(_num(r.get("followers"), "followers", 100, 2_000_000_000)); lk = _num(r.get("avg_likes") or 0, "avg_likes"); cm = _num(r.get("avg_comments") or 0, "avg_comments")
    if lk + cm > fol * 1.5: raise ValueError("likes + comments are far larger than followers: check the numbers")
    ppw = _num(r.get("posts_per_week") or 4, "posts_per_week", 0, 60)
    ver = 1 if g("verified").lower() in ("1", "yes", "y", "true") else 0
    return (h, g("display_name")[:60] or h, cont, c, g("state_or_region")[:60] or None, g("city")[:60] or None, cat, g("account_type").lower()[:20] or "creator",
            ver, fol, lk, cm, ppw, g("as_of")[:10] or time.strftime("%Y-%m-%d"), g("source")[:80] or "uploaded by admin")


def load_csv(data: bytes, replace=False):
    text = data.decode("utf-8-sig", errors="replace")
    rd = csv.DictReader(io.StringIO(text))
    need = {"handle", "country", "category", "followers", "avg_likes", "avg_comments"}
    have = {(h or "").strip() for h in (rd.fieldnames or [])}
    if not need <= have: raise ValueError("The file is missing these columns: " + ", ".join(sorted(need - have)))
    good, bad, seen = [], [], set()
    for i, r in enumerate(rd, start=2):
        r = {(k or "").strip(): v for k, v in r.items()}
        try:
            row = clean_row(r)
            if row[0] in seen: raise ValueError("duplicate handle in this file")
            seen.add(row[0]); good.append(row)
        except ValueError as e: bad.append({"line": i, "handle": (r.get("handle") or "")[:30], "reason": str(e)})
        if len(good) + len(bad) > 50_000: raise ValueError("The file has more than 50,000 rows.")
    c = db.conn()
    try:
        if replace: c.execute("DELETE FROM directory")
        before = c.execute("SELECT COUNT(*) FROM directory").fetchone()[0]
        c.executemany("""INSERT INTO directory(handle,display_name,continent,country,state_or_region,city,category,account_type,verified,followers,avg_likes,avg_comments,posts_per_week,as_of,source,added)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,strftime('%s','now')) ON CONFLICT(handle) DO UPDATE SET display_name=excluded.display_name, continent=excluded.continent,
            country=excluded.country, state_or_region=excluded.state_or_region, city=excluded.city, category=excluded.category, account_type=excluded.account_type,
            verified=excluded.verified, followers=excluded.followers, avg_likes=excluded.avg_likes, avg_comments=excluded.avg_comments, posts_per_week=excluded.posts_per_week,
            as_of=excluded.as_of, source=excluded.source, added=excluded.added""", good)
        c.commit(); after = c.execute("SELECT COUNT(*) FROM directory").fetchone()[0]
    finally: c.close()
    _CACHE["ver"] += 1
    return {"read": len(good) + len(bad), "accepted": len(good), "rejected": len(bad), "new": max(after - before, 0) if not replace else after, "rejected_rows": bad[:200]}


def ensure_seed():
    """first start: remove any old sample rows, then load the bundled directory of real public figures if the table is empty"""
    c = db.conn(); c.execute("DELETE FROM directory WHERE LOWER(source) LIKE '%demo%' OR handle LIKE 'demo\\_%' ESCAPE '\\'"); c.commit()
    n = c.execute("SELECT COUNT(*) FROM directory").fetchone()[0]; c.close(); _CACHE["ver"] += 1
    p = os.path.join(os.path.dirname(os.path.dirname(__file__)), "seed", "influencer_directory.csv")
    if n == 0 and os.path.exists(p):
        with open(p, "rb") as f: return load_csv(f.read())


# ---------------------------------------------------------------- reading with earnings
def rows():
    """every directory row with the estimated earnings attached (cached until the directory changes)"""
    if _CACHE["rows"] is not None and _CACHE["ver_built"] == _CACHE["ver"]: return _CACHE["rows"]
    c = db.conn(); data = [dict(r) for r in c.execute("SELECT * FROM directory")]; c.close()
    for d in data:
        d["demo"] = False; d["er_known"] = (d["avg_likes"] or 0) + (d["avg_comments"] or 0) > 0
        d.update(earn(d["followers"], d["avg_likes"], d["avg_comments"], d["posts_per_week"] or 4, d["category"], d["country"]))
    _CACHE.update(rows=data, ver_built=_CACHE["ver"]); return data


def tree():
    t = {}
    for d in rows():
        co = t.setdefault(d["continent"], {}).setdefault(d["country"], {"n": 0, "states": {}})
        co["n"] += 1
        if d["state_or_region"]: co["states"][d["state_or_region"]] = co["states"].get(d["state_or_region"], 0) + 1
    return t


def select(continent="", country="", state="", category="", tier="", q=""):
    q = q.strip().lower().lstrip("@"); out = []
    for d in rows():
        if continent and d["continent"] != continent: continue
        if country and d["country"] != country: continue
        if state and d["state_or_region"] != state: continue
        if category and d["category"] != category: continue
        if tier and d["tier"] != tier: continue
        if q and q not in d["handle"] and q not in (d["display_name"] or "").lower(): continue
        out.append(d)
    return out


def _median(v):
    v = sorted(v); n = len(v)
    return 0 if not n else v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def summary(sel):
    n = len(sel)
    if not n: return {"n": 0}
    tiers, cats = {}, {}
    for d in sel: tiers[d["tier"]] = tiers.get(d["tier"], 0) + 1; cats[d["category"]] = cats.get(d["category"], 0) + 1
    ys = [d["year"] for d in sel]; lo = max(min(ys), 1); bins = []
    edges = [0, 1e3, 5e3, 2e4, 1e5, 5e5, 2e6, 1e7, float("inf")]; labels = ["<$1K", "$1K-5K", "$5K-20K", "$20K-100K", "$100K-500K", "$500K-2M", "$2M-10M", "$10M+"]
    for i, lb in enumerate(labels): bins.append([lb, sum(1 for y in ys if edges[i] <= y < edges[i + 1])])
    top = sorted(sel, key=lambda d: -d["year"])[:10]
    order = ["Nano", "Micro", "Mid-tier", "Macro", "Mega", "Celebrity"]
    return {"n": n, "followers_total": sum(d["followers"] for d in sel), "er_median": round(_median([d["er_pct"] for d in sel]), 2),
            "year_median": round(_median(ys)), "year_total": sum(ys), "ppw_avg": round(sum(d["posts_per_week"] or 0 for d in sel) / n, 1),
            "top_category": max(cats, key=cats.get), "tiers": [[t, tiers.get(t, 0)] for t in order if tiers.get(t)], "categories": sorted(cats.items(), key=lambda x: -x[1])[:8],
            "hist": bins, "top10": [{"id": d["id"], "handle": d["handle"], "year": d["year"], "followers": d["followers"]} for d in top],
            "demo_share": round(100 * sum(1 for d in sel if d["demo"]) / n)}


# ---------------------------------------------------------------- steps to earn more
def _plus(base, new): return {k: max(new[k] - base[k], 0) for k in ("year_low", "year", "year_high")}


def steps(d):
    """3-6 ranked, explainable actions. Each uplift is the same earnings engine re-run with that one change."""
    f, lk, cm, ppw, cat, co = d["followers"], d["avg_likes"], d["avg_comments"], d["posts_per_week"] or 4, d["category"], d["country"]
    base = earn(f, lk, cm, ppw, cat, co); tier = base["tier"]; out = []
    def add(title, why, todo, up=None, note=""):
        out.append({"title": title, "why": why, "todo": todo, "uplift_usd": up, "note": note})
    # 1 engagement
    if base["ratio"] < .95:
        e = earn(f, lk, cm, ppw, cat, co, ratio=1.0)
        add("Lift engagement to the typical level for your size",
            f"Your engagement is {base['er_pct']}% against about {base['bench_pct']}% typical for a {tier} account ({base['ratio']}x). Brands pay for engaged audiences, not only for size.",
            ["Open every post with a hook in the first line and the first 2 seconds of a reel.", "Ask one clear question per post and reply to comments in the first hour.", "Use more reels and carousels, which are shown to non-followers, and track saves and shares.", "Drop post types that are in your bottom 20% by engagement."], _plus(base, e))
    # 2 posting frequency
    tp = TARGET_PPW.get(tier, 4)
    if ppw < tp:
        e = earn(f, lk, cm, tp, cat, co)
        add(f"Post about {tp} times a week",
            f"You post {ppw:g} times a week. More regular posting means more brand-safe slots to sell and steadier growth.",
            [f"Plan {tp} posts a week with a simple weekly template (1 reel, 1 carousel, 1 story-led post).", "Batch-create on one day and schedule posts for your audience's best hours (see Dashboard: best time to post)."], _plus(base, e))
    elif ppw > tp * 2:
        add("Keep quality up while posting this often", f"You post {ppw:g} times a week, well above the {tp} that works for most {tier} accounts. Too many posts can lower engagement per post.",
            ["Test posting fewer, stronger posts for 4 weeks and compare engagement.", "Keep the best-performing formats and drop the rest."], None, "No income change is estimated for this step.")
    # 3 next tier
    lims = [10_000, 100_000, 500_000, 1_000_000, 10_000_000]
    nxt = next((x for x in lims if x > f), None)
    if nxt:
        e = earn(nxt, lk * nxt / f, cm * nxt / f, ppw, cat, co, ratio=base["ratio"])
        mo = math.ceil(math.log(nxt / f) / math.log(1 + GROWTH_PCT_MONTH / 100)) if f < nxt else 0
        add(f"Reach {nxt:,} followers (next price band)",
            f"You are at {f:,}. You need {nxt - f:,} more followers, about {mo} months at {GROWTH_PCT_MONTH:g}% growth a month. Rates jump when you cross a band.",
            ["Collaborate with 2 accounts of similar size every month (shout-outs, joint reels).", "Use 5-8 relevant hashtags and post reels aimed at people who do not follow you yet.", "Pin your 3 best posts and make your bio say who you help and how to contact you."], _plus(base, e),
            "Income shown is what you would earn after reaching the band, not today.")
    # 4 category
    cf = pricing.CATEGORY_FACTOR.get(cat, 1.0)
    if cf < 1.1:
        alt = ADJACENT.get(cat, "business_&_entrepreneurs"); af = pricing.CATEGORY_FACTOR[alt]
        e = earn(f, lk, cm, ppw, alt, co)
        add(f"Add a higher-paying angle: {alt.replace('_&_', ' & ').replace('_', ' ')}",
            f"Brands in your current niche pay a factor of {cf:g}; the nearby niche pays {af:g}. Blend it into some of your content, you do not have to switch.",
            ["Make 1 post in 4 about the nearby niche (for example tools, tips or money angle).", "Pitch brands that sit between both niches."], _plus(base, e), "The category factor is an assumption of the fee model.")
    # 5 more brand deals
    e = earn(f, lk, cm, ppw, cat, co, share=SPONSORED_SHARE + .10)
    add("Sell more brand campaigns (aim for +10% of your posts)",
        f"The estimate assumes {SPONSORED_SHARE * 100:.0f}% of your posts are paid. Most of the gap between creators is how many deals they close, not the rate.",
        ["Build a one-page media kit: followers, engagement, audience country and age, past results, rates.", "Write a rate card (reel, story, carousel, bundle) and a monthly retainer option.", "Pitch 10 local brands and 3 agencies every month; follow up after 5 days.", "Offer 3-month retainers: steady income and higher rates."], _plus(base, e))
    # 6 regional price level
    if base["region_factor"] < .8:
        e = earn(f, lk, cm, ppw, cat, co, factor_override=min(1.0, base["region_factor"] + .15))
        add("Pitch brands outside your home market",
            f"Rates in {co} are about {base['region_factor']:.2f}x the global level in this model. Export and international brands pay closer to the global rate.",
            ["Add a line to the media kit about your international audience share.", "List yourself on global creator marketplaces and pitch brands that sell abroad."], _plus(base, e), "Assumes a modest +0.15 in price level.")
    # 7 other streams
    o = {k: round(base[k] * OTHER_STREAMS_PCT / 100) for k in ("year_low", "year", "year_high")}
    add("Add a second income stream (affiliate links, product, paid community)", "Creators who only sell sponsored posts depend on a few brands. A second stream adds income when deals are slow.",
        ["Share affiliate links for tools you really use and put them in your bio.", "Offer one small paid product: a guide, template or preset pack."], o, f"Assumes about {OTHER_STREAMS_PCT:g}% on top of sponsored income. A rough assumption.")
    # 8 timing (no money)
    add("Post when your audience is online", "Posting at the best hour gives each post more early engagement, which helps it reach more people.",
        ["Open Dashboard > Best time to post and pick the top 2 time slots.", "Check your own Insights after 4 weeks and adjust."], None, "No income change is estimated for this step.")
    ranked = sorted(out, key=lambda s: -(s["uplift_usd"] or {"year": -1})["year"])
    for i, s in enumerate(ranked, 1): s["rank"] = i
    return ranked[:6]


def projection(d):
    """income per year if nothing changes vs if the steps are followed, at 3, 6, 12 months (a PROJECTION, not a promise)"""
    f, lk, cm, ppw, cat, co = d["followers"], d["avg_likes"], d["avg_comments"], d["posts_per_week"] or 4, d["category"], d["country"]
    base = earn(f, lk, cm, ppw, cat, co); tp = max(ppw, TARGET_PPW.get(base["tier"], 4)); out = []
    for m in (0, 3, 6, 12):
        g = (1 + GROWTH_PCT_MONTH / 100) ** m; ff = f * g
        now = earn(ff, lk * g, cm * g, ppw, cat, co, ratio=base["ratio"])
        better = earn(ff, lk * g, cm * g, tp, cat, co, share=SPONSORED_SHARE + .10, ratio=max(base["ratio"], 1.0))
        out.append({"month": m, "followers": round(ff), "now": now["year"], "with_steps": better["year"]})
    return out


def simulate(followers, er_pct, ppw, share_pct, growth_pct, category, country):
    """12-month what-if. er_pct is engagement as a % of followers."""
    out, tot = [], {"low": 0, "mid": 0, "high": 0}
    for m in range(1, 13):
        ff = followers * (1 + growth_pct / 100) ** m
        e = earn(ff, ff * er_pct / 100 * .985, ff * er_pct / 100 * .015, ppw, category, country, share=share_pct / 100)
        out.append({"month": m, "followers": round(ff), "low": round(e["year_low"] / 12), "mid": round(e["month"]), "high": round(e["year_high"] / 12)})
        tot["low"] += out[-1]["low"]; tot["mid"] += out[-1]["mid"]; tot["high"] += out[-1]["high"]
    return {"months": out, "year_total": tot, "bench_pct": round(bench_er(followers) * 100, 3)}


def profile(i):
    d = next((x for x in rows() if x["id"] == i), None)
    if not d: return None
    return {**d, "steps": steps(d), "projection": projection(d)}
