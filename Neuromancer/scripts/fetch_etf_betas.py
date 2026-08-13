#!/usr/bin/env python3
"""fetch_etf_betas.py — Calcula la beta REAL por regresión para los ETFs de The Bunker
(que no reportan beta en stockanalysis) y la guarda en scripts/betas.json.

Método: retornos semanales de 5 años (misma fuente y ventana que las betas
individuales de stockanalysis) vs S&P 500 (SPY), β = cov(R_etf, R_spy) / var(R_spy).
"""
import json, re, sys, time, urllib.request, os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Neuromancer/
BETAS_JSON = os.path.join(BASE, "scripts", "betas.json")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

ETFS = ["VXUS", "VWO", "GLD", "SLV", "VNQ", "BND", "TIP", "EMB"]
BENCH = "SPY"


def fetch_weekly(ticker, kind="e"):
    url = f"https://stockanalysis.com/api/symbol/{kind}/{ticker}/history?range=5Y&period=Weekly"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    rows = data.get("data", [])
    out = {}
    for row in rows:
        if row.get("c") is not None and row.get("t"):
            out[row["t"]] = float(row["c"])
    return out


def beta_from(etf_close, bench_close):
    dates = sorted(set(etf_close) & set(bench_close))
    ret_e, ret_b = [], []
    for a, b in zip(dates, dates[1:]):
        e0, e1 = etf_close[a], etf_close[b]
        b0, b1 = bench_close[a], bench_close[b]
        if e0 and e1 and b0 and b1:
            ret_e.append(e1 / e0 - 1.0)
            ret_b.append(b1 / b0 - 1.0)
    n = len(ret_e)
    if n < 100:
        return None, n
    me, mb = sum(ret_e) / n, sum(ret_b) / n
    cov = sum((x - me) * (y - mb) for x, y in zip(ret_e, ret_b)) / (n - 1)
    var = sum((y - mb) ** 2 for y in ret_b) / (n - 1)
    return cov / var, n


def main():
    betas = json.load(open(BETAS_JSON, encoding="utf-8"))
    print("descargando SPY (benchmark)...", flush=True)
    spy = fetch_weekly(BENCH, "s")
    print(f"  SPY: {len(spy)} semanas", flush=True)
    for t in ETFS:
        for attempt in range(3):
            try:
                print(f"descargando {t}...", flush=True)
                etf = fetch_weekly(t, "e")
                beta, n = beta_from(etf, spy)
                if beta is None:
                    print(f"  {t}: datos insuficientes ({n}) — sin beta", flush=True)
                else:
                    betas[t] = round(beta, 2)
                    print(f"  {t}: β = {beta:.4f} ({n} semanas) → {betas[t]:.2f}", flush=True)
                break
            except Exception as e:
                print(f"  {t}: error ({e}) — reintento {attempt + 1}/3", flush=True)
                time.sleep(2)
    json.dump({k: betas[k] for k in sorted(betas)}, open(BETAS_JSON, "w", encoding="utf-8"), indent=1)
    print(f"\nbetas.json actualizado: {len(betas)} betas ({len(ETFS)} ETFs por regresión)")


if __name__ == "__main__":
    main()
