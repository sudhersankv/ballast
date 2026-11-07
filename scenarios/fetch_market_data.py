"""Download free public monthly series and write scenarios/data/monthly_returns.csv (committed, so generation is
offline and deterministic). Re-run only to refresh the data.

    python scenarios/fetch_market_data.py

Columns (decimal monthly total returns, USD):
  US_EQ   = CRSP US value-weighted market (Fama-French Mkt-RF + RF)      ~ S&P 500 / total-market TR proxy
  INTL_EQ = Developed ex-US market (Fama-French Developed ex US Mkt-RF + RF) ~ MSCI EAFE TR proxy
  BOND    = modeled from FRED GS10:  y[t-1]/12 - D * (y[t] - y[t-1]),  D = config bond_duration (6.0)
            ~ US Aggregate proxy (duration-matched Treasury carry + price change; no credit spread)
  CASH    = 1-month T-bill (Fama-French RF)
Sources: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html , https://fred.stlouisfed.org/series/GS10
"""
from __future__ import annotations

import csv
import io
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "data" / "monthly_returns.csv"
FF_US = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip"
FF_DEV = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/Developed_ex_US_3_Factors_CSV.zip"
GS10 = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=GS10"
BOND_DURATION = 6.0


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "ballast-scenarios/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def french_monthly(url: str) -> dict[str, tuple[float, float]]:
    """{YYYY-MM: (mkt_total_return, rf)} from the monthly block of a Fama-French CSV zip."""
    z = zipfile.ZipFile(io.BytesIO(_get(url)))
    text = z.read(z.namelist()[0]).decode("latin-1")
    out: dict[str, tuple[float, float]] = {}
    started = False
    for line in text.splitlines():
        cells = [c.strip() for c in line.split(",")]
        if cells and cells[0] == "" and "Mkt-RF" in cells:
            if started:
                break
            started = True
            continue
        if not started:
            continue
        if not cells[0]:
            if out:
                break
            continue
        if not (cells[0].isdigit() and len(cells[0]) == 6):
            break  # reached the annual block
        mkt_rf, rf = float(cells[1]), float(cells[-1])
        if mkt_rf <= -99:
            continue
        out[f"{cells[0][:4]}-{cells[0][4:]}"] = ((mkt_rf + rf) / 100, rf / 100)
    return out


def gs10_returns(duration: float) -> dict[str, float]:
    rows = list(csv.reader(io.StringIO(_get(GS10).decode())))[1:]
    ys = [(d[:7], float(v)) for d, v in rows if v not in ("", ".")]
    return {m1: y0 / 100 / 12 - duration * (y1 - y0) / 100 for (m0, y0), (m1, y1) in zip(ys, ys[1:])}


def main() -> int:
    us, dev, bond = french_monthly(FF_US), french_monthly(FF_DEV), gs10_returns(BOND_DURATION)
    months = sorted(set(us) & set(dev) & set(bond))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["month", "US_EQ", "INTL_EQ", "BOND", "CASH"])
        for m in months:
            w.writerow([m, f"{us[m][0]:.6f}", f"{dev[m][0]:.6f}", f"{bond[m]:.6f}", f"{us[m][1]:.6f}"])
    print(f"wrote {OUT} ({len(months)} months, {months[0]}..{months[-1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
