#!/usr/bin/env python3
"""Entry Zones del Neuromancer engine.

Zona de entrada = intersección de 3 capas:
  1) VALORACIÓN CON MARGEN: precio donde el fwd P/E toca el múltiplo objetivo del tipo de negocio
     (compounder ~24x · growth ~28x · cyclical/pre-revenue: sin ancla de P/E).
  2) SOPORTE TÉCNICO: mínimo de 52 semanas (stockanalysis) como suelo estructural.
  3) GATILLO FUNDAMENTAL: el umbral de 'QUÉ CAMBIARÍA TU OPINIÓN' del propio reporte (ancla si existe).

Reglas:
  - Solo tickers con veredicto BUY/HOLD (los AVOID no tienen zona de entrada).
  - Vehículos indexados/temáticos (ETFs, ARKK, SPCX, RARE-EARTHS) → sin zona.
  - Si hay umbral del reporte → zona = umbral ± 7%.
  - Si no → zona = [max(52w low, margen×0.90), margen], con suelo < techo; si no hay margen ni umbral → sin zona.
  - Estado: DESCUENTO (< suelo) · ZONA ACTIVA (dentro) · ESPERAR (> techo). Sobre el snapshot del análisis.

Salida: scripts/entry_zones.json  ·  Caché de 52w: scripts/entry_zones_cache.json
"""
import re, os, json, glob, urllib.request, time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "scripts", "entry_zones.json")
CACHE = os.path.join(BASE, "scripts", "entry_zones_cache.json")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# ── clasificación por tipo de negocio (ancla de valoración) ──
COMPOUNDER = {"MSFT", "GOOGL", "META", "TXN", "GE", "AVGO", "CEG"}
CYCLICAL = {"MU", "AA", "STM", "CCJ", "LYC", "ILU", "NBT", "MP"}
PREREVENUE = {"ARBE", "RR", "NB", "AREC", "ARU", "TMQ", "LAC", "USAR", "IONQ", "QBTS", "POET", "OKLO"}
MULT = {"compounder": 24.0, "growth": 28.0, "cyclical": None, "prerevenue": None}
NO_ZONA = {"VXUS", "VWO", "GLD", "SLV", "VNQ", "BND", "TIP", "EMB", "ARKK", "SPCX", "RARE-EARTHS", "SCREENING-RARE-EARTHS", "ENHA", "NNE", "RGTI", "PLTR"}

# ── URLs de stockanalysis para no-EEUU + moneda local (el umbral del reporte
#    se interpreta en la misma moneda del precio del fetch) ──
QUOTE = {"HD": "quote/tyo/6324", "NBT": "quote/tyo/6268", "LYC": "quote/asx/lyc",
         "ILU": "quote/asx/ilu", "ARU": "quote/asx/aru", "NEO": "quote/tsx/neo"}
MONEDA = {"HD": "¥", "NBT": "¥", "LYC": "A$", "ILU": "A$", "ARU": "A$", "NEO": "C$"}

def tipo_de(t):
    if t in COMPOUNDER: return "compounder"
    if t in CYCLICAL: return "cyclical"
    if t in PREREVENUE: return "prerevenue"
    return "growth"

def fetch_quote(t):
    """Precio actual + fwd P/E + rango 52 semanas desde stockanalysis (con caché local).
    Fuente uniforme (la misma de las betas) → estado contra el precio de HOY."""
    cache = {}
    if os.path.exists(CACHE):
        cache = json.load(open(CACHE, encoding="utf-8"))
    if t in cache and cache[t] and cache[t].get("ts", 0) > time.time() - 86400 * 1:
        return cache[t]
    path = QUOTE.get(t, f"stocks/{t.lower()}")
    url = f"https://stockanalysis.com/{path}/"
    out = {"precio": None, "fwd": None, "low52": None, "ts": time.time()}
    try:
        req = urllib.request.Request(url, headers=UA)
        html = urllib.request.urlopen(req, timeout=25).read().decode("utf-8", "ignore")
        # precio actual (hero: text-4xl font-bold → 227.42)
        m = re.search(r'text-4xl font-bold[^>]*>\s*([\d.,]+)', html)
        if not m:
            m = re.search(r'itemprop="price"[^>]*content="([\d.,]+)"', html)
        if not m:
            m = re.search(r'"price":\s*([\d.]+)', html)
        if m:
            out["precio"] = float(m.group(1).replace(",", ""))
        # fwd P/E
        m = re.search(r"Forward PE</td>\s*<td[^>]*>\s*([\d.,]+)", html)
        if not m:
            m = re.search(r"Forward PE[^0-9]*([\d.,]+)", html)
        if m:
            out["fwd"] = float(m.group(1).replace(",", ""))
        # rango 52 semanas
        m = re.search(r"52-Week Range</td>\s*<td[^>]*>\s*([\d.,]+)\s*[-–]\s*([\d.,]+)", html)
        if not m:
            m = re.search(r"52-Week Range[^0-9]*([\d.,]+)\s*[-–]\s*([\d.,]+)", html)
        if m:
            out["low52"] = float(m.group(1).replace(",", ""))
    except Exception:
        pass
    cache[t] = out
    json.dump(cache, open(CACHE, "w", encoding="utf-8"))
    return out

