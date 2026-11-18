"""Builds the folder that goes to GitHub for Render:  python tools/make_deploy_repo.py <output folder>
Same app, but warehouse.db is replaced by gzip parts under 40 MB each (GitHub refuses files over 100 MB and warns over 50 MB), and the
two big raw CSV files are left out (the running site does not need them; only re-running the ETL does)."""
import gzip, os, shutil, sys

SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1]
SKIP_DIRS = {"__pycache__", ".pytest_cache", "bin", "uploads"}
SKIP_FILES = {".env", "auth.db", "secret.key", "warehouse.db"}
PART = 20_000_000   # under GitHub's 25 MB browser-upload limit, so the files can also be uploaded with 'Add files via upload'
if os.path.exists(OUT): shutil.rmtree(OUT)
for root, dirs, files in os.walk(SRC):
    dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
    rel = os.path.relpath(root, SRC)
    for f in files:
        if f in SKIP_FILES or f.endswith((".zip", ".pyc")) or f.startswith("auth.db"): continue
        if rel.replace("\\", "/") == "data/raw" and f.endswith(".csv"): continue
        if f.endswith(".gz.joined") or ".gz.part" in f: continue
        dst = os.path.join(OUT, rel, f); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy2(os.path.join(root, f), dst)
wh = os.path.join(SRC, "data", "processed", "warehouse.db")
base = os.path.join(OUT, "data", "processed", "warehouse.db.gz.part")
os.makedirs(os.path.dirname(base), exist_ok=True)
tmp = os.path.join(OUT, "wh.gz")
with open(wh, "rb") as f, gzip.open(tmp, "wb", compresslevel=9) as g: shutil.copyfileobj(f, g, 1 << 20)
n = 0
with open(tmp, "rb") as g:
    while True:
        chunk = g.read(PART)
        if not chunk: break
        n += 1; open(f"{base}{n}", "wb").write(chunk)
os.remove(tmp)
open(os.path.join(OUT, ".gitignore"), "w").write(".env\n__pycache__/\n*.pyc\n.pytest_cache/\ndata/auth.db*\ndata/secret.key\ndata/uploads/\nbin/\ndata/processed/warehouse.db\n")
big = [(os.path.join(r, f), os.path.getsize(os.path.join(r, f))) for r, _, fs in os.walk(OUT) for f in fs if os.path.getsize(os.path.join(r, f)) > 45_000_000]
print("parts:", n, "| files over 45 MB:", big or "none")
print("total size MB:", round(sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(OUT) for f in fs) / 1e6))
