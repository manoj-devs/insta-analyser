"""Data mining API: status/report, admin training + breakouts, caption checker, influencer analyser."""
import re
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app import db
from app.auth import audit, now, require_admin, require_portal_user, require_user
from app.services import mining, pricing

router = APIRouter(prefix="/api")


@router.get("/mining/status")
def status(_=Depends(require_user)):
    r = mining.report()
    return {"trained": mining.available(), "running": mining.STATE["running"], "log": mining.STATE["log"][-40:], "error": mining.STATE["error"],
            "started": mining.STATE["started"], "finished": mining.STATE["finished"], "trained_at": r["trained_at"] if r else None}


@router.get("/mining/report")
def report(_=Depends(require_user)):
    r = mining.report()
    if not r: raise HTTPException(404, "The mining models have not been trained yet. An admin can train them from the Mining Lab.")
    return r


@router.post("/admin/mining/train")
def train(request: Request, u=Depends(require_admin)):
    import os
    from app import config
    if not os.path.exists(config.WAREHOUSE): raise HTTPException(404, "Build the warehouse first (ETL).")
    if not mining.start(): raise HTTPException(409, "Training is already running.")
    audit("mining_train", u["id"], u["email"], request); return {"started": True}


@router.get("/admin/mining/breakouts")
def breakouts(_=Depends(require_admin)):
    r = mining.report(admin=True)
    if not r: raise HTTPException(404, "Train the models first.")
    return r["breakouts"]


class CaptionIn(BaseModel):
    caption: str = Field(min_length=3, max_length=2200)


@router.post("/caption/check")
def caption(b: CaptionIn, u=Depends(require_portal_user)):
    out = mining.check_caption(b.caption)
    if out is None: raise HTTPException(404, "The mining models have not been trained yet.")
    c = db.conn(); c.execute("INSERT INTO events(ts,user_id,kind,name) VALUES (?,?,'feature','caption_check')", (now(), u["id"])); c.commit(); c.close()
    return out


class InfluencerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: str = "influencer"
    followers: int = Field(ge=100, le=2_000_000_000)
    category: str
    business: bool = False
    avg_likes: float | None = Field(default=None, ge=0)
    avg_comments: float | None = Field(default=None, ge=0)
    hashtags_per_post: int | None = Field(default=None, ge=0, le=30)
    caption: str = Field(default="", max_length=2200)
    hour: int | None = Field(default=None, ge=0, le=23)
    weekday: int | None = Field(default=None, ge=0, le=6)
    post_likes: float | None = Field(default=None, ge=0)
    post_comments: float | None = Field(default=None, ge=0)
    sponsored_per_month: int = Field(default=4, ge=0, le=60)
    save: bool = True


@router.post("/influencer/analyse")
def influencer(b: InfluencerIn, u=Depends(require_portal_user)):
    if b.kind not in ("celebrity", "athlete", "influencer", "brand", "other"): raise HTTPException(400, "Unknown account kind.")
    bun = mining.bundle()
    if bun is None: raise HTTPException(404, "The mining models have not been trained yet.")
    if b.category not in bun["cats"]: raise HTTPException(400, "Unknown category.")
    typ = bun["typical"]; cap = b.caption.strip()
    tags, ments = len(set(re.findall(r"#\w+", cap.lower()))), len(re.findall(r"@\w+", cap))
    assumed = b.avg_likes is None or b.avg_comments is None
    if assumed:   # no engagement typed in: assume the typical rate for this audience size (98.5% likes / 1.5% comments)
        er0 = max(mining.tier_er(b.followers), 1e-6) * b.followers
        b.avg_likes = er0 * .985 if b.avg_likes is None else b.avg_likes
        b.avg_comments = er0 * .015 if b.avg_comments is None else b.avg_comments
    habit = typ["hashtags"] if b.hashtags_per_post is None else b.hashtags_per_post
    post = {"hashtags": tags if cap else habit, "mentions": ments if cap else typ["mentions"], "caption_len": len(cap) if cap else typ["caption_len"],
            "hour": typ["hour"] if b.hour is None else b.hour, "weekday": typ["weekday"] if b.weekday is None else b.weekday}
    acct = {"followers": b.followers, "category": b.category, "business": b.business}
    pred = mining.analyse_post(acct, post, b.avg_likes, b.avg_comments, habit_hashtags=habit)
    fo = max(b.followers, 1); ter = max(mining.tier_er(b.followers), 1e-6)
    er = (b.avg_likes + b.avg_comments) / fo
    persona = mining.match_persona(b.followers, er * 100, habit)
    ratio_next = (pred["next_likes"] + pred["next_comments"]) / fo / ter
    fee_next = pricing.fee(b.followers, ratio_next, b.category, b.sponsored_per_month)
    fee_better = pricing.fee(b.followers, ratio_next * (1 + pred["combined_gain_pct"] / 100), b.category, b.sponsored_per_month)
    fee_avg = pricing.fee(b.followers, er / ter, b.category, b.sponsored_per_month)
    this_post = None
    if b.post_likes is not None:
        r = ((b.post_likes + (b.post_comments or 0)) / fo) / ter
        this_post = {"engagement_pct": round((b.post_likes + (b.post_comments or 0)) / fo * 100, 2), "vs_average_pct": round(((b.post_likes + (b.post_comments or 0)) / max(b.avg_likes + b.avg_comments, 1) - 1) * 100),
                     "fee": pricing.fee(b.followers, r, b.category, 1)}
    cc = mining.check_caption(cap) if len(cap) >= 3 else None
    verdict = ("far below" if er / ter < .5 else "below" if er / ter < .85 else "in line with" if er / ter <= 1.3 else "above" if er / ter <= 2.5 else "far above")
    tier = mining.tier_of(b.followers)
    out = {"name": b.name, "kind": b.kind, "tier": tier, "followers": b.followers, "engagement_pct": round(er * 100, 3), "benchmark_pct": round(ter * 100, 3),
           "engagement_vs_benchmark": verdict, "persona": persona, "prediction": pred, "caption": cc, "post_used": post,
           "fee_next": fee_next, "fee_if_improved": fee_better, "fee_at_average": fee_avg, "this_post": this_post,
           "model_in_range": b.followers <= bun["follower_cap"], "engagement_assumed": assumed,
           "avg_likes_used": round(b.avg_likes), "avg_comments_used": round(b.avg_comments),
           "disclaimer": "Estimate only. This tool never contacts Instagram: it uses the public numbers you typed in. The dataset has no real earnings, so fees come from published planning benchmarks scaled by the model's engagement forecast; celebrity-level (10M+) prices follow the Hopper HQ Instagram Rich List agency-rate estimates, and real deals vary widely."}
    if b.save:
        c = db.conn()
        c.execute("INSERT INTO lookups(ts,user_id,name,kind,category,followers,avg_likes,avg_comments,tier,persona,next_likes,fee_low_usd,fee_mid_usd,fee_high_usd,fee_mid_inr) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (now(), u["id"], b.name.strip(), b.kind, b.category, b.followers, b.avg_likes, b.avg_comments, tier, persona["name"] if persona else None,
                   pred["next_likes"], fee_next["usd"]["low"], fee_next["usd"]["mid"], fee_next["usd"]["high"], fee_next["inr"]["mid"]))
        c.commit(); c.close()
    return out
