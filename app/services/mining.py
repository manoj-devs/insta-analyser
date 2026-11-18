"""DATA MINING layer on top of the warehouse.

 1. Engagement predictor   gradient boosting on 605K posts -> expected likes / comments for a post (hold-out tested)
 2. Creator personas       k-means on accounts (audience size, engagement rate, hashtag habit)
 3. Caption text mining    TF-IDF + logistic regression: which wording separates posts that beat the model from those that fell short
 4. Breakout detector      posts far above what the predictor expected (admin list with reasons)

train() writes data/processed/mining/models.joblib and report.json. Everything is computed from the warehouse only.
"""
import os, re, json, time, sqlite3, datetime as dt
import numpy as np, pandas as pd, joblib
from sklearn.cluster import MiniBatchKMeans
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import mean_absolute_error, r2_score, roc_auc_score, silhouette_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from app import config

DIR = os.path.join(config.OUT_DIR, "mining")
MODEL_FILE, REPORT_FILE = os.path.join(DIR, "models.joblib"), os.path.join(DIR, "report.json")
FEATS = ["log_followers", "log_following", "log_posts", "hashtags", "mentions", "caption_len", "hour", "weekday", "category", "business"]
FEAT_LABELS = {"log_followers": "Followers (audience size)", "log_following": "Accounts followed", "log_posts": "Posts published so far",
               "hashtags": "Hashtags in the post", "mentions": "@mentions in the post", "caption_len": "Caption length",
               "hour": "Hour of posting", "weekday": "Day of the week", "category": "Content category", "business": "Business account"}
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TIERS = [(1000, "Nano (<1K)"), (10000, "Micro (1K-10K)"), (100000, "Mid (10K-100K)"), (1000000, "Macro (100K-1M)"), (float("inf"), "Mega (1M+)")]
TOKEN = r"(?u)\b[a-z][a-z']{2,}\b"
STATE = {"running": False, "log": [], "error": None, "started": None, "finished": None}
_CACHE = {}


def tier_of(f):
    for lim, name in TIERS:
        if f < lim: return name


def _log(m):
    STATE["log"].append(f"{dt.datetime.now():%H:%M:%S}  {m}")


def _db():
    return sqlite3.connect(f"file:{config.WAREHOUSE}?mode=ro", uri=True)


# ---------------------------------------------------------------- features
def make_X(df, cats):
    """df needs: followers, following, num_posts, hashtags, mentions, caption_len, hour, weekday (0-6), category (name), business (0/1)"""
    code = {c: i for i, c in enumerate(cats)}
    default = code.get("other_hobbies", 0)
    return pd.DataFrame({
        "log_followers": np.log1p(df["followers"].astype(float)), "log_following": np.log1p(df["following"].astype(float)),
        "log_posts": np.log1p(df["num_posts"].astype(float)), "hashtags": df["hashtags"].astype(float), "mentions": df["mentions"].astype(float),
        "caption_len": df["caption_len"].astype(float), "hour": df["hour"].astype(float), "weekday": df["weekday"].astype(float),
        "category": df["category"].map(code).fillna(default).astype(float), "business": df["business"].astype(float)})[FEATS]


def _regressor():
    return HistGradientBoostingRegressor(max_iter=220, learning_rate=0.12, max_leaf_nodes=63, min_samples_leaf=60, l2_regularization=1.0,
                                         categorical_features=[FEATS.index("category")], early_stopping=True, validation_fraction=0.1,
                                         n_iter_no_change=15, random_state=42)


def _load():
    con = _db()
    df = pd.read_sql("""SELECT f.post_id, f.user_key, f.likes, f.comments, f.followers_at_post followers, f.following_at_post following,
        f.num_posts_at_post num_posts, f.hashtag_count hashtags, f.mention_count mentions, f.description_length caption_len, f.post_hour hour,
        d.weekday wd, c.category_name category, u.is_business_account business, u.username
        FROM fact_posts f JOIN dim_date d USING(date_key) JOIN dim_category c USING(category_key) JOIN dim_user u USING(user_key)""", con)
    con.close()
    df["weekday"] = df["wd"].map({d: i for i, d in enumerate(DAYS)}).fillna(0).astype(int)
    return df.drop(columns="wd")


def _metrics(y, p, base_pred, raw_y):
    pr = np.expm1(np.clip(p, 0, None))
    return {"r2": round(float(r2_score(y, p)), 3), "mae": round(float(mean_absolute_error(raw_y, pr)), 1),
            "within_2x_pct": round(float(np.mean(((pr + 1) / (raw_y + 1) <= 2) & ((pr + 1) / (raw_y + 1) >= 0.5)) * 100), 1),
            "baseline_r2": round(float(r2_score(y, base_pred)), 3)}


