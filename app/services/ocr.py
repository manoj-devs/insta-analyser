"""Read the numbers from a screenshot of Instagram Insights / a post / a profile.

The picture is processed in memory and thrown away: it is never written to disk and its text is never returned or stored.
Only the detected numbers go back to the page, where the user checks and corrects them before anything is used.
Needs the free Tesseract program (see README). When it is missing, available() is False and the page asks for typed numbers.
"""
import io, re, shutil
from PIL import Image, ImageOps, ImageFilter, ImageStat

MAX_BYTES = 6_000_000
MAX_PIXELS = 25_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS

LABELS = {                        # field -> phrases that can sit next to its number (lower case)
    "followers": ["followers"],
    "likes": ["likes", "like"],
    "comments": ["comments", "comment"],
    "saves": ["saves", "saved", "save"],
    "shares": ["shares", "share", "reposts"],
    "reach": ["accounts reached", "reach", "accounts reach"],
    "views": ["views", "plays", "impressions"],
    "profile_visits": ["profile visits", "profile activity"],
}
NUM = re.compile(r"^\(?(\d[\d,\.]*)\s*([KkMmLl]?)\)?$")


def available():
    try:
        import pytesseract                                    # noqa: F401
        return shutil.which("tesseract") is not None
    except Exception:
        return False


def parse_number(tok):
    """'1,234' -> 1234 | '12.3K' -> 12300 | '1.2M' -> 1200000 | '1.234' (three digits after the dot) -> 1234"""
    m = NUM.match(tok.strip().strip(".,:;|"))
    if not m: return None
    body, suf = m.group(1).rstrip(".,"), m.group(2).upper()
    if not body: return None
    try:
        if suf in ("K", "M", "L"):
            v = float(body.replace(",", "")); return int(round(v * {"K": 1e3, "M": 1e6, "L": 1e5}[suf]))
        if "," in body: return int(float(body.replace(",", "")))
        if "." in body:
            a, b = body.split(".", 1)
            if len(b) == 3 and a and len(a) <= 3: return int(a + b)       # 1.234 means one thousand two hundred thirty-four
            return None                                                    # 4.5 with no K/M is not a count
        return int(body)
    except ValueError:
        return None


def _prep(img):
    img = ImageOps.exif_transpose(img).convert("L")
    if img.width < 1100:
        k = 1400 / img.width; img = img.resize((1400, max(int(img.height * k), 1)), Image.LANCZOS)
    elif img.width > 2400:
        k = 2000 / img.width; img = img.resize((2000, max(int(img.height * k), 1)), Image.LANCZOS)
    if ImageStat.Stat(img.resize((32, 32))).mean[0] < 120: img = ImageOps.invert(img)       # dark mode screenshots
    img = ImageOps.autocontrast(img).filter(ImageFilter.SHARPEN)
    return img


def _words(img, psm):
    import pytesseract
    d = pytesseract.image_to_data(img, config=f"--psm {psm} -l eng", output_type=pytesseract.Output.DICT, timeout=25)
    out = []
    for i, t in enumerate(d["text"]):
        t = (t or "").strip()
        if not t or float(d["conf"][i]) < 25: continue
        out.append({"t": t, "l": d["left"][i], "tp": d["top"][i], "w": d["width"][i], "h": d["height"][i], "ln": (d["block_num"][i], d["par_num"][i], d["line_num"][i])})
    return out


def _find(words):
    """Pair each label with the nearest unused number: same line (right, then left) or directly above / below."""
    nums = [dict(w, v=parse_number(w["t"])) for w in words]
    nums = [w for w in nums if w["v"] is not None]
    toks = [re.sub(r"[^a-z]", "", w["t"].lower()) for w in words]
    hits = []                                                              # (field, label word span)
    for field, phrases in LABELS.items():
        for ph in phrases:
            parts = ph.split(); n = len(parts)
            for i in range(len(words) - n + 1):
                if toks[i:i + n] == parts and (n == 1 or all(words[i + j]["ln"] == words[i]["ln"] for j in range(n))):
                    hits.append((field, words[i:i + n]))
    cands = []
    for field, span in hits:
        l0, r0 = min(w["l"] for w in span), max(w["l"] + w["w"] for w in span)
        t0, b0 = min(w["tp"] for w in span), max(w["tp"] + w["h"] for w in span)
        lh = max(b0 - t0, 10); cx = (l0 + r0) / 2
        for j, nw in enumerate(nums):
            ncx = nw["l"] + nw["w"] / 2; ncy = nw["tp"] + nw["h"] / 2; lcy = (t0 + b0) / 2
            same = abs(ncy - lcy) < lh * .7
            if same:
                gap = nw["l"] - r0 if nw["l"] >= r0 - 2 else l0 - (nw["l"] + nw["w"])
                if gap < -2: continue
                d = .5 + .02 * max(gap, 0) / lh + (0 if nw["l"] >= r0 - 2 else .6)     # a number on the same row is the likeliest partner
                cands.append((d, field, j, "side"))
            else:
                dy = abs(ncy - lcy)
                if dy <= lh * 4 and abs(ncx - cx) <= max((r0 - l0), nw["w"]) * .9 + lh:
                    d = dy / lh * 1.6 + abs(ncx - cx) / (lh * 6)
                    cands.append((d, field, j, "above" if ncy < lcy else "below"))
    cands.sort(); used_n, used_f, found = set(), set(), {}
    for d, field, j, where in cands:
        if field in used_f or j in used_n: continue
        used_n.add(j); used_f.add(field)
        found[field] = {"value": nums[j]["v"], "check": where != "side", "where": where}
    return found


def read(data: bytes):
    """-> {"fields": {name: {"value": int, "check": bool}}, "found": int}"""
    if len(data) > MAX_BYTES: raise ValueError("The picture is bigger than 6 MB. Please crop it or send a smaller one.")
    try:
        im = Image.open(io.BytesIO(data)); im.verify(); im = Image.open(io.BytesIO(data))
    except Exception:
        raise ValueError("That file is not a picture I can open. Please upload a PNG or JPG screenshot.")
    if im.format not in ("PNG", "JPEG", "WEBP"): raise ValueError("Please upload a PNG, JPG or WEBP screenshot.")
    if im.width * im.height > MAX_PIXELS: raise ValueError("The picture is too large. Please crop the screenshot.")
    img = _prep(im); best = {}
    for psm in (11, 6):
        try: f = _find(_words(img, psm))
        except Exception as e:
            if "timeout" in str(e).lower(): raise ValueError("Reading the picture took too long. Please crop it to the numbers.")
            raise
        for k, v in f.items():
            if k not in best or (best[k]["check"] and not v["check"]): best[k] = v
    return {"fields": {k: {"value": v["value"], "check": v["check"]} for k, v in best.items()}, "found": len(best)}
