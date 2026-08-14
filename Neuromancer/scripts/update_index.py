#!/usr/bin/env python3
"""
update_index.py — Regenera las secciones dinámicas del index de Neuromancer.

Lee Neuromancer/portfolios.json (generado por sync_portfolios.py desde Obsidian)
y escanea los reportes existentes (neuromancer-council-*.html) para extraer
veredicto + convicción + fecha por ticker. Regenera en index.html:
  - stats (<!-- STATS:START --> ... <!-- STATS:END -->)
  - dashboard de portafolios (<!-- DASHBOARD:START --> ... <!-- DASHBOARD:END -->)
  - sección "Individual Equities" (<!-- MISC:START --> ... <!-- MISC:END -->)

Reglas:
  - Reportes con más de FRESH_DAYS (60) días se consideran caducos: no generan
    chip de análisis (el ticker vuelve a "pendiente") y se listan como STALE
    para `git rm` (el usuario pidió eliminar de GitHub los análisis > 60 días).
  - "Individual Equities" solo muestra analizados de los últimos 60 días que NO
    estén en ningún portafolio.

Pipeline batch: sync_portfolios.py -> [análisis batch] -> update_index.py -> deploy.
"""
import json, os, re, glob, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "portfolios.json")
INDEX = os.path.join(BASE, "index.html")
FRESH_DAYS = 60
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]

ACCENT = {"Manhattan Project 2.0": "var(--cyan)", "Arc Reactor": "var(--magenta)",
          "Emerging players": "var(--amber)", "Quantum Gate": "var(--violet)",
          "Rare Earth": "var(--green)", "The Bunker": "#8b9bb4", "Robotics ExoStack": "#ff7847"}

# ── Lo notable de cada portafolio (resumen del engine, mostrado en su card) ──
NOTABLES = {
    "Manhattan Project 2.0": "El basket más dividido: minerales con fricción máxima (Buffett AVOID 9 vs Cathie BUY 7 en LAC); los 3 BUY tienen margen (fwd ≤27x) — en los 7 HOLD la tesis ganó, el precio llegó primero.",
    "Arc Reactor": "El corazón de la IA: 8 BUY (semis, plataformas, nuclear) incluyendo el primer voto unánime 5-0 del engine (CEG); PLTR (AVOID endurecido a 4-1 tras el +40% sin cambio fundamental) y NNE, los únicos AVOID.",
    "Emerging players": "El portafolio más cauto: 0 BUY — tesis reales con PEG >2 y precios adelantados; Cathie compró sola en 4 de 6 (BE, VRT, ARM, OKLO).",
    "Quantum Gate": "El rechazo más duro del engine: 3-4 AVOID por ticker a 67x-618x ventas sin earnings; solo Cathie compra las S-curves.",
    "Rare Earth": "El portafolio del reshoring: 2 BUY (NEO — el único con earnings reales, PEG ~0.7; UUUU — la doble opcionalidad uranio+NdPr) y 8 HOLD; la mayoría es opcionalidad pre-revenue sobre permiso y ejecución.",
    "The Bunker": "El refugio anti-superbubble (Grantham/GMO): 1 BUY (VXUS — el 60% no-US de Dalio) y 7 HOLD; vehículos impecables que cumplen su rol defensivo — diversificación barata, no alpha.",
    "Robotics ExoStack": "La cadena del video de Elon: 0 BUY, 8 HOLD y 2 AVOID (ARBE y RR — microcaps pre-revenue a P/S 50-75x). El engine reconoce los moats (HD/NBT actuadores, TXN fabs propias, AVAV defensa) pero el precio llegó primero: HD a 92x vs NBT a 23x, el mismo cuello de botella a múltiplos opuestos.",
}

def fecha(ts):
    t = time.localtime(ts)
    return f"{t.tm_mday:02d} {MESES[t.tm_mon-1]} {t.tm_year}"

