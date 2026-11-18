"""CREATOR INCOME ANALYSER (organic income, NO sponsorship).

This module is deliberately separate from the brand-deal fee logic (app/services/pricing.py and directory.earn). It never calls them.
It answers: "what can my own content earn, without a brand paying me?"  Every money figure is an ESTIMATE, shown as low / likely / high.

Real data used: the warehouse (fact_posts, 605K posts) for engagement benchmarks, percentile rank and what worked (hashtags, caption length, day, hour).
Assumptions (conversion rates, prices) are in ASSUMPTIONS below and are shown to the user as they are.
"""
import math, sqlite3, threading
import numpy as np
from app import config

# ------------------------------------------------------------------ size bands (same bands as the warehouse summary_tier table)
BANDS = [(1_000, "Nano (<1K)"), (10_000, "Micro (1K-10K)"), (100_000, "Mid (10K-100K)"), (1_000_000, "Macro (100K-1M)"), (float("inf"), "Mega (1M+)")]
TARGET_PPW = 4            # posts a week that is a good rhythm for building income (assumption)

# ------------------------------------------------------------------ assumptions (all shown to the user)
REACH_RATE = {"Nano (<1K)": .35, "Micro (1K-10K)": .28, "Mid (10K-100K)": .20, "Macro (100K-1M)": .14, "Mega (1M+)": .10}   # share of followers one post reaches (likely)
POST_TYPE_REACH = {"reel": 1.3, "carousel": 1.1, "image": 1.0, "story": .8}
SCEN = {"low": .6, "mid": 1.0, "high": 1.5}          # scenario multiplier on reach
STREAMS = {
    "affiliate": {"title": "Affiliate links", "ctr": (.003, .008, .018), "conv": (.01, .025, .04), "aov_usd": 30.0, "earn_pct": 6.0,
                  "how": "reach of your posts x link clicks x buyers x order value x your commission"},
    "product": {"title": "Your own digital product", "buyers": (.0005, .0015, .004), "price_usd": 9.0, "earn_pct": 85.0,
                "how": "followers x share who buy each month x price x what you keep"},
    "service": {"title": "Services (editing, design, coaching, freelance)", "leads": (.0003, .001, .0025), "close": .30, "price_usd": 35.0, "earn_pct": 100.0,
                "how": "followers x share who enquire x share you win x price per job"},
    "membership": {"title": "Paid broadcast channel / subscription", "subs": (.0005, .002, .006), "price_usd": 2.0, "earn_pct": 85.0,
                   "how": "followers x share who subscribe x monthly price x what you keep"}}
OFFER_DEFAULT = {"affiliate": {"conv": .025, "earn_pct": 6.0, "price_usd": 30.0}, "product": {"conv": .015, "earn_pct": 85.0, "price_usd": 9.0},
                 "service": {"conv": .010, "earn_pct": 100.0, "price_usd": 35.0}}
GROWTH_PCT_MONTH = 2.0
ASSUMPTIONS = {
    "note": "These are planning assumptions, not measured results. They are the numbers behind every estimate; change the inputs on the page to use your own.",
    "reach_rate_of_followers": REACH_RATE, "reach_by_post_type": POST_TYPE_REACH, "scenario_reach_multiplier": SCEN,
    "target_posts_per_week": TARGET_PPW, "growth_pct_per_month": GROWTH_PCT_MONTH,
    "streams": {k: {kk: vv for kk, vv in v.items()} for k, v in STREAMS.items()},
    "platform_programs": "Platform bonuses, gifts and subscriptions depend on the country and change often, so they are NOT included in any number.",
    "sponsorship": "Brand deals and sponsored posts are NOT included. That is the separate Influencer Analyser / Region Influencers page.",
    "benchmark": "Engagement benchmark = 605,563 posts from the warehouse, grouped by account size. The posts end in August 2019, so they show historical patterns."}


def band(f):
    for lim, name in BANDS:
        if f < lim: return name


