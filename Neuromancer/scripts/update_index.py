#!/usr/bin/env python3
"""
update_index.py — Regenera las secciones dinámicas del index de Neuromancer.

Lee Neuromancer/portfolios.json (generado por sync_portfolios.py desde Obsidian)
y escanea los reportes existentes (neuromancer-council-*.html) para extraer
veredicto + convicción por ticker. Regenera en index.html:
  - stats (<!-- STATS:START --> ... <!-- STATS:END -->)
  - dashboard de portafolios (<!-- DASHBOARD:START --> ... <!-- DASHBOARD:END -->)
  - sección "fuera de portafolio" (<!-- MISC:START --> ... <!-- MISC:END -->)

Este es el paso final del pipeline batch: sync_portfolios.py -> [análisis batch]
-> update_index.py -> deploy.
"""
import json, os, re, glob

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "portfolios.json")
INDEX = os.path.join(BASE, "index.html")

ACCENT = {"Manhattan Project 2.0": "var(--cyan)", "1 Million stack": "var(--magenta)",
          "Emerging": "var(--amber)", "Quantum": "var(--violet)"}

def scan_reports():
    """ticker -> {url, verdict, conv} — con alias para nombres de archivo no-ticker"""
    ALIASES = {"palantir": "PLTR", "enha": "ENHA"}
    out = {}
    for f in glob.glob(os.path.join(BASE, "neuromancer-council-*.html")):
        stem = os.path.basename(f).replace("neuromancer-council-", "").replace(".html", "")
        t = ALIASES.get(stem, stem.upper())
        html = open(f, encoding="utf-8").read()
        vm = re.search(r'class="verdict-badge (buy|hold|avoid)">(\w+)<', html)
        cm = re.search(r'Convicción del Consejo: <b>(\d+)/10</b>', html)
        out[t] = {"url": os.path.basename(f),
                  "verdict": vm.group(1) if vm else "hold",
                  "conv": int(cm.group(1)) if cm else 0}
    return out

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
    reports = scan_reports()

    all_listed = sorted({t for p in portfolios for t in p["tickers"]})
    analyzed_all = set(reports)
    analyzed_in_pf = {t for t in all_listed if t in reports}
    pending = [t for t in all_listed if t not in reports]
    outside = sorted(analyzed_all - set(all_listed))   # analizados fuera de listas

    # ── stats ──
    stats = [
        ("4", "Portafolios", ""), (str(len(all_listed)), "Tickers en listas", ""),
        (str(len(analyzed_all)), "Analizados", ""), (str(len(pending)), "Pendientes", ""),
        (str(sum(1 for r in reports.values() if r["verdict"] == "buy")), "Buy", "buy"),
        (str(sum(1 for r in reports.values() if r["verdict"] == "hold")), "Hold", "hold"),
        (str(sum(1 for r in reports.values() if r["verdict"] == "avoid")), "Avoid", "avoid"),
    ]
    stats_html = "\n".join(
        f'    <div class="stat{(" " + cls) if cls else ""}"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for v, k, cls in stats)

    # ── dashboard ──
    cards = []
    for p in portfolios:
        acc = ACCENT.get(p["name"], "var(--cyan)")
        n = len(p["tickers"]); done = sum(1 for t in p["tickers"] if t in reports)
        pct = round(100 * done / n) if n else 0
        desc = re.sub(r"\*\*", "", p["description"])
        cards.append(f"""    <div class="pf-card" style="--accent:{acc};">
      <div class="pf-name">{p["name"]}</div>
      <div class="pf-desc">{desc}</div>
      <div class="pf-progress"><span>{done}/{n} analizados</span><div class="track"><i style="width:{pct}%"></i></div></div>
      <div class="pf-chips">{chips_for(p["tickers"], reports)}</div>
    </div>""")
    dash_html = ('  <section class="dash">\n'
                 '    <div class="sec-title"><span class="n">STACK</span> Portafolios en vigilancia</div>\n'
                 '    <div class="dash-grid">\n' + "\n".join(cards) + "\n    </div>\n  </section>")

    # ── fuera de portafolio ──
    if outside:
        misc_html = ('  <section class="misc">\n'
                     '    <div class="sec-title"><span class="n">EXT</span> Fuera de portafolio (analizados individualmente)</div>\n'
                     '    <div class="pf-chips">' + chips_for(outside, reports) + '</div>\n  </section>')
    else:
        misc_html = ""

    # ── reemplazar entre markers ──
    html = open(INDEX, encoding="utf-8").read()
    def between(html, start, end, new):
        s = html.index(start) + len(start)
        e = html.index(end)
        return html[:s] + "\n" + new + "\n" + html[e:]
    html = between(html, "<!-- STATS:START -->", "<!-- STATS:END -->", stats_html)
    html = between(html, "<!-- DASHBOARD:START -->", "<!-- DASHBOARD:END -->", dash_html)
    html = between(html, "<!-- MISC:START -->", "<!-- MISC:END -->", misc_html)
    open(INDEX, "w", encoding="utf-8").write(html)

    print(f"✔ index regenerado: {len(portfolios)} portafolios, {len(all_listed)} tickers listados")
    print(f"  analizados: {len(analyzed_all)} (en portafolios: {len(analyzed_in_pf)}, fuera: {len(outside)})")
    print(f"  pendientes: {len(pending)} -> {', '.join(pending)}")
    print(f"  fuera de portafolio: {', '.join(outside) if outside else '(ninguno)'}")

if __name__ == "__main__":
    main()