def scan_reports():
    """-> (fresh: ticker->info, stale: [ticker]) con filtro de 60 días.
    La fecha del análisis se parsea de 'Sesión: DD mmm AAAA' en la página;
    si no está, se usa el mtime del archivo."""
    ALIASES = {"palantir": "PLTR", "enha": "ENHA", "screening-rare-earths": "RARE-EARTHS"}
    MES = {m: i + 1 for i, m in enumerate(MESES)}
    all_r = {}
    now = time.time()
    for f in glob.glob(os.path.join(BASE, "neuromancer-council-*.html")):
        stem = os.path.basename(f).replace("neuromancer-council-", "").replace(".html", "")
        t = ALIASES.get(stem, stem.upper())
        html = open(f, encoding="utf-8").read()
        vm = re.search(r'class="verdict-badge (buy|hold|avoid)">(\w+)<', html)
        cm = re.search(r'Convicción del Consejo: <b>(\d+)/10</b>', html)
        dm = re.search(r"Sesi[oó]n:\s*(?:<[^>]+>)?\s*(\d{2})\s+(\w{3})\s+(\d{4})", html)
        if dm and dm.group(2).lower() in MES:
            ts = time.mktime((int(dm.group(3)), MES[dm.group(2).lower()], int(dm.group(1)), 0, 0, 0, 0, 0, -1))
        else:
            ts = os.path.getmtime(f)
        all_r[t] = {"url": os.path.basename(f),
                    "verdict": vm.group(1) if vm else "hold",
                    "conv": int(cm.group(1)) if cm else 0,
                    "mtime": ts}
    fresh = {t: r for t, r in all_r.items() if now - r["mtime"] <= FRESH_DAYS * 86400}
    stale = sorted(t for t, r in all_r.items() if now - r["mtime"] > FRESH_DAYS * 86400)
    return fresh, stale

def metrics_for(tickers, fresh):
    """β = beta promedio (riesgo de mercado, betas reales de stockanalysis).
    α = convicción neta del engine: promedio de convicción × (+1 BUY, 0 HOLD, −1 AVOID), rango −10..+10."""
    betas = json.load(open(os.path.join(BASE, "scripts", "betas.json"), encoding="utf-8"))
    bs = [betas[t] for t in tickers if betas.get(t) is not None]
    beta = sum(bs) / len(bs) if len(bs) >= 3 else None  # None = sin datos suficientes (ETFs)
    sign = {"buy": 1, "hold": 0, "avoid": -1}
    scores = [sign.get(fresh[t]["verdict"], 0) * fresh[t]["conv"] for t in tickers if t in fresh]
    alpha = sum(scores) / len(scores) if scores else None  # None = sin análisis aún
    return beta, alpha