# ------------------------------------------------------------------ benchmarks from the warehouse (built once, cached)
_B = {}
_LOCK = threading.Lock()


def _build():
    import pandas as pd
    c = sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)
    d = pd.read_sql("SELECT p.followers_at_post f, p.engagement_rate_pct er, p.hashtag_count h, p.description_length dl, p.post_hour hr, t.weekday wd "
                    "FROM fact_posts p JOIN dim_date t ON t.date_key=p.date_key WHERE p.followers_at_post>0", c)
    c.close()
    d = d[(d.er >= 0) & (d.er < 1000)]
    d["band"] = [band(x) for x in d.f.values]
    out = {}
    hb = [(0, 0, "no hashtags"), (1, 3, "1-3 hashtags"), (4, 8, "4-8 hashtags"), (9, 15, "9-15 hashtags"), (16, 999, "16+ hashtags")]
    lb = [(0, 49, "under 50 characters"), (50, 149, "50-149 characters"), (150, 299, "150-299 characters"), (300, 99999, "300+ characters")]
    for name in [b[1] for b in BANDS] + ["all"]:
        s = d if name == "all" else d[d.band == name]
        if len(s) < 200: continue
        er = np.sort(s.er.values)
        def grp(col, bins):
            r = []
            for lo, hi, lab in bins:
                x = s[(s[col] >= lo) & (s[col] <= hi)]
                if len(x) >= 150: r.append({"label": lab, "lo": lo, "hi": hi, "posts": int(len(x)), "median_er": round(float(x.er.median()), 2)})
            return r
        wd = [{"label": k, "posts": int(len(g)), "median_er": round(float(g.er.median()), 2)} for k, g in s.groupby("wd") if len(g) >= 150]
        hr = [{"label": f"{int(k):02d}:00", "posts": int(len(g)), "median_er": round(float(g.er.median()), 2)} for k, g in s.groupby("hr") if len(g) >= 150]
        out[name] = {"er": er, "n": int(len(s)), "median": float(np.median(er)), "p25": float(np.percentile(er, 25)), "p75": float(np.percentile(er, 75)),
                     "p90": float(np.percentile(er, 90)), "hashtags": grp("h", hb), "caption": grp("dl", lb), "weekday": wd, "hour": hr}
    _B.update(out)
    del d, c
    import gc; gc.collect()
    try:
        import ctypes; ctypes.CDLL("libc.so.6").malloc_trim(0)       # hand the working memory back to the system (Linux)
    except Exception: pass


def bench(name):
    if not _B:
        with _LOCK:                                   # one thread builds the benchmarks; the others wait for it
            if not _B:
                try: _build()
                except Exception: _B["_failed"] = True
    return _B.get(name) or _B.get("all")


def available():
    return bool(bench("all"))


def percentile(er_pct, b):
    """share (0-100) of posts in the same size band that had a LOWER engagement rate"""
    arr = bench(b)["er"]
    return int(round(100 * np.searchsorted(arr, er_pct, side="left") / len(arr)))


def verdict(p):
    return "Excellent" if p >= 90 else "Above average" if p >= 65 else "About average" if p >= 40 else "Below average" if p >= 15 else "Needs work"


# ------------------------------------------------------------------ helpers
def _f(v, d=0.0, lo=0.0, hi=1e12):
    try: x = float(v)
    except (TypeError, ValueError): return d
    return min(max(x, lo), hi)


def region_price_level(country, followers):
    from app.services import directory as D
    return D.region_factor(country, followers)       # only the country price level is shared, not any sponsorship logic


def quality_factor(er_pct, b):
    """how strong the audience engagement is against the same size band (0.6 - 1.5)"""
    med = bench(b)["median"]
    return min(max(math.sqrt(max(er_pct, .01) / max(med, .01)), .6), 1.5)


def activity_factor(ppw):
    return min(max(ppw / TARGET_PPW, .2), 1.0)


