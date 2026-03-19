"""
Options Trading Assistant — Web UI
Run with:  streamlit run app.py
"""

import sys
import os
import json
import sqlite3
import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wfo_optimizer import walk_forward, load_last_results, WFO_RESULTS_FILE
from options_chatbot import (
    DEFAULT_WATCHLIST,
    RISK_FREE_RATE,
    STRATEGY_PROFILE,
    _get_system_prompt,
    _build_tool_schema_text,
    _build_prompt,
    _call_claude_cli,
    _parse_tool_calls,
    _strip_tool_calls,
    _trim_history,
    run_tool,
    risk_settings,
    _load_predictions,
    log_prediction,
    backfill_predictions,
    backtest_strategy,
    evaluate_trade_signal,
    _get_market_regime,
    _calculate_confidence_score,
    scan_daily_top_trades,
    _save_predictions,
    _save_profile,
)

# ── Database ───────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );
        """)


def db_create_session(title: str = "New conversation") -> str:
    sid = uuid.uuid4().hex[:12]
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (sid, title, now, now),
        )
    return sid


def db_rename_session(session_id: str, title: str):
    with _db() as conn:
        conn.execute(
            "UPDATE sessions SET title=?, updated_at=? WHERE id=?",
            (title[:80], datetime.now().isoformat(), session_id),
        )


def db_save_messages(session_id: str, messages: list):
    now = datetime.now().isoformat()
    with _db() as conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.executemany(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            [(session_id, m["role"], json.dumps(m["content"]), now) for m in messages],
        )
        conn.execute(
            "UPDATE sessions SET updated_at=? WHERE id=?",
            (now, session_id),
        )


def db_load_messages(session_id: str) -> list:
    with _db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM messages WHERE session_id=? ORDER BY id",
            (session_id,),
        ).fetchall()
    return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]


def db_list_sessions(limit: int = 60) -> list:
    with _db() as conn:
        rows = conn.execute(
            "SELECT id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def db_delete_session(session_id: str):
    with _db() as conn:
        conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
        conn.execute("DELETE FROM sessions WHERE id=?", (session_id,))


# ── Init ───────────────────────────────────────────────────────────────────────

init_db()

st.set_page_config(
    page_title="Options Trading Assistant",
    page_icon="📈",
    layout="wide",
)

# ── Session state ──────────────────────────────────────────────────────────────

def _build_system() -> str:
    """Always rebuild from STRATEGY_PROFILE so applied optimizer params take effect immediately."""
    return _get_system_prompt().format(
        watchlist=", ".join(DEFAULT_WATCHLIST),
        datetime=datetime.now().strftime("%A, %Y-%m-%d %H:%M ET"),
        rfr=round(RISK_FREE_RATE * 100, 1),
    ) + "\n\n## Tool Calling\n" + _build_tool_schema_text()


def load_session(session_id: str):
    st.session_state.session_id = session_id
    st.session_state.conversation = db_load_messages(session_id)
    st.session_state.system = _build_system()


def new_session():
    sid = db_create_session("New conversation")
    st.session_state.session_id = sid
    st.session_state.conversation = []
    st.session_state.system = _build_system()


# Bootstrap on first load — always start a fresh conversation
if "session_id" not in st.session_state:
    new_session()

if "system" not in st.session_state:
    st.session_state.system = _build_system()

# ── Sidebar ────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 📈 Options Assistant")
    st.caption("Claude Code · Yahoo Finance · ~15-min delayed")
    st.markdown("---")

    # Account / risk metrics
    account = risk_settings.get("account_size", 0)
    if account:
        st.metric("Account Size", f"${account:,.0f}")
        lo = risk_settings["min_trade_risk_pct"] / 100
        hi = risk_settings["max_trade_risk_pct"] / 100
        col1, col2 = st.columns(2)
        col1.metric("Min/Trade", f"${account * lo:,.0f}")
        col2.metric("Max/Trade", f"${account * hi:,.0f}")
        col1b, col2b = st.columns(2)
        col1b.metric("Stop-Loss", f"{risk_settings['stop_loss_pct']:.0f}%")
        max_dd = risk_settings.get("max_drawdown_pct", 15.0) / 100
        col2b.metric("Max Drawdown", f"${account * max_dd:,.0f}")
    else:
        st.info("Tell the bot your account size to unlock position sizing.")

    st.markdown("---")

    # Conversation controls
    if st.button("➕ New conversation", use_container_width=True):
        new_session()
        st.rerun()

    st.markdown("---")

    # Past sessions
    st.markdown("**Past conversations**")
    sessions = db_list_sessions()
    for s in sessions:
        updated = s["updated_at"][:10]
        label = f"{s['title'][:38]}  \n{updated}"
        is_current = s["id"] == st.session_state.session_id
        if is_current:
            st.markdown(f"**→ {s['title'][:38]}**  \n{updated}")
        else:
            col_a, col_b = st.columns([5, 1])
            if col_a.button(label, key=f"sess_{s['id']}", use_container_width=True):
                load_session(s["id"])
                st.rerun()
            if col_b.button("🗑", key=f"del_{s['id']}"):
                db_delete_session(s["id"])
                if is_current:
                    new_session()
                st.rerun()

    st.markdown("---")

    # Quick prompts
    st.markdown("**Quick prompts**")
    quick = [
        "What's the market setup right now?",
        "Find me the best call to double my money this week",
        "Scan for hot options across the watchlist",
        "Show my paper trading journal",
        "What are my current risk settings?",
    ]
    for q in quick:
        if st.button(q, use_container_width=True, key=f"quick_{q}"):
            st.session_state._pending_prompt = q
            st.rerun()

    st.markdown("---")
    st.caption("⚠️ Not financial advice. Options trading involves substantial risk of loss.")

# ── Header ─────────────────────────────────────────────────────────────────────

st.markdown("# 📈 Options Trading Assistant")
st.caption("Powered by Claude Code · 14 tools · Large-cap single-leg options · 0–21 DTE")
st.markdown("---")

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab_chat, tab_predictions, tab_lab = st.tabs(
    ["💬 Chat", "📊 Predictions", "🔬 Strategy Lab"]
)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: Chat
# ══════════════════════════════════════════════════════════════════════════════

with tab_chat:

    # ── Render chat history ──────────────────────────────────────────────────

    for msg in st.session_state.conversation:
        role = msg["role"]
        content = msg["content"]

        if role == "user":
            if isinstance(content, list) and content and isinstance(content[0], dict) \
                    and content[0].get("type") == "tool_result":
                continue
            with st.chat_message("user"):
                st.markdown(content if isinstance(content, str) else "")

        elif role == "assistant":
            if isinstance(content, str):
                if content.strip():
                    with st.chat_message("assistant"):
                        st.markdown(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text = _strip_tool_calls(item.get("text", ""))
                        if text.strip():
                            with st.chat_message("assistant"):
                                st.markdown(text)

    # ── Handle quick-prompt button clicks ────────────────────────────────────

    pending = st.session_state.pop("_pending_prompt", None)

    # ── Chat input ────────────────────────────────────────────────────────────

    user_input = st.chat_input("Ask about options, request a trade, or backtest a strategy…") or pending

    if user_input:
        if not st.session_state.conversation:
            db_rename_session(st.session_state.session_id, user_input[:80])

        st.session_state.conversation.append({"role": "user", "content": user_input})

        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            text_placeholder = st.empty()
            conversation = st.session_state.conversation[:]

            for _ in range(10):
                with st.spinner("Thinking…"):
                    raw = _call_claude_cli(
                        _build_prompt(_trim_history(conversation)),
                        system=st.session_state.system,
                    )

                tool_calls = _parse_tool_calls(raw)
                visible = _strip_tool_calls(raw)

                if visible.strip():
                    text_placeholder.markdown(visible)

                if not tool_calls:
                    conversation.append({"role": "assistant", "content": visible or raw})
                    break

                tool_results = []
                for call in tool_calls:
                    name = call.get("tool", "unknown")
                    args = call.get("args", {})
                    with st.status(f"🔍 {name}", state="running") as status:
                        result = run_tool(name, args)
                        status.update(label=f"✅ {name}", state="complete", expanded=False)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": call["_id"],
                        "content": result,
                    })

                conversation.append({"role": "assistant", "content": [{"type": "text", "text": raw}]})
                conversation.append({"role": "user", "content": tool_results})

            st.session_state.conversation = conversation

        db_save_messages(st.session_state.session_id, st.session_state.conversation)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: Predictions
# ══════════════════════════════════════════════════════════════════════════════

# ── Sector sentiment helpers ──────────────────────────────────────────────────

_SECTORS = [
    ("Technology",             "XLK"),
    ("Healthcare",             "XLV"),
    ("Financials",             "XLF"),
    ("Energy",                 "XLE"),
    ("Consumer Discretionary", "XLY"),
    ("Consumer Staples",       "XLP"),
    ("Industrials",            "XLI"),
    ("Materials",              "XLB"),
    ("Real Estate",            "XLRE"),
    ("Utilities",              "XLU"),
    ("Communication Services", "XLC"),
]

_SENTIMENT_COLORS = {
    "Very Bullish": "#1a7f3c",
    "Bullish":      "#28a745",
    "Neutral":      "#6c757d",
    "Bearish":      "#e07b00",
    "Very Bearish": "#c0392b",
}

_SENTIMENT_ICONS = {
    "Very Bullish": "⬆⬆",
    "Bullish":      "⬆",
    "Neutral":      "➡",
    "Bearish":      "⬇",
    "Very Bearish": "⬇⬇",
}


def _score_to_sentiment(score: float) -> str:
    if score >= 2.0:  return "Very Bullish"
    if score >= 0.8:  return "Bullish"
    if score > -0.8:  return "Neutral"
    if score > -2.0:  return "Bearish"
    return "Very Bearish"


def _sentiment_for_window(closes: "pd.Series", window: int) -> tuple[str, float]:
    """Return (sentiment label, return_pct) for a lookback window."""
    if len(closes) < window + 5:
        return "Neutral", 0.0
    recent    = float(closes.iloc[-1])
    start     = float(closes.iloc[-window])
    ret_pct   = (recent / start - 1) * 100
    sma       = float(closes.iloc[-window:].mean())
    above_sma = recent > sma

    # Trend slope (normalised % per day)
    x     = np.arange(min(window, len(closes)))
    y     = closes.iloc[-min(window, len(closes)):].values.astype(float)
    slope = float(np.polyfit(x, y, 1)[0]) / (float(y.mean()) + 1e-9) * 100

    score = 0.0
    if   ret_pct >  15: score += 2.0
    elif ret_pct >   5: score += 1.0
    elif ret_pct >  -5: score += 0.0
    elif ret_pct > -15: score -= 1.0
    else:               score -= 2.0

    score += 0.5 if above_sma else -0.5
    score += 0.5 if slope > 0.05 else (-0.5 if slope < -0.05 else 0.0)

    return _score_to_sentiment(score), round(ret_pct, 1)


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_sector_sentiments() -> list[dict]:
    """Fetch all 11 sector ETFs and compute 3-timeframe sentiment. Cached 1 hr."""
    import yfinance as yf
    rows = []
    tickers = [etf for _, etf in _SECTORS]
    hist    = yf.download(tickers, period="760d", progress=False, auto_adjust=True)["Close"]
    for sector, etf in _SECTORS:
        try:
            closes = hist[etf].dropna()
            if len(closes) < 30:
                raise ValueError("insufficient data")
            nt_sent, nt_ret  = _sentiment_for_window(closes, 21)    # ~1 month
            mt_sent, mt_ret  = _sentiment_for_window(closes, 126)   # ~6 months
            lt_sent, lt_ret  = _sentiment_for_window(closes, 252)   # ~1 year
            rows.append({
                "Sector":      sector,
                "ETF":         etf,
                "near_sent":   nt_sent, "near_ret":  nt_ret,
                "med_sent":    mt_sent, "med_ret":   mt_ret,
                "long_sent":   lt_sent, "long_ret":  lt_ret,
            })
        except Exception:
            rows.append({
                "Sector": sector, "ETF": etf,
                "near_sent": "Neutral", "near_ret": 0.0,
                "med_sent":  "Neutral", "med_ret":  0.0,
                "long_sent": "Neutral", "long_ret": 0.0,
            })
    return rows


def _sentiment_badge(sentiment: str, ret_pct: float) -> str:
    color = _SENTIMENT_COLORS.get(sentiment, "#6c757d")
    icon  = _SENTIMENT_ICONS.get(sentiment, "➡")
    sign  = "+" if ret_pct >= 0 else ""
    return (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:4px;font-size:0.82em;font-weight:600;white-space:nowrap">'
        f'{icon} {sentiment}</span>'
        f'<span style="color:{color};font-size:0.78em;margin-left:4px">'
        f'{sign}{ret_pct:.1f}%</span>'
    )


# ── Tab ───────────────────────────────────────────────────────────────────────

with tab_predictions:

    # ══ SECTION 1: Sector Sentiment Dashboard ════════════════════════════════
    hdr_col, ref_col = st.columns([6, 1])
    hdr_col.markdown("### 🗺️ Sector Sentiment Dashboard")
    hdr_col.caption(
        "Live momentum-based sentiment across all 11 GICS sectors. "
        "Scores use price return, SMA position, and trend slope. Cached 1 hr."
    )

    if ref_col.button("🔄", key="refresh_sectors", help="Re-fetch sector data"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("Loading sector data…"):
        sector_rows = _fetch_sector_sentiments()

    # Build styled HTML table
    table_html = """