def scatter_svg(portfolios, fresh):
    """Mapa β×α de los portafolios (SVG inline): riesgo de mercado vs convicción del engine.
    Referencia: S&P 500 = β 1.0 · neutro = α 0. Cuadrantes = la matriz de la guía."""
    accs = []
    for p in portfolios:
        beta, alpha = metrics_for(p["tickers"], fresh)
        if beta is None or alpha is None:
            continue
        accs.append((p["name"], beta, alpha, ACCENT.get(p["name"], "#00e5ff")))
    W, H = 900, 640
    ML, MT, MR, MB = 80, 70, 50, 66
    PW, PH = W - ML - MR, H - MT - MB
    B0, B1, A0, A1 = 0.2, 2.6, -2.5, 2.5
    def X(b): return ML + (b - B0) / (B1 - B0) * PW
    def Y(a): return MT + (A1 - a) / (A1 - A0) * PH

    out = []
    out.append(f'<svg class="map-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Mapa de riesgo y convicción de los portafolios">')

    # cuadrantes (matriz de la guía)
    q = [
        (X(0.2), Y(2.5), X(1.0), Y(0),   "rgba(0,255,157,.045)", "CALIDAD / REFUGIO",  "#00ff9d"),
        (X(1.0), Y(2.5), X(2.6), Y(0),   "rgba(0,229,255,.05)",  "CONVICCIÓN CON RIESGO", "#00e5ff"),
        (X(1.0), Y(0),   X(2.6), Y(-2.5),"rgba(255,46,151,.06)", "RIESGO SIN RETORNO", "#ff2e97"),
        (X(0.2), Y(0),   X(1.0), Y(-2.5),"rgba(139,147,184,.05)","SIN CONVICCIÓN",    "#8b93b8"),
    ]
    for x1, y1, x2, y2, fill, lbl, col in q:
        out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" height="{y2-y1:.1f}" fill="{fill}"/>')
        out.append(f'<text x="{x1+10:.1f}" y="{y2-12:.1f}" font-family="JetBrains Mono,monospace" font-size="9" letter-spacing=".14em" fill="{col}" opacity=".55">{lbl}</text>')

    # grid + ejes
    for b in (0.5, 1.0, 1.5, 2.0, 2.5):
        out.append(f'<line x1="{X(b):.1f}" y1="{MT:.1f}" x2="{X(b):.1f}" y2="{MT+PH:.1f}" stroke="rgba(255,255,255,.06)" stroke-width="1"/>')
        out.append(f'<text x="{X(b):.1f}" y="{MT+PH+18:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#8b93b8" text-anchor="middle">{b:.1f}</text>')
    for a in (-2, -1, 1, 2):
        out.append(f'<line x1="{ML:.1f}" y1="{Y(a):.1f}" x2="{ML+PW:.1f}" y2="{Y(a):.1f}" stroke="rgba(255,255,255,.06)" stroke-width="1"/>')
        out.append(f'<text x="{ML-10:.1f}" y="{Y(a)+3:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#8b93b8" text-anchor="end">{a:+.0f}</text>')

    # referencias: β=1.0 (el mercado) y α=0 (neutro)
    out.append(f'<line x1="{X(1.0):.1f}" y1="{MT:.1f}" x2="{X(1.0):.1f}" y2="{MT+PH:.1f}" stroke="rgba(255,46,151,.5)" stroke-width="1.4" stroke-dasharray="6 5"/>')
    out.append(f'<text x="{X(1.0)-6:.1f}" y="{MT+14:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#ff2e97" text-anchor="end" opacity=".9">S&amp;P 500 · β 1.0</text>')
    out.append(f'<line x1="{ML:.1f}" y1="{Y(0):.1f}" x2="{ML+PW:.1f}" y2="{Y(0):.1f}" stroke="rgba(255,255,255,.28)" stroke-width="1.2"/>')
    out.append(f'<text x="{ML+PW-8:.1f}" y="{Y(0)-8:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#c6cbe8" text-anchor="end">α 0 · neutro</text>')

    # ejes con títulos
    out.append(f'<text x="{ML+PW/2:.1f}" y="{H-20:.1f}" font-family="JetBrains Mono,monospace" font-size="11" letter-spacing=".2em" fill="#8b93b8" text-anchor="middle">β · RIESGO DE MERCADO →</text>')
    out.append(f'<text x="20" y="{MT+PH/2:.1f}" font-family="JetBrains Mono,monospace" font-size="11" letter-spacing=".2em" fill="#8b93b8" text-anchor="middle" transform="rotate(-90 20 {MT+PH/2:.1f})">α · CONVICCIÓN NETA →</text>')

    # puntos por portafolio
    for name, beta, alpha, col in accs:
        cx, cy = X(beta), Y(alpha)
        tip = f"{name} · β {beta:.2f} · α {alpha:+.1f}"
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="15" fill="none" stroke="{col}" stroke-width="1" opacity=".22"/>')
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="6.5" fill="{col}" stroke="#06070f" stroke-width="1.6"><title>{tip}</title></circle>')
        anchor = "start"; lx = cx + 14
        if cx > ML + PW - 150:
            anchor = "end"; lx = cx - 14
        out.append(f'<text x="{lx:.1f}" y="{cy+3:.1f}" font-family="JetBrains Mono,monospace" font-size="10.5" font-weight="600" fill="{col}" text-anchor="{anchor}">{name}</text>')
    out.append('</svg>')
    return "\n".join(out)


