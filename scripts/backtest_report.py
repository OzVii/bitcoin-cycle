"""Backtest-yhteenveto: missä vaiheessa sivu olisi ollut aiempien syklien huippujen ja pohjien
kohdalla, vaiheenvaihdokset ja vaiheiden jälkeiset tuotot.

Huiput ja pohjat tunnistetaan jälkikäteen (vain arviointia varten); itse pisteet ja vaiheet
on laskettu viikko kerrallaan ilman tulevaa dataa.

Ajo: python scripts/backtest_report.py [--md BACKTEST.md]
"""
import sys

import numpy as np
import pandas as pd

from build import evaluate
from common import ROOT, load_config


def fmt_price(x):
    return f"{x:,.0f}".replace(",", " ") + " $" if x >= 100 else f"{x:.2f} $"


def main():
    cfg = load_config()
    ev = evaluate(cfg)
    names = cfg["phases"]["names"]
    short = {int(k): v for k, v in names.items()}
    start = pd.Timestamp(cfg["backtest"]["start"])
    layers = ["valuation", "trend", "momentum", "sentiment", "macro"]
    rows = []
    for it in ev["official"]:
        r = it["row"]
        rows.append({"week": r["week_start"], "date": r["date"], "price": r["price"], "total": it["scored"]["total"],
                     "phase": it["phase"], "cand": it["candidate"],
                     **{k: it["scored"]["layers"][k]["score"] for k in layers}})
    df = pd.DataFrame(rows)
    out = []
    p = out.append

    p("# Backtest-raportti\n")
    p(f"Viikkoja arvioitu: {len(df)} (raportti alkaen {start.date()}). Viimeisin suljettu viikko: "
      f"{df['week'].iloc[-1].date()}, vaihe {short[df['phase'].iloc[-1]]}, piste {df['total'].iloc[-1]:+.0f}.\n")

    def week_of(date):
        date = pd.Timestamp(date)
        m = df[(df["week"] <= date) & (df["week"] + pd.Timedelta(days=6) >= date)]
        return m.iloc[0] if len(m) else None

    def phase_path(date, before=12, after=12, step=4):
        date = pd.Timestamp(date)
        i = df.index[(df["week"] <= date) & (df["week"] + pd.Timedelta(days=6) >= date)]
        if not len(i):
            return ""
        i = i[0]
        parts = []
        for k in range(-before, after + 1, step):
            j = i + k
            if 0 <= j < len(df):
                parts.append(f"{k:+d}vk:{df.loc[j, 'phase']}({df.loc[j, 'total']:+.0f})")
        return " ".join(parts)

    p("## Syklien huiput ja pohjat\n")
    p("| Tapahtuma | Päivä | Hinta | Vaihe sillä viikolla | Piste | Arvostus | Trendi | Momentum | Sentimentti | Makro |")
    p("|---|---|---|---|---|---|---|---|---|---|")
    events = []
    for c in ev["cycles"]:
        events.append(("Pohja", c["bottom_date"], c["bottom_price"]))
        if c["top_confirmed"]:
            events.append(("Huippu", c["top_date"], c["top_price"]))
    events = sorted(set(events), key=lambda e: e[1])
    for kind, d, price in events:
        w = week_of(d)
        if w is None or pd.isna(w["phase"]):
            p(f"| {kind} | {d} | {fmt_price(price)} | (ei signaalia) | | | | | | |")
            continue
        sc = " | ".join("–" if pd.isna(w[k]) else f"{w[k]:+.0f}" for k in layers)
        p(f"| {kind} | {d} | {fmt_price(price)} | {int(w['phase'])} {short[int(w['phase'])]} | {w['total']:+.0f} | {sc} |")

    p("\n### Vaihepolku tapahtumien ympärillä (vaihe(piste) 4 viikon välein, −12 … +12 vk)\n")
    p("```")
    for kind, d, _ in events:
        path = phase_path(d)
        if path:
            p(f"{kind:6s} {d}: {path}")
    p("```")

    # Kuinka aikaisin ennen huippua oltiin vaiheessa 4, ja kuinka pian huipun jälkeen vaiheessa 5
    p("\n### Signaalien ajoitus huippuihin nähden\n")
    for kind, d, _ in events:
        if kind != "Huippu":
            continue
        t = pd.Timestamp(d)
        win = df[(df["week"] >= t - pd.Timedelta(weeks=52)) & (df["week"] <= t + pd.Timedelta(weeks=52))]
        hot = win[win["phase"] == 4]
        bear = win[(win["phase"] == 5) & (win["week"] >= t - pd.Timedelta(weeks=4))]
        s = f"- Huippu {d}: "
        if len(hot):
            first, last = hot["week"].iloc[0], hot["week"].iloc[-1]
            s += (f"ylikuumeneminen ensimmäisen kerran {(t - first).days // 7} vk ennen huippua "
                  f"({fmt_price(hot['price'].iloc[0])}), viimeksi {(last - t).days // 7:+d} vk; ")
        else:
            s += "ylikuumenemista ei tunnistettu ±52 vk aikana; "
        if len(bear):
            s += f"laskumarkkina {(bear['week'].iloc[0] - t).days // 7:+d} vk huipusta ({fmt_price(bear['price'].iloc[0])})."
        else:
            s += "laskumarkkinaa ei tunnistettu 52 vk sisällä."
        p(s)
    for kind, d, _ in events:
        if kind != "Pohja":
            continue
        t = pd.Timestamp(d)
        win = df[(df["week"] >= t - pd.Timedelta(weeks=52)) & (df["week"] <= t + pd.Timedelta(weeks=78))]
        if win.empty:
            continue
        s = f"- Pohja {d}: "
        b = win[win["phase"] == 1]
        e = win[(win["phase"] == 2) & (win["week"] >= t - pd.Timedelta(weeks=26))]
        s += (f"pohjavaihe alkoi {(t - b['week'].iloc[0]).days // 7} vk ennen pohjaa ({fmt_price(b['price'].iloc[0])}); "
              if len(b) else "pohjavaihetta ei tunnistettu; ")
        s += (f"varhainen nousu {(e['week'].iloc[0] - t).days // 7:+d} vk pohjasta ({fmt_price(e['price'].iloc[0])})."
              if len(e) else "varhaista nousua ei tunnistettu 78 vk sisällä.")
        p(s)

    # Vaiheenvaihdokset
    p("\n## Vaiheenvaihdokset\n")
    p("| Viikko | Hinta | Vaihdos | Piste |")
    p("|---|---|---|---|")
    prev = None
    for _, r in df.iterrows():
        if prev is not None and r["phase"] != prev and r["week"] >= start:
            p(f"| {r['week'].date()} | {fmt_price(r['price'])} | {short[int(prev)]} → {short[int(r['phase'])]} | {r['total']:+.0f} |")
        prev = r["phase"]

    # Tuotot vaiheittain
    p("\n## Tuotto vaiheen jälkeen (mediaani, viikot alkaen " + str(start.date()) + ")\n")
    fw = cfg["backtest"]["forward_weeks"]
    for n in fw:
        df[f"fwd{n}"] = (df["price"].shift(-n) / df["price"] - 1) * 100
    bt = df[df["week"] >= start]
    p("| Vaihe | Viikkoja | Osuus | " + " | ".join(f"{n} vk mediaani" for n in fw) + " | 52 vk positiivinen |")
    p("|---|---|---|" + "---|" * len(fw) + "---|")
    for ph in range(1, 6):
        sub = bt[bt["phase"] == ph]
        if sub.empty:
            p(f"| {ph} {short[ph]} | 0 | 0 % |" + " – |" * len(fw) + " – |")
            continue
        med = " | ".join(f"{sub[f'fwd{n}'].median():+.0f} %" if sub[f"fwd{n}"].notna().any() else "–" for n in fw)
        pos = (sub["fwd52"].dropna() > 0).mean() * 100 if sub["fwd52"].notna().any() else np.nan
        p(f"| {ph} {short[ph]} | {len(sub)} | {len(sub) / len(bt) * 100:.0f} % | {med} | {pos:.0f} % |")

    p("\n## Kokonaispisteen ääripäät\n")
    for label, sub in (("Korkeimmat (osto)", bt.nlargest(5, "total")), ("Matalimmat (myynti)", bt.nsmallest(5, "total"))):
        p(f"- {label}: " + "; ".join(f"{r['week'].date()} {r['total']:+.0f} @ {fmt_price(r['price'])}"
                                     for _, r in sub.iterrows()))

    p("\n## Pisteen jakauma vuosittain (min / mediaani / max)\n")
    p("```")
    for y, g in bt.groupby(bt["week"].dt.year):
        ph = g["phase"].value_counts().sort_index()
        p(f"{y}: {g['total'].min():+4.0f} / {g['total'].median():+4.0f} / {g['total'].max():+4.0f}   vaiheet: "
          + ", ".join(f"{int(k)}×{v}" for k, v in ph.items()))
    p("```")

    text = "\n".join(out)
    print(text)
    if "--md" in sys.argv:
        path = ROOT / sys.argv[sys.argv.index("--md") + 1]
        path.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
