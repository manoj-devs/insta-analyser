"""Small chart toolkit for the PDF reports (reportlab vector graphics, no extra packages). Every function returns a reportlab Drawing."""
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon, Group
from reportlab.graphics.charts.barcharts import VerticalBarChart, HorizontalBarChart
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.widgets.markers import makeMarker
from reportlab.lib import colors
from reportlab.lib.units import mm

W = 174 * mm
INK, MUTED, GRID = colors.HexColor("#1b2a52"), colors.HexColor("#6b7390"), colors.HexColor("#d9dded")
PAL = [colors.HexColor(x) for x in ("#5b5fe0", "#ff7a3d", "#14b8a6", "#e8449a", "#f5b50a", "#2f9bf0", "#8b5cf6", "#22c55e")]
GROUP_COL = {"Dashboard": "#5b5fe0", "Warehouse design": "#14b8a6", "Data mining": "#e8449a", "Regions": "#ff7a3d", "Earnings": "#f5b50a", "Admin": "#2f9bf0"}


def ramp(t):
    """0..1 -> indigo, pink, orange, yellow (heat map colours)"""
    st = [(.36, .37, .88), (.91, .27, .60), (1, .48, .24), (.96, .71, .04)]; t = max(0, min(1, t)) * 3; i = min(2, int(t)); f = t - i
    return colors.Color(*[st[i][k] + (st[i + 1][k] - st[i][k]) * f for k in range(3)])


def _short(s, n=18):
    s = str(s); return s if len(s) <= n else s[:n - 1] + "…"


def human(v):
    v = float(v); a = abs(v)
    for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= lim: return f"{v / lim:.1f}".rstrip("0").rstrip(".") + suf
    return f"{v:.0f}" if a >= 100 or v == int(v) else f"{v:.1f}"


def _empty(msg="No data yet", h=60):
    d = Drawing(W, h); d.add(Rect(0, 0, W, h, fillColor=colors.HexColor("#f4f6fd"), strokeColor=GRID))
    d.add(String(W / 2, h / 2 - 3, msg, textAnchor="middle", fontSize=10, fillColor=MUTED)); return d


def bar(labels, values, color=None, h=190, horizontal=False, fmt=human, unit=""):
    if not labels: return _empty()
    n = len(labels); col = color or PAL[0]
    if horizontal:
        h = max(80, 22 * n + 30); d = Drawing(W, h); ch = HorizontalBarChart(); ch.x, ch.y, ch.width, ch.height = 110, 10, W - 150, h - 22
        ch.categoryAxis.categoryNames = [_short(x, 24) for x in labels]; ch.categoryAxis.labels.fontSize = 8; ch.categoryAxis.reverseDirection = 1
        ch.categoryAxis.labels.boxAnchor = "e"; ch.categoryAxis.labels.dx = -4
    else:
        d = Drawing(W, h); ch = VerticalBarChart(); ch.x, ch.y, ch.width, ch.height = 36, 38, W - 56, h - 56
        ch.categoryAxis.categoryNames = [_short(x, 12) for x in labels]; ch.categoryAxis.labels.fontSize = 8
        if n > 7: ch.categoryAxis.labels.angle = 30; ch.categoryAxis.labels.boxAnchor = "ne"; ch.categoryAxis.labels.dx = 4; ch.categoryAxis.labels.dy = -2
    ch.data = [list(values)]; ch.bars[0].fillColor = col; ch.bars[0].strokeColor = None
    if horizontal: ch.barWidth = 12
    ch.valueAxis.valueMin = 0; ch.valueAxis.labels.fontSize = 8; ch.valueAxis.labelTextFormat = lambda v: human(v) + unit
    ch.valueAxis.strokeColor = GRID; ch.valueAxis.gridStrokeColor = GRID; ch.valueAxis.visibleGrid = 1; ch.categoryAxis.strokeColor = GRID
    ch.bars.strokeColor = None
    for i in range(n): ch.bars[(0, i)].fillColor = PAL[i % len(PAL)]
    ch.groupSpacing = 6 if not horizontal else 4
    ch.barLabelFormat = lambda v: fmt(v) + unit; ch.barLabels.fontSize = 7; ch.barLabels.fillColor = INK
    ch.barLabels.nudge = 7 if not horizontal else 0; ch.barLabels.boxAnchor = "s" if not horizontal else "w"
    if horizontal: ch.barLabels.dx = 3; ch.barLabels.boxAnchor = "w"
    d.add(ch); return d


