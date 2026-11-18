"""Phase 2 ETL: raw -> clean -> star warehouse -> combined -> summary tables -> lineage.json"""
import os
import re
import json
import sqlite3
import datetime as dt
import pandas as pd
from app import config


class Run:
    def __init__(self, cb=None):
        self.steps, self.cb = [], cb

    def log(self, m):
        if self.cb:
            self.cb(m)

    def step(self, ds, name, before, after, note=""):
        self.steps.append({"dataset": ds, "step": name, "before": int(before), "after": int(after),
                           "removed": int(before - after), "note": note})
        self.log(f"[{ds}] {name}: {int(before):,} -> {int(after):,}")


def _find(name):
    for ext in (".csv", ".xlsx", ".xls"):
        p = os.path.join(config.RAW_DIR, name + ext)
        if os.path.exists(p):
            return p
    raise FileNotFoundError(f"{name}.csv or .xlsx not found in {config.RAW_DIR}")


def _read(path):
    if path.lower().endswith(".csv"):
        for enc in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
            try:
                return pd.read_csv(path, encoding=enc)
            except UnicodeDecodeError:
                continue
        raise ValueError("cannot decode " + path)
    return pd.read_excel(path)


def _txt(s):
    s = s.astype("string").str.replace(r"\s+", " ", regex=True).str.strip()
    return s.mask(s == "", pd.NA)


def _cols(df):
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    return df


def _tags(text):
    t = re.findall(r"#\w+", str(text).lower())
    return " ".join(dict.fromkeys(t)) if t else "no_hashtag"


# ---------------- clean dataset 1 (reach) ----------------
def clean_reach(run):
    df = _cols(_read(_find("Instagram_data")))
    n = len(df)
    run.step("reach", "extract raw", n, n)
    nums = ["impressions", "from_home", "from_hashtags", "from_explore", "from_other", "saves",
            "comments", "shares", "likes", "profile_visits", "follows"]
    for c in nums:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ["caption", "hashtags"]:
        df[c] = _txt(df[c])
    b = len(df); df = df.dropna(); run.step("reach", "remove null rows", b, len(df))
    b = len(df); df = df.drop_duplicates(); run.step("reach", "remove duplicate rows", b, len(df))
    b = len(df); df = df[(df[nums] >= 0).all(axis=1)]; run.step("reach", "remove negative values", b, len(df))
    df[nums] = df[nums].astype("int64")
    df["hashtag_count"] = df["hashtags"].str.count(r"#\w+").astype("int64")
    df["total_engagement"] = df["likes"] + df["comments"] + df["shares"] + df["saves"]
    df["engagement_rate_pct"] = (df["total_engagement"] / df["impressions"].where(df["impressions"] > 0) * 100).round(2).fillna(0)
    df["follow_conversion_pct"] = (df["follows"] / df["profile_visits"].where(df["profile_visits"] > 0) * 100).round(2).fillna(0)
    df = df.reset_index(drop=True)
    df.insert(0, "post_id", df.index + 1)
    return n, list(df.columns), df


# ---------------- clean dataset 2 (posts) ----------------
def clean_posts(run):
    df = _cols(_read(_find("intsa_data2")))
    n = len(df)
    run.step("posts", "extract raw", n, n)
    df["description"] = _txt(df["description"])
    df["username"] = _txt(df["username"]).str.lower()
    df["description_category"] = _txt(df["description_category"]).str.lower()
    for c in ["likes", "comments", "following", "followers", "num_posts"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], format="%d-%m-%Y %H:%M", errors="coerce")
    df["is_business_account"] = (df["is_business_account"].astype("string").str.strip().str.lower()
                                 .map({"true": 1, "false": 0, "1": 1, "0": 0}))
    b = len(df); df = df.dropna(); run.step("posts", "remove null rows", b, len(df), "includes unreadable dates")
    b = len(df); df = df.drop_duplicates(); run.step("posts", "remove duplicate rows", b, len(df))
    b = len(df)
    df = df[(df[["likes", "comments", "following", "followers", "num_posts"]] >= 0).all(axis=1)]
    run.step("posts", "remove negative values", b, len(df))
    for c in ["likes", "comments", "following", "followers", "num_posts", "is_business_account"]:
        df[c] = df[c].astype("int64")
    df["hashtag_count"] = df["description"].str.count(r"#\w+").astype("int64")
    df["mention_count"] = df["description"].str.count(r"@\w+").astype("int64")
    df["description_length"] = df["description"].str.len().astype("int64")
    df["engagement"] = df["likes"] + df["comments"]
    df["engagement_rate_pct"] = (df["engagement"] / df["followers"].where(df["followers"] > 0) * 100).round(4).fillna(0)
    df["follower_tier"] = pd.cut(df["followers"], [-1, 999, 9999, 99999, 999999, float("inf")],
                                 labels=["Nano (<1K)", "Micro (1K-10K)", "Mid (10K-100K)",
                                         "Macro (100K-1M)", "Mega (1M+)"]).astype("string")
    df = df.sort_values("date").reset_index(drop=True)
    df.insert(0, "post_id", df.index + 1)
    return n, list(df.columns), df


