"""
Builds assets/terminal.svg — an animated market terminal for the GitHub profile.

Data (all free, no API keys):
  - BTC / ETH daily prices and 24h change ...... CoinGecko
  - BTC dominance ............................... CoinGecko /global
  - Fear & Greed index .......................... alternative.me
  - Fed net liquidity = WALCL - TGA - RRP ........ FRED (public CSV)

All text is converted to outlines, so the image looks identical on every device.
Run with --demo to render with synthetic data (no network).
"""
import csv, io, math, random, re, sys, datetime as dt
from pathlib import Path

import uharfbuzz as hb
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parent.parent
FONT = ROOT / "assets" / "Archivo.ttf"
OUT = ROOT / "assets" / "terminal.svg"

# ---------------------------------------------------------------- palette
BG, PANEL, RULE = "#0d1117", "#11161d", "#232a33"
GOLD, IVORY, MUTED, FAINT = "#d9a930", "#ece7dc", "#8a8f98", "#4a515b"
SILVER, UP, DOWN = "#c4c8cf", "#3fb950", "#f0625a"

W, H = 1280, 580

# ---------------------------------------------------------------- text → outlines
_NUM = re.compile(r"-?\d+\.\d+")
_face = hb.Face(hb.Blob.from_file_path(str(FONT)))
_inst = {}

def _instance(wght, wdth):
    k = (wght, wdth)
    if k not in _inst:
        _inst[k] = instantiateVariableFont(TTFont(str(FONT)), {"wght": wght, "wdth": wdth})
    return _inst[k]

def text(s, x, y, size, wght=400, wdth=100, fill=IVORY, anchor="start", track=0, cls=""):
    font = hb.Font(_face)
    font.set_variations({"wght": wght, "wdth": wdth})
    buf = hb.Buffer(); buf.add_str(s); buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "tnum": True})
    inst = _instance(wght, wdth)
    gs, order = inst.getGlyphSet(), inst.getGlyphOrder()
    sc = size / inst["head"].unitsPerEm
    trk = track * size / 1000
    total = sum(p.x_advance for p in buf.glyph_positions) * sc + trk * max(0, len(buf.glyph_infos) - 1)
    if anchor == "middle": x -= total / 2
    elif anchor == "end": x -= total
    pen, cx = SVGPathPen(gs), 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        gs[order[info.codepoint]].draw(TransformPen(pen, (sc, 0, 0, -sc, x + cx * sc, y)))
        cx += pos.x_advance + trk / sc
    c = f' class="{cls}"' if cls else ""
    d = _NUM.sub(lambda m: f"{float(m.group()):.1f}".rstrip("0").rstrip("."), pen.getCommands())
    return f'<path{c} d="{d}" fill="{fill}"/>', total

# ---------------------------------------------------------------- data
def fetch_live():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Behruz44-profile-terminal"
    get = lambda url, **kw: s.get(url, timeout=25, **kw)
    d = {}

    def cg_chart(coin):
        r = get(f"https://api.coingecko.com/api/v3/coins/{coin}/market_chart",
                params={"vs_currency": "usd", "days": 90, "interval": "daily"})
        r.raise_for_status()
        return [(dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).date(), p) for t, p in r.json()["prices"]]

    d["btc"] = cg_chart("bitcoin")
    d["eth"] = cg_chart("ethereum")

    try:
        r = get("https://api.coingecko.com/api/v3/simple/price",
                params={"ids": "bitcoin,ethereum", "vs_currencies": "usd", "include_24hr_change": "true"})
        j = r.json()
        d["btc_chg"] = j["bitcoin"]["usd_24h_change"]
        d["eth_chg"] = j["ethereum"]["usd_24h_change"]
        d["btc"][-1] = (d["btc"][-1][0], j["bitcoin"]["usd"])
        d["eth"][-1] = (d["eth"][-1][0], j["ethereum"]["usd"])
    except Exception:
        pass

    try:
        d["dominance"] = get("https://api.coingecko.com/api/v3/global").json()["data"]["market_cap_percentage"]["btc"]
    except Exception:
        pass

    try:
        f = get("https://api.alternative.me/fng/", params={"limit": 1}).json()["data"][0]
        d["fng"] = (int(f["value"]), f["value_classification"])
    except Exception:
        pass

    try:
        def fred(series):
            r = get("https://fred.stlouisfed.org/graph/fredgraph.csv", params={"id": series})
            rows = list(csv.reader(io.StringIO(r.text)))[1:]
            return [(dt.date.fromisoformat(a), float(b)) for a, b in rows if b not in ("", ".")]
        walcl, tga, rrp = fred("WALCL"), fred("WTREGEN"), fred("RRPONTSYD")

        def last_before(series, day):
            v = None
            for t, x in series:
                if t <= day: v = x
                else: break
            return v

        net = []
        for day, w in walcl[-30:]:
            t, r_ = last_before(tga, day), last_before(rrp, day)
            if t is not None and r_ is not None:
                net.append((day, w / 1000 - t / 1000 - r_))   # billions USD
        d["netliq"] = net
    except Exception:
        pass
    return d