# ------------------------------------------------------------------ one post
def analyze_post(p):
    f = max(_f(p.get("followers")), 1.0); likes, com, sav, sh = (_f(p.get(k)) for k in ("likes", "comments", "saves", "shares"))
    b = band(f); B = bench(b)
    ptype = p.get("post_type") if p.get("post_type") in POST_TYPE_REACH else "image"
    reach_given = _f(p.get("reach")) > 0
    reach = _f(p.get("reach")) if reach_given else f * REACH_RATE[b] * POST_TYPE_REACH[ptype]
    er = (likes + com) / f * 100                         # same definition as the warehouse benchmark
    deep = (likes + com + sav + sh)
    er_reach = deep / reach * 100 if reach else 0
    pc = percentile(er, b)
    offer = p.get("offer") if p.get("offer") in OFFER_DEFAULT else "affiliate"
    od = OFFER_DEFAULT[offer]; rf = region_price_level(p.get("country") or "India", f)
    price = _f(p.get("price_usd"), od["price_usd"] * rf, 0.0, 1e7) or od["price_usd"] * rf
    earn_pct = _f(p.get("earn_pct"), od["earn_pct"], 0, 100)
    q = quality_factor(er, b)
    clicks_given = _f(p.get("link_clicks")) > 0; orders_given = _f(p.get("orders")) > 0
    inc = {}
    for i, k in enumerate(("low", "mid", "high")):
        r = reach if reach_given else reach * SCEN[k]
        ctr = STREAMS["affiliate"]["ctr"][i]; cv = od["conv"] * (.4, 1, 1.6)[i]
        clicks = _f(p.get("link_clicks")) if clicks_given else r * ctr
        orders = _f(p.get("orders")) if orders_given else clicks * cv * q
        inc[k] = round(orders * price * earn_pct / 100, 2)
    tips = []
    for key, lab, mine in (("hashtags", "hashtags", _bin(B["hashtags"], _f(p.get("hashtags"), -1))), ("caption", "caption length", _bin(B["caption"], _f(p.get("caption_len"), -1)))):
        rows = B[key]
        if rows:
            best = max(rows, key=lambda r: r["median_er"])
            if mine is None or mine["label"] != best["label"]:
                tips.append(f"In your size band, posts with {best['label']} had the highest median engagement ({best['median_er']}%) for {lab}.")
    if B["weekday"]:
        bd = max(B["weekday"], key=lambda r: r["median_er"]); tips.append(f"{bd['label']} had the highest median engagement in your size band ({bd['median_er']}%). Historical data, to 2019.")
    if sav + sh > 0 and reach and (sav + sh) / reach * 100 < 1.0:
        tips.append("Saves and shares are low for the reach. Posts that are useful to keep or send to a friend (tips, lists, how-tos) tend to earn more over time.")
    return {"band": b, "er_pct": round(er, 2), "er_on_reach_pct": round(er_reach, 2), "band_median": round(B["median"], 2), "band_p75": round(B["p75"], 2), "posts_in_band": B["n"],
            "percentile": pc, "verdict": verdict(pc), "reach": round(reach), "reach_estimated": not reach_given, "post_type": ptype, "offer": offer,
            "income_usd": inc, "price_usd": round(price, 2), "earn_pct": earn_pct, "quality_factor": round(q, 2), "tips": tips[:4],
            "basis": ("your link clicks" if clicks_given else "estimated link clicks from reach") + (" and your orders" if orders_given else "")}


def _bin(rows, v):
    if v < 0: return None
    for r in rows:
        if r["lo"] <= v <= r["hi"]: return r
    return None


