/* global document, fetch, setInterval */

const ASSET_META = {
  BTC: { name: "Bitcoin", color: "#f7931a", cls: "btc" },
  ETH: { name: "Ethereum", color: "#627eea", cls: "eth" },
  XRP: { name: "XRP", color: "#00aae4", cls: "xrp" },
};

let state = {
  coins: [],
  selected: "BTC",
  loading: false,
};

const $ = (id) => document.getElementById(id);

function fmtPrice(n, asset) {
  if (n == null || Number.isNaN(n)) return "—";
  const x = Number(n);
  if (asset === "XRP" || x < 10) {
    return x.toLocaleString("en-US", { minimumFractionDigits: 4, maximumFractionDigits: 5 });
  }
  if (x < 100) {
    return x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }
  return x.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 2 });
}

function fmtPct(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${Number(n).toFixed(digits)}%`;
}

function fmtNum(n, digits = 2) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("en-US", {
    maximumFractionDigits: digits,
  });
}

/** Compact USD: $1.2B / $45.3M / $12.4K */
function fmtUsd(n, compact = true) {
  if (n == null || Number.isNaN(Number(n))) return "—";
  const x = Number(n);
  const abs = Math.abs(x);
  if (!compact) {
    return (
      "$" +
      x.toLocaleString("en-US", {
        maximumFractionDigits: abs >= 100 ? 0 : 2,
      })
    );
  }
  const sign = x < 0 ? "-" : "";
  const v = abs;
  if (v >= 1e12) return `${sign}$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `${sign}$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `${sign}$${(v / 1e6).toFixed(2)}M`;
  if (v >= 1e3) return `${sign}$${(v / 1e3).toFixed(1)}K`;
  return `${sign}$${v.toFixed(2)}`;
}

function fmtFunding(rate) {
  if (rate == null || Number.isNaN(Number(rate))) return "—";
  return fmtPct(Number(rate) * 100, 4);
}

function fmtTime(ms) {
  if (!ms) return "—";
  return new Date(ms).toLocaleString("ko-KR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function confClass(score) {
  if (score >= 65) return "high";
  if (score >= 45) return "mid";
  return "low";
}

function sparkline(points, color) {
  if (!points || points.length < 2) return "";
  const w = 320;
  const h = 48;
  const vals = points.map((p) => p.c);
  const min = Math.min(...vals);
  const max = Math.max(...vals);
  const range = max - min || 1;
  const coords = vals
    .map((v, i) => {
      const x = (i / (vals.length - 1)) * w;
      const y = h - ((v - min) / range) * (h - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const last = vals[vals.length - 1];
  const first = vals[0];
  const stroke = last >= first ? "#22c55e" : "#ef4444";
  return `
    <svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none">
      <polyline fill="none" stroke="${stroke}" stroke-width="2" points="${coords}" />
    </svg>
  `;
}

function levelList(items, side) {
  if (!items || !items.length) {
    return `<li class="level-item"><span class="level-price">데이터 없음</span></li>`;
  }
  return items
    .map(
      (lv) => `
      <li class="level-item">
        <span class="level-price" style="color:${side === "support" ? "var(--green)" : "var(--red)"}">
          ${fmtPrice(lv.price)}
        </span>
        <span class="level-meta">
          <span class="tag ${lv.strength}">${lv.strength === "major" ? "주요" : "근거리"}</span>
          <span>${fmtPct(lv.distance_pct)}</span>
        </span>
      </li>`
    )
    .join("");
}

function exchangeCard(def, ex) {
  if (!ex || !ex.ok) {
    return `
      <div class="ex-panel" style="--ex-accent:${def.accent}">
        <div class="ex-panel-head">
          <span class="ex-dot" style="background:${def.accent}"></span>
          <strong>${def.name}</strong>
        </div>
        <p class="ex-fail">${ex?.error || "데이터 없음"}</p>
      </div>`;
  }

  const fund = Number(ex.funding_rate);
  const fundColor = fund >= 0 ? "var(--green)" : "var(--red)";
  const hasLs = ex.global_long_pct != null && ex.global_short_pct != null;
  const mark = ex.mark_price ?? ex.price;

  let lsBlock = "";
  if (hasLs) {
    lsBlock = `
      <div class="ex-ls">
        <div class="ls-labels" style="margin-bottom:0.35rem;font-size:0.78rem">
          <span class="long">롱 ${Number(ex.global_long_pct).toFixed(1)}% · ${fmtUsd(ex.long_notional_usd)}</span>
          <span class="short">숏 ${Number(ex.global_short_pct).toFixed(1)}% · ${fmtUsd(ex.short_notional_usd)}</span>
        </div>
        <div class="ls-bar" style="height:10px">
          <div class="long-fill" style="width:${ex.global_long_pct}%"></div>
          <div class="short-fill" style="width:${ex.global_short_pct}%"></div>
        </div>
      </div>`;
  } else {
    lsBlock = `
      <div class="ex-ls-empty">
        계정 롱/숏 비율은 이 거래소 공개 API에 없음
      </div>`;
  }

  return `
    <div class="ex-panel" style="--ex-accent:${def.accent}">
      <div class="ex-panel-head">
        <span class="ex-dot" style="background:${def.accent}"></span>
        <strong>${def.name}</strong>
        <span class="ex-sym">${ex.symbol || ""}</span>
      </div>
      <div class="ex-oi">
        <span class="ex-oi-label">미결제약정 (OI)</span>
        <span class="ex-oi-val">${fmtUsd(ex.oi_usd)}</span>
        <span class="ex-oi-base">${ex.oi_base != null ? fmtNum(ex.oi_base, 2) + " 계약" : ""}</span>
      </div>
      <div class="ex-metrics">
        <div>
          <label>마크가</label>
          <value>$${fmtPrice(mark)}</value>
        </div>
        <div>
          <label>펀딩</label>
          <value style="color:${fundColor}">${fmtFunding(ex.funding_rate)}</value>
        </div>
        <div>
          <label>24h 대금</label>
          <value>${fmtUsd(ex.volume_24h_usd)}</value>
        </div>
      </div>
      ${lsBlock}
    </div>`;
}

function exchangeRows(exchanges, totalOi, primarySource) {
  const defs = [
    { key: "binance", name: "Binance", accent: "#f0b90b" },
    { key: "bybit", name: "Bybit", accent: "#f7a600" },
    { key: "hyperliquid", name: "Hyperliquid", accent: "#0d9488" },
    { key: "kraken", name: "Kraken", accent: "#5741d9" },
  ];

  // Bybit 카드: primary가 아니면서 "미조회"면 숨김
  const showDefs = defs.filter((d) => {
    if (d.key !== "bybit") return true;
    const ex = exchanges?.bybit;
    if (primarySource === "bybit") return true;
    if (ex && ex.ok) return true;
    // primary binance 일 때 bybit 미조회 메시지는 숨김
    return ex && ex.ok !== false && !String(ex.error || "").includes("미조회");
  });

  const panels = showDefs.map((d) => exchangeCard(d, exchanges?.[d.key])).join("");

  const hl = exchanges?.hyperliquid;
  const hlOk = hl && hl.ok;
  const srcNote =
    primarySource === "bybit"
      ? "현재 서버 지역에서 Binance가 막혀 Bybit 롱/숏·차트를 사용 중입니다."
      : "롱/숏·차트 기본 소스: Binance (실패 시 Bybit 자동 전환).";

  return `
    <div class="exchange-card">
      <div class="ex-total card" style="margin-bottom:0.85rem">
        OI 합계(주요+HL+Kraken) <strong>${fmtUsd(totalOi)}</strong>
        <span class="muted"> · primary: ${(primarySource || "—").toUpperCase()}</span>
        ${
          hlOk
            ? `<div class="ex-hl-highlight">Hyperliquid OI <strong>${fmtUsd(hl.oi_usd)}</strong> · 펀딩 <strong style="color:${Number(hl.funding_rate) >= 0 ? "var(--green)" : "var(--red)"}">${fmtFunding(hl.funding_rate)}</strong> · 24h <strong>${fmtUsd(hl.volume_24h_usd)}</strong></div>`
            : ""
        }
      </div>
      <div class="ex-grid ex-grid-4">
        ${panels}
      </div>
      <p class="ex-note">
        ${srcNote}
        Hyperliquid·Kraken은 OI·펀딩·24h 대금. 계정 롱/숏 % 는 Binance 또는 Bybit.
      </p>
    </div>`;
}

function strategyCard(s, asset) {
  return `
    <div class="card strategy-card ${s.side}">
      <div class="strategy-head">
        <div>
          <h3>${s.label}</h3>
          <div style="font-size:0.78rem;color:var(--text-muted);margin-top:0.2rem">${s.entry_type}</div>
        </div>
        <span class="conf ${confClass(s.confidence)}">신뢰도 ${s.confidence} · ${s.confidence_label}</span>
      </div>

      <div class="trade-row">
        <div class="k">진입가</div>
        <div class="v">${fmtPrice(s.entry, asset)}</div>
        <div class="note">${s.entry_type}</div>
      </div>
      <div class="trade-row">
        <div class="k">손절 (SL)</div>
        <div class="v" style="color:var(--red)">${fmtPrice(s.stop_loss, asset)}</div>
        <div class="note">${s.sl_note}</div>
      </div>
      <div class="trade-row">
        <div class="k">익절 1 (TP1)</div>
        <div class="v" style="color:var(--green)">${fmtPrice(s.take_profit_1, asset)}</div>
        <div class="note">${s.tp1_note} · R:R ${s.risk_reward_1}</div>
      </div>
      <div class="trade-row">
        <div class="k">익절 2 (TP2)</div>
        <div class="v" style="color:var(--green)">${fmtPrice(s.take_profit_2, asset)}</div>
        <div class="note">${s.tp2_note} · R:R ${s.risk_reward_2}</div>
      </div>
      <div class="trade-row">
        <div class="k">무효화</div>
        <div class="v" style="font-family:var(--font);font-weight:500;font-size:0.85rem">${s.invalidation}</div>
      </div>

      <div class="rationale">
        <strong style="color:var(--text)">근거</strong><br/>
        ${s.rationale}<br/><br/>
        <span style="color:var(--text-dim)">${s.position_hint}</span>
      </div>
    </div>
  `;
}

function renderOverview() {
  const el = $("overview");
  el.innerHTML = state.coins
    .map((c) => {
      const a = c.analysis;
      const s = a.sentiment;
      const meta = ASSET_META[c.asset] || {};
      const longPct = s.global_long_pct;
      const shortPct = s.global_short_pct;
      const chg = a.change_24h_pct;
      return `
        <div class="ov-card ${state.selected === c.asset ? "active" : ""}" data-asset="${c.asset}">
          <div class="ov-top">
            <span class="ov-name" style="color:${meta.color || "inherit"}">${c.asset}</span>
            <span class="change ${chg >= 0 ? "up" : "down"}" style="font-size:0.75rem">${fmtPct(chg)}</span>
          </div>
          <div class="ov-price">${fmtPrice(a.price, c.asset)}</div>
          <div class="ov-ls">
            <div style="width:${longPct}%;background:#22c55e"></div>
            <div style="width:${shortPct}%;background:#ef4444"></div>
          </div>
          <div class="ov-meta">
            <span>롱 ${longPct.toFixed(1)}%</span>
            <span>${s.label}</span>
            <span>숏 ${shortPct.toFixed(1)}%</span>
          </div>
        </div>`;
    })
    .join("");

  el.querySelectorAll(".ov-card").forEach((card) => {
    card.addEventListener("click", () => {
      state.selected = card.dataset.asset;
      render();
    });
  });
}

function renderTabs() {
  const el = $("tabs");
  el.innerHTML = state.coins
    .map((c) => {
      const meta = ASSET_META[c.asset] || {};
      return `
        <button class="tab ${state.selected === c.asset ? "active" : ""}" data-asset="${c.asset}" type="button">
          <span class="dot ${meta.cls || ""}"></span>
          ${c.asset} · ${meta.name || c.symbol}
        </button>`;
    })
    .join("");

  el.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      state.selected = tab.dataset.asset;
      render();
    });
  });
}

function renderDetail() {
  const coin = state.coins.find((c) => c.asset === state.selected);
  if (!coin) {
    $("detail").innerHTML = "";
    return;
  }

  const a = coin.analysis;
  const s = a.sentiment;
  const lv = a.levels;
  const st = coin.strategies;
  const chg = a.change_24h_pct;
  const pref = st.preference;

  const prefIcon = pref.preferred === "long" ? "📈" : pref.preferred === "short" ? "📉" : "⚖️";
  const prefTitle =
    pref.preferred === "long"
      ? "지금은 롱 쪽이 더 설득력 있음"
      : pref.preferred === "short"
        ? "지금은 숏 쪽이 더 설득력 있음"
        : "롱·숏 팽팽 — 관망하거나 작게";

  const pivots = lv.pivots || {};
  const emas = lv.emas || {};
  const exchanges = a.exchanges || {};

  $("detail").innerHTML = `
    <div class="grid-top">
      <div class="card">
        <div class="card-title">${coin.asset} 현재가 · 24시간</div>
        <div class="price-row">
          <span class="price">$${fmtPrice(a.price, coin.asset)}</span>
          <span class="change ${chg >= 0 ? "up" : "down"}">${fmtPct(chg)}</span>
        </div>
        ${sparkline(a.klines_1h_spark)}
        <div class="stat-grid">
          <div class="stat">
            <label>24h 고가</label>
            <value>$${fmtPrice(a.high_24h, coin.asset)}</value>
          </div>
          <div class="stat">
            <label>24h 저가</label>
            <value>$${fmtPrice(a.low_24h, coin.asset)}</value>
          </div>
          <div class="stat">
            <label>Binance OI</label>
            <value>${fmtUsd(a.open_interest_usd || s.oi_usd)}</value>
          </div>
          <div class="stat">
            <label>펀딩비 (BN)</label>
            <value style="color:${s.funding_rate >= 0 ? "var(--green)" : "var(--red)"}">${fmtPct(s.funding_rate_pct, 4)}</value>
          </div>
          <div class="stat">
            <label>ATR (4h)</label>
            <value>$${fmtPrice(lv.atr_4h, coin.asset)}</value>
          </div>
          <div class="stat">
            <label>3거래소 OI 합</label>
            <value>${fmtUsd(a.total_oi_usd)}</value>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-title">${(a.primary_source || s.ls_source || "binance").toUpperCase()} 계정 롱 · 숏 비율 · 액수</div>
        <div class="ls-wrap">
          <div class="ls-labels">
            <span class="long">롱 ${s.global_long_pct.toFixed(2)}% · ${fmtUsd(s.long_notional_usd)}</span>
            <span class="short">숏 ${s.global_short_pct.toFixed(2)}% · ${fmtUsd(s.short_notional_usd)}</span>
          </div>
          <div class="ls-bar">
            <div class="long-fill" style="width:${s.global_long_pct}%"></div>
            <div class="short-fill" style="width:${s.global_short_pct}%"></div>
          </div>
          <div class="ls-amounts">
            <div class="ls-amt long">
              <span class="ls-amt-label">추정 롱 규모</span>
              <span class="ls-amt-val">${fmtUsd(s.long_notional_usd, false)}</span>
            </div>
            <div class="ls-amt mid">
              <span class="ls-amt-label">OI 총액</span>
              <span class="ls-amt-val">${fmtUsd(s.oi_usd, false)}</span>
            </div>
            <div class="ls-amt short">
              <span class="ls-amt-label">추정 숏 규모</span>
              <span class="ls-amt-val">${fmtUsd(s.short_notional_usd, false)}</span>
            </div>
          </div>
        </div>

        <div class="ratio-metrics">
          <div class="metric">
            <label>글로벌 L/S 비율</label>
            <div class="val">${Number(s.global_ls_ratio ?? 0).toFixed(4)}</div>
          </div>
          <div class="metric">
            <label>탑트레이더 계정 L/S</label>
            <div class="val">${s.top_account_ls_ratio != null ? Number(s.top_account_ls_ratio).toFixed(4) : "—"}</div>
          </div>
          <div class="metric">
            <label>탑 포지션 롱 · 규모</label>
            <div class="val">${Number(s.top_position_long_pct ?? 0).toFixed(1)}% · ${fmtUsd(s.pos_long_notional_usd)}</div>
          </div>
          <div class="metric">
            <label>테이커 매수 / 매도 (1h)</label>
            <div class="val">${fmtUsd(s.taker_buy_usd)} / ${fmtUsd(s.taker_sell_usd)}</div>
          </div>
        </div>

        <div class="bias-badge ${s.bias}">● ${s.label} · 점수 ${s.composite_score}</div>
        ${s.crowded_long ? `<span class="flag danger">⚠ 롱 과밀 (청산/되돌림 주의)</span>` : ""}
        ${s.crowded_short ? `<span class="flag warn">⚠ 숏 과밀 (숏스퀴즈 주의)</span>` : ""}
        <p class="ls-hint">액수 = OI × 계정(또는 탑 포지션) 비율 추정. 선물 OI는 계약상 롱=숏 매칭.</p>
      </div>
    </div>

    <h2 class="section-title">거래소별 포지션 · 유동성</h2>
    ${exchangeRows(exchanges, a.total_oi_usd, a.primary_source || coin.primary_source)}

    <h2 class="section-title">지지 · 저항 레벨</h2>
    <div class="levels-grid">
      <div class="card">
        <div class="card-title">지지선 (Supports)</div>
        <ul class="level-list">${levelList(lv.supports, "support")}</ul>
      </div>
      <div class="card">
        <div class="card-title">저항선 (Resistances)</div>
        <ul class="level-list">${levelList(lv.resistances, "resistance")}</ul>
      </div>
    </div>

    <div class="card" style="margin-bottom:1rem">
      <div class="card-title">피봇 · 피보 · EMA 한눈에</div>
      <div class="pivot-row">
        <span class="pivot-chip">P <strong>${fmtPrice(pivots.pivot, coin.asset)}</strong></span>
        <span class="pivot-chip">S1 <strong>${fmtPrice(pivots.s1, coin.asset)}</strong></span>
        <span class="pivot-chip">S2 <strong>${fmtPrice(pivots.s2, coin.asset)}</strong></span>
        <span class="pivot-chip">R1 <strong>${fmtPrice(pivots.r1, coin.asset)}</strong></span>
        <span class="pivot-chip">R2 <strong>${fmtPrice(pivots.r2, coin.asset)}</strong></span>
        <span class="pivot-chip">EMA20 <strong>${fmtPrice(emas.ema20, coin.asset)}</strong></span>
        <span class="pivot-chip">EMA50 <strong>${fmtPrice(emas.ema50, coin.asset)}</strong></span>
        <span class="pivot-chip">EMA200 <strong>${fmtPrice(emas.ema200, coin.asset)}</strong></span>
        <span class="pivot-chip">Fib 0.5 <strong>${fmtPrice(lv.fib?.["0.5"], coin.asset)}</strong></span>
        <span class="pivot-chip">Fib 0.618 <strong>${fmtPrice(lv.fib?.["0.618"], coin.asset)}</strong></span>
      </div>
    </div>

    <h2 class="section-title">롱 · 숏 시나리오 (진입 / SL / TP)</h2>
    <div class="pref-banner">
      <div class="icon">${prefIcon}</div>
      <div>
        <strong>${prefTitle}</strong>
        <p>${pref.note}</p>
      </div>
    </div>
    <div class="strategy-grid">
      ${strategyCard(st.long, coin.asset)}
      ${strategyCard(st.short, coin.asset)}
    </div>
  `;

  $("disclaimer").textContent = st.disclaimer;
}

function render() {
  renderOverview();
  renderTabs();
  renderDetail();
}

async function loadData(force = false) {
  if (state.loading) return;
  state.loading = true;

  const btn = $("refreshBtn");
  btn.disabled = true;
  $("refreshIcon").textContent = "…";

  if (!state.coins.length) {
    $("loading").classList.remove("hidden");
    $("app").classList.add("hidden");
  }
  $("errorBox").classList.add("hidden");

  try {
    const url = force ? "/api/analyze?refresh=true" : "/api/analyze";
    const res = await fetch(url);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const d = err.detail;
      const msg =
        typeof d === "string"
          ? d
          : d?.message
            ? `${d.message}${d.errors ? " · " + JSON.stringify(d.errors) : ""}`
            : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    const data = await res.json();
    state.coins = data.coins || [];
    if (!state.coins.find((c) => c.asset === state.selected) && state.coins.length) {
      state.selected = state.coins[0].asset;
    }

    $("updatedAt").textContent = data.cached
      ? `캐시 · ${fmtTime(data.generated_at)} (${data.cache_age_sec}s)`
      : `갱신 · ${fmtTime(data.generated_at)}`;

    if (data.errors?.length) {
      $("errorBox").textContent =
        "일부 자산 조회 실패: " + data.errors.map((e) => `${e.asset}: ${e.error}`).join(" · ");
      $("errorBox").classList.remove("hidden");
    }

    $("loading").classList.add("hidden");
    $("app").classList.remove("hidden");
    render();
  } catch (e) {
    $("loading").classList.add("hidden");
    $("errorBox").textContent = `데이터 로드 실패: ${e.message}`;
    $("errorBox").classList.remove("hidden");
    if (!state.coins.length) {
      $("app").classList.add("hidden");
    }
  } finally {
    state.loading = false;
    btn.disabled = false;
    $("refreshIcon").textContent = "↻";
  }
}

$("refreshBtn").addEventListener("click", () => loadData(true));

loadData(false);
// Auto refresh every 60s
setInterval(() => loadData(false), 60000);