# ---------------------------------------------------------------- training
def train(log=_log):
    t0 = time.time(); os.makedirs(DIR, exist_ok=True)
    log("Loading posts from the warehouse ...")
    df = _load(); n = len(df)
    cats = sorted(df["category"].unique().tolist())
    X = make_X(df, cats); yl, yc = np.log1p(df["likes"].values), np.log1p(df["comments"].values)
    tier = df["followers"].map(tier_of)
    log(f"{n:,} posts, {len(FEATS)} features")

    # ---- 1. engagement predictor
    tr, te = train_test_split(np.arange(n), test_size=0.2, random_state=42)
    models, rep_pred = {}, {"n_train": int(len(tr)), "n_test": int(len(te))}
    for name, y, raw in (("likes", yl, df["likes"].values), ("comments", yc, df["comments"].values)):
        log(f"Training the {name} model on {len(tr):,} posts ...")
        m = _regressor().fit(X.iloc[tr], y[tr]); models[name] = m
        p = m.predict(X.iloc[te])
        med = pd.Series(y[tr]).groupby(tier.iloc[tr].values).median()                    # baseline = median of the audience tier
        base = tier.iloc[te].map(med).fillna(float(np.median(y[tr]))).values
        mt = _metrics(y[te], p, base, raw[te])
        res = y[te] - p
        mt["interval"] = [round(float(np.quantile(res, .1)), 3), round(float(np.quantile(res, .9)), 3)]
        rep_pred[name] = mt
        log(f"  {name}: R2 {mt['r2']} (baseline {mt['baseline_r2']}), mean error {mt['mae']} {name}")
    log("Measuring which features matter (permutation importance) ...")
    samp = np.random.RandomState(1).choice(te, size=min(12000, len(te)), replace=False)
    pi = permutation_importance(models["likes"], X.iloc[samp], yl[samp], n_repeats=3, random_state=1, scoring="r2", n_jobs=1)
    imp = np.clip(pi.importances_mean, 0, None); tot = imp.sum() or 1
    rep_pred["importance"] = sorted([{"feature": f, "label": FEAT_LABELS[f], "pct": round(float(v / tot * 100), 1)} for f, v in zip(FEATS, imp)], key=lambda r: -r["pct"])

    # ---- reference numbers used at prediction time
    er = (df["likes"] + df["comments"]) / df["followers"].clip(lower=1)
    tier_er = er.groupby(tier).agg(["median", "size"])
    tier_def = df.groupby(tier).agg(following=("following", "median"), num_posts=("num_posts", "median"))
    typical = {"hashtags": float(df["hashtags"].median()), "mentions": float(df["mentions"].median()), "caption_len": float(df["caption_len"].median()),
               "hour": int(df["hour"].median()), "weekday": int(df["weekday"].median())}
    follower_cap = float(df["followers"].quantile(.9995))

    # ---- residuals of every post (used by text mining and breakouts)
    pred_l = models["likes"].predict(X); resid = yl - pred_l

    # ---- 2. personas
    log("Grouping accounts into personas (k-means) ...")
    pers, persona_model = _personas(df, er, resid, cats, log)

    # ---- 3. caption text mining
    log("Mining caption wording ...")
    text_rep, text_model = _text(df, resid, log)

    # ---- 4. breakouts
    log("Looking for breakout posts ...")
    brk = _breakouts(df, pred_l, models, text_model, cats, log)

    joblib.dump({"likes": models["likes"], "comments": models["comments"], "cats": cats, "typical": typical, "follower_cap": follower_cap,
                 "tier_er": {k: float(v) for k, v in tier_er["median"].items()}, "tier_n": {k: int(v) for k, v in tier_er["size"].items()},
                 "tier_def": {k: {c: float(v) for c, v in r.items()} for k, r in tier_def.iterrows()},
                 "interval": {"likes": rep_pred["likes"]["interval"], "comments": rep_pred["comments"]["interval"]},
                 "persona": persona_model, "text": text_model}, MODEL_FILE, compress=3)
    report = {"trained_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "seconds": round(time.time() - t0), "rows": int(n),
              "predictor": rep_pred, "personas": pers, "text": text_rep, "breakouts": brk}
    with open(REPORT_FILE, "w") as fh: json.dump(report, fh)
    _CACHE.clear()
    log(f"Done in {round(time.time() - t0)} seconds")
    return report