def line(labels, series, names=None, h=170, unit=""):
    """series = list of lists"""
    if not labels or not series or not any(series[0]): return _empty()
    d = Drawing(W, h); ch = HorizontalLineChart(); ch.x, ch.y, ch.width, ch.height = 38, 34, W - 60, h - 56
    ch.data = [list(s) for s in series]; ch.categoryAxis.categoryNames = [_short(x, 10) for x in labels]; ch.categoryAxis.labels.fontSize = 8
    if len(labels) > 8: ch.categoryAxis.labels.angle = 30; ch.categoryAxis.labels.boxAnchor = "ne"
    ch.valueAxis.labels.fontSize = 8; ch.valueAxis.labelTextFormat = lambda v: human(v) + unit; ch.valueAxis.valueMin = 0
    ch.valueAxis.visibleGrid = 1; ch.valueAxis.gridStrokeColor = GRID; ch.valueAxis.strokeColor = GRID; ch.categoryAxis.strokeColor = GRID
    for i in range(len(series)): ch.lines[i].strokeColor = PAL[i % len(PAL)]; ch.lines[i].strokeWidth = 3; ch.lines[i].symbol = makeMarker('FilledCircle'); ch.lines[i].symbol.size = 5; ch.lines[i].symbol.fillColor = PAL[i % len(PAL)]; ch.lines[i].symbol.strokeColor = colors.white
    d.add(ch)
    if names and len(names) > 1:
        x = 40
        for i, nm in enumerate(names):
            d.add(Rect(x, h - 14, 9, 9, fillColor=PAL[i % len(PAL)], strokeColor=None)); d.add(String(x + 13, h - 13, nm, fontSize=8, fillColor=INK)); x += 20 + len(nm) * 4.6
    return d


def pie(labels, values, h=170):
    if not labels or not sum(values): return _empty()
    d = Drawing(W, h); p = Pie(); p.x, p.y, p.width, p.height = 20, 15, h - 30, h - 30
    p.data = list(values); p.labels = None; p.slices.strokeColor = colors.white; p.slices.strokeWidth = 1
    for i in range(len(values)): p.slices[i].fillColor = PAL[i % len(PAL)]
    d.add(p); tot = float(sum(values)); y = h - 28
    for i, (l, v) in enumerate(zip(labels, values)):
        d.add(Rect(h + 10, y, 9, 9, fillColor=PAL[i % len(PAL)], strokeColor=None)); d.add(String(h + 24, y + 1, f"{_short(l, 34)}  {100 * v / tot:.0f}%", fontSize=8.5, fillColor=INK)); y -= 15
        if y < 5: break
    return d


def heat(rows, cols, grid, h=None, fmt=human, rowlab_w=96):
    """grid[r][c] numbers (None = empty). Colour = value, light to dark blue."""
    if not rows or not cols: return _empty()
    cw = (W - rowlab_w - 6) / len(cols); rh = min(15, 170 / len(rows)); h = h or rh * len(rows) + 34
    d = Drawing(W, h); flat = [v for r in grid for v in r if v is not None]
    if not flat: return _empty()
    lo, hi = min(flat), max(flat)
    for ri, r in enumerate(rows):
        y = h - 24 - (ri + 1) * rh
        d.add(String(rowlab_w - 4, y + rh / 2 - 3, _short(r, 22), textAnchor="end", fontSize=7.5, fillColor=INK))
        for ci, v in enumerate(grid[ri]):
            x = rowlab_w + ci * cw
            if v is None: d.add(Rect(x, y, cw - 1, rh - 1, fillColor=colors.HexColor("#f1f2f8"), strokeColor=None)); continue
            t = 0 if hi == lo else (v - lo) / (hi - lo)
            c = ramp(t); d.add(Rect(x, y, cw - 1, rh - 1, fillColor=c, strokeColor=None))
            if cw > 26 and rh > 11: d.add(String(x + cw / 2, y + rh / 2 - 3, fmt(v), textAnchor="middle", fontSize=6.5, fillColor=colors.white if t < .75 else INK))
    for ci, c in enumerate(cols):
        if len(cols) <= 12 or ci % 2 == 0: d.add(String(rowlab_w + ci * cw + cw / 2, h - 20, _short(c, 9), textAnchor="middle", fontSize=7.5, fillColor=MUTED))
    return d


def tiles(items, h=52):
    """items = [(label, value_text)]"""
    n = len(items); gap = 6; w = (W - gap * (n - 1)) / n; d = Drawing(W, h)
    for i, (lab, val) in enumerate(items):
        x = i * (w + gap); d.add(Rect(x, 0, w, h, rx=5, ry=5, fillColor=PAL[i % len(PAL)], strokeColor=None))
        d.add(String(x + 10, h - 30, str(val), fontSize=17, fontName="Helvetica-Bold", fillColor=colors.white)); d.add(String(x + 10, 10, _short(lab, 22), fontSize=8, fillColor=colors.Color(1, 1, 1, .85)))
    return d


def _box(d, x, y, w, h, title, sub="", fill=None, ink=colors.white):
    d.add(Rect(x, y, w, h, rx=5, ry=5, fillColor=fill or PAL[0], strokeColor=None))
    d.add(String(x + w / 2, y + h / 2 + (2 if sub else -3), _short(title, int(w / 5.2)), textAnchor="middle", fontSize=8.5, fontName="Helvetica-Bold", fillColor=ink))
    if sub: d.add(String(x + w / 2, y + h / 2 - 9, _short(sub, int(w / 4.4)), textAnchor="middle", fontSize=7.5, fillColor=ink))


