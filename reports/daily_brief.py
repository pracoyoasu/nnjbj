"""
Daily Geo-Macro Brief -> PDF
Usage : python reports/daily_brief.py reports/content/YYYY-MM-DD.json
Output: reports/pdf/YYYY-MM-DD.pdf

Konten (berita, skenario worst case) ditulis ke JSON oleh analis/agent;
level SMC (OB, FVG, struktur) dihitung dari OHLCV Coinbase BTC-USD
memakai utils/smc_detector.py.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from utils.smc_detector import (detect_fvg, detect_market_structure,  # noqa: E402
                                detect_orderblocks)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DV", FONT_DIR / "DejaVuSans.ttf"))
pdfmetrics.registerFont(TTFont("DVB", FONT_DIR / "DejaVuSans-Bold.ttf"))

NAVY, RED, GREEN, GREY = (colors.HexColor(c) for c in ("#14213d", "#c0392b", "#1e8449", "#6b7280"))
ss = getSampleStyleSheet()
S = {
    "title": ParagraphStyle("t", fontName="DVB", fontSize=18, leading=22, textColor=NAVY),
    "sub":   ParagraphStyle("s", fontName="DV", fontSize=9, textColor=GREY),
    "h1":    ParagraphStyle("h1", fontName="DVB", fontSize=12.5, leading=16, textColor=NAVY, spaceBefore=10, spaceAfter=4),
    "h2":    ParagraphStyle("h2", fontName="DVB", fontSize=10, leading=13, spaceBefore=4),
    "body":  ParagraphStyle("b", fontName="DV", fontSize=8.8, leading=12),
    "small": ParagraphStyle("sm", fontName="DV", fontSize=7.5, leading=10, textColor=GREY),
    "cell":  ParagraphStyle("c", fontName="DV", fontSize=7.8, leading=10),
    "cellb": ParagraphStyle("cb", fontName="DVB", fontSize=7.8, leading=10, textColor=colors.white),
    "box":   ParagraphStyle("bx", fontName="DVB", fontSize=9.5, leading=13, textColor=colors.white, alignment=TA_CENTER),
}


# ── Data ─────────────────────────────────────────────────────────
TF_SEC = {"1D": 86400, "4h": 14400, "30m": 1800}


def load_ohlcv(ticker: str, tf: str, drop_forming: bool = True) -> pd.DataFrame:
    """OHLCV dari reports/ohlcv/<TICKER>_<tf>.json (ditulis agent dari TradingView MCP, format kolom t/o/h/l/c).
    Bar yang belum close dibuang supaya struktur/OB/FVG hanya dari candle final."""
    d = json.loads((ROOT / "reports" / "ohlcv" / f"{ticker}_{tf}.json").read_text())
    df = pd.DataFrame({"t": d["t"], "open": d["o"], "high": d["h"], "low": d["l"], "close": d["c"]})
    if drop_forming:
        df = df[df["t"] + TF_SEC[tf] <= datetime.now(timezone.utc).timestamp()]
    df["time"] = pd.to_datetime(df["t"], unit="s", utc=True)
    df["volume"] = 0.0
    return df[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def smc_levels(df: pd.DataFrame, n: int = 3) -> dict:
    """Zona OB/FVG terdekat di atas (supply) dan di bawah (demand) harga."""
    px = df["close"].iloc[-1]
    ob = detect_orderblocks(df)
    fvg = detect_fvg(df)
    zones = [(r.ob_type, "OB", r.ob_bottom, r.ob_top) for r in ob.itertuples()]
    if not fvg.empty:
        zones += [(r.fvg_type, "FVG", r.fvg_bottom, r.fvg_top) for r in fvg.itertuples()]
    above = sorted([z for z in zones if z[2] > px], key=lambda z: z[2])[:n]
    below = sorted([z for z in zones if z[3] < px], key=lambda z: -z[3])[:n]
    return {"price": px, "structure": detect_market_structure(df), "above": above, "below": below}


# ── Drawing helpers ──────────────────────────────────────────────
def candle_chart(df: pd.DataFrame, lv: dict, title: str, w=180 * mm, h=62 * mm) -> Drawing:
    d = Drawing(w, h)
    pad_l, pad_r, pad_b, pad_t = 8, 42, 10, 14
    zones = lv["above"] + lv["below"]
    lo = min(df["low"].min(), *(z[2] for z in zones)) if zones else df["low"].min()
    hi = max(df["high"].max(), *(z[3] for z in zones)) if zones else df["high"].max()
    y = lambda p: pad_b + (p - lo) / (hi - lo) * (h - pad_b - pad_t)  # noqa: E731
    cw = (w - pad_l - pad_r) / len(df)
    last_ly = -99
    for typ, kind, bot, top in sorted(zones, key=lambda z: z[2]):
        col = colors.Color(0.12, 0.52, 0.29, 0.18) if typ == "bullish" else colors.Color(0.75, 0.22, 0.17, 0.18)
        d.add(Rect(pad_l, y(bot), w - pad_l - pad_r, max(y(top) - y(bot), 1), fillColor=col, strokeColor=None))
        ly = max(y((bot + top) / 2) - 2, last_ly + 7)  # stack labels so they don't overlap
        last_ly = ly
        d.add(String(w - pad_r + 2, ly, f"{kind} {bot:,.0f}", fontName="DV", fontSize=5.5,
                     fillColor=GREEN if typ == "bullish" else RED))
    for i, r in enumerate(df.itertuples()):
        x = pad_l + i * cw + cw / 2
        col = GREEN if r.close >= r.open else RED
        d.add(Line(x, y(r.low), x, y(r.high), strokeColor=col, strokeWidth=0.5))
        d.add(Rect(x - cw * 0.35, y(min(r.open, r.close)), cw * 0.7, max(abs(y(r.close) - y(r.open)), 0.5),
                   fillColor=col, strokeColor=None))
    px = lv["price"]
    d.add(Line(pad_l, y(px), w - pad_r, y(px), strokeColor=NAVY, strokeWidth=0.6, strokeDashArray=[2, 2]))
    d.add(String(w - pad_r + 2, y(px) - 2, f"{px:,.0f}", fontName="DVB", fontSize=6.5, fillColor=NAVY))
    d.add(String(pad_l, h - 9, title, fontName="DVB", fontSize=8, fillColor=NAVY))
    return d


def table(rows, widths, header_bg=NAVY, zebra=True):
    data = [[Paragraph(str(c), S["cellb"] if i == 0 else S["cell"]) for c in row] for i, row in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), header_bg), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d5db")),
             ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if zebra:
        style += [("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f3f4f6")) for i in range(2, len(rows), 2)]
    t.setStyle(TableStyle(style))
    return t


def zone_rows(lv):
    rows = [["Posisi", "Tipe", "Zona (low – high)", "Jarak"]]
    px = lv["price"]
    for side, zs in (("Atas (supply)", lv["above"]), ("Bawah (demand)", lv["below"])):
        for typ, kind, bot, top in zs:
            ref = bot if side.startswith("Atas") else top
            rows.append([side, f"{typ.title()} {kind}", f"{bot:,.0f} – {top:,.0f}", f"{(ref / px - 1) * 100:+.1f}%"])
        if not zs:
            rows.append([side, "Tidak ada zona valid", "-", "-"])
    return rows


# ── Build ────────────────────────────────────────────────────────
def build(content_path: Path) -> Path:
    c = json.loads(content_path.read_text())
    out = ROOT / "reports" / "pdf" / f"{c['date']}.pdf"
    out.parent.mkdir(parents=True, exist_ok=True)

    d1 = load_ohlcv("BTCUSDT", "1D")
    h4 = load_ohlcv("BTCUSDT", "4h")
    lv_d1, lv_h4 = smc_levels(d1.tail(120)), smc_levels(h4)

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title=f"Geo-Macro Brief {c['date']}", author="Daily Geo-Macro Brief")
    W = doc.width
    st = []
    gen = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    st += [Paragraph(f"GEO-MACRO DAILY BRIEF  ·  {c['date']}", S["title"]),
           Paragraph(f"Geopolitik &amp; geo-ekonomi global → dampak ke watchlist (BTC, ETH, HYPE, LIGHTER, DXY, USDIDR, XAUUSD) · fokus worst case · dibuat {gen} · {c.get('data_note', '')}", S["sub"]),
           Spacer(1, 6)]

    # Risk banner
    banner = Table([[Paragraph(f"RISK REGIME: {c['risk_regime']}", S["box"])]], colWidths=[W])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), RED), ("TOPPADDING", (0, 0), (-1, -1), 5),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    st += [banner, Spacer(1, 5), Paragraph(c["headline"], S["body"])]

    st.append(Paragraph("1. Snapshot Pasar", S["h1"]))
    rows = [["Aset", "Harga", "1D", "1W", "1M", "Catatan"]] + [
        [m["asset"], m["price"], m["d1"], m["w1"], m["m1"], m.get("note", "")] for m in c["market"]]
    st.append(table(rows, [W * x for x in (.13, .13, .09, .09, .09, .47)]))

    if "sentiment" in c:
        se = c["sentiment"]
        st.append(Paragraph("1b. Sentimen Market Crypto (CoinMarketCap)", S["h1"]))
        fg = se["fear_greed"]
        col = RED if fg["index"] < 25 else (GREEN if fg["index"] > 60 else GREY)
        big = ParagraphStyle("big", parent=S["box"], fontSize=26, leading=32)
        box = Table([[[Paragraph("FEAR &amp; GREED", S["box"]), Paragraph(str(fg["index"]), big), Paragraph(fg["label"], S["box"])],
                      table([["Metrik", "Nilai"]] + [[k, v] for k, v in se["metrics"]], [W * .30, W * .40])]],
                    colWidths=[W * .28, W * .72])
        box.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), col), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                 ("TOPPADDING", (0, 0), (0, 0), 8), ("BOTTOMPADDING", (0, 0), (0, 0), 8)]))
        st += [box, Spacer(1, 3), Paragraph(se["trend"], S["small"]), Paragraph(se["read"], S["body"])]

    if "derivatives" in c:
        st.append(Paragraph("1c. Derivatif per Ticker (CoinMarketCap · perp 4h, 7 hari)", S["h1"]))
        rows = [["Ticker", "Funding", "Regime", "OI 7d", "OI/MCap", "Liq heatmap atas / bawah", "Bacaan"]] + [
            [d["ticker"], d["funding"], d["regime"], d["oi7d"], d["oi_mcap"], d["liq"], d["read"]] for d in c["derivatives"]]
        st.append(table(rows, [W * x for x in (.11, .11, .10, .08, .09, .19, .32)]))

    for key, label in (("geopolitics", "2. Geopolitik"), ("geoeconomics", "3. Geo-ekonomi")):
        st.append(Paragraph(label, S["h1"]))
        rows = [["Isu", "Perkembangan terbaru", "Dampak ke watchlist"]] + [
            [f"<b>{n['title']}</b>", n["detail"], n["impact"]] for n in c[key]]
        st.append(table(rows, [W * .18, W * .52, W * .30]))

    st.append(Paragraph("4. Skenario Worst Case (2–6 minggu)", S["h1"]))
    st.append(Paragraph("Probabilitas = estimasi subjektif analis, bukan model kuantitatif.", S["small"]))
    rows = [["Skenario", "Prob.", "Pemicu", "USD (DXY · USDIDR)", "BTC / ETH", "HYPE / LIGHTER · XAU"]] + [
        [f"<b>{w['scenario']}</b>", w["prob"], w["trigger"], w["usd"], w["btc"], w.get("alts", "")] for w in c["worst_case"]]
    st.append(table(rows, [W * x for x in (.14, .07, .22, .18, .19, .20)], header_bg=RED))

    st.append(Paragraph("5. Benang Merah: BTC vs USD", S["h1"]))
    st += [Paragraph(p, S["body"]) for p in c["btc_usd_link"]]

    if "smc_table" in c:
        st.append(Paragraph("6. Peta SMC Watchlist · D1 / H4 / M30", S["h1"]))
        rows = [["Ticker", "D1 (bias)", "H4", "M30 (eksekusi)", "Alignment", "OB/FVG terdekat atas · bawah"]] + [
            [r["ticker"], r["d1"], r["h4"], r["m30"], r["align"], r["zones"]] for r in c["smc_table"]]
        st.append(table(rows, [W * x for x in (.10, .17, .16, .17, .14, .26)]))
        st.append(Paragraph("Struktur &amp; zona dihitung utils/smc_detector.py dari OHLCV TradingView (bar yang belum close dibuang). "
                            "Bila detector kekurangan swing atau tertinggal (lag 5 bar), bacaan manual ditandai *.", S["small"]))
    st.append(Paragraph("6b. Chart SMC BTC (D1 &amp; H4)", S["h1"]))
    for name, df, lv in (("D1", d1.tail(90), lv_d1), ("H4", h4.tail(90), lv_h4)):
        s = lv["structure"]
        lbl = (f"{s['structure']} · bias {s['bias']}" if s["structure"] != "INSUFFICIENT DATA"
               else "swing belum cukup untuk detector — lihat tabel SMC")
        st.append(KeepTogether([
            candle_chart(df, lv, f"BTCUSDT {name} · {lbl}"),
            table(zone_rows(lv), [W * .2, W * .25, W * .35, W * .2]), Spacer(1, 6)]))
    st.append(Paragraph(
        "Zona dari utils/smc_detector.py (OHLCV TradingView BINANCE:BTCUSDT). Validitas OB/FVG detector hanya dicek terhadap harga "
        "terakhir, bukan riwayat sentuhan — konfirmasi manual di chart sebelum entry.", S["small"]))
    st += [Paragraph(p, S["body"]) for p in c["smc_note"]]

    st.append(Paragraph("7. Kalender & Level Pemicu", S["h1"]))
    rows = [["Tanggal", "Event", "Kenapa penting"]] + [[e["date"], e["event"], e["why"]] for e in c["calendar"]]
    st.append(table(rows, [W * .14, W * .36, W * .50]))

    st.append(Paragraph("Sumber", S["h1"]))
    st += [Paragraph(f"• {u}", S["small"]) for u in c["sources"]]
    st += [Spacer(1, 6), Paragraph(
        "Disclaimer: riset & edukasi, bukan nasihat keuangan. Berita dari newsletter/blog ditandai bila belum "
        "terkonfirmasi kantor berita. DYOR & kelola risiko.", S["small"])]

    doc.build(st)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