def _personas(df, er, resid, cats, log):
    g = df.assign(er=(er * 100).clip(upper=er.quantile(.99) * 100)).groupby("user_key").agg(
        fo=("followers", "last"), er=("er", "mean"), h=("hashtags", "mean"), dl=("caption_len", "mean"), lk=("likes", "mean"), n=("likes", "size"), biz=("business", "first"))
    F = np.column_stack([np.log10(g.fo + 1), np.log10(g.er + 0.01), g.h.clip(upper=30)])
    sc = StandardScaler().fit(F); Z = sc.transform(F)
    rs = np.random.RandomState(7); sub = rs.choice(len(Z), size=min(20000, len(Z)), replace=False)
    sil, best = {}, None
    for k in (4, 5, 6):
        km = MiniBatchKMeans(n_clusters=k, n_init=5, batch_size=10000, random_state=42).fit(Z)
        sil[k] = round(float(silhouette_score(Z[sub], km.labels_[sub])), 3)
        if best is None or sil[k] > best[0]: best = (sil[k], k, km)
    _, k, km = best; lab = km.labels_; cen = km.cluster_centers_
    log(f"  chose k={k} (silhouette {sil})")
    g["c"] = lab
    # posts -> persona
    pc = pd.Series(lab, index=g.index).reindex(df["user_key"]).values
    names, used = [], {}
    for z in cen:
        lf, le, h = z
        nm = ("Big audience, quiet feed" if lf > .6 and le < -.2 else "Established powerhouses" if lf > .6 else "Small but highly engaged" if lf < -.2 and le > .5
              else "Hashtag-heavy posters" if h > .6 else "Low-engagement accounts" if le < -.5 else "Everyday accounts")
        used[nm] = used.get(nm, 0) + 1; names.append(nm if used[nm] == 1 else f"{nm} ({used[nm]})")
    allh, alldl, allb = g.h.mean(), g.dl.median(), g.biz.mean()
    items = []
    for c in range(k):
        s = g[g.c == c]; posts = df[pc == c]
        top = s[s.er >= s.er.quantile(.75)]
        by_hour = posts.groupby("hour").likes.agg(["mean", "size"]); by_hour = by_hour[by_hour["size"] >= 200]
        cat_share = posts["category"].value_counts(normalize=True).head(3)
        items.append({"id": c, "name": names[c], "accounts": int(len(s)), "share_pct": round(len(s) / len(g) * 100, 1),
                      "median_followers": int(s.fo.median()), "median_engagement_pct": round(float(s.er.median()), 2), "mean_likes": round(float(s.lk.mean()), 1),
                      "hashtags": round(float(s.h.mean()), 1), "caption_len": int(s.dl.median()), "business_pct": round(float(s.biz.mean() * 100), 1),
                      "top_categories": [{"name": i.replace("_", " "), "pct": round(float(v * 100))} for i, v in cat_share.items()],
                      "best_hour": int(by_hour["mean"].idxmax()) if len(by_hour) else None,
                      "top_performers": {"hashtags": round(float(top.h.mean()), 1), "caption_len": int(top.dl.median()), "business_pct": round(float(top.biz.mean() * 100), 1)},
                      "vs_all": {"hashtags": round(float(s.h.mean() - allh), 1), "caption_len": int(s.dl.median() - alldl), "business_pct": round(float((s.biz.mean() - allb) * 100), 1)}})
    return {"k": int(k), "silhouette": sil[k], "silhouettes": sil, "accounts": int(len(g)), "items": items}, {"scaler": sc, "kmeans": km, "items": items}


def _clean(t):
    t = re.sub(r"https?://\S+|www\.\S+", " ", str(t).lower()); t = re.sub(r"@\w+", " ", t)
    return t.replace("#", " ")


def _struct(t):
    t0 = str(t)
    return {"question": "?" in t0, "exclaim": "!" in t0, "emoji": len(re.findall(r"[^\x00-⿿]", t0)), "linkbio": bool(re.search(r"link in (my )?bio", t0.lower())), "words": len(t0.split())}