<style>
.sent-table { width:100%; border-collapse:collapse; font-size:0.88em; }
.sent-table th { background:#1e1e2e; color:#ccc; padding:6px 10px;
                 text-align:left; font-weight:600; border-bottom:2px solid #333; }
.sent-table td { padding:6px 10px; border-bottom:1px solid #2a2a3a; vertical-align:middle; }
.sent-table tr:hover td { background:rgba(255,255,255,0.03); }
.etf-badge { color:#888; font-size:0.8em; margin-left:4px; }
</style>
<table class="sent-table">
<thead><tr>
  <th>Sector</th>
  <th>Near-Term&nbsp;<span style="font-weight:400;color:#888">(0–1 month)</span></th>
  <th>Medium-Term&nbsp;<span style="font-weight:400;color:#888">(1–12 months)</span></th>
  <th>Long-Term&nbsp;<span style="font-weight:400;color:#888">(12–36 months)</span></th>
</tr></thead><tbody>
"""
    for row in sector_rows:
        table_html += (
            f'<tr>'
            f'<td><strong>{row["Sector"]}</strong>'
            f'<span class="etf-badge">{row["ETF"]}</span></td>'
            f'<td>{_sentiment_badge(row["near_sent"], row["near_ret"])}</td>'
            f'<td>{_sentiment_badge(row["med_sent"],  row["med_ret"])}</td>'
            f'<td>{_sentiment_badge(row["long_sent"], row["long_ret"])}</td>'
            f'</tr>'
        )
    table_html += "</tbody></table>"
    st.markdown(table_html, unsafe_allow_html=True)

    # Overall market bias (majority sentiment)
    all_sentiments = [r["near_sent"] for r in sector_rows]
    bull_count = sum(1 for s in all_sentiments if "Bullish" in s)
    bear_count = sum(1 for s in all_sentiments if "Bearish" in s)
    neut_count = len(all_sentiments) - bull_count - bear_count
    bias_color = "#28a745" if bull_count > bear_count else ("#c0392b" if bear_count > bull_count else "#6c757d")
    bias_label = "Bullish Bias" if bull_count > bear_count else ("Bearish Bias" if bear_count > bull_count else "Mixed/Neutral")
    st.markdown(
        f'<div style="margin-top:8px;font-size:0.83em;color:#888">'
        f'Near-term breadth: '
        f'<span style="color:#28a745">▲ {bull_count} bullish</span> · '
        f'<span style="color:#6c757d">➡ {neut_count} neutral</span> · '
        f'<span style="color:#c0392b">▼ {bear_count} bearish</span> — '
        f'<strong style="color:{bias_color}">{bias_label}</strong>'
        f'</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ══ SECTION 2: Daily Top Picks ════════════════════════════════════════════
    st.markdown("### 🎯 Today's Top Trades")

    # ── Next auto-scan countdown banner ───────────────────────────────────────
    def _next_scan_info() -> tuple[str, str]:
        """Return (label, color) describing when the next auto-scan will fire."""
        from zoneinfo import ZoneInfo
        now_et    = datetime.now(ZoneInfo("America/New_York"))
        today_str = now_et.strftime("%Y-%m-%d")
        existing  = _load_predictions()
        today_done = any(
            p.get("entry_date", "")[:10] == today_str and p.get("type") == "daily_scan"
            for p in existing
        )
        # Find next weekday at 10:00 AM ET that hasn't been scanned yet
        from datetime import timedelta as _td
        candidate = now_et.replace(hour=10, minute=0, second=0, microsecond=0)
        # If today is a weekday and scan not done yet and we're before/at 10 AM, it's today
        if now_et.weekday() < 5 and not today_done:
            if now_et < candidate:
                mins_left = int((candidate - now_et).total_seconds() / 60)
                if mins_left < 60:
                    return f"⏱ Auto-scan in {mins_left} min (10:00 AM ET today)", "#e0a800"
                else:
                    hrs = mins_left // 60
                    return f"⏱ Auto-scan in {hrs}h {mins_left % 60}m (10:00 AM ET today)", "#e0a800"
            else:
                return "🔄 Auto-scan due now — will run on next page load", "#28a745"
        # Otherwise find next weekday
        next_day = now_et + _td(days=1)
        while next_day.weekday() >= 5:
            next_day += _td(days=1)
        label = "tomorrow" if (next_day.date() - now_et.date()).days == 1 else next_day.strftime("%A %b %d")
        return f"🕙 Next auto-scan: {label} at 10:00 AM ET", "#6c757d"

    _scan_label, _scan_color = _next_scan_info()
    st.markdown(
        f'<div style="font-size:0.85em;color:{_scan_color};margin-bottom:10px">{_scan_label}</div>',
        unsafe_allow_html=True,
    )

    # ── Auto-scan: run once daily, 30 min after US market open (10:00 AM ET) ──
    def _auto_scan_due() -> bool:
        """Return True if it's a weekday, past 10:00 AM ET, and no picks saved today."""
        from zoneinfo import ZoneInfo
        now_et   = datetime.now(ZoneInfo("America/New_York"))
        if now_et.weekday() >= 5:          # Saturday / Sunday
            return False
        if now_et.hour < 10:               # before 10:00 AM ET
            return False
        today_str = now_et.strftime("%Y-%m-%d")
        existing  = _load_predictions()
        return not any(
            p.get("entry_date", "")[:10] == today_str and p.get("type") == "daily_scan"
            for p in existing
        )

    if _auto_scan_due() and not st.session_state.get("auto_scan_done_today"):
        with st.spinner("Auto-scanning watchlist for today's top picks (10:00 AM ET trigger)…"):
            _auto_picks = scan_daily_top_trades(n_picks=5)
        if _auto_picks:
            _existing = _load_predictions()
            from zoneinfo import ZoneInfo
            _today_str = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
            _new_id = max((p.get("id", 0) for p in _existing), default=0)
            for _p in _auto_picks:
                _new_id += 1
                _rec = dict(_p)
                _rec["id"] = _new_id
                _existing.append(_rec)
            _save_predictions(_existing)
            st.session_state["auto_scan_done_today"] = _today_str
            st.success(f"Auto-scan complete — saved {len(_auto_picks)} picks for {_today_str}.")
            st.rerun()

    scan_col, grade_col, refresh_col = st.columns([3, 2, 1])

    if scan_col.button("🔍 Scan Watchlist for Top 5 Picks", use_container_width=True, key="scan_btn"):
        with st.spinner(f"Scanning {len(DEFAULT_WATCHLIST)} tickers for highest-confidence setups…"):
            st.session_state["daily_picks"] = scan_daily_top_trades(n_picks=5)
        st.rerun()

    if grade_col.button("⚖️ Grade pending picks", use_container_width=True, key="grade_btn"):
        with st.spinner("Grading…"):
            log_prediction(action="grade")
        st.rerun()

    if refresh_col.button("🔄", use_container_width=True, key="refresh_preds", help="Refresh"):
        st.rerun()

    # ── Today's picks ─────────────────────────────────────────────────────────
    picks = st.session_state.get("daily_picks", [])
    if picks:
        st.markdown(
            f"<div style='color:#888;font-size:0.85em;margin-bottom:8px'>"
            f"Scanned {len(DEFAULT_WATCHLIST)} large-cap tickers · "
            f"{datetime.now().strftime('%b %d, %Y %H:%M')} · "
            f"Top {len(picks)} by confidence score</div>",
            unsafe_allow_html=True,
        )

        # Summary table
        scan_rows = []
        for p in picks:
            direction = p.get("direction", "")
            arrow = "📈 CALL" if direction == "call" else "📉 PUT"
            scan_rows.append({
                "Ticker":      p["ticker"],
                "Trade":       arrow,
                "Confidence":  f"{p['confidence']:.1f}%",
                "Tech Score":  f"{p['tech_score']:.0f}/100",
                "IV Rank":     f"{p['iv_rank']:.0f}th pct",
                "Stock Price": f"${p['stock_price']:.2f}",
                "Strike":      f"${p['strike_est']:.2f}",
                "DTE":         p["dte"],
                "Est. Premium":f"${p['est_premium']:.2f}",
                "EV%":         f"{p['ev_pct']:.1f}%",
            })
        st.dataframe(pd.DataFrame(scan_rows), use_container_width=True, hide_index=True)

        # Per-pick signal detail expanders
        for p in picks:
            direction = p.get("direction", "")
            border    = "#28a745" if direction == "call" else "#c0392b"
            arrow     = "📈" if direction == "call" else "📉"
            with st.expander(f"{arrow} {p['ticker']} — {p['confidence']:.1f}% confidence"):
                dc1, dc2, dc3 = st.columns(3)
                dc1.metric("Confidence",   f"{p['confidence']:.1f}%")
                dc2.metric("Tech Score",   f"{p['tech_score']:.0f}/100")
                dc3.metric("IV Rank",      f"{p['iv_rank']:.0f}th pct")
                dc4, dc5, dc6 = st.columns(3)
                dc4.metric("Stock Price",  f"${p['stock_price']:.2f}")
                dc5.metric("Strike",       f"${p['strike_est']:.2f}")
                dc6.metric("Delta Est.",   f"{p['delta_est']:.2f}")
                dc7, dc8, dc9 = st.columns(3)
                dc7.metric("Est. Premium", f"${p['est_premium']:.2f}")
                dc8.metric("EV%",          f"{p['ev_pct']:.1f}%")
                dc9.metric("5-Day Ret",    f"{p['ret5']:+.1f}%")
                if p.get("signal_reasons"):
                    st.markdown("**Signal reasons:**")
                    for reason in p["signal_reasons"]:
                        st.markdown(f"- {reason}")
                st.caption(
                    f"Stop loss: −{p['stop_loss_pct']:.0f}% · "
                    f"Profit target: +{p['profit_target_pct']:.0f}% · "
                    f"Target date: {p['target_date']}"
                )

        # Save button
        if st.button("💾 Save today's picks to history", use_container_width=True, key="save_picks_btn"):
            preds_all = _load_predictions()
            today_str = datetime.now().strftime("%Y-%m-%d")
            # Avoid duplicate saves for today
            already = {p.get("ticker") for p in preds_all
                       if p.get("entry_date", "")[:10] == today_str and p.get("type") == "daily_scan"}
            new_id = max((p.get("id", 0) for p in preds_all), default=0)
            added = 0
            for p in picks:
                if p["ticker"] in already:
                    continue
                new_id += 1
                rec = dict(p)
                rec["id"] = new_id
                preds_all.append(rec)
                added += 1
            _save_predictions(preds_all)
            if added:
                st.success(f"Saved {added} pick(s) to prediction history.")
            else:
                st.info("Today's picks were already saved.")
            st.session_state.pop("daily_picks", None)
            st.rerun()
    else:
        st.info(
            "Click **Scan Watchlist** to generate today's top 5 high-confidence option setups "
            "across all large-cap tickers."
        )

    st.markdown("---")

    # ══ SECTION 3: Prediction History & Grading ═══════════════════════════════
    st.markdown("### 📋 Prediction History")

    preds = _load_predictions()
    # Show only daily_scan type records in this section
    scan_preds = [p for p in preds if p.get("type") == "daily_scan"]
    all_preds  = preds  # keep for stats that include bot predictions

    if not scan_preds:
        st.info("No saved picks yet — scan and save today's picks above.")
    else:
        graded  = [p for p in scan_preds if p.get("outcome")]
        pending = [p for p in scan_preds if not p.get("outcome")]
        hits    = [p for p in graded if p["outcome"] == "hit"]
        dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]
        call_g  = [p for p in graded if p.get("direction") == "call"]
        put_g   = [p for p in graded if p.get("direction") == "put"]

        # Summary metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Picks",   len(scan_preds))
        m2.metric("Pending",       len(pending))
        m3.metric("Hit Rate",      f"{round(len(hits)/len(graded)*100,1)}%" if graded else "—",
                  help="Direction correct AND magnitude ≥ 50% of target")
        m4.metric("Directional",   f"{round(len(dir_ok)/len(graded)*100,1)}%" if graded else "—",
                  help="% where direction was correct regardless of magnitude")
        call_acc = round(sum(1 for p in call_g if p["outcome"] in ("hit","directional"))
                         / max(len(call_g), 1) * 100, 1)
        put_acc  = round(sum(1 for p in put_g  if p["outcome"] in ("hit","directional"))
                         / max(len(put_g),  1) * 100, 1)
        m5.metric("Call/Put Acc",  f"{call_acc}% / {put_acc}%",
                  help="Directional accuracy for call vs put picks")

        hist_tab_pending, hist_tab_graded, hist_tab_breakdown = st.tabs(
            [f"⏳ Pending ({len(pending)})",
             f"✅ Graded ({len(graded)})",
             "📊 Breakdown"]
        )

        # ── Pending ───────────────────────────────────────────────────────────
        with hist_tab_pending:
            if not pending:
                st.info("No pending picks.")
            else:
                pend_rows = []
                for p in sorted(pending, key=lambda x: x.get("target_date", "")):
                    arrow = "📈 CALL" if p.get("direction") == "call" else "📉 PUT"
                    pend_rows.append({
                        "Date":        p.get("entry_date", "")[:10],
                        "Ticker":      p["ticker"],
                        "Trade":       arrow,
                        "Confidence":  f"{p.get('confidence', 0):.1f}%",
                        "Tech Score":  f"{p.get('tech_score', 0):.0f}/100",
                        "Stock Price": f"${p.get('entry_price', 0):.2f}",
                        "Strike":      f"${p.get('strike_est', 0):.2f}",
                        "Target Date": p.get("target_date", "")[:10],
                        "EV%":         f"{p.get('ev_pct', 0):.1f}%",
                    })
                st.dataframe(pd.DataFrame(pend_rows), use_container_width=True, hide_index=True)

        # ── Graded ────────────────────────────────────────────────────────────
        with hist_tab_graded:
            if not graded:
                st.info("No graded picks yet.")
            else:
                outcome_icon = {"hit": "✅", "directional": "🟡", "miss": "❌"}
                sort_col, filter_col = st.columns([2, 2])
                sort_by    = sort_col.selectbox("Sort by", ["Date ↓", "Date ↑", "Option P&L", "Confidence"],
                                                key="pred_sort")
                filter_out = filter_col.multiselect("Show outcomes", ["hit", "directional", "miss"],
                                                    default=["hit", "directional", "miss"],
                                                    key="pred_filter")

                filtered = [p for p in graded if p.get("outcome") in filter_out]
                if sort_by == "Date ↓":
                    filtered.sort(key=lambda x: x.get("entry_date", ""), reverse=True)
                elif sort_by == "Date ↑":
                    filtered.sort(key=lambda x: x.get("entry_date", ""))
                elif sort_by == "Option P&L":
                    filtered.sort(key=lambda x: x.get("est_option_gain_pct") or 0, reverse=True)
                elif sort_by == "Confidence":
                    filtered.sort(key=lambda x: x.get("confidence") or 0, reverse=True)

                rows = []
                for p in filtered:
                    actual  = p.get("actual_move_pct")
                    opt_pnl = p.get("est_option_gain_pct")
                    arrow   = "📈 CALL" if p.get("direction") == "call" else "📉 PUT"
                    rows.append({
                        "Date":          p.get("entry_date", "")[:10],
                        "Ticker":        p["ticker"],
                        "Trade":         arrow,
                        "Confidence":    f"{p.get('confidence', 0):.1f}%",
                        "Stock %":       f"{actual:+.2f}%" if actual is not None else "—",
                        "Est. Option P&L": f"{opt_pnl:+.1f}%" if opt_pnl is not None else "—",
                        "Outcome":       outcome_icon.get(p["outcome"], "?") + " " + p["outcome"].upper(),
                        "Target Date":   p.get("target_date", "")[:10],
                    })

                df_graded = pd.DataFrame(rows)

                def _color_outcome(val: str):
                    if "✅" in val:  return "color: #28a745"
                    if "🟡" in val:  return "color: #e0a800"
                    if "❌" in val:  return "color: #c0392b"
                    return ""

                def _color_pnl(val: str):
                    try:
                        v = float(val.replace("%", "").replace("+", ""))
                        if v > 0:  return "color: #28a745; font-weight:bold"
                        if v < 0:  return "color: #c0392b; font-weight:bold"
                    except Exception:
                        pass
                    return ""

                styled = (
                    df_graded.style
                    .map(_color_outcome, subset=["Outcome"])
                    .map(_color_pnl,     subset=["Stock %", "Est. Option P&L"])
                )
                st.dataframe(styled, use_container_width=True, hide_index=True)

                # ── Rolled picks: same ticker+direction on consecutive days ──
                st.markdown("#### 🔄 Rolled Positions")
                st.caption("If the same pick appeared on back-to-back days, this shows the compounded option P&L had you held and rolled.")

                # Build consecutive runs per ticker+direction (sorted by entry_date)
                from itertools import groupby
                all_graded_sorted = sorted(graded, key=lambda x: (x["ticker"], x.get("direction",""), x.get("entry_date","")))
                rolled_rows = []
                for (ticker, direction), group in groupby(all_graded_sorted, key=lambda x: (x["ticker"], x.get("direction",""))):
                    run: list[dict] = []
                    for p in group:
                        if p.get("est_option_gain_pct") is None:
                            continue
                        if not run:
                            run.append(p)
                            continue
                        # Check if consecutive trading day (within 4 calendar days)
                        try:
                            prev_date = pd.to_datetime(run[-1]["entry_date"])
                            curr_date = pd.to_datetime(p["entry_date"])
                            gap = (curr_date - prev_date).days
                        except Exception:
                            gap = 999
                        if 1 <= gap <= 4:
                            run.append(p)
                        else:
                            if len(run) >= 2:
                                # Compute compounded return
                                compound = 1.0
                                for r in run:
                                    compound *= (1 + r["est_option_gain_pct"] / 100.0)
                                total_pct = round((compound - 1.0) * 100, 1)
                                arrow = "📈 CALL" if direction == "call" else "📉 PUT"
                                rolled_rows.append({
                                    "Ticker":      ticker,
                                    "Trade":       arrow,
                                    "Days Rolled": len(run),
                                    "From":        run[0]["entry_date"][:10],
                                    "To":          run[-1]["entry_date"][:10],
                                    "Daily P&Ls":  " → ".join(f"{r['est_option_gain_pct']:+.1f}%" for r in run),
                                    "Rolled P&L":  f"{total_pct:+.1f}%",
                                })
                            run = [p]
                    # flush final run
                    if len(run) >= 2:
                        compound = 1.0
                        for r in run:
                            compound *= (1 + r["est_option_gain_pct"] / 100.0)
                        total_pct = round((compound - 1.0) * 100, 1)
                        arrow = "📈 CALL" if direction == "call" else "📉 PUT"
                        rolled_rows.append({
                            "Ticker":      ticker,
                            "Trade":       arrow,
                            "Days Rolled": len(run),
                            "From":        run[0]["entry_date"][:10],
                            "To":          run[-1]["entry_date"][:10],
                            "Daily P&Ls":  " → ".join(f"{r['est_option_gain_pct']:+.1f}%" for r in run),
                            "Rolled P&L":  f"{total_pct:+.1f}%",
                        })

                if not rolled_rows:
                    st.info("No consecutive same-direction picks yet — rolled returns will appear here once the same pick repeats on back-to-back days.")
                else:
                    df_rolled = pd.DataFrame(rolled_rows).sort_values("Days Rolled", ascending=False)
                    def _color_rolled(val: str):
                        try:
                            v = float(val.replace("%","").replace("+",""))
                            if v > 0: return "color: #28a745; font-weight:bold"
                            if v < 0: return "color: #c0392b; font-weight:bold"
                        except Exception:
                            pass
                        return ""
                    st.dataframe(
                        df_rolled.style.map(_color_rolled, subset=["Rolled P&L"]),
                        use_container_width=True, hide_index=True,
                    )

        # ── Breakdown ─────────────────────────────────────────────────────────
        with hist_tab_breakdown:
            if not graded:
                st.info("No graded picks to break down yet.")
            else:
                st.markdown("#### Per-Ticker Accuracy")
                tickers_seen = sorted({p["ticker"] for p in graded})
                tk_rows = []
                for tk in tickers_seen:
                    tk_preds = [p for p in graded if p["ticker"] == tk]
                    tk_hits  = [p for p in tk_preds if p["outcome"] == "hit"]
                    tk_dir   = [p for p in tk_preds if p["outcome"] in ("hit", "directional")]
                    tk_call  = [p for p in tk_preds if p.get("direction") == "call"]
                    tk_put   = [p for p in tk_preds if p.get("direction") == "put"]
                    avg_conf = round(sum(p.get("confidence") or 0 for p in tk_preds)
                                     / max(len(tk_preds), 1), 1)
                    avg_actual = [p.get("actual_move_pct") for p in tk_preds if p.get("actual_move_pct") is not None]
                    tk_rows.append({
                        "Ticker":       tk,
                        "Picks":        len(tk_preds),
                        "Hit %":        f"{round(len(tk_hits)/len(tk_preds)*100,1)}%",
                        "Dir %":        f"{round(len(tk_dir)/len(tk_preds)*100,1)}%",
                        "Call / Put":   f"{len(tk_call)} / {len(tk_put)}",
                        "Avg Conf":     f"{avg_conf:.1f}%",
                        "Avg Move %":   f"{sum(avg_actual)/len(avg_actual):+.2f}%" if avg_actual else "—",
                    })
                tk_df = pd.DataFrame(tk_rows).sort_values("Dir %", ascending=False)
                st.dataframe(tk_df, use_container_width=True, hide_index=True)

                st.markdown("#### Confidence vs Accuracy")
                conf_buckets = {"0–40%": [], "40–55%": [], "55–70%": [], "70%+": []}
                for p in graded:
                    c = p.get("confidence") or 0
                    if c < 40:
                        bucket = "0–40%"
                    elif c < 55:
                        bucket = "40–55%"
                    elif c < 70:
                        bucket = "55–70%"
                    else:
                        bucket = "70%+"
                    conf_buckets[bucket].append(p["outcome"] in ("hit", "directional"))
                cb_rows = []
                for bucket, results in conf_buckets.items():
                    if results:
                        cb_rows.append({
                            "Confidence Band": bucket,
                            "Picks": len(results),
                            "Directional %": f"{round(sum(results)/len(results)*100,1)}%",
                        })
                if cb_rows:
                    st.dataframe(pd.DataFrame(cb_rows), use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: Strategy Lab  (Backtest · Optimizer)
# ══════════════════════════════════════════════════════════════════════════════
import options_chatbot as _oc

with tab_lab:
    st.markdown(
        "<h3 style='margin-bottom:0'>🔬 Strategy Lab</h3>"
        "<p style='color:gray;margin-top:2px'>Inspect every parameter the brain uses to score trades. "
        "Run the optimizer to improve them. Changes apply instantly across Chat and all tools.</p>",
        unsafe_allow_html=True,
    )
    sub_brain, sub_opt = st.tabs(["🧠 Strategy Brain", "🎯 Optimizer"])


    # ── SUB-TAB: Strategy Brain ───────────────────────────────────────────────
    with sub_brain:
        _sp  = _oc.STRATEGY_PROFILE
        _cw  = _sp["confidence_weights"]
        _tgt = _sp["targets"]
        _risk = _sp["risk"]
        _filt = _sp["filters"]
        _w_sum = sum(_cw.values()) or 1.0

        st.markdown("#### Confidence Score")
        st.caption(
            "Every candidate trade is scored 0–100. All four components are normalized "
            "so their weights always sum to 100%, regardless of the raw values. "
            "The optimizer tunes all four weights — these are the live values it's currently using."
        )

        # Weight bars
        w_labels = ["IV Rank", "Delta", "DTE", "Technical"]
        w_keys   = ["iv_percentile", "delta", "dte", "technical"]
        w_descs  = [
            "Lower IV rank = cheaper options = higher score. Peaks at IV rank 0, falls linearly to 0 at the 50th percentile.",
            "Peaks at the delta target, falls off as the option moves further ITM or OTM. Gaussian fall-off controlled by delta_falloff.",
            "Peaks at the optimal DTE, falls off for shorter or longer expirations. Triangle function centered on dte_optimal.",
            "RSI + MACD + SMA trend alignment on the underlying stock. 40% SMA stack, 35% RSI positioning, 25% MACD momentum.",
        ]
        cw1, cw2, cw3, cw4 = st.columns(4)
        for col, label, key, desc in zip([cw1, cw2, cw3, cw4], w_labels, w_keys, w_descs):
            raw_w  = _cw.get(key, 0.0)
            norm_w = raw_w / _w_sum * 100
            col.metric(label, f"{norm_w:.1f}%", help=desc)

        st.markdown(
            "<div style='background:rgba(255,255,255,0.04);border-radius:6px;padding:10px 14px;"
            "font-size:0.85em;color:#aaa;margin-top:4px'>"
            "<strong style='color:#eee'>Formula:</strong>  "
            "Confidence = ( IV_score × <em>w_iv</em> + Delta_score × <em>w_δ</em> + "
            "DTE_score × <em>w_dte</em> + Tech_score × <em>w_tech</em> ) ÷ Σweights"
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # ── Technical Score ───────────────────────────────────────────────────
        st.markdown("#### Technical Score  *(0 – 100)*")
        st.caption(
            "Computed live from the underlying stock's last 90 days of price data. "
            "Direction-aware: a bullish setup (CALL) and bearish setup (PUT) are scored differently on the same data."
        )

        tc1, tc2, tc3 = st.columns(3)
        tc1.metric("SMA Trend", "40% weight",
                   help="CALL: price > SMA20 (+50pts) AND SMA20 > SMA50 (+50pts)\n"
                        "PUT:  price < SMA20 (+50pts) AND SMA20 < SMA50 (+50pts)")
        tc2.metric("RSI (14)", "35% weight",
                   help="CALL: peaks when RSI ≈ 55 (mild bullish momentum, not overbought). Score = 100 − |RSI − 55| × (100/35)\n"
                        "PUT:  peaks when RSI ≈ 45 (mild bearish momentum, not oversold)")
        tc3.metric("MACD Histogram", "25% weight",
                   help="CALL: 100pts if MACD > 0 AND rising, 50pts if MACD > 0 only, 0 otherwise\n"
                        "PUT:  100pts if MACD < 0 AND falling, 50pts if MACD < 0 only, 0 otherwise")

        st.markdown(
            "<div style='background:rgba(255,255,255,0.04);border-radius:6px;padding:10px 14px;"
            "font-size:0.85em;color:#aaa;margin-top:4px'>"
            "<strong style='color:#eee'>Neutral baseline:</strong> 50 — a ticker with flat RSI, "
            "neutral MACD, and price mid-range between SMAs scores 50. "
            "Score → 100 = strong setup aligned with trade direction. Score → 0 = setup directly opposed."
            "</div>",
            unsafe_allow_html=True,
        )

        st.markdown("---")

        # ── Entry Targets & Filters ────────────────────────────────────────────
        st.markdown("#### Entry Rules")

        e1, e2, e3, e4 = st.columns(4)
        e1.metric("Delta Target",   f"{_tgt['delta_optimal']:.2f}",
                  help=f"Optimal option delta. Score peaks here, falls to 0 at ±{_tgt['delta_falloff']:.2f} away.")
        e2.metric("Delta Falloff",  f"±{_tgt['delta_falloff']:.2f}",
                  help="How quickly the delta component drops off. Wider = more tolerant of off-target strikes.")
        e3.metric("DTE Target",     f"{_tgt['dte_optimal']}d",
                  help=f"Optimal days-to-expiry. Score falls to 0 at ±{_tgt['dte_falloff']}d away.")
        e4.metric("DTE Falloff",    f"±{_tgt['dte_falloff']}d",
                  help="How quickly the DTE component drops off. Wider = more tolerant of non-optimal expirations.")

        e5, e6, e7, e8 = st.columns(4)
        e5.metric("IV Rank Max",    f"{_tgt['iv_percentile_max']}th pct",
                  help="IV rank score peaks at 0 (cheapest options) and falls linearly to 0 at this percentile. Above this = IV is expensive.")
        e6.metric("Min EV %",       f"{_filt['min_ev_return_pct']:.0f}%",
                  help="Trade only fires if Expected Value ≥ this. EV = P(win)×profit_target − P(loss)×stop_loss.")
        e7.metric("5-Day Momentum", "±0.3%",
                  help="Minimum 5-day return to generate a directional signal. Below this threshold = no trade.")
        e8.metric("SMA20 Confirm",  "Required",
                  help="Price must be above SMA20 for CALLs, below for PUTs. Momentum + trend must agree.")

        st.markdown("---")

        # ── Exit Rules ─────────────────────────────────────────────────────────
        st.markdown("#### Exit Rules")

        x1, x2, x3, x4 = st.columns(4)
        x1.metric("Stop-Loss",       f"−{_risk['stop_loss_pct']:.0f}%",
                  help="Exit the option when it loses this % of the premium paid. Non-negotiable.")
        x2.metric("Profit Target",   f"+{_risk['profit_target_pct']:.0f}%",
                  help="Take profit when the option gains this % of premium. 100% = double the premium.")
        x3.metric("Max Drawdown",    f"{_risk['max_drawdown_pct']:.0f}%",
                  help="Pause all trading if the portfolio drops this % from its peak.")
        x4.metric("0DTE Cap",        f"{_risk['dte_0_max_pct']:.0f}% of account",
                  help="Same-day expiry trades are limited to this % of total account size.")

        st.markdown("---")

        # ── Defense & Risk Filters ──────────────────────────────────────────────
        st.markdown("#### Defense & Risk Filters")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("VIX Defense Trigger", f"{_filt['vix_defense_threshold']:.0f}",
                  help="When VIX rises above this level, Defense Mode activates: position sizes are reduced.")
        d2.metric("Defense Size Mult",   f"{_filt['defense_position_mult']}×",
                  help=f"In Defense Mode, all position sizes are multiplied by this. "
                       f"E.g. {_filt['defense_position_mult']}× = half the normal size.")
        d3.metric("ATR Stop Widener",    f"{_filt['atr_expansion_stop_mult']}×",
                  help="When ATR is expanding (volatile market), stop-losses are multiplied by this to avoid whipsaws.")
        d4.metric("IV Crush Threshold",  f"{_filt['iv_crush_z_threshold']:.1f}σ",
                  help="If the option's IV is this many standard deviations above 30-day HV mean, IV crush risk is flagged.")

        d5, d6, d7, _ = st.columns(4)
        d5.metric("IV Crush Penalty",    f"−{_filt['iv_crush_confidence_penalty']:.0f} pts",
                  help="Confidence score is reduced by this amount when IV crush risk is detected.")
        d6.metric("Liquidity Max Spread",f"{_filt['liquidity_spread_max_pct']:.1f}%",
                  help="Bid-ask spread above this % of mid-price = flagged as illiquid.")
        d7.metric("Illiquid Margin",     f"+{_filt['illiquid_extra_margin_pct']:.0f}%",
                  help="Illiquid options require this much extra EV margin above the min_ev_return_pct threshold.")

    # ── SUB-TAB: Walk-Forward Optimizer ──────────────────────────────────────
    with sub_opt:
        st.subheader("🎯 Walk-Forward Optimizer")
        st.caption(
            "Finds optimal parameters by testing across rolling windows. "
            "Run it, then hit **Apply** to lock in what it learned. "
            "Nothing changes automatically."
        )

        # ── Read-only current parameters ──────────────────────────────────────
        with st.expander("📌 Current Strategy Parameters (read-only)", expanded=False):
            st.caption(
                "These are the parameters the system is actively using for every trade, "
                "backtest, and chat response. Change them only via the optimizer Apply button."
            )
            _sp_ro = _oc.STRATEGY_PROFILE
            _cw    = _sp_ro["confidence_weights"]
            _tgt   = _sp_ro["targets"]
            _risk  = _sp_ro["risk"]
            _filt  = _sp_ro["filters"]

            st.markdown("**Confidence weights** *(normalized)*")
            ro1, ro2, ro3, ro4 = st.columns(4)
            _w_sum = sum(_cw.values()) or 1.0
            ro1.metric("IV Rank",    f"{_cw['iv_percentile']/_w_sum*100:.1f}%")
            ro2.metric("Delta",      f"{_cw['delta']/_w_sum*100:.1f}%")
            ro3.metric("DTE",        f"{_cw['dte']/_w_sum*100:.1f}%")
            ro4.metric("Technical",  f"{_cw.get('technical',0.0)/_w_sum*100:.1f}%",
                       help="RSI + MACD + SMA trend alignment — optimizer-learned weight")

            st.markdown("**Entry rules**")
            re1, re2, re3, re4 = st.columns(4)
            re1.metric("Delta target",     f"{_tgt['delta_optimal']:.2f}")
            re2.metric("Optimal DTE",      f"{_tgt['dte_optimal']}d")
            re3.metric("Min EV %",         f"{_filt['min_ev_return_pct']:.0f}%")
            re4.metric("VIX defense at",   f"{_filt['vix_defense_threshold']:.0f}")

            st.markdown("**Exit rules**")
            rx1, rx2, rx3, rx4 = st.columns(4)
            rx1.metric("Stop-loss",        f"{_risk['stop_loss_pct']:.0f}%")
            rx2.metric("Profit target",    f"{_risk['profit_target_pct']:.0f}%")
            rx3.metric("Max drawdown",     f"{_risk['max_drawdown_pct']:.0f}%")
            rx4.metric("Defense pos mult", f"{_filt['defense_position_mult']}×")

        with st.expander("📋 How it works", expanded=False):
            st.markdown("""
**Pipeline**
1. Downloads price history for your chosen tickers
2. Splits into **expanding windows**: training always starts from day 1 and grows with each step. The test window advances 2 months at a time. Later windows have more training data and produce more stable params.
3. Optuna (Bayesian search) tunes **9 parameters** that maximise Profit Factor on the training slice. Each window warm-starts from the prior window's best params, so the optimizer builds on what it learned.
4. Best params are validated on the held-out test slice — all 5 guardrails must pass
5. Stop-loss and profit-target search bounds adapt automatically based on what prior window trades reveal (stop-out rate, target hit rate, avg win/loss)

**What gets optimised (10 parameters)**
- **Confidence weights** — IV Rank, Delta, DTE, **Technical** (RSI + MACD + SMA trend)
- **Entry rules** — delta target, momentum threshold, min confidence, min EV %
- **Exit rules** — stop-loss %, profit target %

**Technical score (RSI + MACD + SMA trend)**
Every candidate trade is scored on the underlying's technical setup — 40% SMA trend alignment (price/SMA20/SMA50 stack), 35% RSI positioning, 25% MACD momentum. The optimizer decides how much weight to give this vs the options-specific signals. A `w_tech = 0` result means the current regime rewards ignoring technicals; a high weight means setups with confirmed momentum are strongly preferred.

**Two modes**
- **Pooled** — pools trades from all tickers per window. Finds universal params that generalise across stock types and vol regimes. More trades per window = more statistical power.
- **Per-ticker** — optimises independently for each ticker. NVDA gets its own params, SPY gets its own. Useful when your tickers behave very differently.

**5 Guardrails — ALL must pass before a window is accepted**

| # | Gate | Rule |
|---|------|------|
| G1 | Overfitting | OOS PF ≥ 1.0 (profitable on unseen data); if IS PF > 3.0, OOS PF must also be ≥ 70% of IS PF |
| G2 | Stability | IV rank + delta weight drift ≤ your drift limit (default 75%) |
| G3 | Sample size | Auto floor: max(10, test_days ÷ 4) × √tickers |
| G4 | Noise | Top-10 trial IV rank + delta std < 0.15 |
| G5 | Consistency | OOS win rate ≥ 35% |

Results are saved to `wfo_results.json`. **You decide whether to apply them.**
""")

        st.markdown("### What to optimize")
        opt_symbols = st.multiselect(
            "Tickers",
            options=DEFAULT_WATCHLIST,
            default=["SPY", "QQQ", "NVDA"],
            key="opt_symbols",
            help="The stocks whose price history the optimizer trains and tests on. More tickers = more trade samples per window = more reliable results.",
        )
        opt_mode = st.radio(
            "Mode",
            ["pooled", "per_ticker"],
            format_func=lambda x: "🌐 One strategy for all tickers" if x == "pooled" else "🎯 Separate strategy per ticker",
            horizontal=True,
            key="opt_mode",
            help="Pooled finds universal params that work across all your tickers. Per-ticker lets each stock get its own tuned params — better fit, but needs more data.",
        )

        # Internal constants — not exposed to the user
        _TRAIN_MONTHS = 12  # minimum initial training period (expands with each window)
        _TEST_MONTHS  = 2   # test window size (advances by this each step)

        st.markdown("### How far back to look")
        from datetime import date as _date
        opt_years = st.slider(
            "Years of history",
            2, 7, 5, key="opt_years",
            format="%d yrs",
            help="How far back to start. The optimizer will begin at that date and walk forward to today, learning and self-correcting along the way.",
        )
        _start_year = _date.today().year - opt_years
        st.caption(
            f"The optimizer will start in **{_start_year}** and walk forward to today in 2-month steps. "
            f"Each step trains on **all available history up to that point** — so later windows have more data and produce more stable params."
        )

        st.markdown("### Search depth")
        opt_trials = st.slider(
            "Attempts per time period",
            20, 200, 50, step=10, key="opt_trials",
            help="How many parameter combinations to try before picking the best one for each period. More = smarter result but longer runtime. 50 is fast; 100+ is thorough.",
        )

        st.markdown("### Stability guard")
        opt_drift = st.slider(
            "How much the strategy is allowed to change",
            10, 80, 75, step=5, key="opt_drift",
            help=(
                "If a time period finds params that are too different from the current strategy it gets rejected as a fluke. "
                "Lower = stricter, fewer periods accepted. Higher = more flexible, more periods accepted. "
                "75% is recommended — too low causes excessive rejections."
            ),
            format="%d%%",
        )

        # Timeline summary
        n_windows_est = max(1, int(opt_years * 12 / _TEST_MONTHS) - int(_TRAIN_MONTHS / _TEST_MONTHS))
        n_syms = max(1, len(opt_symbols))
        total_evals = n_windows_est * (1 if opt_mode == "pooled" else n_syms) * opt_trials
        mins_lo = max(1, round(total_evals * 0.3 / 60))
        mins_hi = max(2, round(total_evals * 0.8 / 60))
        st.info(
            f"**Timeline:** {_start_year} → today · ~{n_windows_est} periods · "
            f"{opt_trials} searches each "
            f"({'all tickers together' if opt_mode == 'pooled' else f'{n_syms} tickers separately'})  \n"
            f"**Estimated runtime: {mins_lo}–{mins_hi} min**"
        )

        # Pass internal window sizes to walk_forward
        opt_train = _TRAIN_MONTHS
        opt_test  = _TEST_MONTHS

        run_wfo = st.button(
            "▶ Run Walk-Forward Optimization", type="primary",
            use_container_width=True,
            disabled=len(opt_symbols) == 0,
        )

        if run_wfo:
            progress_bar = st.progress(0.0)
            status_text  = st.empty()

            def _cb(msg: str, pct: float) -> None:
                progress_bar.progress(min(pct, 1.0))
                status_text.caption(msg)

            with st.spinner("Running WFO — this may take several minutes…"):
                wfo_data = walk_forward(
                    symbols=opt_symbols,
                    train_months=opt_train,
                    test_months=opt_test,
                    n_trials=opt_trials,
                    lookback_years=opt_years,
                    mode=opt_mode,
                    max_drift_pct=opt_drift / 100,
                    progress_callback=_cb,
                )
            progress_bar.empty()
            status_text.empty()

            if "error" in wfo_data:
                st.error(wfo_data["error"])
            else:
                st.session_state["wfo_results"] = wfo_data
                if opt_mode == "pooled":
                    st.success(
                        f"Done — {wfo_data['windows_passed']}/{wfo_data['windows_total']} "
                        f"windows passed ({wfo_data['pass_rate_pct']}%)"
                    )
                else:
                    passed_total = sum(
                        r.get("windows_passed", 0)
                        for r in wfo_data.get("per_ticker", {}).values()
                    )
                    total_total = sum(
                        r.get("windows_total", 0)
                        for r in wfo_data.get("per_ticker", {}).values()
                    )
                    st.success(f"Done — {passed_total}/{total_total} windows passed across all tickers")

        # ── Helper: format a YYYY-MM-DD date as "Mon 'YY" ───────────────────────
        def _fmt_d(d: str) -> str:
            try:
                from datetime import datetime as _dt
                return _dt.strptime(d, "%Y-%m-%d").strftime("%b '%y")
            except Exception:
                return d

        # ── Helper: render windows table + apply button for one result set ────
        def _render_wfo_result(result: dict, label: str, apply_key_suffix: str,
                                sim_capital: float = 10_000.0, sim_risk_pct: float = 10.0):
            all_windows = result.get("accepted", []) + result.get("rejected", [])
            all_windows.sort(key=lambda w: w["window"])
            accepted_wins = [w for w in all_windows if w["passed"]]

            # ── OOS equity curve — the most important visual, shown first ─────
            all_oos_trades = []
            for w in accepted_wins:
                all_oos_trades.extend(w.get("oos_trade_pnl", []))

            if all_oos_trades:
                # Sort chronologically across all tickers before building curves
                all_oos_trades.sort(key=lambda t: t["date"])

                cum, gross_win, gross_loss = 0.0, 0.0, 0.0
                cum_list, peak_list, dates = [], [], []
                n_wins = 0
                hwm = float("-inf")   # high water mark starts at negative infinity
                max_dd_abs = 0.0      # largest absolute drop from a peak
                max_dd_pct = 0.0      # largest % drop from a peak

                for t in all_oos_trades:
                    p   = t["pnl_pct"]
                    cum = round(cum + p, 2)
                    hwm = max(hwm, cum)
                    drop_abs = hwm - cum                        # dollars below the peak
                    drop_pct = (drop_abs / abs(hwm) * 100) if hwm != 0 else 0.0
                    max_dd_abs = max(max_dd_abs, drop_abs)
                    max_dd_pct = max(max_dd_pct, drop_pct)
                    if p > 0: gross_win  += p; n_wins += 1
                    else:     gross_loss += abs(p)
                    cum_list.append(cum)
                    peak_list.append(hwm)
                    dates.append(t["date"])

                n_total  = len(all_oos_trades)
                win_rate = n_wins / n_total * 100
                pf_oos   = (gross_win / gross_loss) if gross_loss > 0.01 else gross_win / 0.01

                st.markdown("#### Account Growth")
                st.caption(
                    "Starting balance compounded trade-by-trade through the full history. "
                    "Flat sections = time periods the optimizer wasn't confident enough to trade."
                )

                # Build account-level curve using compounding position sizing.
                # Cap each trade's pnl_pct at the strategy stop/target to prevent
                # tiny-premium OTM options from producing unrealistic 1000%+ returns.
                _stop_cap   = -abs(_oc.STRATEGY_PROFILE["risk"]["stop_loss_pct"])
                _target_cap =  abs(_oc.STRATEGY_PROFILE["risk"]["profit_target_pct"])
                acct = sim_capital
                acct_max_dd_pct = 0.0
                acct_hwm_inner  = sim_capital
                acct_vals = []
                for t in all_oos_trades:
                    pnl_capped = max(_stop_cap, min(_target_cap, t["pnl_pct"]))
                    position   = acct * sim_risk_pct / 100
                    pnl_dol    = position * pnl_capped / 100
                    acct       = max(acct + pnl_dol, 0.0)
                    acct_hwm_inner = max(acct_hwm_inner, acct)
                    if acct_hwm_inner > 0:
                        acct_max_dd_pct = max(acct_max_dd_pct, (acct_hwm_inner - acct) / acct_hwm_inner * 100)
                    acct_vals.append(round(acct, 2))

                final_acct = acct_vals[-1] if acct_vals else sim_capital
                total_ret  = (final_acct - sim_capital) / sim_capital * 100

                kc1, kc2, kc3, kc4 = st.columns(4)
                kc1.metric("Win Rate",       f"{win_rate:.1f}%",
                           help=f"{n_wins} wins / {n_total} trades across accepted windows")
                kc2.metric("Profit Factor",  f"{pf_oos:.2f}",
                           help="Gross profit ÷ gross loss. >1.5 = solid, >2.0 = excellent")
                kc3.metric("Account Value",  f"${final_acct:,.0f}",
                           delta=f"{total_ret:+.1f}% from ${sim_capital:,.0f}",
                           help=f"Starting ${sim_capital:,.0f}, risking {sim_risk_pct}% per trade")
                kc4.metric("Max Drawdown",   f"{acct_max_dd_pct:.1f}%", delta_color="inverse",
                           help="Largest peak-to-trough drop in account value during active trading")

                # Build a full-history chart anchored at the first window's test start
                # so the x-axis always spans the entire lookback period, not just accepted windows
                _trade_dates = pd.to_datetime(dates)
                acct_sparse  = pd.Series(acct_vals, index=_trade_dates, name="Account Value ($)")

                # Anchor: use the earliest test_start across ALL windows (accepted + rejected)
                _all_test_starts = [w.get("test_start") for w in all_windows if w.get("test_start")]
                if _all_test_starts:
                    _history_start = pd.to_datetime(min(_all_test_starts)) - pd.Timedelta(days=1)
                else:
                    _history_start = _trade_dates[0] - pd.Timedelta(days=1)

                _origin_row = pd.Series([sim_capital], index=[_history_start], name="Account Value ($)")
                acct_full   = pd.concat([_origin_row, acct_sparse])
                # Resample to daily, forward-fill gaps (flat line during rejected windows)
                acct_daily  = acct_full.resample("D").last().ffill()
                st.line_chart(acct_daily, color=["#00c17c"])

                pass_rate = result.get("pass_rate_pct", 0)
                if pass_rate < 30:
                    st.warning(
                        f"⚠️ Only **{pass_rate:.0f}%** of time periods had trades — "
                        "the strategy is being too selective. "
                        "Re-run with **'How much the strategy is allowed to change'** set higher (try 60–80%), "
                        "or add more tickers to give the optimizer more data per period."
                    )

                st.caption(
                    f"Starting ${sim_capital:,.0f} · {sim_risk_pct}% risked per trade · "
                    "Flat sections = periods with no qualifying trades."
                )

                st.markdown("##### Per-Trade P&L %")
                oos_bar = pd.DataFrame({
                    "Profit":  [t["pnl_pct"] if t["pnl_pct"] > 0 else 0.0 for t in all_oos_trades],
                    "Loss":    [t["pnl_pct"] if t["pnl_pct"] <= 0 else 0.0 for t in all_oos_trades],
                }, index=pd.to_datetime(dates))
                st.bar_chart(oos_bar, color=["#00c17c", "#ff4b4b"])
                st.caption(
                    "Each bar = one trade's return on option premium (e.g. +100% = option doubled, "
                    f"-50% = stop hit at half premium). {sim_risk_pct}% of account was at risk per trade."
                )

                with st.expander(f"📋 All trades ({len(all_oos_trades)})", expanded=False):
                    trade_rows = []
                    for t in all_oos_trades:
                        pnl = t["pnl_pct"]
                        exit_r = t.get("exit_reason", "")
                        exit_icon = "🎯" if exit_r == "target" else ("🛑" if exit_r == "stop" else "⏳")
                        trade_rows.append({
                            "Ticker":     t.get("ticker", "—") or "—",
                            "Date":       t["date"][:10],
                            "Type":       ("📈 CALL" if t.get("type") == "call" else "📉 PUT") if t.get("type") else "—",
                            "Confidence": f"{t.get('confidence', 0):.1f}%",
                            "Tech Score": f"{t.get('tech_score', 0):.0f}/100",
                            "EV":         f"{t.get('ev', 0):.1f}%",
                            "Strike":     f"${t.get('strike', 0):.2f}" if t.get("strike") else "—",
                            "Entry Px":   f"${t.get('entry_px', 0):.3f}" if t.get("entry_px") else "—",
                            "Exit Px":    f"${t.get('exit_px', 0):.3f}" if t.get("exit_px") else "—",
                            "P&L %":      f"{pnl:+.1f}%",
                            "Exit":       f"{exit_icon} {exit_r}",
                        })
                    df_trades = pd.DataFrame(trade_rows)

                    def _color_pnl_trade(val: str):
                        try:
                            v = float(val.replace("%", "").replace("+", ""))
                            if v > 0: return "color: #28a745; font-weight:bold"
                            if v < 0: return "color: #c0392b; font-weight:bold"
                        except Exception:
                            pass
                        return ""

                    st.dataframe(
                        df_trades.style.map(_color_pnl_trade, subset=["P&L %"]),
                        use_container_width=True, hide_index=True,
                    )

                st.markdown("---")

            # ── Accepted windows summary table ────────────────────────────────
            if accepted_wins:
                st.markdown(f"#### Accepted Windows ({len(accepted_wins)} of {len(all_windows)})")
                st.caption("Each row = one time period where the optimizer found profitable params that held up on unseen data.")
                acc_rows = []
                for w in accepted_wins:
                    pf_v = w.get("oos_profit_factor", 0)
                    pf_label = ("🟢 " if pf_v >= 1.5 else "🟡 " if pf_v >= 1.0 else "🔴 ") + f"{pf_v:.2f}"
                    adapt = w.get("adaptation_notes", [])
                    acc_rows.append({
                        "Test Period":    f"{_fmt_d(w['test_start'])} → {_fmt_d(w['test_end'])}",
                        "Trades":         w["oos_trades"],
                        "Win Rate":       f"{w.get('oos_win_rate', 0):.1f}%",
                        "Profit Factor":  pf_label,
                        "Stop (search)":  f"{w.get('stop_search_bounds', ['-','-'])[0]}–{w.get('stop_search_bounds', ['-','-'])[1]}%",
                        "Target (search)": f"{w.get('target_search_bounds', ['-','-'])[0]}–{w.get('target_search_bounds', ['-','-'])[1]}%",
                        "What was learned": "; ".join(adapt) if adapt else "—",
                    })
                st.dataframe(pd.DataFrame(acc_rows), use_container_width=True, hide_index=True)

            # ── Trade learning breakdown (OOS) ────────────────────────────────
            if all_oos_trades:
                oos_stops   = sum(1 for t in all_oos_trades if "stop"   in t.get("exit_reason", ""))
                oos_targets = sum(1 for t in all_oos_trades if "target" in t.get("exit_reason", ""))
                oos_expiry  = sum(1 for t in all_oos_trades if "expir"  in t.get("exit_reason", ""))
                oos_win_t   = [t for t in all_oos_trades if t.get("pnl_pct", 0) > 0]
                oos_loss_t  = [t for t in all_oos_trades if t.get("pnl_pct", 0) <= 0]
                avg_win_pnl  = sum(t["pnl_pct"] for t in oos_win_t)  / max(len(oos_win_t),  1)
                avg_loss_pnl = sum(t["pnl_pct"] for t in oos_loss_t) / max(len(oos_loss_t), 1)
                stop_rate_l  = oos_stops   / max(len(oos_loss_t), 1) * 100
                tgt_rate_w   = oos_targets / max(len(oos_win_t),  1) * 100

                with st.expander("🔬 Trade Learning — why trades won and lost", expanded=False):
                    st.markdown(
                        "The optimizer studies these exit patterns each window and shifts its "
                        "stop-loss / profit-target search range accordingly for the next window."
                    )
                    tl1, tl2, tl3, tl4 = st.columns(4)
                    tl1.metric("Avg winning trade",  f"{avg_win_pnl:+.1f}%",
                               help="Average premium return on winning OOS trades")
                    tl2.metric("Avg losing trade",   f"{avg_loss_pnl:+.1f}%",
                               help="Average premium return on losing OOS trades")
                    tl3.metric("Losses → stopped out", f"{stop_rate_l:.0f}%",
                               help="% of losses that hit the stop (vs expiring worthless). "
                                    ">60% = stop too tight; <25% = losses bleeding to expiry")
                    tl4.metric("Wins → hit target",    f"{tgt_rate_w:.0f}%",
                               help="% of wins that hit the profit target (vs expiring profitably). "
                                    ">65% = target too low; <30% = target too high for this regime")

                    ec1, ec2, ec3 = st.columns(3)
                    ec1.metric("Stop-outs",     oos_stops)
                    ec2.metric("Target hits",   oos_targets)
                    ec3.metric("Held to expiry", oos_expiry)

                    # Show adaptation notes from all accepted windows
                    all_notes = []
                    for w in accepted_wins:
                        notes = w.get("adaptation_notes", [])
                        if notes:
                            period = f"{_fmt_d(w['test_start'])} → {_fmt_d(w['test_end'])}"
                            for n in notes:
                                all_notes.append(f"**{period}:** {n}")
                    if all_notes:
                        st.markdown("**Adaptations made during this run:**")
                        for note in all_notes:
                            st.markdown(f"- {note}")
                    else:
                        st.info("No adaptations triggered — exit bounds stayed at defaults. "
                                "Run more windows or use a longer history to generate enough IS trades.")

            # ── All-windows status table (collapsible) ────────────────────────
            if all_windows:
                with st.expander(f"📋 All {len(all_windows)} windows — full detail", expanded=False):
                    rows = []
                    for w in all_windows:
                        rows.append({
                            "Test Period":    f"{_fmt_d(w['test_start'])} → {_fmt_d(w['test_end'])}",
                            "Result":         "✅ Accepted" if w["passed"] else "❌ Rejected",
                            "Trades":         w["oos_trades"],
                            "Win Rate":       f"{w.get('oos_win_rate', 0):.1f}%",
                            "OOS PF":         f"{w.get('oos_profit_factor', 0):.2f}",
                            "IS PF":          f"{w.get('is_profit_factor', 0):.2f}",
                            "OOS Sharpe":     w["oos_sharpe"],
                            "Rejection Reason": " | ".join(w.get("issues", [])) or "—",
                        })
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            rejected = result.get("rejected", [])
            if rejected and not all_oos_trades:
                # Only show this when there's nothing else to display
                st.warning(
                    f"All {len(rejected)} windows were rejected. Common fixes: increase history, "
                    "raise the drift limit, or add more tickers."
                )

            # Prefer full 9-param recommendations; fall back to weights-only for old files
            final = result.get("final_recommendations") or {}
            if not final:
                # old file: build from final_weights with no entry/exit params
                final = {r: dict(w) for r, w in result.get("final_weights", {}).items()}

            if final:
                sp      = _oc.STRATEGY_PROFILE
                cur_cw  = sp["confidence_weights"]
                cur_tgt = sp["targets"]
                cur_risk = sp["risk"]
                cur_filt = sp["filters"]

                # Human-readable labels for each optimized param
                _PARAM_LABELS = {
                    "iv_percentile":   ("IV Rank weight",      lambda: round(cur_cw.get("iv_percentile", 0), 4),  "%", 100),
                    "delta":           ("Delta weight",         lambda: round(cur_cw.get("delta", 0), 4),          "%", 100),
                    "dte":             ("DTE weight",           lambda: round(cur_cw.get("dte", 0), 4),            "%", 100),
                    "technical":       ("Technical weight",     lambda: round(cur_cw.get("technical", 0.0), 4),    "%", 100),
                    "delta_target":    ("Delta target",         lambda: cur_tgt.get("delta_optimal", 0.30),        "",  1),
                    "entry_momentum":  ("Entry momentum %",     lambda: 0.5,                                       "%", 1),
                    "min_confidence":  ("Min confidence",       lambda: 50.0,                                      "",  1),
                    "min_ev_pct":      ("Min EV %",             lambda: cur_filt.get("min_ev_return_pct", 10.0),   "%", 1),
                    "stop_loss_pct":   ("Stop-loss %",          lambda: cur_risk.get("stop_loss_pct", 50.0),       "%", 1),
                    "profit_target_pct": ("Profit target %",   lambda: cur_risk.get("profit_target_pct", 100.0),  "%", 1),
                }

                n_acc  = result.get("windows_passed", len(result.get("accepted", [])))
                for regime, params in final.items():
                    rlabel = "🛡️ Defense" if regime == "defense" else "📈 Normal"
                    with st.expander(f"{rlabel} — {n_acc} accepted windows", expanded=True):
                        st.markdown("**Before → After (9 optimized parameters)**")

                        col_left, col_right = st.columns(2)
                        with col_left:
                            st.markdown("**Confidence weights**")
                            for key in ("iv_percentile", "delta", "dte", "technical"):
                                lbl, cur_fn, unit, scale = _PARAM_LABELS[key]
                                cur_v = round(cur_fn() * scale, 1)
                                new_v = round(params.get(key, cur_fn()) * scale, 1)
                                delta_str = f"{new_v - cur_v:+.1f}{unit}"
                                st.metric(lbl, f"{new_v}{unit}", delta=delta_str)

                        with col_right:
                            st.markdown("**Entry & exit parameters**")
                            for key in ("delta_target", "entry_momentum", "min_confidence", "min_ev_pct", "stop_loss_pct", "profit_target_pct"):
                                if key not in params:
                                    continue
                                lbl, cur_fn, unit, scale = _PARAM_LABELS[key]
                                cur_v = round(cur_fn() * scale, 1)
                                new_v = round(params[key] * scale, 1)
                                delta_str = f"{new_v - cur_v:+.1f}{unit}"
                                st.metric(lbl, f"{new_v}{unit}", delta=delta_str)

                        if st.button(
                            f"Apply {label} {regime.capitalize()} Recommendations",
                            key=f"apply_{apply_key_suffix}_{regime}",
                            type="primary",
                        ):
                            # ── Write to STRATEGY_PROFILE (live, picked up by chatbot) ──
                            cw = sp["confidence_weights"]
                            if "iv_percentile"     in params: cw["iv_percentile"]                    = params["iv_percentile"]
                            if "delta"             in params: cw["delta"]                            = params["delta"]
                            if "dte"               in params: cw["dte"]                              = params["dte"]
                            if "technical"         in params: cw["technical"]                        = params["technical"]
                            if "delta_target"      in params: sp["targets"]["delta_optimal"]         = params["delta_target"]
                            if "stop_loss_pct"     in params: sp["risk"]["stop_loss_pct"]            = params["stop_loss_pct"]
                            if "profit_target_pct" in params: sp["risk"]["profit_target_pct"]        = params["profit_target_pct"]
                            if "min_ev_pct"        in params: sp["filters"]["min_ev_return_pct"]     = params["min_ev_pct"]

                            _save_profile()
                            st.success(
                                f"✅ Applied {regime} recommendations from {n_acc} accepted windows. "
                                "Chatbot and backtest are now using the new params."
                            )
                            st.rerun()
            else:
                st.warning(
                    f"No windows passed all guardrails for {label}. "
                    "Try raising the drift limit, using more history, or adding more tickers."
                )

        # ── Display results ───────────────────────────────────────────────────
        wfo_display = st.session_state.get("wfo_results") or load_last_results()

        if wfo_display and "error" not in wfo_display:
            st.markdown("---")
            syms_str = ", ".join(wfo_display.get("symbols", []))
            st.markdown(
                f"**Last run:** {wfo_display['run_at']}  |  "
                f"**Mode:** {wfo_display.get('mode', 'pooled')}  |  "
                f"**Tickers:** {syms_str}"
            )

            # ── Account simulation inputs ─────────────────────────────────────
            sc1, sc2 = st.columns(2)
            wfo_capital  = sc1.number_input(
                "Starting account capital $", min_value=1_000, max_value=10_000_000,
                value=10_000, step=1_000, key="wfo_capital",
                help="How much capital you started with. Account value chart shows growth from this base.",
            )
            wfo_risk_pct = sc2.slider(
                "Risk per trade (% of account)", min_value=1, max_value=30, value=10,
                key="wfo_risk_pct",
                help="What % of your current account balance is risked on each trade.",
            )

            if wfo_display.get("mode", "pooled") == "pooled":
                st.markdown(
                    f"**Windows:** {wfo_display['windows_passed']}/{wfo_display['windows_total']} "
                    f"passed ({wfo_display['pass_rate_pct']}%)"
                )
                _render_wfo_result(wfo_display, "Pooled", "pooled",
                                   sim_capital=wfo_capital, sim_risk_pct=wfo_risk_pct)

            else:  # per_ticker
                for sym, result in wfo_display.get("per_ticker", {}).items():
                    if "error" in result:
                        st.error(f"{sym}: {result['error']}")
                        continue
                    with st.expander(
                        f"**{sym}** — {result['windows_passed']}/{result['windows_total']} "
                        f"windows passed ({result['pass_rate_pct']}%)",
                        expanded=result["windows_passed"] > 0,
                    ):
                        _render_wfo_result(result, sym, sym.lower(),
                                           sim_capital=wfo_capital, sim_risk_pct=wfo_risk_pct)