def scatter_tickers_svg(portfolios, fresh):
    """Mapa β×α por TICKER: cada análisis del archive con beta disponible.
    α individual = convicción × signo del veredicto (−10..+10); tamaño = convicción; color = portafolio."""
    betas = json.load(open(os.path.join(BASE, "scripts", "betas.json"), encoding="utf-8"))
    sign = {"buy": 1, "hold": 0, "avoid": -1}
    pcolor = {}
    for p in portfolios:
        acc = ACCENT.get(p["name"], "#00e5ff")
        for t in p["tickers"]:
            pcolor.setdefault(t, acc)
    pts = []
    for t, r in sorted(fresh.items()):
        b = betas.get(t)
        if b is None:
            continue
        a = sign.get(r["verdict"], 0) * r["conv"]
        pts.append((t, b, a, r["conv"], r["verdict"], pcolor.get(t, "#8b93b8")))
    if not pts:
        return ""
    W, H = 900, 720
    ML, MT, MR, MB = 80, 70, 50, 66
    PW, PH = W - ML - MR, H - MT - MB
    B0, B1, A0, A1 = 0.2, 2.6, -10, 10
    def X(b): return ML + (b - B0) / (B1 - B0) * PW
    def Y(a): return MT + (A1 - a) / (A1 - A0) * PH

    out = []
    out.append(f'<svg class="map-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Mapa de riesgo y convicción por ticker">')

    # cuadrantes
    q = [
        (X(0.2), Y(10), X(1.0), Y(0),    "rgba(0,255,157,.045)", "CALIDAD / REFUGIO",      "#00ff9d"),
        (X(1.0), Y(10), X(2.6), Y(0),    "rgba(0,229,255,.05)",  "CONVICCIÓN CON RIESGO", "#00e5ff"),
        (X(1.0), Y(0),   X(2.6), Y(-10), "rgba(255,46,151,.06)", "RIESGO SIN RETORNO",    "#ff2e97"),
        (X(0.2), Y(0),   X(1.0), Y(-10), "rgba(139,147,184,.05)","SIN CONVICCIÓN",        "#8b93b8"),
    ]
    for x1, y1, x2, y2, fill, lbl, col in q:
        out.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" height="{y2-y1:.1f}" fill="{fill}"/>')
        out.append(f'<text x="{x1+10:.1f}" y="{y2-12:.1f}" font-family="JetBrains Mono,monospace" font-size="9" letter-spacing=".14em" fill="{col}" opacity=".55">{lbl}</text>')

    # grid + ticks
    for b in (0.5, 1.0, 1.5, 2.0, 2.5):
        out.append(f'<line x1="{X(b):.1f}" y1="{MT:.1f}" x2="{X(b):.1f}" y2="{MT+PH:.1f}" stroke="rgba(255,255,255,.06)" stroke-width="1"/>')
        out.append(f'<text x="{X(b):.1f}" y="{MT+PH+18:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#8b93b8" text-anchor="middle">{b:.1f}</text>')
    for a in (-8, -4, 4, 8):
        out.append(f'<line x1="{ML:.1f}" y1="{Y(a):.1f}" x2="{ML+PW:.1f}" y2="{Y(a):.1f}" stroke="rgba(255,255,255,.06)" stroke-width="1"/>')
        out.append(f'<text x="{ML-10:.1f}" y="{Y(a)+3:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#8b93b8" text-anchor="end">{a:+.0f}</text>')

    # referencias
    out.append(f'<line x1="{X(1.0):.1f}" y1="{MT:.1f}" x2="{X(1.0):.1f}" y2="{MT+PH:.1f}" stroke="rgba(255,46,151,.5)" stroke-width="1.4" stroke-dasharray="6 5"/>')
    out.append(f'<text x="{X(1.0)-6:.1f}" y="{MT+14:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#ff2e97" text-anchor="end" opacity=".9">S&amp;P 500 · β 1.0</text>')
    out.append(f'<line x1="{ML:.1f}" y1="{Y(0):.1f}" x2="{ML+PW:.1f}" y2="{Y(0):.1f}" stroke="rgba(255,255,255,.28)" stroke-width="1.2"/>')
    out.append(f'<text x="{ML+PW-8:.1f}" y="{Y(0)-8:.1f}" font-family="JetBrains Mono,monospace" font-size="10" fill="#c6cbe8" text-anchor="end">α 0 · neutro (HOLD)</text>')

    # ejes
    out.append(f'<text x="{ML+PW/2:.1f}" y="{H-20:.1f}" font-family="JetBrains Mono,monospace" font-size="11" letter-spacing=".2em" fill="#8b93b8" text-anchor="middle">β · RIESGO DE MERCADO →</text>')
    out.append(f'<text x="20" y="{MT+PH/2:.1f}" font-family="JetBrains Mono,monospace" font-size="11" letter-spacing=".2em" fill="#8b93b8" text-anchor="middle" transform="rotate(-90 20 {MT+PH/2:.1f})">α · CONVICCIÓN (por ticker) →</text>')

    # puntos: tamaño = convicción, color = portafolio
    for t, b, a, conv, verdict, col in pts:
        cx, cy = X(b), Y(a)
        r = 3.0 + conv * 0.28
        v = {"buy": "BUY", "hold": "HOLD", "avoid": "AVOID"}.get(verdict, verdict.upper())
        tip = f"{t} · β {b:.2f} · α {a:+.0f} · {v} {conv}/10"
        out.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}" fill-opacity=".78" stroke="#06070f" stroke-width="1"><title>{tip}</title></circle>')
    out.append('</svg>')
    return "\n".join(out)

