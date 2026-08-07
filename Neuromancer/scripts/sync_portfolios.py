#!/usr/bin/env python3
"""
sync_portfolios.py — Sincroniza Neuromancer/portfolios.json desde Obsidian.

Fuente de verdad: <vault>/Trading/Neuromancer Portfolios Stack/*.md
Formato esperado por archivo:
  # Nombre del portafolio
  ## Descripción
  texto libre...
  ## Tickers
  - TICKER        (o ### Set N con - TICKER debajo)

Genera Neuromancer/portfolios.json y reporta diff (nuevos/eliminados/cambios)
vs el estado anterior. Ejecutar ANTES de cada update de Neuromancer.
"""
import json, os, re, sys, datetime

VAULT = "/Users/juangcastro/Library/Mobile Documents/iCloud~md~obsidian/Documents/Notes"
STACK_DIR = os.path.join(VAULT, "Trading", "Neuromancer Portfolios Stack")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "portfolios.json")
OUT = os.path.normpath(OUT)

def parse_portfolio(path):
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    name = "Sin nombre"
    desc = ""
    tickers = []
    current_set = None
    sets = {}
    section = None
    for ln in lines:
        s = ln.strip()
        if s.startswith("# ") and not s.startswith("## "):
            name = s[2:].strip()
            section = None
        elif s.startswith("## Descripción"):
            section = "desc"
        elif s.startswith("## Tickers"):
            section = "tickers"
        elif s.startswith("### "):
            current_set = s[4:].strip()
            section = "tickers"
        elif s.startswith("## "):
            section = None
        elif section == "desc" and s:
            desc += ((" " if desc else "") + s)
        elif section == "tickers":
            m = re.match(r"^[-*]\s*([A-Za-z0-9.\-]{1,10})\s*$", s)
            if m:
                t = m.group(1).upper()
                if t not in tickers:
                    tickers.append(t)
                if current_set:
                    sets.setdefault(current_set, []).append(t)
    return {"name": name, "description": desc, "tickers": tickers, "sets": sets}

def main():
    if not os.path.isdir(STACK_DIR):
        print(f"ERROR: no existe {STACK_DIR}"); sys.exit(1)
    portfolios = []
    for fn in sorted(os.listdir(STACK_DIR)):
        if fn.endswith(".md"):
            portfolios.append(parse_portfolio(os.path.join(STACK_DIR, fn)))
    # orden: Manhattan Project 2.0 primero si existe, luego alfabético
    portfolios.sort(key=lambda p: (0 if "manhattan" in p["name"].lower() else 1, p["name"].lower()))

    prev = None
    if os.path.exists(OUT):
        try: prev = json.load(open(OUT, encoding="utf-8")).get("portfolios")
        except Exception: prev = None

    manifest = {"generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
                "portfolios": portfolios}
    json.dump(manifest, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✔ portfolios.json generado ({len(portfolios)} portafolios, "
          f"{len({t for p in portfolios for t in p['tickers']})} tickers únicos)")

    # diff vs estado anterior
    if prev is not None:
        prev_map = {p["name"]: p["tickers"] for p in prev}
        new_map = {p["name"]: p["tickers"] for p in portfolios}
        for name, tk in new_map.items():
            if name not in prev_map:
                print(f"  ➕ NUEVO portafolio: {name} ({len(tk)} tickers)")
            elif tk != prev_map[name]:
                added = set(tk) - set(prev_map[name]); removed = set(prev_map[name]) - set(tk)
                print(f"  ✏️  CAMBIÓ: {name} — +{sorted(added)} -{sorted(removed)}")
        for name in prev_map:
            if name not in new_map:
                print(f"  ➖ ELIMINADO: {name}")
        if new_map == prev_map:
            print("  (sin cambios en portafolios)")

if __name__ == "__main__":
    main()