# ---------------- combine ----------------
def combine(reach, posts, run):
    a = pd.DataFrame({"source": "posts_dataset", "original_post_id": posts["post_id"],
                      "text": posts["description"], "likes": posts["likes"], "comments": posts["comments"]})
    b = pd.DataFrame({"source": "reach_dataset", "original_post_id": reach["post_id"],
                      "text": reach["caption"], "likes": reach["likes"], "comments": reach["comments"]})
    c = pd.concat([a, b], ignore_index=True)
    c["text"] = _txt(c["text"])
    c["hashtags"] = c["text"].apply(_tags)
    m = c["source"] == "reach_dataset"
    c.loc[m, "hashtags"] = [_tags(h) for h in reach["hashtags"]]
    c["hashtag_count"] = c["hashtags"].where(c["hashtags"] != "no_hashtag", "").str.count("#")
    c["mention_count"] = c["text"].str.count(r"@\w+")
    c["text_length"] = c["text"].str.len()
    c["engagement"] = c["likes"] + c["comments"]
    n = len(c)
    run.step("combined", "stack both clean datasets", len(reach) + len(posts), n)
    c = c.dropna()
    run.step("combined", "remove null / blank rows", n, len(c))
    c = c.drop_duplicates(["source", "original_post_id"]).reset_index(drop=True)
    for k in ["likes", "comments", "engagement", "hashtag_count", "mention_count", "text_length"]:
        c[k] = c[k].astype("int64")
    c.insert(0, "combined_id", c.index + 1)
    return c[["combined_id", "source", "original_post_id", "text", "hashtags", "hashtag_count",
              "mention_count", "text_length", "likes", "comments", "engagement"]]


# ---------------- warehouse + summary tables ----------------
SUMMARIES = {
    "summary_year": "SELECT d.year, COUNT(*) posts, SUM(f.likes) total_likes, SUM(f.comments) total_comments, ROUND(AVG(f.likes),2) avg_likes, ROUND(AVG(f.comments),2) avg_comments FROM fact_posts f JOIN dim_date d USING(date_key) GROUP BY d.year ORDER BY d.year",
    "summary_category": "SELECT c.category_name, COUNT(*) posts, ROUND(AVG(f.likes),2) avg_likes, ROUND(AVG(f.comments),2) avg_comments FROM fact_posts f JOIN dim_category c USING(category_key) GROUP BY c.category_name ORDER BY avg_likes DESC",
    "summary_tier": "SELECT u.follower_tier, COUNT(DISTINCT u.user_key) accounts, COUNT(*) posts, ROUND(AVG(f.likes),2) avg_likes, ROUND(AVG(f.comments),2) avg_comments FROM fact_posts f JOIN dim_user u USING(user_key) GROUP BY u.follower_tier",
    "summary_hour_weekday": "SELECT d.weekday, f.post_hour hour, COUNT(*) posts, ROUND(AVG(f.likes),2) avg_likes FROM fact_posts f JOIN dim_date d USING(date_key) GROUP BY d.weekday, f.post_hour",
    "summary_hashtags": "SELECT MIN(hashtag_count,5) hashtag_bin, COUNT(*) posts, ROUND(AVG(likes),2) avg_likes, ROUND(AVG(comments),2) avg_comments FROM combined_posts GROUP BY hashtag_bin ORDER BY hashtag_bin",
}