def chips_for(tickers, reports):
    chips = []
    for t in tickers:
        r = reports.get(t)
        if r:
            chips.append(f'<a class="pf-chip {r["verdict"]}" href="{r["url"]}">'
                         f'<span class="dot"></span>{t}<span class="pct">{r["conv"]}/10</span></a>')
        else:
            chips.append(f'<span class="pf-chip pending"><span class="dot" style="background:var(--border);"></span>{t}</span>')
    return " ".join(chips)

def main():
    manifest = json.load(open(MANIFEST, encoding="utf-8"))
    portfolios = manifest["portfolios"]
    fresh, stale = scan_reports()

    all_listed = sorted({t for p in portfolios for t in p["tickers"]})
    pending = [t for t in all_listed if t not in fresh]
    outside = sorted(set(fresh) - set(all_listed))

    # ── stats (una palabra, cuadros) ──
    stats = [
        (str(len(portfolios)), "Stack", ""), (str(len(all_listed)), "Tickers", ""),
        (str(len(fresh)), "Análisis", ""), (str(len(pending)), "Pendientes", ""),
        (str(sum(1 for r in fresh.values() if r["verdict"] == "buy")), "Buy", "buy"),
        (str(sum(1 for r in fresh.values() if r["verdict"] == "hold")), "Hold", "hold"),
        (str(sum(1 for r in fresh.values() if r["verdict"] == "avoid")), "Avoid", "avoid"),
    ]
    stats_html = '  <div class="stats">\n' + "\n".join(
        f'    <div class="stat{(" " + cls) if cls else ""}"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for v, k, cls in stats) + '\n  </div>'

    # ── dashboard: panel grande ──
    cards = []
    for p in portfolios:
        acc = ACCENT.get(p["name"], "var(--cyan)")
        n = len(p["tickers"]); done = sum(1 for t in p["tickers"] if t in fresh)
        pct = round(100 * done / n) if n else 0
        desc = re.sub(r"\*\*", "", p["description"])
        mtimes = [fresh[t]["mtime"] for t in p["tickers"] if t in fresh]
        upd = fecha(max(mtimes)) if mtimes else "—"
        beta, alpha = metrics_for(p["tickers"], fresh)
        beta_str = f"{beta:.2f}" if beta is not None else "—"
        alpha_str = f"{alpha:+.1f}" if alpha is not None else "—"
        alpha_cls = "pos" if (alpha or 0) > 0.3 else ("neg" if (alpha or 0) < -0.3 else "zero")
        cards.append(f"""    <div class="pf-card" style="--accent:{acc};">
      <div class="pf-name">{p["name"]}</div>
      <div class="pf-desc">{desc}</div>
      <div class="pf-progress"><span>{done}/{n} analizados</span><div class="track"><i style="width:{pct}%"></i></div></div>
      <div class="pf-metrics" title="β = beta promedio de los tickers (riesgo de mercado) · α = convicción neta del engine (BUY + / HOLD 0 / AVOID −), escala −10 a +10">
        <span class="m"><span class="k">β</span><b>{beta_str}</b></span>
        <span class="m"><span class="k">α</span><b class="{alpha_cls}">{alpha_str}</b></span>
        <span class="hint">beta = riesgo · alpha = convicción neta</span>
      </div>
      <div class="pf-chips">{chips_for(p["tickers"], fresh)}</div>
      <div class="pf-note">◈ {NOTABLES.get(p["name"], "")}</div>
      <div class="pf-date">actualizado {upd}</div>
    </div>""")
    dash_html = ('  <section class="dash">\n'
                 '    <div class="sec-title"><span class="n">PF</span> Portfolio architecture</div>\n'
                 '    <div class="dash-grid">\n' + "\n".join(cards) + "\n    </div>\n  </section>")

    # ── MISC: vacío — la cronología "Individual Equities" es manual (solo
    # análisis ≤60d fuera de portafolio; los de portafolio viven en el dashboard).
    misc_html = ""

    # ── reemplazar entre markers ──
    html = open(INDEX, encoding="utf-8").read()
    def between(html, start, end, new):
        s = html.index(start) + len(start)
        e = html.index(end)
        return html[:s] + "\n" + new + "\n" + html[e:]
    html = between(html, "<!-- STATS:START -->", "<!-- STATS:END -->", stats_html)
    html = between(html, "<!-- DASHBOARD:START -->", "<!-- DASHBOARD:END -->", dash_html)
    map_html = scatter_svg(portfolios, fresh)
    map_html = ('  <section class="map-section" id="mapa">\n'
                '    <div class="sec-title"><span class="n">MAP</span> Portfolio map · β × α</div>\n'
                '    <p class="map-sub">Cada punto es un portafolio: <b>β</b> (riesgo de mercado, eje X) contra <b>α</b> (convicción neta del engine, eje Y). Referencia: <b>S&amp;P 500 = β 1.0</b> · neutro = α 0 — los cuadrantes son la matriz de la <a href="alpha-beta.html">guía</a>. Pasa el cursor sobre cada punto.</p>\n'
                + map_html + '\n'
                '    <div class="map-cta">\n'
                '      <a class="guide-btn" href="alpha-beta.html">\n'
                '        <span class="gb-icon">αβ</span>\n'
                '        <span class="gb-txt">\n'
                '          <span class="gb-title">Guía: cómo leer β y α</span>\n'
                '          <span class="gb-sub">riesgo y convicción del engine</span>\n'
                '        </span>\n'
                '        <span class="gb-arr">→</span>\n'
                '      </a>\n'
                '    </div>\n'
                '  </section>')
    html = between(html, "<!-- MAP:START -->", "<!-- MAP:END -->", map_html)

    tk_html = scatter_tickers_svg(portfolios, fresh)
    tk_html = ('  <section class="map-section" id="mapa-tickers">\n'
               '    <div class="sec-title"><span class="n">TK</span> Ticker map · β × α</div>\n'
               '    <p class="map-sub">El mismo mapa, a nivel de <b>ticker individual</b>: cada punto es un análisis del archive con beta disponible — <b>α individual = convicción × signo del veredicto</b> (BUY + / HOLD 0 / AVOID −, escala −10..+10). El <b>tamaño del punto = convicción</b> y el <b>color = portafolio</b>. Los HOLD viven sobre la línea α 0: el engine está neutro en la mayoría. Pasa el cursor sobre cada punto.</p>\n'
               + tk_html + '\n'
               '    <div class="map-legend"><span><i style="background:#00e5ff"></i>Color = portafolio</span><span>● Tamaño = convicción 1–10</span><span>HOLD → α 0</span></div>\n'
               '  </section>')
    html = between(html, "<!-- TICKERS:START -->", "<!-- TICKERS:END -->", tk_html)
    html = between(html, "<!-- MISC:START -->", "<!-- MISC:END -->", misc_html)
    open(INDEX, "w", encoding="utf-8").write(html)

    print(f"✔ index regenerado: {len(portfolios)} portafolios, {len(all_listed)} tickers listados")
    print(f"  analizados frescos (≤{FRESH_DAYS}d): {len(fresh)} | en portafolios: {len(set(fresh) & set(all_listed))} | fuera: {len(outside)}")
    print(f"  pendientes: {len(pending)}")
    print(f"  individual equities: {', '.join(outside) if outside else '(ninguno)'}")
    if stale:
        print(f"  ⚠ STALE ({len(stale)} análisis > {FRESH_DAYS} días, eliminar de GitHub):")
        for t in stale:
            print(f"     git rm 'Neuromancer/{fresh.get(t, {}).get('url', f'neuromancer-council-{t.lower()}.html')}'")
    else:
        print("  (sin análisis stale — nada que purgar)")

if __name__ == "__main__":
    main()