# ------------------------------------------------------------------ monthly income model (all streams) - every "step" re-runs this with ONE change
def monthly(p):
    f = max(_f(p.get("followers")), 1.0); b = band(f); ppw = _f(p.get("posts_per_week"), 3, 0, 40)
    er = _f(p.get("er_pct"), 0, 0, 1000) or bench(b)["median"]
    rf = region_price_level(p.get("country") or "India", f); q = quality_factor(er, b); act = activity_factor(ppw)
    ptype = p.get("post_type") if p.get("post_type") in POST_TYPE_REACH else "image"
    reach_post = _f(p.get("reach_per_post")) or f * REACH_RATE[b] * POST_TYPE_REACH[ptype]
    ppm = ppw * 52 / 12
    en = p["enabled"] if p.get("enabled") is not None else {"affiliate": True}          # an empty dict means every stream is switched off
    pr = p.get("prices") or {}
    out = {}
    for k, S in STREAMS.items():
        usd = {}
        price = _f(pr.get(k), 0, 0, 1e7) or S["aov_usd" if k == "affiliate" else "price_usd"] * rf
        earn = _f((p.get("earn_pct") or {}).get(k), S["earn_pct"], 0, 100) if isinstance(p.get("earn_pct"), dict) else S["earn_pct"]
        for i, sc in enumerate(("low", "mid", "high")):
            if k == "affiliate":
                clicks = ppm * reach_post * (SCEN[sc] if not p.get("reach_per_post") else 1) * S["ctr"][i]
                orders = clicks * S["conv"][i] * q
                usd[sc] = orders * price * earn / 100
            elif k == "product":
                usd[sc] = f * S["buyers"][i] * q * act * price * earn / 100
            elif k == "service":
                usd[sc] = f * S["leads"][i] * q * act * S["close"] * price * earn / 100
            else:
                usd[sc] = f * S["subs"][i] * q * act * price * earn / 100
        out[k] = {"title": S["title"], "how": S["how"], "enabled": bool(en.get(k)), "price_usd": round(price, 2), "usd": {a: round(v, 2) for a, v in usd.items()}}
    tot = {sc: round(sum(v["usd"][sc] for v in out.values() if v["enabled"]), 2) for sc in ("low", "mid", "high")}
    return {"band": b, "er_pct": round(er, 2), "quality_factor": round(q, 2), "activity_factor": round(act, 2), "reach_per_post": round(reach_post), "posts_per_month": round(ppm, 1),
            "price_level": round(rf, 2), "streams": out, "total_usd": tot}


# ------------------------------------------------------------------ readiness score
def readiness(p):
    f = max(_f(p.get("followers")), 1.0); b = band(f); ppw = _f(p.get("posts_per_week"), 3, 0, 40); er = _f(p.get("er_pct"), 0, 0, 1000) or bench(b)["median"]
    pc = percentile(er, b); chk = p.get("checklist") or {}
    reach = _f(p.get("reach_per_post")) or f * REACH_RATE[b]
    depth = _f(p.get("save_share_pct"), -1)
    items = []
    s1 = round(30 * pc / 100); items.append(("Engagement quality", s1, 30, f"Your engagement is ahead of {pc}% of posts in your size band."))
    s2 = round(20 * min(ppw / TARGET_PPW, 1)); items.append(("Posting rhythm", s2, 20, f"{ppw:g} posts a week; about {TARGET_PPW} a week works well for building income."))
    s3 = round(20 * min(max(math.log10(f / 100) / 2, 0), 1)); items.append(("Audience size", s3, 20, f"{int(f):,} followers. About 10,000 opens the most income options."))
    s4 = 8 if depth < 0 else round(15 * min(depth / 2.0, 1)); items.append(("Saves and shares", s4, 15, "Not entered, so half marks are assumed." if depth < 0 else f"Saves + shares are {depth:g}% of reach (2% or more is strong)."))
    boxes = [("link", "A link in your bio"), ("niche", "One clear topic"), ("business", "Creator or business account"), ("contact", "A contact email on the profile")]
    done = [lab for key, lab in boxes if chk.get(key)]; s5 = round(15 * len(done) / 4); items.append(("Profile set-up", s5, 15, f"{len(done)} of 4 set-up items done."))
    total = sum(i[1] for i in items)
    label = "Just starting" if total < 35 else "Building" if total < 55 else "Ready to start earning" if total < 75 else "Strong"
    missing = [lab for key, lab in boxes if not chk.get(key)]
    return {"score": total, "label": label, "percentile": pc, "items": [{"name": a, "got": g, "of": m, "note": n} for a, g, m, n in items], "missing_setup": missing}