def build_warehouse(reach, posts, comb, run):
    if os.path.exists(config.WAREHOUSE):
        os.remove(config.WAREHOUSE)
    con = sqlite3.connect(config.WAREHOUSE)
    d = pd.DataFrame({"full_date": posts["date"].dt.normalize().unique()}).sort_values("full_date").reset_index(drop=True)
    d["date_key"] = d["full_date"].dt.strftime("%Y%m%d").astype(int)
    d["day"], d["month"], d["month_name"] = d.full_date.dt.day, d.full_date.dt.month, d.full_date.dt.month_name()
    d["quarter"], d["year"], d["weekday"] = d.full_date.dt.quarter, d.full_date.dt.year, d.full_date.dt.day_name()
    d["is_weekend"] = d.full_date.dt.dayofweek.ge(5).astype(int)
    d["full_date"] = d.full_date.dt.strftime("%Y-%m-%d")
    cat = posts[["description_category"]].drop_duplicates().sort_values("description_category").reset_index(drop=True)
    cat.insert(0, "category_key", cat.index + 1)
    cat = cat.rename(columns={"description_category": "category_name"})
    usr = (posts.sort_values("date").drop_duplicates("username", keep="last")
           [["username", "followers", "following", "num_posts", "is_business_account", "follower_tier"]]
           .sort_values("username").reset_index(drop=True))
    usr.insert(0, "user_key", usr.index + 1)
    usr = usr.rename(columns={"followers": "latest_followers", "following": "latest_following",
                              "num_posts": "latest_num_posts"})
    f = posts.copy()
    f["date_key"] = f["date"].dt.strftime("%Y%m%d").astype(int)
    f["post_hour"] = f["date"].dt.hour
    f = f.merge(usr[["user_key", "username"]], on="username").merge(cat, left_on="description_category", right_on="category_name")
    fact = f[["post_id", "date_key", "post_hour", "user_key", "category_key", "likes", "comments", "engagement",
              "engagement_rate_pct", "followers", "following", "num_posts", "hashtag_count", "mention_count",
              "description_length"]].rename(columns={"followers": "followers_at_post", "following": "following_at_post",
                                                     "num_posts": "num_posts_at_post"})
    tg = (reach[["post_id", "hashtags"]].assign(tag=lambda x: x.hashtags.str.lower().apply(lambda s: re.findall(r"#\w+", s)))
          .explode("tag").dropna(subset=["tag"]).drop_duplicates(["post_id", "tag"]))
    hs = pd.DataFrame({"hashtag": sorted(tg.tag.unique())})
    hs.insert(0, "hashtag_key", hs.index + 1)
    br = tg.merge(hs, left_on="tag", right_on="hashtag")[["post_id", "hashtag_key"]]
    for name, df in [("dim_date", d), ("dim_category", cat), ("dim_user", usr), ("fact_posts", fact),
                     ("fact_reach", reach), ("dim_hashtag", hs), ("bridge_reach_hashtag", br), ("combined_posts", comb)]:
        df.to_sql(name, con, index=False, chunksize=50000)
        run.log(f"loaded {name}: {len(df):,} rows")
    con.execute("CREATE UNIQUE INDEX ix_comb ON combined_posts(combined_id)")
    con.execute("CREATE INDEX ix_comb_src ON combined_posts(source)")
    for name, sql in SUMMARIES.items():
        pd.read_sql(sql, con).to_sql(name, con, index=False)
        run.log(f"summary table {name} built")
    con.commit()
    return con


# ---------------- orchestration ----------------
CLEAN_FILES = ("clean_instagram_posts", "clean_instagram_reach", "combined_instagram_data")


def _find_clean(name):
    for folder in (config.RAW_DIR, os.path.dirname(config.RAW_DIR)):
        p = os.path.join(folder, name + ".csv")
        if os.path.exists(p):
            return p
    return None


def clean_files_present():
    return all(_find_clean(n) for n in CLEAN_FILES)


def run_etl(log_cb=None):
    """If the already-cleaned files are in data/raw, replay the ETL from them (fast); otherwise start from the raw files."""
    return run_from_clean(log_cb) if clean_files_present() else run_from_raw(log_cb)


