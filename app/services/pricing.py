"""Estimated fee for ONE sponsored Instagram post.

The warehouse has no real earnings, so the fee is an ESTIMATE built from three transparent parts:
  1. a price curve through published planning benchmarks (follower count -> USD per sponsored post),
  2. an engagement factor from the mining model (how strong this post is expected to be for its audience),
  3. a small category factor (assumption).
Benchmarks (USD per sponsored post): nano <10K $10-$100, micro 10K-100K $100-$500, mid 100K-500K $500-$5,000,
macro 500K-1M $5,000-$10,000, mega 1M+ $10,000+.  Source: Influencer Marketing Hub, "Instagram Influencer Rates" (2026).
Celebrity range (10M+): anchored on Hopper HQ's Instagram Rich List (agency-rate estimates: 2019 and 2024 editions,
about $5-6 per 1,000 followers for the biggest accounts, e.g. 633M followers ~ $3.4M per post, 293M ~ $1.8M).
Above ~650M followers (beyond any listed account) the curve is EXTRAPOLATED and flagged as such.
"""
import math, os

INR_PER_USD = float(os.getenv("INR_PER_USD", "88"))              # assumption, change with the environment variable
# (followers, typical USD per sponsored post): anchor points placed inside the benchmark ranges above
ANCHORS = [(1_000, 10), (10_000, 75), (100_000, 300), (500_000, 2_500), (1_000_000, 9_000), (10_000_000, 60_000), (100_000_000, 580_000),
           (300_000_000, 1_760_000), (630_000_000, 3_430_000)]
MARKET_TIERS = [(10_000, "Nano (<10K)"), (100_000, "Micro (10K-100K)"), (500_000, "Mid-tier (100K-500K)"),
                (1_000_000, "Macro (500K-1M)"), (10_000_000, "Mega (1M-10M)"), (float("inf"), "Celebrity (10M+)")]
CATEGORY_FACTOR = {"business_&_entrepreneurs": 1.25, "science_&_technology": 1.2, "fashion_&_style": 1.15, "fitness_&_health": 1.15,
                   "travel_&_adventure": 1.1, "celebrity_&_pop_culture": 1.1, "sports": 1.05, "film_tv_&_video": 1.05, "music": 1.0,
                   "food_&_dining": 1.0, "gaming": 1.0, "learning_&_educational": 1.0, "family": .95, "arts_&_culture": .9,
                   "news_&_social_concern": .9, "relationships": .9, "other_hobbies": .9, "diaries_&_daily_life": .85, "youth_&_student_life": .85}


def market_tier(f):
    for lim, name in MARKET_TIERS:
        if f < lim: return name


def curve_usd(followers):
    """log-log interpolation between the anchor points (price grows slower than followers)."""
    f = max(float(followers), 1000.0)
    pts = ANCHORS
    if f >= pts[-1][0]:
        (x0, y0), (x1, y1) = pts[-2], pts[-1]
    else:
        i = next(i for i in range(1, len(pts)) if f <= pts[i][0]); (x0, y0), (x1, y1) = pts[i - 1], pts[i]
    k = (math.log(y1) - math.log(y0)) / (math.log(x1) - math.log(x0))
    return math.exp(math.log(y0) + k * (math.log(f) - math.log(x0)))


def fee(followers, engagement_ratio, category=None, posts_per_month=4):
    """engagement_ratio = this post's expected engagement rate / typical engagement rate for the same audience size."""
    base = curve_usd(followers)
    eng = min(max(math.sqrt(max(engagement_ratio, 1e-6)), 0.6), 1.6)
    cat = CATEGORY_FACTOR.get(category, 1.0)
    mid = base * eng * cat
    usd = {"low": mid * 0.5, "mid": mid, "high": mid * 1.8}
    return {"market_tier": market_tier(followers), "extrapolated": followers > 650_000_000, "celebrity_reference": followers > 10_000_000,
            "base_usd": round(base), "engagement_factor": round(eng, 2), "category_factor": cat,
            "usd": {k: round(v) for k, v in usd.items()}, "inr": {k: round(v * INR_PER_USD) for k, v in usd.items()},
            "monthly_usd": round(mid * posts_per_month), "monthly_inr": round(mid * posts_per_month * INR_PER_USD),
            "yearly_inr": round(mid * posts_per_month * 12 * INR_PER_USD), "posts_per_month": posts_per_month, "inr_per_usd": INR_PER_USD}