def parse_report(f):
    """-> (ticker, verdict, conv, umbral) desde el HTML del reporte (precio/fwd vienen del fetch)."""
    h = open(f, encoding="utf-8").read()
    stem = os.path.basename(f).replace("neuromancer-council-", "").replace(".html", "")
    ALIAS = {"palantir": "PLTR", "enha": "ENHA", "screening-rare-earths": "RARE-EARTHS"}
    t = ALIAS.get(stem, stem.upper())
    vm = re.search(r'class="verdict-badge (buy|hold|avoid)">', h)
    verdict = vm.group(1) if vm else "hold"
    cm = re.search(r"Convicción del Consejo: <b>(\d+)/10</b>", h)
    conv = int(cm.group(1)) if cm else 0
    # umbral de compra del reporte: "≤$230" / "≤ ~$13" / "<$38.19" / "≤¥4,100"
    # (solo ≤ o < como ancla — el "~" suelto captura "P/S ~3.5x" falso)
    umbral = None
    um = re.search(r"(?:≤|<=|<)\s*(?:~)?([$¥])\s*(\d+(?:[.,]\d+)?)", h)
    if um:
        umbral = (um.group(1), float(um.group(2).replace(",", "")))
    return t, verdict, conv, umbral

def calcular(t, verdict, umbral, q):
    """-> dict con la zona (low, high) + estado, o None si no aplica."""
    if verdict not in ("buy", "hold") or t in NO_ZONA or not q or not q.get("precio"):
        return None
    precio = q["precio"]; fwd = q.get("fwd"); low52 = q.get("low52")
    moneda = MONEDA.get(t, "$")
    mult = MULT[tipo_de(t)]
    margen = None
    if fwd and mult and fwd > 0:
        margen = (precio / fwd) * mult  # EPS fwd × múltiplo objetivo
    # capa 3: umbral del reporte (ancla)
    ancla = umbral[1] if umbral else None
    if ancla:
        zona_lo, zona_hi = ancla * 0.93, ancla * 1.07
        fuente = "umbral del reporte"
    else:
        piso = None
        if low52 and low52 > 0:
            piso = low52
        elif margen:
            piso = margen * 0.90
        if not margen or not piso:
            return None
        zona_lo, zona_hi = max(piso, margen * 0.90), margen
        if zona_lo >= zona_hi:
            return None
        fuente = "valoración + soporte"
    if precio < zona_lo:
        estado = "DESCUENTO"
    elif precio <= zona_hi:
        estado = "ZONA ACTIVA"
    else:
        estado = "ESPERAR"
    dist = (precio / zona_hi - 1) * 100 if zona_hi else 0
    return {"ticker": t, "verdict": verdict, "precio": round(precio, 2), "moneda": moneda,
            "zona": [round(zona_lo, 2), round(zona_hi, 2)], "estado": estado,
            "dist_pct": round(dist, 1), "fuente": fuente,
            "tipo": tipo_de(t), "fwd": fwd, "52w_low": low52, "margen": round(margen, 2) if margen else None}

def main():
    zonas = {}
    pendientes = []
    for f in sorted(glob.glob(os.path.join(BASE, "neuromancer-council-*.html"))):
        t, verdict, conv, umbral = parse_report(f)
        if verdict not in ("buy", "hold") or t in NO_ZONA:
            continue
        pendientes.append((t, verdict, conv, umbral))
    print(f"fetcheando quotes de {len(pendientes)} tickers…")
    for i, (t, verdict, conv, umbral) in enumerate(pendientes, 1):
        q = fetch_quote(t)
        z = calcular(t, verdict, umbral, q)
        if z:
            z["conv"] = conv
            zonas[t] = z
        if i % 10 == 0:
            print(f"  {i}/{len(pendientes)}…")
    json.dump(zonas, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    act = [t for t, z in zonas.items() if z["estado"] == "ZONA ACTIVA"]
    esp = [t for t, z in zonas.items() if z["estado"] == "ESPERAR"]
    desc = [t for t, z in zonas.items() if z["estado"] == "DESCUENTO"]
    print(f"entry_zones.json: {len(zonas)} zonas")
    print(f"  ZONA ACTIVA ({len(act)}): {', '.join(sorted(act)) or '—'}")
    print(f"  ESPERAR ({len(esp)}): {', '.join(sorted(esp)) or '—'}")
    print(f"  DESCUENTO ({len(desc)}): {', '.join(sorted(desc)) or '—'}")

if __name__ == "__main__":
    main()