def fake_data():
    random.seed(42)
    end = dt.date.today()
    def walk(start, vol, drift, n=91):
        p, out = start, []
        for i in range(n):
            p *= 1 + random.gauss(drift, vol)
            out.append((end - dt.timedelta(days=n - 1 - i), p))
        return out
    net, v = [], 5700.0
    for i in range(30):
        v += random.gauss(4, 18)
        net.append((end - dt.timedelta(weeks=29 - i), v))
    return {"btc": walk(98000, 0.021, 0.0011), "eth": walk(3400, 0.028, 0.0008),
            "btc_chg": 1.84, "eth_chg": -0.62, "dominance": 58.4,
            "fng": (64, "Greed"), "netliq": net}

# ---------------------------------------------------------------- drawing helpers
def money(v):
    return f"${v:,.0f}" if v >= 1000 else f"${v:,.2f}"

def pct(v):
    return f"{'+' if v >= 0 else '−'}{abs(v):.2f}%"

def chart(series, x, y, w, h, color, cid, area=True, delay=0.0):
    """Line chart with gridlines, last-price dot. Returns svg string."""
    vals = [p for _, p in series]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.12 or 1
    lo, hi = lo - pad, hi + pad
    n = len(vals)
    pts = [(x + i * w / (n - 1), y + h - (v - lo) / (hi - lo) * h) for i, v in enumerate(vals)]
    out = []
    # gridlines + price labels
    for k in range(4):
        gy = y + h * k / 3
        out.append(f'<line x1="{x}" y1="{gy:.1f}" x2="{x + w}" y2="{gy:.1f}" stroke="{RULE}" stroke-width="1"/>')
        val = hi - (hi - lo) * k / 3
        t, _ = text(money(val), x + w + 12, gy + 4, 11.5, 430, fill=FAINT)
        out.append(t)
    # date labels
    for idx in (0, n // 2, n - 1):
        lbl = series[idx][0].strftime("%d %b")
        anchor = "start" if idx == 0 else "end" if idx == n - 1 else "middle"
        t, _ = text(lbl, pts[idx][0], y + h + 22, 11.5, 430, fill=FAINT, anchor=anchor)
        out.append(t)

    path = "M" + " L".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    length = sum(math.dist(pts[i], pts[i + 1]) for i in range(n - 1))
    if area:
        out.append(f'<defs><linearGradient id="g{cid}" x1="0" y1="0" x2="0" y2="1">'
                   f'<stop offset="0" stop-color="{color}" stop-opacity="0.22"/>'
                   f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient></defs>')
        out.append(f'<path class="fade" style="animation-delay:{delay + 1.6:.1f}s" '
                   f'd="{path} L{pts[-1][0]:.1f},{y + h} L{pts[0][0]:.1f},{y + h} Z" fill="url(#g{cid})"/>')
    out.append(f'<path class="draw" style="--len:{length:.0f};animation-delay:{delay:.1f}s" d="{path}" '
               f'fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>')
    lx, ly = pts[-1]
    out.append(f'<circle class="pulse" cx="{lx:.1f}" cy="{ly:.1f}" r="5" fill="none" stroke="{color}" stroke-width="1.5"/>')
    out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.6" fill="{color}"/>')
    return "".join(out)

def sparkline(series, x, y, w, h, color):
    vals = [v for _, v in series]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1
    pts = [(x + i * w / (len(vals) - 1), y + h - (v - lo) / rng * h) for i, v in enumerate(vals)]
    d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in pts)
    return (f'<path d="{d}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>'
            f'<circle cx="{pts[-1][0]:.1f}" cy="{pts[-1][1]:.1f}" r="2.6" fill="{color}"/>')

# ---------------------------------------------------------------- build
def build(d):
    o = []
    o.append(f'<rect width="{W}" height="{H}" rx="14" fill="{BG}"/>')
    o.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="14" fill="none" stroke="{RULE}"/>')

    # ---- left column: identity
    L = 56
    t, _ = text("Behruz", L, 100, 52, 820, 110, IVORY, track=-12); o.append(t)
    t, _ = text("Abdumanapov", L, 156, 52, 820, 110, IVORY, track=-12); o.append(t)
    t, _ = text("Software engineer", L, 200, 21, 620, 106, GOLD); o.append(t)
    t, _ = text("Payments, trading systems and macro research", L, 228, 16.5, 430, 100, MUTED); o.append(t)

    # ---- left column: macro block
    o.append(f'<line x1="{L}" y1="268" x2="{L + 392}" y2="268" stroke="{RULE}"/>')
    row_y = 302

    def macro_row(label, value, sub, sub_color, y):
        a, _ = text(label, L, y, 14, 460, 100, MUTED)
        b, _ = text(value, L, y + 30, 26, 700, 104, IVORY)
        c, _ = text(sub, L + 392, y + 30, 14.5, 560, 100, sub_color, anchor="end")
        o.extend([a, b, c])

    if d.get("netliq"):
        net = d["netliq"]
        cur, prev = net[-1][1], net[-5][1] if len(net) >= 5 else net[0][1]
        chg = cur - prev
        macro_row("Fed net liquidity", f"${cur / 1000:.2f}T",
                  f"{'+' if chg >= 0 else '−'}${abs(chg):.0f}B in 4 weeks", UP if chg >= 0 else DOWN, row_y)
        o.append(sparkline(net[-26:], L + 132, row_y + 8, 96, 24, GOLD))
    else:
        macro_row("Fed net liquidity", "—", "", MUTED, row_y)

    y2 = row_y + 72
    if d.get("fng"):
        v, cls = d["fng"]
        macro_row("Fear and Greed", f"{v}", cls, GOLD, y2)
        bx, bw = L + 70, 210
        o.append(f'<rect x="{bx}" y="{y2 + 18}" width="{bw}" height="5" rx="2.5" fill="{RULE}"/>')
        o.append(f'<rect x="{bx}" y="{y2 + 18}" width="{bw * v / 100:.1f}" height="5" rx="2.5" fill="{GOLD}"/>')
    y3 = y2 + 72
    if d.get("dominance"):
        macro_row("Bitcoin dominance", f"{d['dominance']:.1f}%", "share of crypto market", MUTED, y3)

    # ---- right column: charts
    R, CW = 520, 620
    o.append(f'<rect x="{R - 28}" y="28" width="{W - R}" height="{H - 104}" rx="10" fill="{PANEL}"/>')

    btc, eth = d["btc"], d["eth"]
    t, _ = text("BTC / USD", R, 76, 15, 600, 106, MUTED); o.append(t)
    t, w = text(money(btc[-1][1]), R, 112, 34, 760, 104, IVORY); o.append(t)
    if d.get("btc_chg") is not None:
        c = d["btc_chg"]
        t, _ = text(f"{pct(c)} 24h", R + w + 14, 112, 16, 600, 100, UP if c >= 0 else DOWN); o.append(t)
    t, _ = text("90 days", R + CW, 76, 13, 460, 100, FAINT, anchor="end"); o.append(t)
    o.append(chart(btc, R, 132, CW, 150, GOLD, "btc", delay=0.2))

    t, _ = text("ETH / USD", R, 338, 15, 600, 106, MUTED); o.append(t)
    t, w = text(money(eth[-1][1]), R, 370, 26, 720, 104, IVORY); o.append(t)
    if d.get("eth_chg") is not None:
        c = d["eth_chg"]
        t, _ = text(f"{pct(c)} 24h", R + w + 12, 370, 14.5, 600, 100, UP if c >= 0 else DOWN); o.append(t)
    o.append(chart(eth, R, 386, CW, 52, SILVER, "eth", area=False, delay=0.9))

    # ---- ticker tape
    items = [("BTC", btc[-1][1], d.get("btc_chg")), ("ETH", eth[-1][1], d.get("eth_chg"))]
    tape, tx = [], 0.0
    for _ in range(2):  # duplicated for a seamless loop
        for sym, price, chg in items * 3:
            a, wa = text(sym, tx, 0, 14, 700, 106, GOLD); tape.append(a); tx += wa + 10
            b, wb = text(money(price), tx, 0, 14, 500, 100, IVORY); tape.append(b); tx += wb + 10
            if chg is not None:
                c, wc = text(pct(chg), tx, 0, 14, 500, 100, UP if chg >= 0 else DOWN); tape.append(c); tx += wc
            tx += 48
        if d.get("netliq"):
            a, wa = text("FED NET LIQUIDITY", tx, 0, 14, 700, 106, GOLD); tape.append(a); tx += wa + 10
            b, wb = text(f"${d['netliq'][-1][1] / 1000:.2f}T", tx, 0, 14, 500, 100, IVORY); tape.append(b); tx += wb + 48
    half = tx / 2
    o.append(f'<line x1="0" y1="{H - 62}" x2="{W}" y2="{H - 62}" stroke="{RULE}"/>')
    o.append(f'<clipPath id="tape"><rect x="1" y="{H - 61}" width="{W - 2}" height="46"/></clipPath>')
    o.append(f'<g clip-path="url(#tape)"><g transform="translate(0 {H - 32})">'
             f'<g class="tape" style="--half:{half:.0f}px">{"".join(tape)}</g></g></g>')

    stamp = dt.datetime.now(dt.timezone.utc).strftime("Updated %d %b %Y, %H:%M UTC")
    t, _ = text(stamp, L, H - 82, 11.5, 430, 100, FAINT); o.append(t)

    css = """
    <style>
      .draw { stroke-dasharray: var(--len); animation: draw 2.4s cubic-bezier(.3,.7,.2,1) both; }
      @keyframes draw { from { stroke-dashoffset: var(--len); } to { stroke-dashoffset: 0; } }
      .fade { animation: fade 1.2s ease-out both; }
      @keyframes fade { from { opacity: 0; } to { opacity: 1; } }
      .pulse { transform-box: fill-box; transform-origin: center; animation: pulse 2.2s ease-out 2.6s infinite; opacity: 0; }
      @keyframes pulse { 0% { transform: scale(1); opacity: .9; } 100% { transform: scale(3.2); opacity: 0; } }
      .tape { animation: tape 38s linear infinite; }
      @keyframes tape { from { transform: translateX(0); } to { transform: translateX(calc(-1 * var(--half))); } }
      @media (prefers-reduced-motion: reduce) {
        .draw, .fade, .pulse, .tape { animation: none; }
      }
    </style>"""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            f'{css}{"".join(o)}</svg>')

if __name__ == "__main__":
    demo = "--demo" in sys.argv
    try:
        data = fake_data() if demo else fetch_live()
    except Exception as e:
        print(f"price data unavailable ({e}); keeping previous image")
        sys.exit(0)
    OUT.write_text(build(data), encoding="utf-8")
    print(f"wrote {OUT}")