def _text(df, resid, log):
    con = _db()
    tx = pd.read_sql("SELECT original_post_id post_id, text FROM combined_posts WHERE source='posts_dataset'", con); con.close()
    d = df[["post_id"]].assign(res=resid).merge(tx, on="post_id")
    d = d[d.text.str.len() >= 3].sample(n=min(260000, len(d)), random_state=3)
    lo, hi = d.res.quantile(.30), d.res.quantile(.70)
    d = d[(d.res <= lo) | (d.res >= hi)].copy(); d["y"] = (d.res >= hi).astype(int)
    d["clean"] = d.text.map(_clean)
    a, b = train_test_split(d.index, test_size=0.2, random_state=5, stratify=d.y)
    vec = TfidfVectorizer(token_pattern=TOKEN, stop_words="english", min_df=150, max_features=20000, ngram_range=(1, 2), sublinear_tf=True, dtype=np.float32)
    Xa = vec.fit_transform(d.loc[a, "clean"]); Xb = vec.transform(d.loc[b, "clean"])
    clf = LogisticRegression(solver="liblinear", C=0.6).fit(Xa, d.loc[a, "y"])
    pb = clf.predict_proba(Xb)[:, 1]; auc = float(roc_auc_score(d.loc[b, "y"], pb))
    log(f"  caption model AUC {auc:.3f} on {len(b):,} held-out captions")
    voc = np.array(vec.get_feature_names_out()); coef = clf.coef_[0]
    Xall = vec.transform(d["clean"]); pres = (Xall > 0).tocsc()
    y = d.y.values; n1, n0 = max(y.sum(), 1), max((1 - y).sum(), 1)
    def words(idx):
        out = []
        for i in idx:
            col = pres[:, i]; hit = np.asarray(col.todense()).ravel() > 0
            out.append({"word": voc[i], "weight": round(float(coef[i]), 2), "pct_beat": round(float(hit[y == 1].sum() / n1 * 100), 1), "pct_short": round(float(hit[y == 0].sum() / n0 * 100), 1)})
        return out
    order = np.argsort(coef)
    pos = [i for i in order[::-1][:60]][:25]; neg = [i for i in order[:60]][:25]
    S = d.text.map(_struct); base = d.y.mean()
    feats = pd.DataFrame(list(S), index=d.index)
    def row(label, mask):
        m = mask.values; return {"label": label, "posts": int(m.sum()), "beat_pct": round(float(d.y[m].mean() * 100), 1), "lift": round(float(d.y[m].mean() / base), 2)} if m.sum() >= 500 else None
    struct = [r for r in [row("Caption asks a question (?)", feats.question), row("Caption has an exclamation mark", feats.exclaim),
              row("No emoji", feats.emoji == 0), row("1 to 2 emoji", feats.emoji.between(1, 2)), row("3 or more emoji", feats.emoji >= 3),
              row("Says \"link in bio\"", feats.linkbio), row("Very short (under 5 words)", feats.words < 5), row("5 to 15 words", feats.words.between(5, 15)),
              row("16 to 40 words", feats.words.between(16, 40)), row("Long (over 40 words)", feats.words > 40)] if r]
    rep = {"auc": round(auc, 3), "docs": int(len(d)), "note": "Posts were labelled by whether they got more (top 30%) or fewer (bottom 30%) likes than the engagement model expected for their audience size, so the words below show wording linked to doing better than expected, not audience size. It is a correlation, not proof that a word causes likes.",
           "beat_words": words(pos), "short_words": words(neg), "structure": struct, "base_rate_pct": round(float(base * 100), 1)}
    return rep, {"vec": vec, "clf": clf, "pct": np.percentile(pb, range(101)).tolist(), "base": float(base)}