def _arrow(d, x1, y1, x2, y2, col=MUTED):
    d.add(Line(x1, y1, x2, y2, strokeColor=col, strokeWidth=1.2))
    import math
    a = math.atan2(y2 - y1, x2 - x1); s = 5
    d.add(Polygon([x2, y2, x2 - s * math.cos(a - .45), y2 - s * math.sin(a - .45), x2 - s * math.cos(a + .45), y2 - s * math.sin(a + .45)], fillColor=col, strokeColor=col))


def flow(steps, h=84):
    """steps = [(title, sub, ok_bool|None)] drawn left to right with arrows"""
    n = len(steps); gap = 18; w = (W - gap * (n - 1)) / n; d = Drawing(W, h)
    for i, (t, s, ok) in enumerate(steps):
        x = i * (w + gap); fill = PAL[0] if ok is None else (PAL[2] if ok else colors.HexColor("#d64545"))
        _box(d, x, 14, w, h - 28, t, s, fill)
        if i < n - 1: _arrow(d, x + w + 2, h / 2, x + w + gap - 2, h / 2)
    return d


def star(fact, fact_sub, dims, h=250, extra=None):
    """star schema picture: the fact table in the middle, dimensions around it. dims = [(name, sub)]. extra = {dim_index: [(name, sub)]} (snowflake outriggers)"""
    import math
    d = Drawing(W, h); cx, cy = W / 2, h / 2; bw, bh = 104, 34; n = len(dims); rx, ry = W / 2 - bw / 2 - 8, h / 2 - bh / 2 - 6
    pos = []
    for i in range(n):
        a = math.pi / 2 - 2 * math.pi * i / n; pos.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    for (x, y), (nm, sub) in zip(pos, dims): _arrow(d, cx, cy, x, y, GRID)
    for i, ((x, y), (nm, sub)) in enumerate(zip(pos, dims)):
        _box(d, x - bw / 2, y - bh / 2, bw, bh, nm, sub, PAL[1] if not extra or i not in extra else PAL[3])
    _box(d, cx - 62, cy - 22, 124, 44, fact, fact_sub, PAL[0])
    return d


def hierarchy(levels, h=70):
    """snowflake date hierarchy: day -> month -> quarter -> year"""
    return flow([(a, b, None) for a, b in levels], h)


def banner(num, title, group, h=30):
    c = colors.HexColor(GROUP_COL.get(group, "#5b5fe0")); d = Drawing(W, h)
    d.add(Rect(0, 0, W, h, rx=7, ry=7, fillColor=c, strokeColor=None)); d.add(Rect(W - 90, 0, 90, h, rx=7, ry=7, fillColor=colors.Color(1, 1, 1, .16), strokeColor=None))
    d.add(String(12, h / 2 - 5, f"{num}", fontSize=14, fontName="Helvetica-Bold", fillColor=colors.Color(1, 1, 1, .7)))
    d.add(String(34, h / 2 - 5, _short(title, 60), fontSize=13, fontName="Helvetica-Bold", fillColor=colors.white))
    d.add(String(W - 45, h / 2 - 4, group.upper(), textAnchor="middle", fontSize=7.5, fontName="Helvetica-Bold", fillColor=colors.white)); return d


def panel(d, pad=6):
    """put a chart on a soft tinted card"""
    nd = Drawing(d.width, d.height + 2 * pad); nd.add(Rect(0, 0, d.width, d.height + 2 * pad, rx=8, ry=8, fillColor=colors.HexColor("#f6f7fd"), strokeColor=colors.HexColor("#e3e6f5")))
    g = Group(d); g.translate(0, pad); nd.add(g); return nd


def cover_chips(items, h=None):
    """contents as coloured chips, two per row: items = [(title, group)]"""
    cw = (W - 8) / 2; rows = (len(items) + 1) // 2; h = rows * 30; d = Drawing(W, h)
    for i, (t, g) in enumerate(items):
        x = (i % 2) * (cw + 8); y = h - (i // 2 + 1) * 30 + 4; c = colors.HexColor(GROUP_COL.get(g, "#5b5fe0"))
        d.add(Rect(x, y, cw, 24, rx=12, ry=12, fillColor=colors.Color(1, 1, 1, .12), strokeColor=None)); d.add(Rect(x, y, 24, 24, rx=12, ry=12, fillColor=c, strokeColor=None))
        d.add(String(x + 12, y + 8, str(i + 1), textAnchor="middle", fontSize=9, fontName="Helvetica-Bold", fillColor=colors.white)); d.add(String(x + 32, y + 8, _short(t, 40), fontSize=9.5, fillColor=colors.white))
    return d