# ------------------------------------------------------------------ steps: each one is the same model with one change
def steps(p, base):
    f = max(_f(p.get("followers")), 1.0); b = band(f); B = bench(b); ppw = _f(p.get("posts_per_week"), 3); er = base["er_pct"]
    en = dict(p["enabled"] if p.get("enabled") is not None else {"affiliate": True}); cur = base["total_usd"]["mid"]; out = []
    def add(title, why, todo, q):
        m = monthly(q)["total_usd"]["mid"]; d = m - cur
        if d > 0.005: out.append({"title": title, "why": why, "todo": todo, "extra_usd_month": round(d, 2), "extra_pct": round(100 * d / cur) if cur > 0 else None})
    if ppw < TARGET_PPW:
        add(f"Post {TARGET_PPW} times a week", f"You post {ppw:g} times a week. More posts means more reach for your links and offers.", "Plan a simple weekly calendar and batch-make content on one day.", {**p, "posts_per_week": TARGET_PPW})
    target = B["p75"] if er < B["p75"] else None
    if target:
        add("Lift engagement to the top quarter of your size band", f"Your engagement is {er:g}%; the top quarter in your band starts at {B['p75']:.1f}%.", "Ask a question in every caption, reply to comments in the first hour, and use the formats that held attention best.", {**p, "er_pct": target})
    for k, S in STREAMS.items():
        if not en.get(k):
            add(f"Start: {S['title'].lower()}", f"This stream is switched off in your plan. {S['how'].capitalize()}.", {"affiliate": "Pick products you really use and put the link in your bio and stories.", "product": "Package one thing you already know (a template, a guide, a preset pack).", "service": "Say clearly in your bio what you offer and how to message you.", "membership": "Offer a small perk to your most loyal followers each month."}[k], {**p, "enabled": {**en, k: True}})
    add("Grow followers by 20%", "A bigger audience lifts every stream.", "Collaborate with similar-size creators and post your most shareable content more often.", {**p, "followers": f * 1.2, "reach_per_post": None})
    out.sort(key=lambda s: -s["extra_usd_month"])
    return out[:6]


def projection(p, growth_pct=None, months=12):
    g = GROWTH_PCT_MONTH if growth_pct is None else _f(growth_pct, GROWTH_PCT_MONTH, -20, 50)
    f0 = max(_f(p.get("followers")), 1.0); rows = []; cum = 0.0
    for m in range(1, months + 1):
        f = f0 * (1 + g / 100) ** m; q = {**p, "followers": f, "reach_per_post": None}
        t = monthly(q)["total_usd"]; cum += t["mid"]
        rows.append({"month": m, "followers": round(f), "low": t["low"], "mid": t["mid"], "high": t["high"], "cumulative_mid": round(cum, 2)})
    return {"growth_pct_month": g, "rows": rows, "milestones": {str(m): rows[m - 1] for m in (3, 6, 12) if m <= months}}


def plan(p):
    base = monthly(p)
    return {"inputs_band": base["band"], "model": base, "readiness": readiness({**p, "er_pct": base["er_pct"]}), "steps": steps(p, base),
            "projection": projection(p, p.get("growth_pct")), "note": "Organic income only. No sponsorship, no brand deals. Estimates, not actual earnings."}


def insights(b=None):
    B = bench(b) if b else bench("all")
    return {"band": b or "all", "posts": B["n"], "median_er": round(B["median"], 2), "p25": round(B["p25"], 2), "p75": round(B["p75"], 2), "p90": round(B["p90"], 2),
            "hashtags": B["hashtags"], "caption": B["caption"], "weekday": B["weekday"], "hour": B["hour"],
            "bands": [x[1] for x in BANDS if x[1] in _B], "note": "Historical posts up to August 2019. Use them as patterns to test, not rules."}