def _breakouts(df, pred_l, models, text_model, cats, log):
    pl = np.expm1(np.clip(pred_l, 0, None)); ratio = (df["likes"].values + 1) / (pl + 1)
    ok = df["likes"].values >= 30
    cnt = {f"ge{t}": int(((ratio >= t) & ok).sum()) for t in (3, 5, 10)}
    top = np.argsort(-(ratio * ok))[:100]
    ids = df.iloc[top]["post_id"].tolist()
    con = _db(); tx = pd.read_sql(f"SELECT original_post_id post_id, text FROM combined_posts WHERE source='posts_dataset' AND original_post_id IN ({','.join(map(str, ids))})", con); con.close()
    txt = dict(zip(tx.post_id, tx.text))
    vec, clf = text_model["vec"], text_model["clf"]; voc = np.array(vec.get_feature_names_out())
    med_fo = df["followers"].median(); out = []
    for i in top:
        r = df.iloc[i]; t = txt.get(r.post_id, ""); why = [f"{ratio[i]:.1f}x the likes the model expected ({int(r.likes):,} actual vs about {int(pl[i]):,})"]
        if r.followers < med_fo: why.append(f"small audience ({int(r.followers):,} followers) but strong reach")
        elif r.followers > med_fo * 20: why.append(f"large audience ({int(r.followers):,} followers) and still above expectation")
        v = vec.transform([_clean(t)]); contrib = v.multiply(clf.coef_[0]).tocoo()
        best = sorted(zip(contrib.data, contrib.col), reverse=True)[:3]
        words = [voc[c] for w, c in best if w > 0.05]
        if words: why.append("wording linked to over-performance: " + ", ".join(words))
        s = _struct(t)
        if s["question"]: why.append("caption asks a question")
        if s["emoji"] >= 1: why.append(f"{s['emoji']} emoji in the caption")
        why.append(f"{int(r.hashtags)} hashtag(s), posted {DAYS[int(r.weekday)]} {int(r.hour):02d}:00")
        u = str(r.username); out.append({"post_id": int(r.post_id), "account": (u[:2] + "***") if len(u) > 2 else "***", "category": r.category.replace("_", " "), "followers": int(r.followers),
                                         "likes": int(r.likes), "expected": int(pl[i]), "ratio": round(float(ratio[i]), 1), "caption": t[:160], "why": why})
    return {"counts": cnt, "eligible_posts": int(ok.sum()), "items": out}


# ---------------------------------------------------------------- using the trained models
def available():
    return os.path.exists(MODEL_FILE) and os.path.exists(REPORT_FILE)


def bundle():
    if not available(): return None
    mt = os.path.getmtime(MODEL_FILE)
    if _CACHE.get("m") != mt: _CACHE.clear(); _CACHE["m"] = mt; _CACHE["b"] = joblib.load(MODEL_FILE)
    return _CACHE["b"]


def report(admin=False):
    if not os.path.exists(REPORT_FILE): return None
    with open(REPORT_FILE) as fh: r = json.load(fh)
    if not admin: r = {k: v for k, v in r.items() if k != "breakouts"} | {"breakouts": {"counts": r["breakouts"]["counts"], "eligible_posts": r["breakouts"]["eligible_posts"]}}
    return r


def _rows(acct, posts, b):
    t = tier_of(acct["followers"]); d = b["tier_def"].get(t) or next(iter(b["tier_def"].values()))
    rows = []
    for p in posts:
        rows.append({"followers": acct["followers"], "following": acct.get("following") or d["following"], "num_posts": acct.get("num_posts") or d["num_posts"],
                     "hashtags": p["hashtags"], "mentions": p["mentions"], "caption_len": p["caption_len"], "hour": p["hour"], "weekday": p["weekday"],
                     "category": acct["category"], "business": 1 if acct.get("business") else 0})
    return pd.DataFrame(rows)


def predict(acct, posts):
    """returns (likes[], comments[]) as raw model output (likes of an account like this one, not calibrated to the user)."""
    b = bundle(); X = make_X(_rows(acct, posts, b), b["cats"])
    return np.expm1(np.clip(b["likes"].predict(X), 0, None)), np.expm1(np.clip(b["comments"].predict(X), 0, None))


LEVERS = {"hashtags": [0, 1, 2, 3, 5, 8, 12, 20, 30], "hour": list(range(24)), "weekday": list(range(7)),
          "caption_len": [20, 50, 100, 150, 250, 400, 700], "mentions": [0, 1, 2, 3]}


def _lever_text(k, v, cur):
    if k == "hashtags": return f"Use {v} hashtag{'s' if v != 1 else ''} instead of {int(cur)}"
    if k == "hour": return f"Post around {int(v):02d}:00 instead of {int(cur):02d}:00"
    if k == "weekday": return f"Post on {DAYS[int(v)]} instead of {DAYS[int(cur)]}"
    if k == "caption_len": return f"Write a caption of about {int(v)} characters instead of {int(cur)}"
    return f"Use {v} @mention{'s' if v != 1 else ''} instead of {int(cur)}"


