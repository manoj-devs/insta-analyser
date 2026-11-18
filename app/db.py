import sqlite3
from app import config


def conn():
    c = sqlite3.connect(config.AUTH_DB, timeout=15)
    c.row_factory = sqlite3.Row
    return c


# columns added to `users` / `sessions` after the first release (applied automatically to older databases)
USER_COLS = {"phone": "TEXT", "country": "TEXT", "user_type": "TEXT", "handle": "TEXT", "consent_at": "REAL",
             "signup_ip": "TEXT", "last_login": "REAL", "login_count": "INTEGER DEFAULT 0", "otp_purpose": "TEXT",
             "pw_changed": "REAL", "must_change": "INTEGER DEFAULT 0", "interests": "TEXT",
             "otp_lock": "REAL", "otp_sent": "REAL", "otp_sends": "INTEGER DEFAULT 0", "otp_win": "REAL", "otp_ticket": "TEXT", "avatar": "TEXT"}


def init():
    c = conn()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, name TEXT, pw TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'user', status TEXT NOT NULL DEFAULT 'active', reason TEXT,
        verified INTEGER NOT NULL DEFAULT 0, otp TEXT, otp_exp REAL, otp_tries INTEGER DEFAULT 0, created REAL);
    CREATE TABLE IF NOT EXISTS sessions(
        token TEXT PRIMARY KEY, user_id INTEGER, created REAL, expires REAL, last_seen REAL, ip TEXT, ua TEXT);
    CREATE TABLE IF NOT EXISTS audit(
        id INTEGER PRIMARY KEY, ts REAL, user_id INTEGER, email TEXT, event TEXT, ip TEXT, ua TEXT, detail TEXT);
    CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit(ts);
    CREATE TABLE IF NOT EXISTS analyses(
        id INTEGER PRIMARY KEY, ts REAL, user_id INTEGER, handle TEXT, followers INTEGER, tier TEXT, category TEXT,
        account_type TEXT, avg_likes REAL, avg_comments REAL, hashtags INTEGER, posts_per_week REAL,
        score INTEGER, income_per_post INTEGER, income_monthly INTEGER, best_hashtags TEXT);
    CREATE INDEX IF NOT EXISTS ix_an_user ON analyses(user_id, ts);
    CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts REAL, user_id INTEGER, kind TEXT, name TEXT);
    CREATE INDEX IF NOT EXISTS ix_ev_ts ON events(ts);
    CREATE TABLE IF NOT EXISTS lookups(
        id INTEGER PRIMARY KEY, ts REAL, user_id INTEGER, name TEXT, kind TEXT, category TEXT, followers INTEGER, avg_likes REAL, avg_comments REAL,
        tier TEXT, persona TEXT, next_likes INTEGER, fee_low_usd INTEGER, fee_mid_usd INTEGER, fee_high_usd INTEGER, fee_mid_inr INTEGER);
    CREATE TABLE IF NOT EXISTS directory(
        id INTEGER PRIMARY KEY, handle TEXT UNIQUE NOT NULL, display_name TEXT, continent TEXT, country TEXT NOT NULL, state_or_region TEXT, city TEXT,
        category TEXT NOT NULL, account_type TEXT, verified INTEGER DEFAULT 0, followers INTEGER NOT NULL, avg_likes REAL NOT NULL, avg_comments REAL NOT NULL,
        posts_per_week REAL DEFAULT 4, as_of TEXT, source TEXT, added REAL);
    CREATE INDEX IF NOT EXISTS ix_dir_country ON directory(country, state_or_region);
    CREATE TABLE IF NOT EXISTS devices(
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, token_hash TEXT NOT NULL, label TEXT, ip TEXT, first_seen REAL, last_seen REAL);
    CREATE INDEX IF NOT EXISTS ix_dev_user ON devices(user_id);
    CREATE TABLE IF NOT EXISTS feedback(id INTEGER PRIMARY KEY, ts REAL, user_id INTEGER, rating INTEGER, topic TEXT, message TEXT);
    CREATE TABLE IF NOT EXISTS creator_profile(user_id INTEGER PRIMARY KEY, data TEXT, updated REAL);
    CREATE TABLE IF NOT EXISTS creator_posts(
        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, ts REAL, label TEXT, post_type TEXT, posted_on TEXT, followers INTEGER, likes INTEGER, comments INTEGER,
        saves INTEGER, shares INTEGER, reach INTEGER, er_pct REAL, percentile INTEGER, income_low INTEGER, income_mid INTEGER, income_high INTEGER, source TEXT);
    CREATE INDEX IF NOT EXISTS ix_cp_user ON creator_posts(user_id, ts);
    """)
    have = {r[1] for r in c.execute("PRAGMA table_info(users)")}
    for col, typ in USER_COLS.items():
        if col not in have:
            c.execute(f"ALTER TABLE users ADD COLUMN {col} {typ}")
    for col, typ in (("pred_likes", "INTEGER"), ("persona", "TEXT"), ("fee_mid_usd", "INTEGER")):
        if col not in {r[1] for r in c.execute("PRAGMA table_info(analyses)")}:
            c.execute(f"ALTER TABLE analyses ADD COLUMN {col} {typ}")
    if "kind" not in {r[1] for r in c.execute("PRAGMA table_info(sessions)")}:
        c.execute("ALTER TABLE sessions ADD COLUMN kind TEXT DEFAULT 'user'")
    c.commit(); c.close()