def run_from_clean(log_cb=None):
    import time
    run = Run(log_cb)
    run.log("Ready-made clean files found in data/raw, so the cleaning stage is not repeated")
    reach = pd.read_csv(_find_clean("clean_instagram_reach"), encoding="utf-8-sig")
    run.step("reach", "load clean file", len(reach), len(reach), "clean_instagram_reach.csv")
    posts = pd.read_csv(_find_clean("clean_instagram_posts"), encoding="utf-8-sig", parse_dates=["date"])
    run.step("posts", "load clean file", len(posts), len(posts), "clean_instagram_posts.csv")
    comb = pd.read_csv(_find_clean("combined_instagram_data"), encoding="utf-8-sig")
    run.step("combined", "load combined file", len(comb), len(comb), "combined_instagram_data.csv")
    time.sleep(0.4)
    for nm, df, key in (("reach", reach, "post_id"), ("posts", posts, "post_id"), ("combined", comb, "combined_id")):
        nulls, dups = int(df.isna().sum().sum()), int(df.duplicated(key).sum())
        run.log(f"[{nm}] check: {nulls} null values, {dups} duplicate ids")
        if nulls or dups:
            raise ValueError(f"{nm} file is not clean ({nulls} nulls, {dups} duplicate ids)")
    if len(comb) != len(reach) + len(posts):
        raise ValueError(f"combined rows ({len(comb):,}) must equal reach + posts ({len(reach) + len(posts):,})")
    run.log("[combined] check: rows = clean reach + clean posts")
    for c in ("hashtags", "text"):
        comb[c] = comb[c].astype(str)
    reach["hashtags"] = reach["hashtags"].astype(str)
    run.log("Building star-schema warehouse tables ...")
    con = build_warehouse(reach, posts, comb, run)
    return _finish(run, con, reach, posts, comb, None, None, list(reach.columns), list(posts.columns))


def run_from_raw(log_cb=None):
    run = Run(log_cb)
    run.log("ETL started")
    r_raw, r_cols, reach = clean_reach(run)
    p_raw, p_cols, posts = clean_posts(run)
    reach.to_csv(os.path.join(config.OUT_DIR, "clean_reach.csv"), index=False, encoding="utf-8-sig")
    posts.to_csv(os.path.join(config.OUT_DIR, "clean_posts.csv"), index=False, encoding="utf-8-sig")
    comb = combine(reach, posts, run)
    comb.to_csv(os.path.join(config.OUT_DIR, "combined.csv"), index=False, encoding="utf-8-sig")
    con = build_warehouse(reach, posts, comb, run)
    return _finish(run, con, reach, posts, comb, r_raw, p_raw, r_cols, p_cols)


def _finish(run, con, reach, posts, comb, r_raw, p_raw, r_cols, p_cols):
    cnt = lambda t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    removed = lambda ds: sum(s["removed"] for s in run.steps if s["dataset"] == ds and s["step"] != "extract raw")
    checks = []
    if r_raw is not None:
        checks += [
            {"name": "Reach: raw rows - removed = clean rows", "expected": r_raw - removed("reach"), "actual": len(reach)},
            {"name": "Posts: raw rows - removed = clean rows", "expected": p_raw - removed("posts"), "actual": len(posts)}]
    checks += [
        {"name": "Combined rows = clean reach + clean posts", "expected": len(reach) + len(posts), "actual": len(comb)},
        {"name": "Warehouse fact_posts rows = clean posts rows", "expected": len(posts), "actual": cnt("fact_posts")},
        {"name": "Warehouse fact_reach rows = clean reach rows", "expected": len(reach), "actual": cnt("fact_reach")},
        {"name": "Warehouse combined_posts rows = combined rows", "expected": len(comb), "actual": cnt("combined_posts")},
        {"name": "Null values in combined dataset", "expected": 0, "actual": int(comb.isna().sum().sum())},
    ]
    for c in checks:
        c["ok"] = c["expected"] == c["actual"]
    lineage = {"generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
               "datasets": {"raw_reach": {"rows": r_raw}, "raw_posts": {"rows": p_raw},
                            "clean_reach": {"rows": len(reach), "columns": len(r_cols)},
                            "clean_posts": {"rows": len(posts), "columns": len(p_cols)},
                            "combined": {"rows": len(comb), "columns": comb.shape[1]}},
               "steps": run.steps, "checks": checks, "all_ok": all(c["ok"] for c in checks)}
    with open(config.LINEAGE, "w") as fh:
        json.dump(lineage, fh, indent=2)
    con.close()
    run.log("ETL finished")
    return lineage
