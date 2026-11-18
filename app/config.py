import os
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env():
    """Reads KEY=value lines from <project>/.env (written by setup_email.py). Real environment variables win."""
    path = os.path.join(ROOT, ".env")
    if not os.path.exists(path): return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k, v = line.split("=", 1); k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ: os.environ[k] = v


_load_env()
DATA_DIR = os.getenv("DATA_DIR") or os.path.join(ROOT, "data")     # on a host, point this at the persistent disk
RAW_DIR = os.path.join(DATA_DIR, "raw")          # put Instagram_data.csv and intsa_data2.csv here
OUT_DIR = os.path.join(DATA_DIR, "processed")    # clean CSVs, combined CSV, lineage.json, warehouse.db
WAREHOUSE = os.path.join(OUT_DIR, "warehouse.db")    # read-only for the app, written only by the ETL
LINEAGE = os.path.join(OUT_DIR, "lineage.json")
AUTH_DB = os.path.join(DATA_DIR, "auth.db")      # logins, sessions, audit log (separate from the warehouse)
os.makedirs(DATA_DIR, exist_ok=True)
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")        # profile pictures (server storage)
os.makedirs(UPLOAD_DIR, exist_ok=True)


def unpack_warehouse():
    """The deploy copy for GitHub keeps the warehouse as two gzip parts (each under GitHub's size warning). Rebuild warehouse.db from them once."""
    import glob, gzip, shutil
    dest = os.path.join(ROOT, "data", "processed", "warehouse.db")
    parts = sorted(glob.glob(dest + ".gz.part*"))
    if os.path.exists(dest) or not parts: return
    print("  Unpacking the warehouse from its compressed parts (one time, about a minute) ...", flush=True)
    tmp, joined = dest + ".tmp", dest + ".gz.joined"
    with open(joined, "wb") as j:                              # put the parts back together, then unzip the result
        for part in parts:
            with open(part, "rb") as f: shutil.copyfileobj(f, j, 1 << 20)
    with gzip.open(joined, "rb") as g, open(tmp, "wb") as o: shutil.copyfileobj(g, o, 1 << 20)
    os.remove(joined); os.replace(tmp, dest)
    print("  Warehouse ready.", flush=True)


def bootstrap_data():
    """On a host the persistent disk (DATA_DIR) starts EMPTY. Copy the warehouse, the trained models and the CSVs that ship inside the app image onto it once."""
    import shutil
    bundled = os.path.join(ROOT, "data")
    if os.path.abspath(bundled) == os.path.abspath(DATA_DIR): return
    src_wh = os.path.join(bundled, "processed", "warehouse.db")
    if os.path.exists(os.path.join(DATA_DIR, "processed", "warehouse.db")) or not os.path.exists(src_wh): return
    print("  First start on a new data disk: copying the warehouse, models and CSV files (one time, about a minute) ...", flush=True)
    for sub in ("processed", "raw"):
        if os.path.isdir(os.path.join(bundled, sub)): shutil.copytree(os.path.join(bundled, sub), os.path.join(DATA_DIR, sub), dirs_exist_ok=True)
    print("  Copy finished.", flush=True)


PUBLIC_MODE = os.getenv("PUBLIC_MODE", "0") == "1"              # set by share_online.py: the site is reachable from the internet
PRODUCTION = os.getenv("APP_ENV", "development").lower() == "production" or PUBLIC_MODE
os.makedirs(RAW_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)
unpack_warehouse()
bootstrap_data()
