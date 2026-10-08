/* Bitcoin Cycle: reads data/latest.json and data/history.json and renders the page. */
(() => {
  "use strict";

  const C = {
    bg: "#141414", border: "#262626", text: "#FFFFFF", muted: "#A3A3A3", dim: "#6b6b6b",
    accent: "#F7931A", buy: "#22C55E", sell: "#EF4444", band: "#60A5FA", sma50: "#C084FC",
  };
  const PHASE_BG = {
    1: "rgba(34,197,94,0.11)", 2: "rgba(34,197,94,0.24)", 3: "rgba(163,163,163,0.08)",
    4: "rgba(239,68,68,0.24)", 5: "rgba(239,68,68,0.11)",
  };
  const PHASE_SHORT = { 1: "Bottom", 2: "Early bull", 3: "Bull", 4: "Overheated", 5: "Bear" };
  let INFO = {};

  // ---------------------------------------------------------------- formatting
  const LOC = "en-US";
  const nf0 = new Intl.NumberFormat(LOC, { maximumFractionDigits: 0 });
  const nf = (x, d = 1) => x == null ? "–" :
    x.toLocaleString(LOC, { minimumFractionDigits: d, maximumFractionDigits: d });
  const usd = (x) => x == null ? "–" : `$${nf0.format(x)}`;
  const usdShort = (x) => x >= 1e6 ? `$${nf(x / 1e6, 2)}M` : x >= 1e3 ? `$${nf(x / 1e3, 0)}k` : `$${nf0.format(x)}`;
  const pct = (x, d = 1) => x == null ? "–" : `${x > 0 ? "+" : x < 0 ? "−" : ""}${nf(Math.abs(x), d)}%`;
  const sgn = (x) => { if (x == null) return "–"; const v = Math.round(x); return v > 0 ? `+${v}` : v < 0 ? `−${-v}` : "0"; };
  const fdate = (s) => s ? new Date(`${s.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB",
    { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }) : "–";
  const fdateShort = (s) => new Date(`${s.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-GB",
    { timeZone: "UTC", day: "numeric", month: "short" });
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const infoBtn = (key) => `<button class="info" data-info="${key}" aria-label="About: ${esc((INFO[key] || {}).title || key)}">i</button>`;
  const helpBtn = (key, label = "What's this?") => `<button class="help" data-info="${key}">${esc(label)}</button>`;

  async function getJSON(url) {
    const r = await fetch(url, { cache: "no-cache" });
    if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`);
    return r.json();
  }

  // ---------------------------------------------------------------- header and warnings
  function renderHeader(L) {
    const gen = new Date(L.generated_at);
    const thru = new Date(Date.parse(L.data_as_of) - 864e5).toISOString();
    $("updated").textContent = `Updated ${gen.toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short" })} · data through ${fdate(thru)}`;
    const p = L.price_now;
    $("priceNow").innerHTML = `<div class="p">${usd(p.price)}</div><div class="d">${esc(p.source)} · ${fdate(p.date)}</div>`;

    const warn = [];
    const ageH = (Date.now() - Date.parse(L.data_as_of)) / 36e5;
    if (ageH > L.stale_hours) {
      warn.push(`<p class="warn">Data is ${nf0.format(ageH)} hours old (limit ${L.stale_hours} h). The update run may have failed.</p>`);
    }
    const names = { coinmetrics: "CoinMetrics", ohlc_daily: "Bitstamp", fng: "Fear & Greed", m2: "FRED M2", dollar: "FRED dollar index" };
    const failed = Object.entries(L.sources || {}).filter(([, s]) => s.ok === false);
    if (failed.length) {
      const list = failed.map(([k, s]) => `${names[k] || k} (stored data through ${fdate(s.last_date)})`).join(", ");
      warn.push(`<p class="warn soft">Source did not respond in the latest run: ${esc(list)}. Using the latest stored data.</p>`);
    }
    $("warnings").innerHTML = warn.join("");
  }

  // ---------------------------------------------------------------- cycle gauge
  function arcPoint(score, r) {
    const th = Math.PI - ((score + 100) / 200) * Math.PI;
    return [150 + r * Math.cos(th), 150 - r * Math.sin(th)];
  }

  function renderHero(L) {
    const s = L.signal;
    $("gTicks").innerHTML = [-100, -50, 0, 50, 100].map((v) => {
      const [x1, y1] = arcPoint(v, 108), [x2, y2] = arcPoint(v, 132), [tx, ty] = arcPoint(v, 146);
      return `<line class="g-tick" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/>` +
        (Math.abs(v) === 100 ? "" : `<text class="g-num" x="${tx}" y="${ty + 3}">${sgn(v)}</text>`);
    }).join("");
    const total = Math.max(-100, Math.min(100, s.total));
    const sc = $("score");
    sc.textContent = sgn(total);
    sc.style.color = total > 10 ? C.buy : total < -10 ? C.sell : C.text;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      $("gNeedle").style.transform = `rotate(${(total / 100) * 90}deg)`;
    }));

    $("weekLabel").textContent = `${fdateShort(s.week_start)} – ${fdate(s.week_end)}`;
    $("phaseName").innerHTML = `<span class="num">${s.phase}</span>${esc(s.phase_name)}`;
    $("phaseSteps").innerHTML = [1, 2, 3, 4, 5].map((n) =>
      `<li class="${n === s.phase ? "on" : ""}" title="${esc(L.phase_names[n])}"><span>${PHASE_SHORT[n]}</span></li>`).join("");
    $("summary").textContent = L.summary;

    const pv = L.preview;
    if (pv) {
      const diff = pv.phase !== s.phase ? ` <strong style="color:${C.accent}">The phase would change if the week closed now.</strong>` : "";
      $("preview").innerHTML = `Running week from ${fdateShort(pv.week_start)} (data through ${fdate(pv.data_through)}): ` +
        `${esc(pv.phase_name)}, score ${sgn(pv.total)}. Preview only; does not change the official signal.${diff} ${helpBtn("preview", "About the preview")}`;
    } else {
      $("preview").innerHTML = `No data for the new week yet. ${helpBtn("preview", "About the preview")}`;
    }

    const ch = L.changes || [];
    const head = `<div class="row-between"><strong>Changes from last week</strong>${helpBtn("changes")}</div>`;
    $("changes").innerHTML = ch.length
      ? `<div class="changes">${head}<ul>${ch.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></div>`
      : `<div class="changes">${head}<p class="muted">No significant changes from last week.</p></div>`;
  }

  // ---------------------------------------------------------------- zones
  function renderZones(L) {
    const zones = L.signal.zones.slice();
    const P = L.price_now.price;
    const byId = Object.fromEntries(zones.map((z) => [z.id, z]));
    const lo = Math.min(...zones.map((z) => z.low), P) * 0.9;
    const hi = Math.max(...zones.map((z) => z.high), P) * 1.06;
    const pos = (x) => ((Math.log(x) - Math.log(lo)) / (Math.log(hi) - Math.log(lo))) * 100;

    let bar = `<div class="track"></div>`;
    if (byId.buy1 && byId.buy3) {
      const a = pos(Math.min(byId.buy3.low, byId.buy1.low)), b = pos(Math.max(byId.buy1.high, byId.buy3.high));
      bar += `<div class="seg buy" style="left:${a}%;width:${b - a}%"></div>`;
    }
    if (byId.sell1 && byId.sell3) {
      const a = pos(byId.sell1.low), b = pos(byId.sell3.high);
      bar += `<div class="seg sell" style="left:${a}%;width:${b - a}%"></div>`;
    }
    const short = { buy1: "B1", buy2: "B2", buy3: "B3", sell1: "S1", sell2: "S2", sell3: "S3", pi: "" };
    let lastLabel = -100;
    zones.slice().sort((a, b) => a.price - b.price).forEach((z) => {
      const x = pos(z.price);
      bar += `<div class="tick" style="left:${x}%"></div>`;
      if (short[z.id] && x - lastLabel > 7) { bar += `<div class="tl" style="left:${x}%">${short[z.id]}</div>`; lastLabel = x; }
    });
    bar += `<div class="now" style="left:${pos(P)}%"><b>${usdShort(P)}</b><i></i></div>`;
    $("zoneBar").innerHTML = bar;

    const rows = zones.map((z) => ({ ...z, sortP: z.price }));
    rows.push({ cur: true, sortP: P });
    rows.sort((a, b) => b.sortP - a.sortP);
    $("ladder").innerHTML = rows.map((z) => {
      if (z.cur) {
        return `<li class="cur"><div><div class="nm">Current price</div><div class="bs">${esc(L.price_now.source)} ${fdate(L.price_now.date)}</div></div>` +
          `<div><div class="rg">${usd(P)}</div></div></li>`;
      }
      const inside = P >= z.low && P <= z.high;
      return `<li class="${z.kind}${inside ? " in" : ""}"><div><div class="nm">${esc(z.name)}${inside ? " · price in range" : ""}</div>` +
        `<div class="bs">${esc(z.basis)}</div></div><div><div class="rg">${usd(z.low)}–${usd(z.high)}</div>` +
        `<div class="ds">${pct(z.distance_pct, 1)}</div></div></li>`;
    }).join("");
  }

  // ---------------------------------------------------------------- layers
  function renderLayers(L) {
    $("layers").innerHTML = L.signal.layers.map((l) => {
      const s = l.score;
      const cls = s == null ? "" : s > 10 ? "pos" : s < -10 ? "neg" : "";
      const w = Math.round(l.weight * 100), nw = Math.round(l.nominal_weight * 100);
      const wTxt = s == null ? `weight ${nw}% · no data` : w !== nw ? `weight ${w}% (base ${nw}%)` : `weight ${w}%`;
      const metrics = l.metrics.map((m) =>
        `<div><dt>${esc(m.label)} ${infoBtn(m.info)}</dt><dd>${esc(m.value)}</dd></div>`).join("");
      const left = s == null ? 50 : 50 + Math.min(0, s) / 2, width = s == null ? 0 : Math.abs(s) / 2;
      return `<article class="card layer fade-in">
        <h3>${esc(l.name)} <span class="w">${wTxt}</span><span class="sc ${cls}">${sgn(s)}</span></h3>
        <div class="minibar" title="Sell −100 … +100 Buy"><i class="${s >= 0 ? "pos" : "neg"}" data-left="${left}" data-width="${width}" style="left:50%"></i></div>
        <dl class="metrics">${metrics}</dl>
        <p>${esc(l.text)}</p>
        <div class="layer-foot">${helpBtn(`layer_${l.key}`, `About ${l.name.toLowerCase()}`)}</div>
      </article>`;
    }).join("");
    requestAnimationFrame(() => requestAnimationFrame(() => {
      document.querySelectorAll(".minibar i").forEach((el) => {
        el.style.left = `${el.dataset.left}%`;
        el.style.width = `${el.dataset.width}%`;
      });
    }));
  }

  // ---------------------------------------------------------------- charts
  const LWC = window.LightweightCharts;
  const baseChartOpts = (extra = {}) => ({
    autoSize: true,
    layout: { background: { type: "solid", color: C.bg }, textColor: C.muted, fontFamily: "JetBrains Mono, monospace", fontSize: 11 },
    grid: { vertLines: { visible: false }, horzLines: { visible: false } },
    rightPriceScale: { borderColor: C.border },
    timeScale: { borderColor: C.border, lockVisibleTimeRangeOnResize: true },
    crosshair: { mode: LWC.CrosshairMode.Normal },
    localization: { locale: LOC, priceFormatter: (p) => (p >= 100 ? nf0.format(p) : nf(p, 2)) },
    handleScroll: { vertTouchDrag: false },
    ...extra,
  });
  const silent = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
  // set the initial view only after the browser has computed the final layout
  const afterLayout = (fn) => requestAnimationFrame(() => requestAnimationFrame(fn));

  function lineData(H, key) {
    const t = H.lines.t, v = H.lines[key];
    const out = [];
    for (let i = 0; i < t.length; i++) if (v[i] != null) out.push({ time: t[i], value: v[i] });
    return out;
  }

  function renderPriceChart(L, H) {
    const chart = LWC.createChart($("priceChart"), baseChartOpts({
      rightPriceScale: { borderColor: C.border, mode: LWC.PriceScaleMode.Logarithmic, scaleMargins: { top: 0.06, bottom: 0.04 } },
    }));
    const area = (color) => chart.addAreaSeries({ ...silent, topColor: color, bottomColor: color, lineVisible: false, lineColor: "rgba(0,0,0,0)" });
    // Zones: translucent fill down from the upper edge, background-coloured mask below the lower edge
    const zoneSeries = [
      [area("rgba(239,68,68,0.14)"), "sell3"], [area(C.bg), "sell1"],
      [area("rgba(34,197,94,0.14)"), "buy1"], [area(C.bg), "buy3"],
    ].map(([s, k]) => { s.setData(lineData(H, k)); return s; });
    const zoneLines = ["sell1", "sell3", "buy1", "buy3"].map((k) => {
      const s = chart.addLineSeries({ ...silent, color: k.startsWith("sell") ? "rgba(239,68,68,0.45)" : "rgba(34,197,94,0.45)", lineWidth: 1, lineStyle: LWC.LineStyle.Dotted });
      s.setData(lineData(H, k));
      return s;
    });

    const mk = (key, color, width = 1, style = LWC.LineStyle.Solid) => {
      const s = chart.addLineSeries({ ...silent, color, lineWidth: width, lineStyle: style });
      s.setData(lineData(H, key));
      return s;
    };
    const s200 = mk("sma200w", C.accent, 2);
    const s20 = mk("sma20w", C.band, 1);
    const e21 = mk("ema21w", C.band, 1, LWC.LineStyle.Dashed);
    const s50 = mk("sma50w", C.sma50, 1);
    s50.applyOptions({ visible: false });

    const candles = chart.addCandlestickSeries({
      upColor: "#d4d4d4", downColor: "#4a4a4a", borderUpColor: "#d4d4d4", borderDownColor: "#6b6b6b",
      wickUpColor: "#8a8a8a", wickDownColor: "#6b6b6b", priceLineColor: C.accent,
    });
    candles.setData(H.candles.map(([t, o, h, l, c, done]) => done
      ? { time: t, open: o, high: h, low: l, close: c }
      : { time: t, open: o, high: h, low: l, close: c, color: C.accent, borderColor: C.accent, wickColor: C.accent }));

    const fib = L.fib;
    let fibLines = [];
    const fibOn = (on) => {
      fibLines.forEach((pl) => candles.removePriceLine(pl));
      fibLines = [];
      if (!on) return;
      const add = (price, title, color) => fibLines.push(candles.createPriceLine({
        price, color, lineWidth: 1, lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title,
      }));
      add(fib.low, "0 (bottom)", "rgba(163,163,163,0.55)");
      add(fib.high, "1 (top)", "rgba(163,163,163,0.55)");
      fib.retracements.forEach((r) => add(r.price, nf(r.ratio, 3), "rgba(163,163,163,0.75)"));
      fib.extensions.forEach((e) => add(e.price, nf(e.ratio, 3), "rgba(247,147,26,0.7)"));
    };
    $("fibNote").textContent =
      `Fibonacci: cycle bottom ${usd(fib.low)} (${fdate(fib.low_date)}) → top ${usd(fib.high)} (${fdate(fib.high_date)}), ${fib.scale === "log" ? "log" : "linear"} scale. ` +
      `Candles: Bitstamp, Monday–Sunday (UTC); the orange candle is the running week.`;

    const groups = { sma200w: [s200], band: [s20, e21], sma50w: [s50], zones: [...zoneSeries, ...zoneLines] };
    document.querySelectorAll("#toggles input").forEach((inp) => {
      inp.addEventListener("change", () => {
        const k = inp.dataset.t;
        if (k === "fib") fibOn(inp.checked);
        else groups[k].forEach((s) => s.applyOptions({ visible: inp.checked }));
      });
    });

    const last = H.candles[H.candles.length - 1][0];
    chart.timeScale().applyOptions({ rightOffset: 4 });
    afterLayout(() => chart.timeScale().setVisibleRange({ from: Date.UTC(2017, 0, 1) / 1000, to: last }));
  }

  // ---------------------------------------------------------------- cycle comparison (SVG)
  function renderCycles(L, H) {
    const hv = L.halving;
    $("halvingNote").textContent =
      `Last halving ${fdate(hv.last)}, ${nf0.format(hv.days_since)} days ago. Next one estimated around ${fdate(hv.next_estimate)}. ` +
      `Price relative to the halving-day price, log scale.`;
    const W = 800, Hh = 380, pl = 46, pr = 78, pt = 14, pb = 28;
    const cyc = H.cycles;
    const all = cyc.flatMap((c) => c.ratio).filter((v) => v > 0);
    const yMin = Math.min(...all) * 0.85, yMax = Math.max(...all) * 1.15;
    const X = (d) => pl + (d / 1460) * (W - pl - pr);
    const Y = (r) => pt + (1 - (Math.log(r) - Math.log(yMin)) / (Math.log(yMax) - Math.log(yMin))) * (Hh - pt - pb);
    let svg = `<svg viewBox="0 0 ${W} ${Hh}" role="img" aria-label="Cycle comparison">`;
    [0.25, 0.5, 1, 2, 5, 10, 20, 50, 100, 200].filter((v) => v >= yMin && v <= yMax).forEach((v) => {
      svg += `<line class="ax" x1="${pl}" x2="${W - pr}" y1="${Y(v)}" y2="${Y(v)}" ${v === 1 ? 'stroke="#3a3a3a"' : ""}/>` +
        `<text class="lbl" x="${pl - 6}" y="${Y(v) + 3}" text-anchor="end">${nf(v, v < 1 ? 2 : 0)}×</text>`;
    });
    [0, 365, 730, 1095, 1460].forEach((d, i) => {
      svg += `<line class="ax" x1="${X(d)}" x2="${X(d)}" y1="${pt}" y2="${Hh - pb}" stroke-dasharray="2 4"/>` +
        `<text class="lbl" x="${X(d)}" y="${Hh - 10}" text-anchor="middle">${i === 0 ? "halving" : `${i} yr`}</text>`;
    });
    const lastH = hv.last;
    const tops = Object.fromEntries((hv.cycles || []).map((c) => [c.halving, c]));
    cyc.forEach((c, i) => {
      const cur = c.halving === lastH;
      const pts = c.days.map((d, j) => `${X(d).toFixed(1)},${Y(c.ratio[j]).toFixed(1)}`).join(" ");
      const op = cur ? 1 : 0.28 + 0.12 * i;
      svg += `<polyline points="${pts}" fill="none" stroke="${cur ? C.accent : "#A3A3A3"}" stroke-opacity="${op}" stroke-width="${cur ? 2.6 : 1.4}" stroke-linejoin="round"/>`;
      const ld = c.days[c.days.length - 1], lr = c.ratio[c.ratio.length - 1];
      svg += `<text class="tag" x="${X(ld) + 6}" y="${Y(lr) + 4}" fill="${cur ? C.accent : "#A3A3A3"}" fill-opacity="${cur ? 1 : 0.8}">${c.halving.slice(0, 4)} · ${nf(lr, lr < 10 ? 1 : 0)}×</text>`;
      const t = tops[c.halving];
      if (t && t.top_days_after_halving <= 1460) {
        const j = c.days.findIndex((d) => d >= t.top_days_after_halving);
        if (j >= 0) svg += `<circle cx="${X(c.days[j])}" cy="${Y(c.ratio[j])}" r="3" fill="${cur ? C.accent : "#A3A3A3"}" fill-opacity="${op}"/>`;
      }
    });
    svg += `<line x1="${X(hv.days_since)}" x2="${X(hv.days_since)}" y1="${pt}" y2="${Hh - pb}" stroke="${C.accent}" stroke-opacity=".5" stroke-dasharray="3 3"/>`;
    svg += `<text class="lbl" x="${X(hv.days_since) + 4}" y="${pt + 10}" fill="${C.accent}">now, day ${hv.days_since}</text>`;
    svg += "</svg>";
    $("cycleChart").innerHTML = svg;
    $("cycleLegend").innerHTML = (hv.cycles || []).map((c) =>
      `<span><i style="background:${c.halving === lastH ? C.accent : "#5a5a5a"}"></i>${c.halving.slice(0, 4)}: top day ${nf0.format(c.top_days_after_halving)}${c.top_confirmed ? "" : " (unconfirmed)"}` +
      `${c.next_bottom_days_after_halving ? `, bottom day ${nf0.format(c.next_bottom_days_after_halving)}` : ""}</span>`).join("") +
      `<span>● = cycle top</span>`;
  }

  // ---------------------------------------------------------------- backtest
  function renderBacktest(L, H) {
    $("phaseLegend").innerHTML = [1, 2, 3, 4, 5].map((n) =>
      `<span><i style="background:${PHASE_BG[n].replace(/0\.\d+\)$/, "0.7)")}"></i>${n} ${esc(L.phase_names[n])}</span>`).join("") +
      helpBtn("phase", "Phases explained");
    const weeks = H.weeks;
    const phaseData = weeks.map((w) => ({ time: w.t, value: 1, color: PHASE_BG[w.p] || "rgba(0,0,0,0)" }));
    const phaseBg = (chart) => {
      const s = chart.addHistogramSeries({ ...silent, priceScaleId: "ph", base: 0 });
      chart.priceScale("ph").applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
      s.setData(phaseData);
      return s;
    };

    const a = LWC.createChart($("btPrice"), baseChartOpts({
      rightPriceScale: { borderColor: C.border, mode: LWC.PriceScaleMode.Logarithmic, minimumWidth: 70 },
      timeScale: { visible: false, borderColor: C.border, lockVisibleTimeRangeOnResize: true },
    }));
    phaseBg(a);
    a.addLineSeries({ ...silent, color: "#e5e5e5", lineWidth: 1.5, lastValueVisible: true })
      .setData(weeks.map((w) => ({ time: w.t, value: w.c })));

    const b = LWC.createChart($("btScore"), baseChartOpts({
      rightPriceScale: { borderColor: C.border, minimumWidth: 70, scaleMargins: { top: 0.08, bottom: 0.08 } },
      localization: { locale: LOC, priceFormatter: (p) => sgn(p) },
    }));
    phaseBg(b);
    const sc = b.addBaselineSeries({
      ...silent, lastValueVisible: true, baseValue: { type: "price", price: 0 },
      topLineColor: C.buy, topFillColor1: "rgba(34,197,94,0.25)", topFillColor2: "rgba(34,197,94,0.02)",
      bottomLineColor: C.sell, bottomFillColor1: "rgba(239,68,68,0.02)", bottomFillColor2: "rgba(239,68,68,0.25)",
      lineWidth: 1.5, priceFormat: { type: "price", precision: 0, minMove: 1 },
    });
    sc.setData(weeks.filter((w) => w.s != null).map((w) => ({ time: w.t, value: w.s })));
    sc.createPriceLine({ price: 0, color: "#3a3a3a", lineWidth: 1, lineStyle: LWC.LineStyle.Solid, axisLabelVisible: false });

    // keep the two time axes in sync
    let syncing = false;
    const sync = (src, dst) => src.timeScale().subscribeVisibleLogicalRangeChange((r) => {
      if (syncing || !r) return;
      syncing = true; dst.timeScale().setVisibleLogicalRange(r); syncing = false;
    });
    sync(a, b); sync(b, a);
    afterLayout(() => b.timeScale().fitContent());

    const tr = (H.transitions || []).slice().reverse();
    $("trCount").innerHTML = `(${tr.length}) ${helpBtn("transitions")}`;
    $("trBody").innerHTML = tr.map((t) =>
      `<tr><td class="num">${fdate(t.week_start)}</td>` +
      `<td><span class="pill" style="background:${PHASE_BG[t.from]}">${PHASE_SHORT[t.from]}</span> → ` +
      `<span class="pill" style="background:${PHASE_BG[t.to]}">${PHASE_SHORT[t.to]}</span></td>` +
      `<td class="num">${usd(t.price)}</td><td class="num">${sgn(t.total)}</td></tr>`).join("");
  }

  // ---------------------------------------------------------------- help popups
  function bindInfo() {
    const dlg = $("infoDialog");
    document.addEventListener("click", (e) => {
      const btn = e.target.closest(".info, .help");
      if (btn) {
        e.preventDefault();
        const item = INFO[btn.dataset.info] || { title: btn.dataset.info, body: ["No explanation available."] };
        $("infoTitle").textContent = item.title;
        $("infoBody").innerHTML = item.body.map((b) => Array.isArray(b)
          ? `<ul>${b.map((li) => `<li>${esc(li)}</li>`).join("")}</ul>`
          : `<p>${esc(b)}</p>`).join("");
        dlg.showModal();
        return;
      }
      if (e.target === dlg) dlg.close(); // click on the backdrop
    });
  }

  // ---------------------------------------------------------------- start
  async function main() {
    try {
      const [L, H] = await Promise.all([getJSON("data/latest.json"), getJSON("data/history.json")]);
      INFO = L.info || {};
      bindInfo();
      renderHeader(L);
      renderHero(L);
      renderZones(L);
      renderLayers(L);
      if (!LWC) throw new Error("The chart library failed to load");
      renderPriceChart(L, H);
      renderCycles(L, H);
      renderBacktest(L, H);
    } catch (err) {
      console.error(err);
      $("warnings").insertAdjacentHTML("beforeend", `<p class="warn">Failed to load the page: ${esc(err.message)}</p>`);
    }
  }
  main();
})();