def analyse_post(acct, post, avg_likes, avg_comments, habit_hashtags=None):
    """Next-post forecast.  next = the account's own average x (model(this post) / model(typical post)), so the answer is anchored on the
    account's real numbers and the model only supplies the effect of THIS post's choices.  Works for tiny and huge accounts alike."""
    b = bundle()
    if b is None: return None
    typ = dict(b["typical"])
    if habit_hashtags is not None: typ["hashtags"] = habit_hashtags          # the account's own habit is the reference, other settings are typical
    variants = [post, typ]; tags = [("plan", None), ("typ", None)]
    for k, vals in LEVERS.items():
        for v in vals:
            if v != post[k]: variants.append({**post, k: v}); tags.append((k, v))
    L, C = predict(acct, variants); L, C = np.maximum(L, 0.05), np.maximum(C, 0.05)
    rl, rc = float(np.clip(L[0] / L[1], 0.3, 3)), float(np.clip(C[0] / C[1], 0.3, 3))
    nxt_l, nxt_c = avg_likes * rl, avg_comments * rc
    lo, hi = b["interval"]["likes"]
    best = {}
    for i, (k, v) in enumerate(tags[2:], start=2):
        g = L[i] / L[0] - 1
        if k not in best or g > best[k][0]: best[k] = (g, v)
    ranked = sorted([(g, k, v) for k, (g, v) in best.items() if g >= 0.02], reverse=True)[:3]
    changes = [{"lever": k, "value": v, "text": _lever_text(k, v, post[k]), "gain_pct": round(g * 100)} for g, k, v in ranked]
    combo = 0.0
    if ranked:
        cp = {**post, **{k: v for _, k, v in ranked}}; cl, _ = predict(acct, [cp]); combo = float(cl[0] / max(L[0], .05) - 1)
    peers = None
    if acct["followers"] <= b["follower_cap"]: peers = {"likes": int(round(L[0])), "comments": int(round(float(C[0])))}
    return {"next_likes": int(round(nxt_l)), "next_comments": int(round(nxt_c)), "likes_range": [int(round(nxt_l * np.exp(lo))), int(round(nxt_l * np.exp(hi)))],
            "post_effect_pct": round((rl - 1) * 100), "changes": changes, "combined_gain_pct": round(combo * 100),
            "improved_likes": int(round(nxt_l * (1 + combo))), "peers": peers, "interval_note": "About 8 in 10 posts like this land inside the range."}


def match_persona(followers, er_pct, hashtags):
    b = bundle()
    if b is None: return None
    pm = b["persona"]; z = pm["scaler"].transform([[np.log10(followers + 1), np.log10(min(er_pct, 400) + 0.01), min(hashtags, 30)]])
    dist = pm["kmeans"].transform(z)[0]; c = int(np.argmin(dist))
    return {**{k: v for k, v in pm["items"][c].items()}, "match_distance": round(float(dist[c]), 2)}


def tier_er(followers):
    b = bundle(); t = tier_of(followers)
    return b["tier_er"].get(t) or float(np.median(list(b["tier_er"].values())))


def check_caption(text):
    b = bundle()
    if b is None: return None
    tm = b["text"]; vec, clf = tm["vec"], tm["clf"]; clean = _clean(text)
    v = vec.transform([clean]); p = float(clf.predict_proba(v)[0, 1])
    pct = int(np.searchsorted(tm["pct"], p)); voc = np.array(vec.get_feature_names_out())
    c = v.multiply(clf.coef_[0]).tocoo(); items = sorted(zip(c.data, c.col))
    helped = [{"word": voc[j], "weight": round(float(w), 2)} for w, j in reversed(items) if w > 0.02][:6]
    hurt = [{"word": voc[j], "weight": round(float(w), 2)} for w, j in items if w < -0.02][:6]
    s = _struct(text); tips = []
    if not s["question"]: tips.append("Captions that ask a question tend to prompt replies; consider ending with one.")
    if s["emoji"] == 0: tips.append("A couple of emoji can make a caption feel friendlier (see the structure table on the Data Mining page).")
    if s["words"] < 5: tips.append("Very short captions give the audience little to react to.")
    if s["words"] > 60: tips.append("Long captions are often skimmed; put the main point in the first line.")
    return {"score": pct, "probability_pct": round(p * 100, 1), "helped": helped, "hurt": hurt, "tips": tips, "words": s["words"], "emoji": s["emoji"], "question": s["question"]}


# ---------------------------------------------------------------- background run
def start(on_done=None):
    import threading
    if STATE["running"]: return False
    STATE.update(running=True, log=[], error=None, started=dt.datetime.now().isoformat(timespec="seconds"), finished=None)
    def work():
        try: train(_log)
        except Exception as e:
            STATE["error"] = str(e); _log("ERROR: " + str(e))
        finally:
            STATE["running"] = False; STATE["finished"] = dt.datetime.now().isoformat(timespec="seconds")
            if on_done: on_done()
    threading.Thread(target=work, daemon=True).start()
    return True
