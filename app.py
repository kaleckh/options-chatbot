"""
Options Trading Assistant — Web UI
Run with:  streamlit run app.py
"""

import sys
import os
import json
import sqlite3
import uuid
import contextlib
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wfo_optimizer import walk_forward, load_last_results, WFO_RESULTS_FILE, run_historical_backtest
from options_chatbot import (
    DEFAULT_WATCHLIST,
    RISK_FREE_RATE,
    DTE_MIN,
    DTE_MAX,
    STRATEGY_PROFILE,
    STRATEGY_PROFILES,
    INDEX_TICKERS,
    PREDICTIONS_FILE,
    _get_system_prompt,
    _build_tool_schema_text,
    _build_prompt,
    _call_claude_cli,
    _parse_tool_calls,
    _strip_tool_calls,
    _trim_history,
    run_tool,
    risk_settings,
    CHAT_MODEL as _DEFAULT_CHAT_MODEL,
    _load_predictions,
    log_prediction,
    backfill_predictions,
    backtest_strategy,
    evaluate_trade_signal,
    _get_market_regime,
    scan_daily_top_trades,
    roll_forward_daily_picks,
    generate_position_recommendations,
    _save_predictions,
    _save_profile,
    CHANGELOG_FILE,
    CHANGELOG_FILES,
)

# ── Database ───────────────────────────────────────────────────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chat_history.db")


@contextlib.contextmanager
def _db():
    """Context manager: opens, yields, commits, and closes the SQLite connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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


def db_clear_all_sessions():
    with _db() as conn:
        conn.execute("DELETE FROM messages")
        conn.execute("DELETE FROM sessions")


# ── Init ───────────────────────────────────────────────────────────────────────

init_db()


# ── Fintech HTML table renderer ─────────────────────────────────────────────────
def _ft_table(
    data,                          # pd.DataFrame or list[dict]
    pnl_cols:   list[str] = None,  # colour by sign: +green, -red, 0=dim
    rate_cols:  list[str] = None,  # win-rate colouring: ≥60 green, ≥40 amber, <40 red
    mono_cols:  list[str] = None,  # monospace font
    right_cols: list[str] = None,  # right-align (numeric cols auto-detected)
    dim_cols:   list[str] = None,  # muted text (--text-2)
    max_height: str = "460px",
    badge_col:  str = None,        # column whose value triggers call/put badge colouring
) -> str:
    """Render a DataFrame as a fintech-styled HTML table with sticky header,
    alternating rows, hover highlighting, and conditional value colouring."""
    import pandas as _pd
    if not isinstance(data, _pd.DataFrame):
        data = _pd.DataFrame(data)
    if data.empty:
        return '<div class="ft-wrap" style="padding:1rem;color:var(--text-2);font-size:0.78rem;">No data</div>'

    pnl_cols   = set(pnl_cols   or [])
    rate_cols  = set(rate_cols  or [])
    mono_cols  = set(mono_cols  or [])
    right_cols = set(right_cols or [])
    dim_cols   = set(dim_cols   or [])

    # Auto-detect right-align for all-numeric columns (after stripping % $ + signs)
    for col in data.columns:
        if col in right_cols:
            continue
        sample = data[col].dropna().astype(str).head(20)
        cleaned = sample.str.replace(r'[\$%+,—–]', '', regex=True).str.strip()
        try:
            cleaned.astype(float)
            right_cols.add(col)
        except (ValueError, TypeError):
            pass

    def _cell_classes(col: str, val_str: str) -> tuple[str, str]:
        """Return (css_classes, inline_style) for a cell."""
        classes = []
        if col in right_cols:   classes.append("r")
        if col in mono_cols or col in pnl_cols or col in rate_cols:
            classes.append("mono")
        if col in dim_cols:     classes.append("dim")

        # PnL colouring
        if col in pnl_cols:
            raw = val_str.replace("%", "").replace("+", "").replace("$", "").replace(",", "").replace("—", "").strip()
            try:
                n = float(raw)
                if n > 0:   classes.append("pos")
                elif n < 0: classes.append("neg")
                else:       classes.append("dim")
            except ValueError:
                pass

        # Win-rate colouring
        elif col in rate_cols:
            raw = val_str.replace("%", "").replace("—", "").strip()
            try:
                n = float(raw)
                if n >= 60:   classes.append("pos")
                elif n >= 40: classes.append("warn")
                else:         classes.append("neg")
            except ValueError:
                pass

        return " ".join(classes), ""

    def _cell_html(col: str, val) -> str:
        val_str = "" if val is None else str(val)

        # Badge rendering for direction column
        if badge_col and col == badge_col:
            v = val_str.upper()
            if "CALL" in v:
                return f'<td><span class="badge-call">CALL</span></td>'
            elif "PUT" in v:
                return f'<td><span class="badge-put">PUT</span></td>'

        # Outcome badges
        if "✅" in val_str:
            inner = f'<span class="badge-hit">{val_str}</span>'
            return f'<td>{inner}</td>'
        if "❌" in val_str:
            inner = f'<span class="badge-miss">{val_str}</span>'
            return f'<td>{inner}</td>'
        if "🟡" in val_str:
            inner = f'<span class="badge-dir">{val_str}</span>'
            return f'<td>{inner}</td>'

        classes, style = _cell_classes(col, val_str)
        cls_attr   = f' class="{classes}"'   if classes else ""
        style_attr = f' style="{style}"'     if style   else ""
        return f'<td{cls_attr}{style_attr}>{val_str}</td>'

    # Header row
    header_cells = []
    for col in data.columns:
        align_cls = ' class="r"' if col in right_cols else ""
        header_cells.append(f'<th{align_cls}>{col}</th>')
    thead = f'<thead><tr>{"".join(header_cells)}</tr></thead>'

    # Body rows
    body_rows = []
    for _, row in data.iterrows():
        cells = "".join(_cell_html(col, row[col]) for col in data.columns)
        body_rows.append(f"<tr>{cells}</tr>")
    tbody = f'<tbody>{"".join(body_rows)}</tbody>'

    return (
        f'<div class="ft-wrap" style="max-height:{max_height}">'
        f'<table class="ft-table">{thead}{tbody}</table>'
        f'</div>'
    )


st.set_page_config(
    page_title="OptionsAI",
    page_icon="📈",
    layout="wide",
)

# ── Global Fintech Dark Theme ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg-0:          #080b10;
  --bg-1:          #0c1017;
  --bg-2:          #11161e;
  --bg-3:          #151c26;
  --bg-4:          #1a2332;
  --border:        #1e2736;
  --border-subtle: #151c26;
  --text-0:        #edf2f7;
  --text-1:        #b8c4d0;
  --text-2:        #6b7a8d;
  --text-3:        #3d4a5c;
  --accent:        #4a90f7;
  --accent-dim:    rgba(74,144,247,0.12);
  --accent-glow:   rgba(74,144,247,0.06);
  --green:         #34d399;
  --green-dim:     rgba(52,211,153,0.10);
  --red:           #f87171;
  --red-dim:       rgba(248,113,113,0.10);
  --amber:         #fbbf24;
  --amber-dim:     rgba(251,191,36,0.10);
  --mono:          'JetBrains Mono', 'Consolas', 'Courier New', monospace;
  --sans:          'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}

/* ── Base ─────────────────────────────────────────────────────── */
.stApp, .stApp > div { background: var(--bg-1) !important; }
section.main > div.block-container { padding: 1.25rem 2rem 2.5rem !important; max-width: 100% !important; }
#MainMenu, header[data-testid="stHeader"], footer, [data-testid="stToolbar"] { display: none !important; }
* { scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-3); }

/* ── Typography — 4-level hierarchy ───────────────────────────── */
/*  L1  Page title    1.0rem  600  --text-0  (rendered in custom HTML header)  */
/*  L2  Section hdr   0.65rem 700  --text-3  uppercase 0.12em  (.section-header) */
/*  L3  Data label    0.65rem 600  --text-2  uppercase 0.09em  (.label / stMetricLabel) */
/*  L4  Data value    0.82rem 400  --text-1  body; mono variant for numbers    */
html, body, [class*="css"] { font-family: var(--sans) !important; }
/* h1/h2: used sparingly inside tab content — treated as sub-page titles */
h1 { font-size: 1.0rem !important; font-weight: 600 !important; letter-spacing: -0.02em !important; color: var(--text-0) !important; margin: 0 0 0.5rem !important; }
h2 { font-size: 0.82rem !important; font-weight: 600 !important; letter-spacing: -0.01em !important; color: var(--text-0) !important; margin: 0 0 0.5rem !important; }
/* h3/h4/h5: treated as section-header equivalents when used in markdown */
h3 { font-size: 0.65rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.12em !important; color: var(--text-3) !important; margin: 1.5rem 0 0.5rem !important; padding-bottom: 0.5rem !important; border-bottom: 1px solid var(--border-subtle) !important; }
h4 { font-size: 0.65rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.12em !important; color: var(--text-3) !important; margin: 1rem 0 0.5rem !important; }
h5, h6 { font-size: 0.65rem !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.1em !important; color: var(--text-3) !important; margin: 0.75rem 0 0.25rem !important; }
p, li { font-family: var(--sans) !important; font-size: 0.82rem !important; color: var(--text-1) !important; line-height: 1.55 !important; }
/* Prevent global div/span rule from fighting specific overrides */
div, span { font-family: var(--sans) !important; }
[data-testid="stCaptionContainer"] p, .stCaption p, [data-testid="stCaptionContainer"], .stCaption { color: var(--text-2) !important; font-size: 0.72rem !important; line-height: 1.5 !important; }
hr { border-color: var(--border) !important; margin: 0.5rem 0 !important; }
a { color: var(--accent) !important; text-decoration: none !important; }
a:hover { text-decoration: underline !important; }
code, pre, .stCode { font-family: var(--mono) !important; font-size: 0.78rem !important; background: var(--bg-3) !important; border: 1px solid var(--border) !important; border-radius: 3px !important; }

/* ── Hide sidebar collapse button entirely to prevent accidental collapse ── */
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stSidebar"] [data-testid="stBaseButton-header"],
[data-testid="stSidebar"] button[kind="header"] {
  display: none !important;
}
/* Hide ALL Material Icons ligature text (arrow_right, arrow_down, etc.) */
[data-testid="stExpander"] summary span,
details summary span,
[data-testid="stExpander"] summary > span {
  font-size: 0 !important; width: 0 !important; overflow: hidden !important;
  display: inline-block !important; line-height: 0 !important;
}
/* Restore the actual label text inside the summary */
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"],
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] span,
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"] p {
  font-size: 0.82rem !important; width: auto !important; overflow: visible !important;
  display: inline !important; line-height: normal !important;
}

/* ── Sidebar ───────────────────────────────────────────────────── */
[data-testid="stSidebar"] { background: linear-gradient(180deg, var(--bg-2) 0%, var(--bg-0) 100%) !important; border-right: 1px solid var(--border) !important; }
[data-testid="stSidebar"] > div:first-child { padding: 1.25rem 1rem !important; }
[data-testid="stSidebar"] .stMarkdown h2 { font-size: 0.82rem !important; text-transform: uppercase; letter-spacing: 0.1em; color: var(--text-2) !important; font-weight: 600 !important; margin-bottom: 0 !important; }
[data-testid="stSidebar"] .stMarkdown p { font-size: 0.72rem !important; color: var(--text-3) !important; }

/* ── Metrics ───────────────────────────────────────────────────── */
[data-testid="stMetric"] { background: linear-gradient(135deg, var(--bg-2) 0%, var(--bg-3) 100%) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; padding: 0.85rem 1.1rem !important; transition: border-color 0.2s ease, box-shadow 0.2s ease !important; }
[data-testid="stMetric"]:hover { border-color: var(--accent) !important; box-shadow: 0 0 12px var(--accent-glow) !important; }
[data-testid="stMetricLabel"] > div { font-size: 0.65rem !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.09em !important; color: var(--text-2) !important; }
[data-testid="stMetricValue"] { font-family: var(--mono) !important; font-size: 1.05rem !important; font-weight: 500 !important; color: var(--text-0) !important; letter-spacing: -0.03em !important; }
[data-testid="stMetricDelta"] { font-family: var(--mono) !important; font-size: 0.72rem !important; }

/* ── Buttons ───────────────────────────────────────────────────── */
button[kind="primary"] { background: linear-gradient(135deg, var(--accent) 0%, #3a7be8 100%) !important; border: none !important; border-radius: 6px !important; font-family: var(--sans) !important; font-size: 0.82rem !important; font-weight: 500 !important; color: #fff !important; letter-spacing: 0.01em !important; padding: 0.55rem 1.1rem !important; box-shadow: 0 2px 8px rgba(74,144,247,0.2) !important; transition: all 0.15s ease !important; }
button[kind="primary"]:hover { background: linear-gradient(135deg, #5a9df8 0%, #4a90f7 100%) !important; box-shadow: 0 4px 14px rgba(74,144,247,0.3) !important; transform: translateY(-1px) !important; }
button[kind="secondary"], .stButton > button { background: var(--bg-3) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; color: var(--text-1) !important; font-family: var(--sans) !important; font-size: 0.82rem !important; font-weight: 400 !important; transition: all 0.15s ease !important; }
.stButton > button:hover { background: var(--bg-4) !important; border-color: var(--text-3) !important; color: var(--text-0) !important; }
button[kind="tertiary"] { background: transparent !important; border: none !important; color: var(--text-2) !important; font-size: 0.78rem !important; }

/* ── Inputs ────────────────────────────────────────────────────── */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox div[data-baseweb="select"] > div { background: var(--bg-3) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; color: var(--text-0) !important; font-family: var(--sans) !important; font-size: 0.82rem !important; transition: border-color 0.15s ease, box-shadow 0.15s ease !important; }
.stTextInput input:focus, .stNumberInput input:focus, .stTextArea textarea:focus { border-color: var(--accent) !important; box-shadow: 0 0 0 3px var(--accent-dim), 0 0 16px var(--accent-glow) !important; outline: none !important; }
.stSelectbox div[data-baseweb="select"] * { color: var(--text-1) !important; font-size: 0.82rem !important; }

/* ── Sliders ───────────────────────────────────────────────────── */
[data-baseweb="slider"] [role="slider"] { background: var(--accent) !important; border: 2px solid var(--accent) !important; }
[data-baseweb="slider"] div[data-testid="stThumbValue"] { background: var(--accent) !important; color: #fff !important; font-family: var(--mono) !important; font-size: 0.72rem !important; }
[data-baseweb="slider"] > div > div { background: var(--border) !important; }
[data-baseweb="slider"] > div > div > div:first-child { background: var(--accent) !important; }

/* ── Radio & Toggle ────────────────────────────────────────────── */
.stRadio label { font-size: 0.8rem !important; color: var(--text-1) !important; }
.stRadio [data-baseweb="radio"] div { border-color: var(--border) !important; }
.stCheckbox label { font-size: 0.8rem !important; color: var(--text-1) !important; }

/* ── Expanders ─────────────────────────────────────────────────── */
[data-testid="stExpander"] { border: 1px solid var(--border) !important; border-radius: 6px !important; background: var(--bg-2) !important; margin-bottom: 0.5rem !important; overflow: hidden !important; transition: border-color 0.15s ease !important; }
[data-testid="stExpander"]:hover { border-color: var(--text-3) !important; }
[data-testid="stExpander"] summary { display: flex !important; align-items: center !important; gap: 0.5rem !important; padding: 0.5rem 1rem !important; background: transparent !important; cursor: pointer !important; }
[data-testid="stExpander"] summary svg { flex-shrink: 0 !important; width: 1rem !important; height: 1rem !important; color: var(--text-3) !important; }
/* Hide material-icons span — font ligature renders as raw text when CDN is blocked */
[data-testid="stExpander"] summary span.material-icons,
[data-testid="stExpander"] summary span[class*="material"] { display: none !important; }
[data-testid="stExpander"] summary p { margin: 0 !important; font-size: 0.65rem !important; font-weight: 700 !important; color: var(--text-2) !important; text-transform: uppercase !important; letter-spacing: 0.1em !important; line-height: 1.2 !important; }
[data-testid="stExpander"] summary:hover p { color: var(--text-0) !important; }
[data-testid="stExpander"] summary:hover svg { color: var(--text-1) !important; }
[data-testid="stExpander"] > div:last-child { border-top: 1px solid var(--border-subtle) !important; padding: 1rem !important; }

/* ── Tabs (st.tabs) ────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] { background: transparent !important; border-bottom: 1px solid var(--border) !important; gap: 0 !important; padding: 0 !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: var(--text-2) !important; font-size: 0.78rem !important; font-weight: 500 !important; padding: 0.6rem 1.1rem !important; border-bottom: 2px solid transparent !important; text-transform: uppercase !important; letter-spacing: 0.06em !important; margin: 0 !important; transition: color 0.15s ease !important; }
.stTabs [data-baseweb="tab"]:hover { color: var(--text-1) !important; }
.stTabs [aria-selected="true"] { color: var(--text-0) !important; border-bottom: 2px solid var(--accent) !important; background: transparent !important; }
.stTabs [data-baseweb="tab-panel"] { padding: 1.15rem 0 0 !important; }

/* ── DataFrames ────────────────────────────────────────────────── */
.stDataFrame { border: 1px solid var(--border) !important; border-radius: 3px !important; overflow: hidden !important; }
.stDataFrame [data-testid="stDataFrameGlideDataEditor"] { background: var(--bg-2) !important; }
iframe[title="st_aggrid"] { border: 1px solid var(--border) !important; border-radius: 3px !important; }

/* ── Chat ──────────────────────────────────────────────────────── */
[data-testid="stChatMessageContainer"] { gap: 0.6rem !important; }
[data-testid="stChatMessage"] { background: var(--bg-2) !important; border: 1px solid var(--border-subtle) !important; border-radius: 8px !important; padding: 0.9rem 1.15rem !important; transition: border-color 0.15s ease !important; }
[data-testid="stChatMessage"]:hover { border-color: var(--border) !important; }
[data-testid="stChatMessage"][data-from="user"] { background: linear-gradient(135deg, var(--bg-4) 0%, var(--bg-3) 100%) !important; border-color: var(--border) !important; border-left: 2px solid var(--accent) !important; }
[data-testid="stChatInput"] { position: sticky !important; bottom: 0 !important; padding: 0.75rem 0 1rem !important; background: linear-gradient(180deg, transparent 0%, var(--bg-1) 20%) !important; z-index: 100 !important; }
[data-testid="stChatInput"] > div { background: var(--bg-3) !important; border: 1px solid var(--border) !important; border-radius: 12px !important; padding: 0.15rem 0.25rem !important; box-shadow: 0 2px 12px rgba(0,0,0,0.3), 0 0 0 1px var(--border) !important; transition: all 0.2s ease !important; }
[data-testid="stChatInput"] > div:focus-within { border-color: var(--accent) !important; box-shadow: 0 2px 16px rgba(0,0,0,0.4), 0 0 0 2px var(--accent-dim), 0 0 30px var(--accent-glow) !important; }
[data-testid="stChatInput"] textarea { background: transparent !important; color: var(--text-0) !important; font-size: 0.85rem !important; font-family: var(--sans) !important; padding: 0.6rem 0.75rem !important; }
[data-testid="stChatInput"] textarea::placeholder { color: var(--text-3) !important; font-style: normal !important; }
[data-testid="stChatInput"] button { background: var(--accent) !important; border: none !important; border-radius: 8px !important; width: 34px !important; height: 34px !important; margin: 4px !important; transition: all 0.15s ease !important; }
[data-testid="stChatInput"] button:hover { background: #5a9df8 !important; box-shadow: 0 0 10px var(--accent-dim) !important; }
[data-testid="stChatInput"] button svg { color: #fff !important; }

/* ── Hide material-icons ligature spans (show as raw text when font blocked) ── */
span.material-icons, span.material-icons-outlined, span.material-icons-round, span.material-symbols-outlined, span.material-symbols-rounded { display: none !important; }
/* ── Hide scroll-to-top button (uses material icon ligature) ── */
[data-testid="ScrollToTopButton"], button[data-testid*="scroll"], .stApp > div > button[kind="scrollToTop"] { display: none !important; }

/* ── Status / Spinners ─────────────────────────────────────────── */
[data-testid="stStatus"] { background: var(--bg-2) !important; border: 1px solid var(--border) !important; border-radius: 6px !important; }
[data-testid="stStatus"] summary { font-size: 0.72rem !important; color: var(--text-2) !important; }
.stSpinner > div { border-color: var(--accent) transparent transparent !important; }

/* ── Alerts ────────────────────────────────────────────────────── */
[data-testid="stAlert"] { border-radius: 3px !important; font-size: 0.8rem !important; border-left-width: 3px !important; }
[data-testid="stNotification"] { border-radius: 3px !important; }
div[data-testid="stAlert"][data-baseweb="notification"] { background: var(--bg-3) !important; }

/* ── Info / Warning / Error boxes ─────────────────────────────── */
.element-container [data-testid="stMarkdownContainer"] > div[style*="background"] { border-radius: 3px !important; border-left: 3px solid var(--accent) !important; }

/* ── Progress bars ─────────────────────────────────────────────── */
[data-testid="stProgressBar"] > div { background: var(--bg-4) !important; border-radius: 2px !important; }
[data-testid="stProgressBar"] > div > div { background: var(--accent) !important; border-radius: 2px !important; }

/* ── Tooltips ──────────────────────────────────────────────────── */
[data-testid="stTooltipHoverTarget"] svg { fill: var(--text-3) !important; width: 12px !important; }

/* ── Markdown tables ───────────────────────────────────────────── */
.stMarkdown table { border-collapse: collapse !important; width: 100% !important; font-size: 0.78rem !important; }
.stMarkdown th { background: var(--bg-3) !important; color: var(--text-2) !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.09em !important; padding: 0.5rem 0.75rem !important; border-bottom: 1px solid var(--border) !important; font-size: 0.65rem !important; }
.stMarkdown td { padding: 0.5rem 0.75rem !important; border-bottom: 1px solid var(--border-subtle) !important; color: var(--text-1) !important; font-size: 0.82rem !important; }
.stMarkdown tr:hover td { background: rgba(255,255,255,0.02) !important; }

/* ── Sidebar Nav Buttons (override for active state) ───────────── */
div[data-testid="stSidebar"] .nav-btn button,
div[data-testid="stSidebar"] .nav-btn-active button {
  width: 100% !important; text-align: left !important;
  padding: 0.6rem 0.85rem !important; font-size: 0.8rem !important;
  font-weight: 400 !important; border-radius: 6px !important;
  border: none !important; box-shadow: none !important; margin: 0 !important;
  background: transparent !important; color: var(--text-2) !important;
  letter-spacing: 0.01em !important;
  transition: all 0.15s ease !important;
}
div[data-testid="stSidebar"] .nav-btn button:hover { background: rgba(255,255,255,0.04) !important; color: var(--text-0) !important; }
div[data-testid="stSidebar"] .nav-btn-active button { background: linear-gradient(135deg, var(--accent-dim) 0%, rgba(74,144,247,0.06) 100%) !important; color: var(--text-0) !important; font-weight: 500 !important; border-left: 2px solid var(--accent) !important; padding-left: calc(0.85rem - 2px) !important; box-shadow: 0 0 12px var(--accent-glow) !important; }
div[data-testid="stSidebar"] .nav-btn, div[data-testid="stSidebar"] .nav-btn-active { margin-bottom: 2px !important; }

/* ── Fintech Table ─────────────────────────────────────────────── */
.ft-wrap { overflow-x: auto; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-2); }
.ft-table { width: 100%; border-collapse: collapse; font-size: 0.78rem; font-family: var(--sans); }
.ft-table thead { position: sticky; top: 0; z-index: 10; }
.ft-table thead th { background: linear-gradient(180deg, var(--bg-3) 0%, var(--bg-2) 100%); color: var(--text-2); font-size: 0.65rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.09em; padding: 0.55rem 0.75rem; border-bottom: 2px solid var(--border); white-space: nowrap; user-select: none; }
.ft-table thead th.r { text-align: right; }
.ft-table tbody tr { border-bottom: 1px solid var(--border-subtle); transition: background 0.08s ease; }
.ft-table tbody tr:nth-child(even) { background: rgba(255,255,255,0.022); }
.ft-table tbody tr:hover { background: rgba(45,125,247,0.09) !important; }
.ft-table td { padding: 0.5rem 0.75rem; color: var(--text-1); white-space: nowrap; vertical-align: middle; }
.ft-table td.r { text-align: right; }
.ft-table td.mono { font-family: var(--mono); }
.ft-table td.pos  { color: #3fb950 !important; font-family: var(--mono); }
.ft-table td.neg  { color: #f85149 !important; font-family: var(--mono); }
.ft-table td.warn { color: #d29922 !important; font-family: var(--mono); }
.ft-table td.dim  { color: var(--text-2); }
.ft-table .badge-call { display:inline-block; padding:2px 8px; border-radius:4px; background:var(--green-dim); color:var(--green); font-size:0.65rem; font-weight:600; letter-spacing:0.04em; font-family:var(--mono); }
.ft-table .badge-put  { display:inline-block; padding:2px 8px; border-radius:4px; background:var(--red-dim);  color:var(--red); font-size:0.65rem; font-weight:600; letter-spacing:0.04em; font-family:var(--mono); }
.ft-table .badge-hit  { display:inline-block; padding:2px 8px; border-radius:4px; background:var(--green-dim);  color:var(--green); font-size:0.72rem; }
.ft-table .badge-miss { display:inline-block; padding:2px 8px; border-radius:4px; background:var(--red-dim);  color:var(--red); font-size:0.72rem; }
.ft-table .badge-dir  { display:inline-block; padding:2px 8px; border-radius:4px; background:var(--amber-dim); color:var(--amber); font-size:0.72rem; }
/* Sent-table (sector sentiment) — same language */
.sent-table { width:100%; border-collapse:collapse; font-size:0.78rem; font-family:var(--sans); }
.sent-table thead { position:sticky; top:0; z-index:10; }
.sent-table thead th { background:var(--bg-3); color:var(--text-2); font-size:0.65rem; font-weight:600; text-transform:uppercase; letter-spacing:0.09em; padding:0.5rem 0.75rem; border-bottom:2px solid var(--border); white-space:nowrap; }
.sent-table tbody tr { border-bottom:1px solid var(--border-subtle); transition:background 0.08s ease; }
.sent-table tbody tr:nth-child(even) { background:rgba(255,255,255,0.022); }
.sent-table tbody tr:hover { background:rgba(45,125,247,0.09) !important; }
.sent-table td { padding:0.5rem 0.75rem; color:var(--text-1); white-space:nowrap; }
.changed-row { background:rgba(210,153,34,0.06) !important; }
.changed-row:hover { background:rgba(45,125,247,0.09) !important; }

/* ── Pred grid table (st.columns-based, interactive rows) ─────── */
.pred-hdr { font-size:0.65rem; color:var(--text-2); text-transform:uppercase; font-weight:600;
            letter-spacing:0.09em; padding:0.5rem 0.75rem;
            border-top:1px solid var(--border-subtle); border-bottom:2px solid var(--border);
            cursor:help; white-space:nowrap; user-select:none; }
.pred-hdr:hover { color:var(--text-1); }
.pred-cell { font-size:0.82rem; padding:0.5rem 0.75rem; border-bottom:1px solid var(--border-subtle);
             color:var(--text-1); white-space:nowrap; vertical-align:middle; }
.pred-row-even { background:rgba(255,255,255,0.022); }
.pred-row-odd  { background:transparent; }

/* ── Summary cards (batch metrics) ─────────────────────────────── */
.summary-card { background:linear-gradient(135deg, var(--bg-3) 0%, var(--bg-2) 100%); border:1px solid var(--border); border-radius:6px; padding:0.65rem 0.85rem; text-align:center; margin-bottom:1rem; transition:border-color 0.15s ease; }
.summary-card:hover { border-color:var(--text-3); }
.summary-card .sc-label { font-size:0.65rem; color:var(--text-2); letter-spacing:0.06em; text-transform:uppercase; margin-bottom:0.25rem; }
.summary-card .sc-value { font-size:1.05rem; font-weight:500; line-height:1.1; }
.summary-card .sc-sub   { font-size:0.72rem; color:var(--text-3); margin-top:0.25rem; }

/* ── Utility classes for inline HTML ───────────────────────────── */
.mono { font-family: var(--mono) !important; }
.label { font-size: 0.65rem !important; font-weight: 600 !important; text-transform: uppercase !important; letter-spacing: 0.09em !important; color: var(--text-2) !important; }
.tag-call { display: inline-block; padding: 1px 7px; border-radius: 2px; background: var(--green-dim); color: var(--green); font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; font-family: var(--mono); }
.tag-put  { display: inline-block; padding: 1px 7px; border-radius: 2px; background: var(--red-dim);   color: var(--red);   font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; font-family: var(--mono); }
.tag-neutral { display: inline-block; padding: 1px 7px; border-radius: 2px; background: var(--bg-4); color: var(--text-2); font-size: 0.72rem; font-weight: 500; }
.pos { color: var(--green) !important; font-family: var(--mono); }
.neg { color: var(--red) !important; font-family: var(--mono); }
.muted { color: var(--text-2) !important; }
.section-header { font-size: 0.65rem !important; font-weight: 700 !important; text-transform: uppercase !important; letter-spacing: 0.12em !important; color: var(--text-3) !important; margin: 1.5rem 0 0.75rem !important; padding-bottom: 0.5rem !important; border-bottom: 1px solid var(--border-subtle) !important; }
/* First .section-header in a container gets less top margin */
.element-container:first-child .section-header { margin-top: 0.5rem !important; }
/* Utility: consistent section spacing for st.column containers */
.stColumn > div { padding-top: 0 !important; }
/* Consistent gap between st.columns */
[data-testid="stHorizontalBlock"] { gap: 1rem !important; }
/* Add breathing room between stacked metric rows */
[data-testid="stMetric"] + [data-testid="stMetric"] { margin-top: 0.75rem !important; }
/* Tag sizes — align to L3 label size */
.tag-call, .tag-put, .tag-neutral { font-size: 0.65rem !important; }
</style>
""", unsafe_allow_html=True)

# ── Authentication ─────────────────────────────────────────────────────────────

import yaml
import streamlit_authenticator as stauth

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.yaml")

_auth_config = None
_auth_error = None

if os.path.exists(_CONFIG_PATH):
    # Local: load from config.yaml file
    with open(_CONFIG_PATH) as _cf:
        _auth_config = yaml.safe_load(_cf)
else:
    # Cloud: load from st.secrets
    try:
        _auth_config = yaml.safe_load(st.secrets["auth"]["config_yaml"])
    except KeyError:
        _auth_error = "Missing [auth] config_yaml in Streamlit secrets."
    except Exception as _e:
        _auth_error = f"Failed to parse auth config: {_e}"

if _auth_config is None:
    # Auth config missing — block access entirely
    st.markdown("""
    <div style="max-width:480px; margin:3rem auto; text-align:center;">
      <div style="font-family:var(--mono); font-size:1.5rem; font-weight:600; color:var(--text-0); margin-bottom:1rem;">
        OPTIONS<span style="color:var(--accent);">AI</span>
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.error(_auth_error or "Authentication configuration not found. Add config.yaml or set Streamlit secrets.")
    st.stop()

_authenticator = stauth.Authenticate(
    _auth_config["credentials"],
    _auth_config["cookie"]["name"],
    _auth_config["cookie"]["key"],
    _auth_config["cookie"]["expiry_days"],
)

# Ensure session state keys exist before cookie re-auth attempt
for _k in ("name", "username", "authentication_status"):
    st.session_state.setdefault(_k, None)

# Let authenticator handle cookie re-auth silently (no UI rendered)
_authenticator.login(location="unrendered")

if st.session_state.get("authentication_status") is not True:
    # ── Login page CSS ─────────────────────────────────────────────────
    st.markdown("""
    <style>
    /* Center + constrain login page */
    section.main > .block-container {
        max-width: 420px !important;
        margin: 0 auto !important;
        padding: 12vh 1rem 2rem !important;
    }
    /* Hide sidebar on login */
    [data-testid="stSidebar"] { display: none !important; }
    /* Input labels */
    .stTextInput > label {
        font-size: 0.68rem !important;
        font-weight: 600 !important;
        color: var(--text-2) !important;
        text-transform: uppercase !important;
        letter-spacing: 0.1em !important;
        margin-bottom: 0.3rem !important;
    }
    /* Input fields */
    .stTextInput input {
        background: var(--bg-0) !important;
        border: 1px solid var(--border) !important;
        border-radius: 6px !important;
        padding: 0.65rem 0.85rem !important;
        font-size: 0.88rem !important;
        color: var(--text-0) !important;
        transition: border-color 0.2s, box-shadow 0.2s !important;
    }
    .stTextInput input:focus {
        border-color: var(--accent) !important;
        box-shadow: 0 0 0 3px var(--accent-dim) !important;
    }
    .stTextInput input::placeholder {
        color: var(--text-3) !important;
        font-weight: 400 !important;
    }
    /* Sign In button */
    .stButton > button {
        width: 100% !important;
        background: var(--accent) !important;
        border: none !important;
        border-radius: 6px !important;
        padding: 0.6rem 1.5rem !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        color: #fff !important;
        letter-spacing: 0.02em !important;
        margin-top: 0.5rem !important;
        transition: background 0.15s, box-shadow 0.15s, transform 0.1s !important;
    }
    .stButton > button:hover {
        background: #3d8ef8 !important;
        box-shadow: 0 4px 16px rgba(45,125,247,0.35) !important;
    }
    .stButton > button:active {
        transform: scale(0.98) !important;
    }
    /* Error alert */
    [data-testid="stAlert"] {
        border-radius: 6px !important;
        margin-top: 0.75rem !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Branding ───────────────────────────────────────────────────────
    st.markdown("""
    <div style="text-align:center; margin-bottom:2rem;">
      <div style="font-family:var(--mono); font-size:1.8rem; font-weight:700; color:var(--text-0); letter-spacing:-0.03em; margin-bottom:0.3rem;">
        OPTIONS<span style="color:var(--accent);">AI</span>
      </div>
      <div style="font-size:0.68rem; color:var(--text-3); text-transform:uppercase; letter-spacing:0.16em;">
        Intelligent Options Trading Assistant
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Custom login form ──────────────────────────────────────────────
    _login_container = st.container()
    with _login_container:
        _login_user = st.text_input("Username", key="login_username", placeholder="Enter username")
        _login_pass = st.text_input("Password", key="login_password", type="password", placeholder="Enter password")
        _login_submit = st.button("Sign In", key="login_submit", use_container_width=True)
        if _login_submit and _login_user and _login_pass:
            try:
                _result = _authenticator.authentication_controller.login(
                    _login_user, _login_pass
                )
                if _result is True:
                    _authenticator.cookie_controller.set_cookie()
                    st.rerun()
            except Exception:
                st.session_state["authentication_status"] = False
        if st.session_state.get("authentication_status") is False:
            st.error("Incorrect username or password.")

    # ── Feature highlights ─────────────────────────────────────────────
    st.markdown("""
    <div style="margin-top:2.5rem; padding-top:1.5rem; border-top:1px solid var(--border-subtle);">
      <div style="display:flex; align-items:flex-start; gap:0.75rem; margin-bottom:0.85rem;">
        <div style="flex-shrink:0; width:6px; height:6px; border-radius:50%; background:var(--accent); margin-top:0.4rem;"></div>
        <div style="font-size:0.76rem; color:var(--text-2); line-height:1.5;">AI-powered daily scan across 60+ large-cap tickers with real options chain data</div>
      </div>
      <div style="display:flex; align-items:flex-start; gap:0.75rem; margin-bottom:0.85rem;">
        <div style="flex-shrink:0; width:6px; height:6px; border-radius:50%; background:var(--green); margin-top:0.4rem;"></div>
        <div style="font-size:0.76rem; color:var(--text-2); line-height:1.5;">Smart position management with automatic HOLD / EXIT / REPLACE recommendations</div>
      </div>
      <div style="display:flex; align-items:flex-start; gap:0.75rem;">
        <div style="flex-shrink:0; width:6px; height:6px; border-radius:50%; background:var(--amber); margin-top:0.4rem;"></div>
        <div style="font-size:0.76rem; color:var(--text-2); line-height:1.5;">Walk-forward optimized strategy brain with live indicator-based early exit logic</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.stop()

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
    # ── Auth: logout + username ───────────────────────────────────────────
    if _auth_config:
        _auth_col1, _auth_col2 = st.columns([3, 1])
        _auth_col1.markdown(
            f"<div style='font-size:0.65rem;color:var(--text-3);text-transform:uppercase;letter-spacing:0.08em;padding:0.25rem 0'>"
            f"{st.session_state.get('name', '')}</div>",
            unsafe_allow_html=True,
        )
        _authenticator.logout("Logout", location="sidebar", key="sidebar_logout")

    st.markdown("""
<div style="padding:0.5rem 0 0.85rem; border-bottom:1px solid var(--border); margin-bottom:0.85rem;">
  <div style="font-family:var(--mono); font-size:1.0rem; font-weight:700; color:var(--text-0); letter-spacing:-0.02em;">OPTIONS<span style="color:var(--accent);">AI</span></div>
  <div style="display:flex; align-items:center; gap:0.4rem; margin-top:0.4rem;">
    <span style="display:inline-block; width:6px; height:6px; border-radius:50%; background:var(--green); box-shadow:0 0 6px var(--green);"></span>
    <span style="font-size:0.62rem; color:var(--text-2); letter-spacing:0.06em; text-transform:uppercase; font-weight:500;">Yahoo Finance · ~15 min delay</span>
  </div>
</div>
""", unsafe_allow_html=True)

    # Primary navigation

    if "active_tab" not in st.session_state:
        st.session_state["active_tab"] = "💬 Chat"

    _tabs = ["💬 Chat", "📊 Predictions", "🔬 Strategy Lab"]
    for _t in _tabs:
        _is_active = st.session_state["active_tab"] == _t
        _cls = "nav-btn-active nav-btn" if _is_active else "nav-btn"
        with st.container():
            st.markdown(f'<div class="{_cls}">', unsafe_allow_html=True)
            if st.button(_t, key=f"nav_{_t}", use_container_width=True):
                st.session_state["active_tab"] = _t
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    _active_tab = st.session_state["active_tab"]

    # Hide stale chat elements on non-chat tabs without forcing a scroll jump
    _is_chat = st.session_state.get("active_tab", "💬 Chat") == "💬 Chat"
    st.html(f"""<script>
try {{
  var doc = window.parent.document;
  // Hide stale chat elements immediately when not on chat tab
  var hide = {'false' if _is_chat else 'true'};
  doc.querySelectorAll('[data-testid="stChatMessage"], [data-testid="stChatInput"], [data-testid="stChatInputContainer"]').forEach(function(el) {{
    el.style.display = hide ? 'none' : '';
  }});
}} catch(e) {{}}
</script>""")

    st.markdown("---")

    # Chat-specific sidebar content
    if _active_tab == "💬 Chat":
        # Account / risk metrics
        account = risk_settings.get("account_size", 0)
        if account:
            st.metric("Account Size", f"${account:,.0f}")
            lo = risk_settings["min_position_pct"] / 100
            hi = risk_settings["max_position_pct"] / 100
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

        # Model toggle
        import options_chatbot as _oc_model
        _model_choice = st.radio(
            "🤖 Chat model",
            options=["Haiku (fast)", "Sonnet (smart)"],
            index=0 if st.session_state.get("chat_model", _DEFAULT_CHAT_MODEL) == _DEFAULT_CHAT_MODEL else 1,
            horizontal=True,
            help="Haiku: ~5× faster, good for most questions. Sonnet: slower but better at complex multi-step analysis.",
            key="model_radio",
        )
        _selected_model = (
            "claude-haiku-4-5-20251001" if _model_choice == "Haiku (fast)"
            else "claude-sonnet-4-6"
        )
        if st.session_state.get("chat_model") != _selected_model:
            st.session_state["chat_model"] = _selected_model
            _oc_model.CHAT_MODEL = _selected_model

        st.markdown("---")

        # Conversation controls
        if st.button("➕ New conversation", use_container_width=True):
            new_session()
            st.rerun()

        if st.button("🗑 Clear all history", use_container_width=True, type="secondary"):
            st.session_state["_confirm_clear_all"] = True

        if st.session_state.get("_confirm_clear_all"):
            st.warning("Delete every conversation? This cannot be undone.")
            _cc1, _cc2 = st.columns(2)
            if _cc1.button("Yes, delete all", key="confirm_clear_yes", type="primary", use_container_width=True):
                db_clear_all_sessions()
                st.session_state.pop("_confirm_clear_all", None)
                new_session()
                st.rerun()
            if _cc2.button("Cancel", key="confirm_clear_no", use_container_width=True):
                st.session_state.pop("_confirm_clear_all", None)
                st.rerun()

        st.markdown("---")

        # Past sessions
        st.markdown('<div class="section-header">Conversations</div>', unsafe_allow_html=True)
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
        st.markdown('<div class="section-header">Quick Prompts</div>', unsafe_allow_html=True)
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
    st.markdown("""<div style="font-size:0.65rem; color:var(--text-3); line-height:1.5; padding-top:0.25rem;">Not financial advice. Options trading involves substantial risk of loss. Quotes delayed ~15 min.</div>""", unsafe_allow_html=True)

# ── Header ─────────────────────────────────────────────────────────────────────

_now_str = datetime.now().strftime("%a %b %d, %Y  %H:%M ET")
st.markdown(f"""
<div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 0 0.85rem; border-bottom:1px solid var(--border); margin-bottom:1.25rem;">
  <div style="display:flex; align-items:center; gap:1rem;">
    <div style="font-family:var(--mono); font-size:1.2rem; font-weight:700; color:var(--text-0); letter-spacing:-0.03em;">OPTIONS<span style="color:var(--accent);">AI</span></div>
    <div style="display:flex; gap:0.5rem; align-items:center;">
      <span style="display:inline-block; padding:2px 8px; border-radius:4px; background:var(--accent-dim); color:var(--accent); font-size:0.6rem; font-weight:600; letter-spacing:0.06em; text-transform:uppercase; font-family:var(--mono);">Claude Code</span>
      <span style="display:inline-block; padding:2px 8px; border-radius:4px; background:var(--bg-4); color:var(--text-2); font-size:0.6rem; font-weight:500; letter-spacing:0.04em; text-transform:uppercase; font-family:var(--mono);">16 Tools</span>
      <span style="display:inline-block; padding:2px 8px; border-radius:4px; background:var(--bg-4); color:var(--text-2); font-size:0.6rem; font-weight:500; letter-spacing:0.04em; text-transform:uppercase; font-family:var(--mono);">Single-Leg · 5–35 DTE</span>
    </div>
  </div>
  <div style="font-family:var(--mono); font-size:0.7rem; color:var(--text-3); background:var(--bg-3); padding:4px 10px; border-radius:4px; border:1px solid var(--border);">{_now_str}</div>
</div>
""", unsafe_allow_html=True)

# ── Auto-refresh: detect external updates (auto_scan.py) and reload ───────────
# Lightweight background check every 90s — only active on Predictions tab.
# If predictions.json was updated (e.g. by auto_scan.py), triggers a full rerun.
@st.fragment(run_every=90)
def _watch_predictions_file():
    _mtime = os.path.getmtime(PREDICTIONS_FILE) if os.path.exists(PREDICTIONS_FILE) else 0.0
    if st.session_state.get("pred_file_mtime", 0) != _mtime:
        st.session_state["pred_file_mtime"] = _mtime
        st.rerun()

if st.session_state.get("active_tab", "💬 Chat") == "📊 Predictions":
    _watch_predictions_file()

# ── Sector sentiment helpers (used in Predictions tab) ───────────────────────

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
    "Very Bullish": "#1f6b36",
    "Bullish":      "#3fb950",
    "Neutral":      "#484f58",
    "Bearish":      "#d29922",
    "Very Bearish": "#f85149",
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
            nt_sent, nt_ret  = _sentiment_for_window(closes, 21)
            mt_sent, mt_ret  = _sentiment_for_window(closes, 126)
            lt_sent, lt_ret  = _sentiment_for_window(closes, 252)
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


def _sentiment_badge(sentiment: str, ret_pct: float | None = None) -> str:
    color = _SENTIMENT_COLORS.get(sentiment, "#484f58")
    icon  = _SENTIMENT_ICONS.get(sentiment, "➡")
    badge = (
        f'<span style="background:{color};color:white;padding:2px 8px;'
        f'border-radius:0.25rem;font-size:0.82rem;font-weight:600;white-space:nowrap">'
        f'{icon} {sentiment}</span>'
    )
    if ret_pct is not None:
        sign = "+" if ret_pct >= 0 else ""
        badge += (
            f'<span style="color:{color};font-size:0.72rem;margin-left:0.25rem">'
            f'{sign}{ret_pct:.1f}%</span>'
        )
    return badge


def _sentiment_badge_delta(new_sent: str, new_ret: float, old_sent: str | None) -> str:
    """Badge with before→after indicator when sentiment changed."""
    new_badge = _sentiment_badge(new_sent, new_ret)
    if old_sent and old_sent != new_sent:
        old_badge = _sentiment_badge(old_sent)
        return (
            f'<span style="opacity:0.55">{old_badge}</span>'
            f'<span style="color:var(--text-3);font-size:0.72rem;margin:0 0.25rem">→</span>'
            f'{new_badge}'
            f'<span style="font-size:0.72rem;color:var(--amber);margin-left:0.25rem">changed</span>'
        )
    return new_badge


# ── Main content area — driven by sidebar navigation ───────────────────────────

_nav = _active_tab  # single source of truth — set in sidebar

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: Chat
# ══════════════════════════════════════════════════════════════════════════════

if _nav == "💬 Chat":

    # ── Empty state welcome ──────────────────────────────────────────────────
    if not st.session_state.conversation:
        st.markdown("""
<div style="max-width:560px; margin:3rem auto; text-align:center;">
  <div style="font-family:var(--mono); font-size:1.6rem; font-weight:700; color:var(--text-0); letter-spacing:-0.03em; margin-bottom:0.35rem;">
    OPTIONS<span style="color:var(--accent);">AI</span>
  </div>
  <div style="font-size:0.78rem; color:var(--text-2); margin-bottom:2.5rem; line-height:1.6;">
    AI-powered options analysis with real-time market data.<br>
    Ask about any ticker, scan for trades, or backtest a strategy.
  </div>
  <div style="display:grid; grid-template-columns:1fr 1fr; gap:0.6rem; text-align:left;">
    <div style="background:var(--bg-3); border:1px solid var(--border); border-radius:8px; padding:0.85rem 1rem;">
      <div style="font-size:0.62rem; color:var(--accent); text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:0.35rem;">Market Overview</div>
      <div style="font-size:0.78rem; color:var(--text-1); line-height:1.5;">"What's the market setup right now?"</div>
    </div>
    <div style="background:var(--bg-3); border:1px solid var(--border); border-radius:8px; padding:0.85rem 1rem;">
      <div style="font-size:0.62rem; color:var(--green); text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:0.35rem;">Find Trades</div>
      <div style="font-size:0.78rem; color:var(--text-1); line-height:1.5;">"Best NVDA calls this week"</div>
    </div>
    <div style="background:var(--bg-3); border:1px solid var(--border); border-radius:8px; padding:0.85rem 1rem;">
      <div style="font-size:0.62rem; color:var(--amber); text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:0.35rem;">Analysis</div>
      <div style="font-size:0.78rem; color:var(--text-1); line-height:1.5;">"Is IV on TSLA cheap or expensive?"</div>
    </div>
    <div style="background:var(--bg-3); border:1px solid var(--border); border-radius:8px; padding:0.85rem 1rem;">
      <div style="font-size:0.62rem; color:var(--red); text-transform:uppercase; letter-spacing:0.08em; font-weight:600; margin-bottom:0.35rem;">Backtest</div>
      <div style="font-size:0.78rem; color:var(--text-1); line-height:1.5;">"Backtest NVDA 5% OTM calls, 7 DTE"</div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

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

            # Apply current model selection before each call
            import options_chatbot as _oc_chat
            _oc_chat.CHAT_MODEL = st.session_state.get("chat_model", _DEFAULT_CHAT_MODEL)

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

elif _nav == "📊 Predictions":

    # ══ SECTION 1: Sector Sentiment Dashboard ════════════════════════════════
    @st.fragment
    def _sector_dashboard():
        # Refresh once per day at 10 AM ET — same trigger as the daily scan.
        # _watch_predictions_file() fires st.rerun() when predictions.json is
        # updated by auto_scan.py at ~10:10 AM, which lands here and clears the
        # sector cache for the day.
        from zoneinfo import ZoneInfo as _ZI
        _now_et   = datetime.now(_ZI("America/New_York"))
        _today_et = _now_et.strftime("%Y-%m-%d")
        if (
            st.session_state.get("_sector_fetch_date") != _today_et
            and _now_et.hour >= 10
        ):
            _fetch_sector_sentiments.clear()
            st.session_state["_sector_fetch_date"] = _today_et

        sector_rows = _fetch_sector_sentiments()

        # Compare against previous snapshot stored in session state
        prev_map: dict[str, dict] = {
            r["Sector"]: r
            for r in st.session_state.get("_sector_prev_rows", [])
        }
        # Detect any changes this cycle
        changed_sectors = [
            r["Sector"] for r in sector_rows
            if r["Sector"] in prev_map and any(
                r[k] != prev_map[r["Sector"]][k]
                for k in ("near_sent", "med_sent", "long_sent")
            )
        ]
        # Persist current as new "previous"
        st.session_state["_sector_prev_rows"] = sector_rows

        # Header row
        hdr_col, ref_col = st.columns([6, 1])
        hdr_col.markdown("### 🗺️ Sector Sentiment Dashboard")
        _last_refresh = st.session_state.get("_sector_last_refresh", "")
        hdr_col.caption(
            "Refreshes daily at 10 AM ET · Scores use price return, SMA position, and trend slope"
            + (f" · Last updated {_last_refresh}" if _last_refresh else "")
        )
        if ref_col.button("🔄", key="refresh_sectors", help="Force re-fetch sector data"):
            st.cache_data.clear()
            st.rerun()

        st.session_state["_sector_last_refresh"] = datetime.now().strftime("%H:%M")

        if changed_sectors:
            st.toast(f"Sector sentiment updated: {', '.join(changed_sectors)}", icon="📊")

        # Build table
        table_html = """
<style>
.sent-table { width:100%; border-collapse:collapse; font-size:0.82rem; }
.sent-table th { background:var(--bg-3); color:var(--text-1); padding:0.5rem 0.75rem;
                 text-align:left; font-weight:600; border-bottom:2px solid var(--border-subtle); }
.sent-table td { padding:0.5rem 0.75rem; border-bottom:1px solid var(--border); vertical-align:middle; }
.sent-table tr:hover td { background:rgba(255,255,255,0.03); }
.sent-table tr.changed-row td { background:rgba(224,168,0,0.05); }
.etf-badge { color:var(--text-3); font-size:0.72rem; margin-left:0.25rem; }
</style>
<table class="sent-table">
<thead><tr>
  <th>Sector</th>
  <th>Near-Term&nbsp;<span style="font-weight:400;color:var(--text-2)">(0–1 month)</span></th>
  <th>Medium-Term&nbsp;<span style="font-weight:400;color:var(--text-2)">(1–12 months)</span></th>
  <th>Long-Term&nbsp;<span style="font-weight:400;color:var(--text-2)">(12–36 months)</span></th>
</tr></thead><tbody>
"""
        for row in sector_rows:
            prev = prev_map.get(row["Sector"])
            row_changed = row["Sector"] in changed_sectors
            row_cls = " class='changed-row'" if row_changed else ""
            table_html += (
                f'<tr{row_cls}>'
                f'<td><strong>{row["Sector"]}</strong>'
                f'<span class="etf-badge">{row["ETF"]}</span></td>'
                f'<td>{_sentiment_badge_delta(row["near_sent"], row["near_ret"], prev["near_sent"] if prev else None)}</td>'
                f'<td>{_sentiment_badge_delta(row["med_sent"],  row["med_ret"],  prev["med_sent"]  if prev else None)}</td>'
                f'<td>{_sentiment_badge_delta(row["long_sent"], row["long_ret"], prev["long_sent"] if prev else None)}</td>'
                f'</tr>'
            )
        table_html += "</tbody></table>"
        st.markdown(table_html, unsafe_allow_html=True)

        # Near-term breadth summary
        all_sentiments = [r["near_sent"] for r in sector_rows]
        bull_count = sum(1 for s in all_sentiments if "Bullish" in s)
        bear_count = sum(1 for s in all_sentiments if "Bearish" in s)
        neut_count = len(all_sentiments) - bull_count - bear_count
        bias_color = "var(--green)" if bull_count > bear_count else ("var(--red)" if bear_count > bull_count else "var(--text-3)")
        bias_label = "Bullish Bias" if bull_count > bear_count else ("Bearish Bias" if bear_count > bull_count else "Mixed/Neutral")
        st.markdown(
            f'<div style="margin-top:0.5rem;font-size:0.82rem;color:var(--text-2)">'
            f'Near-term breadth: '
            f'<span style="color:var(--green)">▲ {bull_count} bullish</span> · '
            f'<span style="color:var(--text-3)">➡ {neut_count} neutral</span> · '
            f'<span style="color:var(--red)">▼ {bear_count} bearish</span> — '
            f'<strong style="color:{bias_color}">{bias_label}</strong>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Helper: enrich a pick with live chain data / derived fields ───────────
    import options_chatbot as _oc_pred

    def _enrich_pick(p: dict) -> dict:
        """
        Fill in any fields that may be missing from older saved records.
        For records without live chain data, fetch the real options chain once
        per ticker+direction per session (cached in st.session_state).
        """
        p = dict(p)
        sl_pct = p.get("stop_loss_pct", 50)
        tp_pct = p.get("profit_target_pct", 100)

        # ── Refresh strike/premium from live chain if record is stale ─────────
        if not p.get("live_chain") and p.get("ticker") and p.get("direction"):
            _cache_key = f"_chain_{p['ticker']}_{p['direction']}"
            if _cache_key not in st.session_state:
                try:
                    _opt = _oc_pred._fetch_best_option(
                        ticker        = p["ticker"],
                        trade_type    = p["direction"],
                        delta_target  = float(p.get("delta_est", 0.30)),
                        target_dte    = int(p.get("dte", 10)),
                        hv30_fallback = 0.30,
                    )
                    st.session_state[_cache_key] = _opt
                except Exception:
                    st.session_state[_cache_key] = None

            _opt = st.session_state.get(_cache_key)
            if _opt and _opt.get("live_chain"):
                p["strike_est"]    = _opt["strike"]
                p["live_premium"]  = _opt["premium"]  # current market price — display only
                # est_premium stays as the original entry estimate — P&L basis must not change
                if not p.get("est_premium"):
                    p["est_premium"] = _opt["premium"]
                p["delta_est"]     = _opt["delta"]
                if _opt.get("expiry"):
                    p["target_date"] = _opt["expiry"]
                p["dte"]           = _opt["dte"]
                p["live_chain"]    = True

        prem = p.get("est_premium", 0) or 0

        # ── SL / TP option prices ─────────────────────────────────────────────
        if prem:
            p["sl_option_px"] = round(prem * (1 - sl_pct / 100), 3)
            p["tp_option_px"] = round(prem * (1 + tp_pct / 100), 3)

        # ── Quality score ─────────────────────────────────────────────────────
        if p.get("quality_score") is None and p.get("iv_rank") is not None:
            p["quality_score"] = _oc_pred._compute_quality_score(
                p["iv_rank"], p.get("delta_est", 0.30), p.get("dte", 10),
                sp=_oc_pred._get_profile(p.get("ticker", "")),
            )

        # ── Strategy fields ───────────────────────────────────────────────────
        if p.get("strategy_label") is None and prem and p.get("stock_price"):
            strat = _oc_pred._generate_trade_strategy(
                trade_type        = p.get("direction", "call"),
                direction_score   = p.get("direction_score", p.get("confidence", 60)),
                quality_score     = p.get("quality_score", 50),
                iv_rank           = p.get("iv_rank", 50),
                rsi14             = p.get("rsi14", 50),
                spy_ret5          = p.get("spy_ret5", 0),
                est_premium       = prem,
                stop_loss_pct     = sl_pct,
                profit_target_pct = tp_pct,
                stock_price       = p["stock_price"],
                delta_est         = p.get("delta_est", 0.30),
            )
            p.update(strat)
        return p

    # ══ SECTION 2: Prediction History & Grading ══════════════════════════════
    st.markdown('<div class="section-header">Prediction History</div>', unsafe_allow_html=True)

    preds = _load_predictions()
    # Show only daily_scan type records in this section
    scan_preds = [p for p in preds if p.get("type") == "daily_scan"]

    graded  = [p for p in scan_preds if p.get("outcome")]
    pending = [p for p in scan_preds if not p.get("outcome")]

    if not scan_preds:
        st.info("No saved picks yet — scan and save today's picks below.")

    # Always render tabs + scan section (even when no picks yet)
    if True:
        hits    = [p for p in graded if p["outcome"] == "hit"]
        dir_ok  = [p for p in graded if p["outcome"] in ("hit", "directional")]
        call_g  = [p for p in graded if p.get("direction") == "call"]
        put_g   = [p for p in graded if p.get("direction") == "put"]

        # Summary metrics
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Total Picks",   len(scan_preds))
        m2.metric("Active Trades", len(pending))
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

        # Split performance: index vs equity
        if graded:
            _idx_graded = [p for p in graded if p.get("asset_class") == "index" or p.get("ticker", "").upper() in INDEX_TICKERS]
            _eq_graded  = [p for p in graded if p.get("asset_class") != "index" and p.get("ticker", "").upper() not in INDEX_TICKERS]
            if _idx_graded or _eq_graded:
                _split_idx_col, _split_eq_col = st.columns(2)
                with _split_idx_col:
                    st.markdown("**📊 Index picks**")
                    _idx_wins = [p for p in _idx_graded if p["outcome"] in ("hit", "directional")]
                    _idx_pnls = [p.get("option_gain_pct") or p.get("est_option_gain_pct") for p in _idx_graded if (p.get("option_gain_pct") or p.get("est_option_gain_pct")) is not None]
                    _ic1, _ic2 = st.columns(2)
                    _ic1.metric("Win Rate", f"{round(len(_idx_wins)/max(len(_idx_graded),1)*100,1)}%" if _idx_graded else "—",
                                help="Directional accuracy for index picks (QQQ/SPY/IWM/DIA/XLK)")
                    _ic2.metric("Avg Option P&L", f"{round(sum(_idx_pnls)/max(len(_idx_pnls),1),1)}%" if _idx_pnls else "—",
                                help="Average option gain/loss % across graded index picks")
                with _split_eq_col:
                    st.markdown("**📈 Equity picks**")
                    _eq_wins = [p for p in _eq_graded if p["outcome"] in ("hit", "directional")]
                    _eq_pnls = [p.get("option_gain_pct") or p.get("est_option_gain_pct") for p in _eq_graded if (p.get("option_gain_pct") or p.get("est_option_gain_pct")) is not None]
                    _ec1, _ec2 = st.columns(2)
                    _ec1.metric("Win Rate", f"{round(len(_eq_wins)/max(len(_eq_graded),1)*100,1)}%" if _eq_graded else "—",
                                help="Directional accuracy for single-stock equity picks")
                    _ec2.metric("Avg Option P&L", f"{round(sum(_eq_pnls)/max(len(_eq_pnls),1),1)}%" if _eq_pnls else "—",
                                help="Average option gain/loss % across graded equity picks")

        hist_tab_pending, hist_tab_graded, hist_tab_breakdown, hist_tab_sim, hist_tab_sectors = st.tabs(
            [f"⏳ Active ({len(pending)})",
             f"✅ Graded ({len(graded)})",
             "📊 Breakdown",
             "💰 Portfolio Sim",
             "🗺️ Sectors"]
        )

        # ── Auto-grade fragment (runs every 10 min when toggle is on) ────────────
        @st.fragment(run_every=600)
        def _auto_grade_runner():
            _enabled = st.session_state.get("auto_grade_enabled", False)
            if _enabled:
                # Only run during market hours + 30 min after close (9:30 AM - 4:30 PM ET, weekdays)
                from zoneinfo import ZoneInfo
                _now_et = datetime.now(ZoneInfo("America/New_York"))
                _wd = _now_et.weekday()
                _hr = _now_et.hour
                _mn = _now_et.minute
                _mins = _hr * 60 + _mn
                _market_open  = 9 * 60 + 30   # 9:30 AM ET
                _market_final = 18 * 60         # 6:00 PM ET (allow for settlement + yfinance data lag)
                if _wd >= 5 or _mins < _market_open or _mins > _market_final:
                    st.session_state["auto_grade_last_run"] = f"{_now_et.strftime('%H:%M')} ET — outside market hours, skipped"
                    return
                _ag_result = json.loads(log_prediction(action="grade"))
                _ag_msg = _ag_result.get("message", "Graded 0")
                try: _ag_n = int(_ag_msg.split()[1])
                except Exception: _ag_n = 0
                st.session_state["auto_grade_last_run"] = f"{_now_et.strftime('%H:%M')} ET"
                if _ag_n > 0:
                    st.toast(f"Auto-graded {_ag_n} pick(s)", icon="⚖️")
                    st.rerun()
        _auto_grade_runner()

        # ── Pending ───────────────────────────────────────────────────────────
        with hist_tab_pending:
            _ag_toggle_col, _ag_ts_col = st.columns([2, 6])
            _ag_toggle_col.toggle(
                "⚖️ Auto-grade (every 10 min)",
                value=True,
                key="auto_grade_enabled",
                help="Automatically checks all pending picks every 10 minutes and grades any that hit their TP, SL, or expiry.",
            )
            _ag_last = st.session_state.get("auto_grade_last_run")
            if _ag_last:
                _ag_ts_col.caption(f"Last ran: {_ag_last}")
            if not pending:
                st.info("No active trades.")
            else:
                # Group by effective batch date: rolled picks use last_rolled_date so they
                # appear in today's active batch rather than their original entry batch.
                _by_date: dict[str, list] = {}
                for p in pending:
                    _d = (p.get("last_rolled_date") or p.get("entry_date", ""))[:10]
                    _by_date.setdefault(_d, []).append(p)

                _sorted_dates = sorted(_by_date.keys(), reverse=True)
                for _i, _scan_date in enumerate(_sorted_dates):
                    _picks = _by_date[_scan_date]
                    _pending_count = len(_picks)
                    # Show time from the first pick's entry_date if it contains a time component
                    _raw_entry = _picks[0].get("entry_date", _scan_date)
                    _time_str  = _raw_entry[10:].strip() if len(_raw_entry) > 10 else ""
                    _label = f"📅 {_scan_date}{('  ' + _time_str) if _time_str else ''}  ·  {_pending_count} PICKS ACTIVE"
                    # Most recent section expanded by default, older ones collapsed
                    with st.expander(_label, expanded=(_i == 0)):
                        _gcol, _ = st.columns([2, 5])
                        if _gcol.button("⚖️ Grade this batch", key=f"grade_{_scan_date}",
                                        use_container_width=True,
                                        help="Check if any pick in this run hit its profit target or stop loss — grades immediately without waiting for the target date."):
                            with st.spinner(f"Grading {_scan_date}…"):
                                _grade_result = json.loads(log_prediction(action="grade", scan_date=_scan_date))
                            _grade_msg = _grade_result.get("message", "")
                            _n_graded  = int(_grade_msg.split()[1]) if _grade_msg else 0
                            _n_still   = sum(1 for _p in _picks if not _p.get("outcome"))
                            if _n_graded > 0:
                                st.toast(f"✅ Graded {_n_graded} pick(s) — check the Graded tab.", icon="⚖️")
                            else:
                                from datetime import date as _date
                                _entry_is_today = _scan_date == str(_date.today())
                                if _entry_is_today:
                                    st.toast("No data yet — picks were scanned today. Try again tomorrow after market close.", icon="⏳")
                                else:
                                    st.toast(f"No exits triggered yet — {_n_still} pick(s) still open within their window.", icon="📊")
                            st.rerun()
                        pend_rows = []
                        _batch_pnls = []   # collect option P&L values for batch summary
                        _batch_stks = []   # collect stock % values for batch summary
                        for p in sorted(_picks, key=lambda x: x.get("direction_score", x.get("confidence", 0)), reverse=True):
                            p      = _enrich_pick(p)
                            arrow  = "▲ CALL" if p.get("direction") == "call" else "▼ PUT"
                            sl_px  = p.get("sl_option_px")
                            tp_px  = p.get("tp_option_px")
                            cur_stk    = p.get("current_stock_pct")

                            # P&L: real live option price only — no delta estimation
                            _entry_px = p.get("est_premium")              # what was paid at entry
                            _live_px  = (p.get("current_option_px")       # real chain price from grading (same expiry/strike)
                                         or p.get("live_premium"))         # enriched live price (best current match)
                            if _live_px and _entry_px and _entry_px > 0:
                                cur_pnl  = round((_live_px / _entry_px - 1) * 100, 1)
                                pnl_cell = f"{cur_pnl:+.1f}%"
                                _batch_pnls.append(cur_pnl)
                            else:
                                cur_pnl  = None
                                pnl_cell = "—"
                            if cur_stk is not None:
                                _batch_stks.append(cur_stk)

                            _ep        = p.get("entry_open_price") or p.get("entry_price") or p.get("stock_price", 0)
                            _at_open   = p.get("entry_at_open") and not p.get("entry_open_price")
                            _ep_label  = f"${_ep:.2f} ⏳" if _at_open else f"${_ep:.2f}"
                            # Current live stock price set directly by _enrich_pick
                            _cur_stk_px = p.get("current_stock_px")
                            pend_rows.append({
                                "Ticker":       p["ticker"],
                                "Trade":        arrow,
                                "Dir. Score":   f"{p.get('direction_score', p.get('confidence', 0)):.0f}",
                                "Tech":         f"{p.get('tech_score', 0):.0f}",
                                "Quality":      f"{p.get('quality_score', 0):.0f}",
                                "Stock Price":  _ep_label,
                                "Curr. Price":  f"${_cur_stk_px:.2f}" if _cur_stk_px is not None else "—",
                                "Stock %":      f"{cur_stk:+.2f}%" if cur_stk is not None else "—",
                                "Options P&L":  pnl_cell,
                                "Strike":       f"${p.get('strike_est', 0):.2f}".rstrip("0").rstrip(".") if p.get("live_chain") else f"~${p.get('strike_est', 0):.0f}",
                                "Premium":      f"${_entry_px:.2f}" if _entry_px else "—",
                                "Current":      f"${_live_px:.2f}" if _live_px else "—",
                                "SL":           f"${sl_px:.2f}" if sl_px is not None else "—",
                                "TP":           f"${tp_px:.2f}" if tp_px is not None else "—",
                                "Option Expiry": p.get("expiry", "—")[:10] if p.get("expiry") else "—",
                                "Target Date":  p.get("target_date", "")[:10],
                            })
                        # Manual row-by-row table so delete button is inline with each row
                        _sorted_pend_picks = sorted(_picks, key=lambda x: x.get("direction_score", x.get("confidence", 0)), reverse=True)
                        _COL_W = [1.1, 1.1, 0.85, 0.55, 0.8, 0.95, 0.9, 0.8, 1.0, 0.75, 0.8, 0.8, 0.65, 0.8, 1.1, 1.1, 0.35]
                        _COL_H = ["Ticker","Trade","Dir. Score","Tech","Quality","Stock Price","Curr. Price","Stock %",
                                  "Options P&L","Strike","Premium","Current","SL","TP",
                                  "Option Expiry","Target Date",""]
                        _COL_TIPS = {
                            "Ticker":       "The stock symbol for this prediction",
                            "Trade":        "Direction of the trade — CALL (bullish) or PUT (bearish)",
                            "Dir. Score":   "Directional confidence score (0–100). Combines IV percentile, delta, DTE, and technical signals. Higher = stronger conviction.",
                            "Tech":         "Technical setup score (0–100). SMA trend + RSI + MACD at entry.",
                            "Quality":      "Quality score (0–100). Measures option structure quality: liquidity, spread, and Greeks alignment.",
                            "Stock Price":  "Stock price at the time the prediction was made",
                            "Curr. Price":  "Current stock price (equity feed, ~1–5 min delay)",
                            "Stock %":      "Percentage move of the stock since the prediction was entered",
                            "Options P&L":  "Estimated option gain/loss % based on current vs entry option price",
                            "Strike":       "The option strike price selected at entry",
                            "Premium":      "Estimated option premium (mid price) at entry",
                            "Current":      "Current live option mid price (~15 min delayed)",
                            "SL":           "Stop-loss price — option mid price at which the trade would be exited for a loss",
                            "TP":           "Take-profit price — option mid price at which the trade would be exited for a gain",
                            "Option Expiry":"Expiration date of the option contract",
                            "Target Date":  "The date by which the predicted move is expected to occur",
                            "":             "",
                        }


                        # Header
                        _hc = st.columns(_COL_W)
                        for _hi, _hn in enumerate(_COL_H):
                            _tip = _COL_TIPS.get(_hn, "")
                            _title_attr = f' title="{_tip}"' if _tip else ""
                            _hc[_hi].markdown(
                                f"<div class='pred-hdr'{_title_attr}>{_hn}</div>",
                                unsafe_allow_html=True,
                            )
                        # Data rows
                        for _ri, (_dp, _row) in enumerate(zip(_sorted_pend_picks, pend_rows)):
                            _row_cls = "pred-row-even" if _ri % 2 == 0 else "pred-row-odd"
                            _rc = st.columns(_COL_W)
                            _idx_badge = (
                                "<span title='Index ETF' style='font-size:0.72rem;margin-left:0.25rem;vertical-align:middle'>📊</span>"
                                if _dp.get("asset_class") == "index" else ""
                            )
                            _rc[0].markdown(f"<div class='pred-cell {_row_cls}'><b>{_row['Ticker']}</b>{_idx_badge}</div>", unsafe_allow_html=True)
                            _is_call = "CALL" in _row["Trade"]
                            _is_rolled = _dp.get("pick_status") == "rolled"
                            _roll_ct   = _dp.get("roll_count", 0)
                            _rolled_badge = (
                                f"<span title='Rolled forward {_roll_ct}x — original entry preserved' "
                                f"style='font-size:0.65rem;color:var(--text-3);margin-left:0.25rem;vertical-align:middle;"
                                f"background:var(--bg-3);border:1px solid var(--border-subtle);border-radius:0.25rem;padding:0.125rem 0.25rem'>↻{_roll_ct}</span>"
                                if _is_rolled else ""
                            )
                            _rc[1].markdown(
                                f"<div class='pred-cell {_row_cls}'>"
                                f"<span style='background:{'var(--green-dim,#0d2e0d)' if _is_call else 'var(--red-dim,#2e0d0d)'};"
                                f"color:{'var(--green)' if _is_call else 'var(--red)'};"
                                f"padding:0.125rem 0.5rem;border-radius:0.25rem;font-size:0.82rem;font-weight:700'>{_row['Trade']}</span>"
                                f"{_rolled_badge}</div>",
                                unsafe_allow_html=True,
                            )
                            _rc[2].markdown(f"<div class='pred-cell {_row_cls}'>{_row['Dir. Score']}</div>", unsafe_allow_html=True)
                            _rc[3].markdown(f"<div class='pred-cell {_row_cls}'><span style='color:var(--text-2)'>{_row['Tech']}</span></div>", unsafe_allow_html=True)
                            _rc[4].markdown(f"<div class='pred-cell {_row_cls}'><span style='color:var(--text-2)'>{_row['Quality']}</span></div>", unsafe_allow_html=True)
                            _rc[5].markdown(f"<div class='pred-cell {_row_cls}'>{_row['Stock Price']}</div>", unsafe_allow_html=True)
                            _rc[6].markdown(f"<div class='pred-cell {_row_cls}'><span style='color:var(--amber)'>{_row['Curr. Price']}</span></div>", unsafe_allow_html=True)
                            _sv = _row["Stock %"]
                            _sc = "var(--green)" if _sv.startswith("+") else ("var(--red)" if _sv.startswith("-") else "var(--text-2)")
                            _rc[7].markdown(f"<div class='pred-cell {_row_cls}'><span style='color:{_sc};font-weight:600'>{_sv}</span></div>", unsafe_allow_html=True)
                            _pv = _row["Options P&L"]
                            _pc = "var(--green)" if _pv.startswith("+") else ("var(--red)" if _pv.startswith("-") else "var(--text-2)")
                            _rc[8].markdown(f"<div class='pred-cell {_row_cls}'><span style='color:{_pc};font-weight:700'>{_pv}</span></div>", unsafe_allow_html=True)
                            for _ci, _key in enumerate(["Strike","Premium","Current","SL","TP","Option Expiry","Target Date"], start=9):
                                _rc[_ci].markdown(f"<div class='pred-cell {_row_cls}'>{_row[_key]}</div>", unsafe_allow_html=True)
                            # Inline delete button
                            _pid = _dp.get("id")
                            _confirm_key = f"_confirm_del_{_pid}"
                            if not st.session_state.get(_confirm_key):
                                if _rc[16].button("🗑", key=f"del_{_pid}", help=f"Delete {_dp.get('ticker')}"):
                                    st.session_state[_confirm_key] = True
                                    st.rerun()
                            else:
                                if _rc[16].button("✓", key=f"delconfirm_{_pid}", type="primary", help=f"Confirm delete {_dp.get('ticker')}"):
                                    _oc_pred.log_prediction(action="delete", prediction_id=_pid)
                                    st.session_state.pop(_confirm_key, None)
                                    st.rerun()

                        # ── Batch summary metrics ─────────────────────────────
                        if _batch_pnls or _batch_stks:
                            _avg_pnl = round(sum(_batch_pnls) / len(_batch_pnls), 1) if _batch_pnls else None
                            _avg_stk = round(sum(_batch_stks) / len(_batch_stks), 2) if _batch_stks else None
                            _best    = max(_batch_pnls) if _batch_pnls else None
                            _worst   = min(_batch_pnls) if _batch_pnls else None
                            _n_pos   = sum(1 for v in _batch_pnls if v > 0)
                            _n_neg   = sum(1 for v in _batch_pnls if v < 0)
                            _n_priced = len(_batch_pnls)

                            def _val_color(v):
                                if v is None: return "var(--text-3)"
                                return "var(--green)" if v >= 0 else "var(--red)"

                            def _summary_card(label, value_str, color, sub="&nbsp;"):
                                return (
                                    f"<div class='summary-card'>"
                                    f"<div class='sc-label'>{label}</div>"
                                    f"<div class='sc-value' style='color:{color}'>{value_str}</div>"
                                    f"<div class='sc-sub'>{sub}</div>"
                                    f"</div>"
                                )

                            _c1, _c2, _c3, _c4, _c5 = st.columns(5)
                            _win_color = "var(--green)" if _n_pos > _n_neg else ("var(--red)" if _n_neg > _n_pos else "var(--text-3)")
                            _c1.markdown(_summary_card(
                                "Avg Options P&L",
                                f"{_avg_pnl:+.1f}%" if _avg_pnl is not None else "—",
                                _val_color(_avg_pnl),
                                sub=f"{_n_priced}/{len(_picks)} picks priced",
                            ), unsafe_allow_html=True)
                            _c2.markdown(_summary_card(
                                "Avg Stock Move",
                                f"{_avg_stk:+.2f}%" if _avg_stk is not None else "—",
                                _val_color(_avg_stk),
                                sub=f"across {len(_batch_stks)} picks",
                            ), unsafe_allow_html=True)
                            _c3.markdown(_summary_card(
                                "Best Pick",
                                f"{_best:+.1f}%" if _best is not None else "—",
                                _val_color(_best),
                                sub="highest option P&L",
                            ), unsafe_allow_html=True)
                            _c4.markdown(_summary_card(
                                "Worst Pick",
                                f"{_worst:+.1f}%" if _worst is not None else "—",
                                _val_color(_worst),
                                sub="lowest option P&L",
                            ), unsafe_allow_html=True)
                            _c5.markdown(_summary_card(
                                "Winning / Losing",
                                f"{_n_pos} / {_n_neg}",
                                _win_color,
                                sub=f"{round(_n_pos / _n_priced * 100) if _n_priced else 0}% win rate",
                            ), unsafe_allow_html=True)

            st.markdown("---")

            # ══ SECTION 3: Daily Top Picks ════════════════════════════════════════════
            st.markdown('<div class="section-header">Today\'s Top Trades</div>', unsafe_allow_html=True)

            # ── Next auto-scan countdown banner ───────────────────────────────────────
            def _next_scan_info() -> tuple[str, str]:
                """Return (label, color) describing when the next auto-scan will fire."""
                from zoneinfo import ZoneInfo
                now_et    = datetime.now(ZoneInfo("America/New_York"))
                today_str = now_et.strftime("%Y-%m-%d")
                existing  = _load_predictions()
                today_done = any(
                    p.get("type") == "daily_scan" and not p.get("outcome") and
                    (p.get("last_rolled_date") or p.get("entry_date", ""))[:10] == today_str
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
                            return f"⏱ Auto-scan in {mins_left} min (10:00 AM ET today)", "#d29922"
                        else:
                            hrs = mins_left // 60
                            return f"⏱ Auto-scan in {hrs}h {mins_left % 60}m (10:00 AM ET today)", "#d29922"
                    else:
                        return "🔄 Auto-scan due now — will run on next page load", "#3fb950"
                # Otherwise find next weekday
                next_day = now_et + _td(days=1)
                while next_day.weekday() >= 5:
                    next_day += _td(days=1)
                label = "tomorrow" if (next_day.date() - now_et.date()).days == 1 else next_day.strftime("%A %b %d")
                return f"🕙 Next auto-scan: {label} at 10:00 AM ET", "#484f58"

            _scan_label, _scan_color = _next_scan_info()
            st.markdown(
                f'<div style="font-size:0.82rem;color:{_scan_color};margin-bottom:0.5rem">{_scan_label}</div>',
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
                    p.get("type") == "daily_scan" and not p.get("outcome") and
                    (p.get("last_rolled_date") or p.get("entry_date", ""))[:10] == today_str
                    for p in existing
                )

            if _auto_scan_due() and not st.session_state.get("auto_scan_done_today"):
                with st.spinner("Auto-scanning watchlist for today's top picks (10:00 AM ET trigger)…"):
                    _existing  = _load_predictions()
                    _pending   = [p for p in _existing if p.get("type") == "daily_scan" and not p.get("outcome")]
                    _rf_result = roll_forward_daily_picks(_pending, n_picks=5)
                from zoneinfo import ZoneInfo
                _today_str  = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
                _rolled     = _rf_result["rolled"]
                _new        = _rf_result["new"]
                if _rolled or _new:
                    _new_id = max((p.get("id", 0) for p in _existing), default=0)
                    for _p in _new:
                        _new_id += 1
                        _p["id"] = _new_id
                    _non_pending = [p for p in _existing if not (p.get("type") == "daily_scan" and not p.get("outcome"))]
                    _save_predictions(_non_pending + _rolled + _new)
                    st.session_state["auto_scan_done_today"] = _today_str
                    st.success(f"Auto-scan complete — {len(_rolled)} rolled, {len(_new)} new picks for {_today_str}.")
                    st.rerun()

            scan_col, refresh_col = st.columns([5, 1])

            if scan_col.button("🔍 Scan Watchlist for Top 5 Picks", use_container_width=True, key="scan_btn",
                               help="Analyzes all tickers in your watchlist using technical indicators, IV rank, and momentum. Returns the top 5 highest-confidence option setups for today with recommended strikes, premiums, and TP/SL targets."):
                with st.spinner(f"Scanning {len(DEFAULT_WATCHLIST)} tickers & evaluating active positions…"):
                    _existing = _load_predictions()
                    _pending  = [p for p in _existing if p.get("type") == "daily_scan" and not p.get("outcome")]
                    _result   = generate_position_recommendations(_pending, n_picks=5)
                    st.session_state["scan_result"] = _result
                    # daily_picks = HOLDs + new opportunities (for save compatibility)
                    st.session_state["daily_picks"] = (
                        [p for p in _result["active_positions"] if p["recommendation"] == "HOLD"]
                        + _result["new_opportunities"]
                    )
                st.rerun()


            if refresh_col.button("🔄", use_container_width=True, key="refresh_preds",
                                  help="Reload the page to pull the latest saved picks and grading results without running a new scan."):
                st.rerun()

            # ── Today's picks ─────────────────────────────────────────────────────────
            _scan_result = st.session_state.get("scan_result")
            picks = st.session_state.get("daily_picks", [])

            # ── Helper: render a single pick's detail expander ────────────────────
            def _render_pick_expander(p, prefix="", extra_label=""):
                p = _enrich_pick(p)
                direction = p.get("direction", "")
                arrow     = "📈" if direction == "call" else "📉"
                _dir_s    = p.get("direction_score", p.get("confidence", 0))
                _qual_s   = p.get("quality_score")
                _qual_str = f" · quality {_qual_s:.0f}" if _qual_s is not None else ""
                _label    = f"{arrow} {p['ticker']} — {_dir_s:.0f} direction{_qual_str}{extra_label}"
                with st.expander(_label):
                    dc1, dc2, dc3, dc4 = st.columns(4)
                    dc1.metric("Direction Score", f"{_dir_s:.0f}",
                               help="Predicts if stock moves the right way")
                    dc2.metric("Quality Score", f"{_qual_s:.0f}" if _qual_s is not None else "—",
                               help="Rates the option to buy if direction is right")
                    dc3.metric("Tech Score",   f"{p.get('tech_score', 0):.0f}")
                    dc4.metric("IV Rank",      f"{p.get('iv_rank', 0):.0f}th pct")
                    dc4, dc5, dc6 = st.columns(3)
                    dc4.metric("Stock Price",  f"${p.get('stock_price', 0):.2f}")
                    dc5.metric(
                        "Strike" + (" ✓" if p.get("live_chain") else " ~est"),
                        f"${p.get('strike_est', 0):.2f}".rstrip("0").rstrip("."),
                    )
                    dc6.metric("Delta Est.",   f"{p.get('delta_est', 0):.2f}")
                    dc7, dc8, dc9 = st.columns(3)
                    dc7.metric("Est. Premium", f"${p.get('est_premium', 0):.2f}")
                    dc8.metric("EV%",          f"{p.get('ev_pct', 0):.1f}%")
                    dc9.metric("5-Day Ret",    f"{p.get('ret5', 0):+.1f}%")
                    if p.get("signal_reasons"):
                        st.markdown("**Signal reasons:**")
                        for reason in p["signal_reasons"]:
                            st.markdown(f"- {reason}")
                    # Exit strategy
                    st.markdown("**Exit strategy:**")
                    is_call = direction == "call"
                    sl_px   = p.get("sl_option_px")
                    tp_px   = p.get("tp_option_px")
                    stk_sl  = p.get("stock_sl")
                    stk_tp  = p.get("stock_tp")
                    s1, s2, s3, s4 = st.columns(4)
                    s1.metric("Stop Loss",
                              f"${sl_px:.2f}" if sl_px is not None else f"−{p.get('stop_loss_pct', 50):.0f}%",
                              f"−{p.get('stop_loss_pct', 50):.0f}% on premium", delta_color="inverse")
                    s2.metric("Take Profit",
                              f"${tp_px:.2f}" if tp_px is not None else f"+{p.get('profit_target_pct', 100):.0f}%",
                              f"+{p.get('profit_target_pct', 100):.0f}% on premium", delta_color="normal")
                    s3.metric("Stock SL ~",
                              f"${stk_sl:.2f}" if stk_sl is not None else "—",
                              f"{'rises' if not is_call else 'falls'} to this", delta_color="inverse")
                    s4.metric("Stock TP ~",
                              f"${stk_tp:.2f}" if stk_tp is not None else "—",
                              f"{'falls' if not is_call else 'rises'} to this", delta_color="normal")
                    if p.get("strategy_comment"):
                        st.info(f"💡 {p['strategy_comment']}", icon=None)
                    st.caption(f"Target date: {p.get('target_date', '—')} · DTE at entry: {p.get('dte', '—')}d")

            # ── Section A: Active Positions with Recommendations ──────────────────
            if _scan_result and _scan_result.get("active_positions"):
                _active = _scan_result["active_positions"]
                st.markdown('<div class="section-header">ACTIVE POSITIONS</div>', unsafe_allow_html=True)
                st.markdown(
                    f"<div style='color:var(--text-3);font-size:0.72rem;margin-bottom:0.5rem'>"
                    f"{len(_active)} open position(s) re-evaluated against today\'s market data</div>",
                    unsafe_allow_html=True,
                )

                # Active positions table
                _active_rows = []
                for ap in _active:
                    ap = _enrich_pick(ap)
                    _dir = ap.get("direction", "")
                    _arrow = "📈 CALL" if _dir == "call" else "📉 PUT"
                    _rec = ap.get("recommendation", "HOLD")
                    _fresh_ds = ap.get("fresh_direction_score")
                    _score_d = ap.get("score_delta")
                    _pnl = ap.get("current_pnl_pct")
                    _active_rows.append({
                        "Ticker":       ap["ticker"],
                        "Trade":        _arrow,
                        "Action":       _rec,
                        "Dir. Score":   f"{_fresh_ds:.0f}" if _fresh_ds is not None else "—",
                        "Change":       f"{_score_d:+.1f}" if _score_d is not None else "—",
                        "P&L":          f"{_pnl:+.1f}%" if _pnl is not None else "—",
                        "Strike":       f"${ap.get('strike_est', 0):.2f}".rstrip("0").rstrip("."),
                        "Premium":      f"${ap.get('est_premium', 0):.2f}",
                        "Expiry":       ap.get("expiry", "—"),
                        "Reason":       ap.get("rec_reason", ""),
                    })
                st.markdown(_ft_table(
                    _active_rows,
                    pnl_cols=["P&L", "Change"],
                    rate_cols=["Dir. Score"],
                    badge_col="Trade",
                    mono_cols=["Strike", "Premium"],
                ), unsafe_allow_html=True)

                # Per-position expanders with action buttons
                for _idx, ap in enumerate(_active):
                    _rec = ap.get("recommendation", "HOLD")
                    _rec_icon = {"HOLD": "🟢", "EXIT": "🔴", "REPLACE": "🟡"}.get(_rec, "⚪")
                    _render_pick_expander(ap, extra_label=f" · {_rec_icon} {_rec}")

                    # Recommendation reason + action buttons
                    _reason = ap.get("rec_reason", "")
                    _pick_id = ap.get("id", _idx)

                    if _rec == "EXIT":
                        st.caption(f"Recommendation: {_reason}")
                        if st.button(f"Accept EXIT — close {ap['ticker']}", key=f"exit_{_pick_id}",
                                     use_container_width=True):
                            # Grade as manual_exit in predictions.json
                            _all_preds = _load_predictions()
                            for _pp in _all_preds:
                                if _pp.get("id") == ap.get("id"):
                                    _pp["outcome"] = "manual_exit"
                                    _pp["exit_reason"] = "manual_exit"
                                    _pp["graded_date"] = datetime.now().strftime("%Y-%m-%d")
                                    break
                            _save_predictions(_all_preds)
                            # Remove from scan_result
                            _scan_result["active_positions"] = [
                                x for x in _scan_result["active_positions"]
                                if x.get("id") != ap.get("id")
                            ]
                            st.session_state["scan_result"] = _scan_result
                            st.rerun()

                    elif _rec == "REPLACE":
                        st.caption(f"Recommendation: {_reason}")
                        _repl = ap.get("replace_with")
                        if _repl:
                            st.markdown(
                                f"<div style='color:var(--amber);font-size:0.72rem;margin-bottom:0.25rem'>"
                                f"Suggested replacement: <b>{_repl['ticker']} "
                                f"{_repl['direction'].upper()}</b> — "
                                f"direction {_repl['direction_score']:.0f}%, "
                                f"EV {_repl['ev_pct']:.1f}%</div>",
                                unsafe_allow_html=True,
                            )
                        _bc1, _bc2 = st.columns(2)
                        if _bc1.button(f"Accept REPLACE", key=f"replace_{_pick_id}",
                                       use_container_width=True):
                            # Grade old as replaced
                            _all_preds = _load_predictions()
                            for _pp in _all_preds:
                                if _pp.get("id") == ap.get("id"):
                                    _pp["outcome"] = "replaced"
                                    _pp["exit_reason"] = "replaced"
                                    _pp["graded_date"] = datetime.now().strftime("%Y-%m-%d")
                                    break
                            _save_predictions(_all_preds)
                            # Move replacement to new_opportunities
                            if _repl:
                                _scan_result["new_opportunities"].append(_repl)
                            _scan_result["active_positions"] = [
                                x for x in _scan_result["active_positions"]
                                if x.get("id") != ap.get("id")
                            ]
                            st.session_state["scan_result"] = _scan_result
                            # Update daily_picks
                            st.session_state["daily_picks"] = (
                                [p for p in _scan_result["active_positions"] if p.get("recommendation") == "HOLD"]
                                + _scan_result["new_opportunities"]
                            )
                            st.rerun()
                        if _bc2.button(f"Override: HOLD", key=f"override_hold_{_pick_id}",
                                       use_container_width=True):
                            for _ap2 in _scan_result["active_positions"]:
                                if _ap2.get("id") == ap.get("id"):
                                    _ap2["recommendation"] = "HOLD"
                                    _ap2["rec_reason"] = "User override — holding position"
                                    break
                            st.session_state["scan_result"] = _scan_result
                            st.session_state["daily_picks"] = (
                                [p for p in _scan_result["active_positions"] if p.get("recommendation") == "HOLD"]
                                + _scan_result["new_opportunities"]
                            )
                            st.rerun()

                    else:  # HOLD
                        st.caption(f"Recommendation: {_reason}")

                st.markdown("---")

            # ── Section B: New Opportunities ──────────────────────────────────────
            _new_opps = (_scan_result or {}).get("new_opportunities", []) if _scan_result else picks
            if not _scan_result and picks:
                _new_opps = picks  # fallback: no scan_result, just raw picks

            if _new_opps:
                _header = "NEW OPPORTUNITIES" if _scan_result and _scan_result.get("active_positions") else "TODAY\'S TOP TRADES"
                st.markdown(f'<div class="section-header">{_header}</div>', unsafe_allow_html=True)
                st.markdown(
                    f"<div style='color:var(--text-3);font-size:0.72rem;margin-bottom:0.5rem'>"
                    f"Scanned {len(DEFAULT_WATCHLIST)} large-cap tickers · "
                    f"{datetime.now().strftime('%b %d, %Y %H:%M')} · "
                    f"Top {len(_new_opps)} by confidence score</div>",
                    unsafe_allow_html=True,
                )

                # New opportunities table
                scan_rows = []
                for p in _new_opps:
                    p = _enrich_pick(p)
                    direction = p.get("direction", "")
                    arrow = "📈 CALL" if direction == "call" else "📉 PUT"
                    sl_px = p.get("sl_option_px")
                    tp_px = p.get("tp_option_px")
                    scan_rows.append({
                        "Ticker":       p["ticker"],
                        "Trade":        arrow,
                        "Dir. Score":   f"{p.get('direction_score', p.get('confidence', 0)):.0f}",
                        "Quality":      f"{p.get('quality_score', 0):.0f}",
                        "Stock Price":  f"${p.get('stock_price', 0):.2f}",
                        "Strike":       f"${p.get('strike_est', 0):.2f}".rstrip("0").rstrip(".") if p.get("live_chain") else f"~${p.get('strike_est', 0):.0f}",
                        "Premium":      f"${p.get('est_premium', 0):.2f}" + ("" if p.get("live_chain") else " ~"),
                        "SL":           f"${sl_px:.2f}" if sl_px is not None else "—",
                        "TP":           f"${tp_px:.2f}" if tp_px is not None else "—",
                        "Strategy":     p.get("strategy_label", "Standard"),
                        "EV%":          f"{p.get('ev_pct', 0):.1f}%",
                    })
                st.markdown(_ft_table(
                    scan_rows,
                    pnl_cols=["EV%"],
                    rate_cols=["Dir. Score", "Quality"],
                    badge_col="Trade",
                    mono_cols=["Stock Price", "Strike", "Premium", "SL", "TP"],
                ), unsafe_allow_html=True)

                # Per-pick expanders
                for p in _new_opps:
                    _render_pick_expander(p)

                # ── Save button ───────────────────────────────────────────────────
                if st.button("💾 Save picks to history", use_container_width=True, key="save_picks_btn"):
                    preds_all = _load_predictions()
                    today_str = datetime.now().strftime("%Y-%m-%d")

                    # Picks to save: HOLDs (refresh scores) + new opportunities
                    _holds = [p for p in (_scan_result or {}).get("active_positions", [])
                              if p.get("recommendation") == "HOLD"] if _scan_result else []
                    _to_save = _new_opps  # new picks always saved

                    # Refresh HOLD picks in predictions.json (update scoring, preserve entry)
                    _existing_ids = {p.get("id") for p in _holds if p.get("id")}
                    for _pp in preds_all:
                        if _pp.get("id") in _existing_ids:
                            _hold_match = next((h for h in _holds if h.get("id") == _pp.get("id")), None)
                            if _hold_match:
                                for _f in ("direction_score", "tech_score", "quality_score",
                                           "iv_rank", "ret5", "rsi14", "spy_ret5", "ev_pct",
                                           "signal_reasons", "strategy_label", "strategy_comment",
                                           "last_rolled_date"):
                                    if _f in _hold_match:
                                        _pp[_f] = _hold_match[_f]
                                _pp["pick_status"] = "rolled"
                                _pp["roll_count"] = _pp.get("roll_count", 0) + 1
                                _pp["last_rolled_date"] = datetime.now().strftime("%Y-%m-%d")

                    # Add new picks (dedup by ticker for today)
                    already = {p.get("ticker") for p in preds_all
                               if p.get("entry_date", "")[:10] == today_str and p.get("type") == "daily_scan"}
                    new_id = max((p.get("id", 0) for p in preds_all), default=0)
                    added = 0
                    for p in _to_save:
                        if p["ticker"] in already:
                            continue
                        new_id += 1
                        rec = dict(p)
                        rec["id"] = new_id
                        preds_all.append(rec)
                        added += 1

                    _save_predictions(preds_all)
                    _held = len(_existing_ids)
                    if added or _held:
                        st.success(f"Saved {added} new pick(s), refreshed {_held} held position(s).")
                    else:
                        st.info("Today's picks were already saved.")
                    st.session_state.pop("daily_picks", None)
                    st.session_state.pop("scan_result", None)
                    st.rerun()

            elif not picks and not _scan_result:
                st.info(
                    "Click **Scan Watchlist** to generate today\'s top 5 high-confidence option setups "
                    "across all large-cap tickers."
                )

            # ── Daily Performance Trends ───────────────────────────────────────────────
            st.markdown("---")
            st.markdown('<div class="section-header">Daily Performance Trends</div>', unsafe_allow_html=True)

            _PERF_FILE = os.path.join(os.path.dirname(__file__), "daily_performance.json")
            _perf_data: list[dict] = []
            if os.path.exists(_PERF_FILE):
                try:
                    with open(_PERF_FILE) as _pf:
                        _perf_data = json.load(_pf)
                except Exception:
                    _perf_data = []

            if not _perf_data:
                st.info("No daily performance data yet — auto-grading will populate this after the first picks expire.")
            else:
                _perf_df = pd.DataFrame(sorted(_perf_data, key=lambda x: x["date"], reverse=True))

                # ── All-time KPIs ──────────────────────────────────────────────────────
                _latest = _perf_df.iloc[0]
                _k1, _k2, _k3, _k4 = st.columns(4)
                _k1.metric(
                    "All-Time Win Rate",
                    f"{_latest.get('all_time_win_rate_pct', '—')}%",
                    help="Directional accuracy across all graded picks ever"
                )
                _k2.metric(
                    "Total Graded",
                    _latest.get("all_time_graded", "—"),
                    help="Total picks graded (wins + losses)"
                )
                _streak_val = _latest.get("current_streak", 0)
                _streak_typ = _latest.get("current_streak_type", "")
                _streak_icon = "🟢" if _streak_typ == "win" else "🔴"
                _k3.metric(
                    "Current Streak",
                    f"{_streak_icon} {_streak_val}x {_streak_typ}",
                    help="Consecutive wins or losses heading into today"
                )
                _gains = [r["avg_est_option_gain_pct"] for r in _perf_data if r.get("avg_est_option_gain_pct") is not None]
                _k4.metric(
                    "Avg Option Gain",
                    f"{round(sum(_gains)/len(_gains), 1)}%" if _gains else "—",
                    help="Average estimated option P&L across all graded days"
                )

                # ── Score calibration insight ──────────────────────────────────────────
                _hi_rates = [r["high_score_win_rate"] for r in _perf_data if r.get("high_score_win_rate") is not None]
                _lo_rates = [r["low_score_win_rate"]  for r in _perf_data if r.get("low_score_win_rate")  is not None]
                if _hi_rates and _lo_rates:
                    _hi_avg = round(sum(_hi_rates) / len(_hi_rates), 1)
                    _lo_avg = round(sum(_lo_rates) / len(_lo_rates), 1)
                    _diff   = _hi_avg - _lo_avg
                    _cal_color = "var(--green)" if _diff >= 5 else ("var(--amber)" if _diff >= 0 else "var(--red)")
                    st.markdown(
                        f"<div style='background:rgba(255,255,255,0.04);border-radius:0.5rem;padding:0.75rem 1rem;margin-bottom:0.75rem'>"
                        f"<span style='color:var(--text-2);font-size:0.82rem'>Score Calibration — Dir Score ≥80 vs &lt;80</span><br>"
                        f"<span style='color:{_cal_color};font-weight:600'>High-score picks: {_hi_avg}% win rate &nbsp;|&nbsp; "
                        f"Low-score picks: {_lo_avg}% win rate &nbsp;|&nbsp; Edge: {'+' if _diff>=0 else ''}{_diff}pp</span>"
                        f"<span style='color:var(--text-3);font-size:0.72rem;margin-left:0.5rem'>"
                        f"{'✅ Scores are predictive' if _diff >= 5 else ('⚠️ Weak separation' if _diff >= 0 else '❌ Scores may be inverted')}"
                        f"</span></div>",
                        unsafe_allow_html=True,
                    )

                # ── Per-day table ──────────────────────────────────────────────────────
                _display_cols = {
                    "date":                    "Date",
                    "picks_graded":            "Graded",
                    "win_rate_pct":            "Win Rate",
                    "avg_est_option_gain_pct": "Avg Gain",
                    "high_score_win_rate":     "High Score W%",
                    "low_score_win_rate":      "Low Score W%",
                    "current_streak":          "Streak",
                }
                _perf_show = _perf_df[[c for c in _display_cols if c in _perf_df.columns]].rename(columns=_display_cols)
                for _pct_col in ["Win Rate", "Avg Gain", "High Score W%", "Low Score W%"]:
                    if _pct_col in _perf_show.columns:
                        _perf_show[_pct_col] = _perf_show[_pct_col].apply(
                            lambda v: f"{v}%" if pd.notna(v) and v != "" else "—"
                        )
                with st.expander("📅 Day-by-day breakdown", expanded=True):
                    st.markdown(_ft_table(
                        _perf_show,
                        pnl_cols=["Avg Gain"],
                        rate_cols=["Win Rate", "High Score W%", "Low Score W%"],
                    ), unsafe_allow_html=True)

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
                    filtered.sort(key=lambda x: x.get("option_gain_pct") or x.get("est_option_gain_pct") or 0, reverse=True)
                elif sort_by == "Confidence":
                    filtered.sort(key=lambda x: x.get("direction_score") or x.get("confidence") or 0, reverse=True)

                rows = []
                for p in filtered:
                    actual  = p.get("actual_move_pct")
                    opt_pnl = p.get("option_gain_pct") or p.get("est_option_gain_pct")
                    arrow   = "▲ CALL" if p.get("direction") == "call" else "▼ PUT"
                    exit_r  = p.get("exit_reason", "expired")
                    exit_label = {"tp_hit": "TP Hit", "sl_hit": "SL Hit",
                                  "time_exit": "Time Exit", "expired": "Expired",
                                  "indicator_exit": "Smart Exit"}.get(exit_r, exit_r)
                    rows.append({
                        "Date":         p.get("entry_date", "")[:16],  # include HH:MM if present
                        "Ticker":       p["ticker"],
                        "Trade":        arrow,
                        "Confidence":   f"{p.get('direction_score') or p.get('confidence', 0):.0f}",
                        "Stock %":      f"{actual:+.2f}%" if actual is not None else "—",
                        "Options P&L":  f"{opt_pnl:+.1f}%" if opt_pnl is not None else "—",
                        "Exit":         exit_label,
                        "Outcome":      outcome_icon.get(p["outcome"], "?") + " " + p["outcome"].upper(),
                        "Option Expiry": p.get("expiry", "—")[:10] if p.get("expiry") else "—",
                        "Target Date":  p.get("target_date", "")[:10],
                    })

                # Exit type counts
                _n_smart = sum(1 for p in filtered if p.get("exit_reason") == "indicator_exit")
                if _n_smart > 0:
                    st.caption(f"Smart Exits: {_n_smart} trade(s) closed early by indicator logic")

                # Group graded picks by scan date, each with its own Undo button
                _graded_by_date: dict[str, list] = {}
                for _row_p, _row_r in zip(filtered, rows):
                    _gd = _row_p.get("entry_date", "")[:10]
                    _graded_by_date.setdefault(_gd, []).append((_row_p, _row_r))

                for _gdate in sorted(_graded_by_date.keys(), reverse=True):
                    _gpicks = _graded_by_date[_gdate]
                    _gcnt   = len(_gpicks)
                    _glabel = f"📅 {_gdate}  ·  {_gcnt} graded pick{'s' if _gcnt != 1 else ''}"
                    with st.expander(_glabel, expanded=True):
                        _undo_col, _ = st.columns([2, 5])
                        if _undo_col.button("↩ Undo grading", key=f"ungrade_{_gdate}",
                                            use_container_width=True,
                                            help="Restore these picks to Pending so you can re-grade them."):
                            log_prediction(action="ungrade", scan_date=_gdate)
                            st.rerun()

                        _sub_rows = [r for _, r in _gpicks]
                        _gtbl_col, _gdel_col = st.columns([30, 1])
                        with _gtbl_col:
                            st.markdown(_ft_table(
                                _sub_rows,
                                pnl_cols=["Stock %", "Options P&L"],
                                rate_cols=["Confidence"],
                                badge_col="Trade",
                            ), unsafe_allow_html=True)
                        with _gdel_col:
                            st.markdown("<div style='height:2.5rem'></div>", unsafe_allow_html=True)
                            for _gp, _ in _gpicks:
                                _gpid = _gp.get("id")
                                _gconfirm_key = f"_confirm_del_{_gpid}"
                                if not st.session_state.get(_gconfirm_key):
                                    if st.button("🗑", key=f"gdel_{_gpid}", help=f"Delete {_gp.get('ticker')}"):
                                        st.session_state[_gconfirm_key] = True
                                        st.rerun()
                                else:
                                    if st.button("✓", key=f"gdelconfirm_{_gpid}", type="primary", help=f"Confirm delete {_gp.get('ticker')}"):
                                        _oc_pred.log_prediction(action="delete", prediction_id=_gpid)
                                        st.session_state.pop(_gconfirm_key, None)
                                        st.rerun()

                # ── Per-pick daily performance breakdown ──────────────────────
                st.markdown('<div class="section-header">Daily Performance by Pick</div>', unsafe_allow_html=True)
                st.caption("Estimated option value each day the trade was held, using delta-approximation + linear theta decay.")
                for p in filtered:
                    daily = p.get("daily_option_pnl")
                    _icon = {"hit": "✅", "directional": "🟡", "miss": "❌"}.get(p.get("outcome",""), "?")
                    _dir  = "📈 CALL" if p.get("direction") == "call" else "📉 PUT"
                    _lbl  = f"{_icon} {p['ticker']} {_dir} — entered {p.get('entry_date','')[:10]}"
                    with st.expander(_lbl, expanded=False):
                        if not daily:
                            st.caption("Daily breakdown unavailable — re-grade this pick to generate it.")
                        else:
                            _d_df = pd.DataFrame(daily)
                            _d_df = _d_df.rename(columns={
                                "date":      "Date",
                                "stock_px":  "Stock Price",
                                "stock_chg": "Stock Δ%",
                                "opt_px":    "Est. Option $",
                                "day_pct":   "Day %",
                                "cum_pct":   "Cumulative %",
                            })

                            st.markdown(_ft_table(
                                _d_df,
                                pnl_cols=["Day %", "Cumulative %", "Stock Δ%"],
                                mono_cols=["Stock Price", "Est. Option $"],
                            ), unsafe_allow_html=True)

                            # mini summary: best day, worst day, max drawdown
                            _days = [r["day_pct"] for r in daily]
                            _cums = [r["cum_pct"] for r in daily]
                            _s1, _s2, _s3 = st.columns(3)
                            _s1.metric("Best Day",  f"{max(_days):+.1f}%")
                            _s2.metric("Worst Day", f"{min(_days):+.1f}%")
                            _peak = max(_cums)
                            _trough_after_peak = min(_cums[_cums.index(_peak):]) if _peak in _cums else min(_cums)
                            _s3.metric("Peak → Trough", f"{_peak:+.1f}% → {_trough_after_peak:+.1f}%")

                # ── Rolled picks: same ticker+direction on consecutive days ──
                st.markdown('<div class="section-header">Rolled Positions</div>', unsafe_allow_html=True)
                st.caption("If the same pick appeared on back-to-back days, this shows the compounded option P&L had you held and rolled.")

                # Build consecutive runs per ticker+direction (sorted by entry_date)
                from itertools import groupby
                all_graded_sorted = sorted(graded, key=lambda x: (x["ticker"], x.get("direction",""), x.get("entry_date","")))
                rolled_rows = []
                for (ticker, direction), group in groupby(all_graded_sorted, key=lambda x: (x["ticker"], x.get("direction",""))):
                    run: list[dict] = []
                    for p in group:
                        if p.get("option_gain_pct") is None and p.get("est_option_gain_pct") is None:
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
                                    compound *= (1 + (r.get("option_gain_pct") or r.get("est_option_gain_pct") or 0) / 100.0)
                                total_pct = round((compound - 1.0) * 100, 1)
                                arrow = "📈 CALL" if direction == "call" else "📉 PUT"
                                rolled_rows.append({
                                    "Ticker":      ticker,
                                    "Trade":       arrow,
                                    "Days Rolled": len(run),
                                    "From":        run[0]["entry_date"][:10],
                                    "To":          run[-1]["entry_date"][:10],
                                    "Daily P&Ls":  " → ".join(f"{(r.get('option_gain_pct') or r.get('est_option_gain_pct') or 0):+.1f}%" for r in run),
                                    "Rolled P&L":  f"{total_pct:+.1f}%",
                                })
                            run = [p]
                    # flush final run
                    if len(run) >= 2:
                        compound = 1.0
                        for r in run:
                            compound *= (1 + (r.get("option_gain_pct") or r.get("est_option_gain_pct") or 0) / 100.0)
                        total_pct = round((compound - 1.0) * 100, 1)
                        arrow = "📈 CALL" if direction == "call" else "📉 PUT"
                        rolled_rows.append({
                            "Ticker":      ticker,
                            "Trade":       arrow,
                            "Days Rolled": len(run),
                            "From":        run[0]["entry_date"][:10],
                            "To":          run[-1]["entry_date"][:10],
                            "Daily P&Ls":  " → ".join(f"{(r.get('option_gain_pct') or r.get('est_option_gain_pct') or 0):+.1f}%" for r in run),
                            "Rolled P&L":  f"{total_pct:+.1f}%",
                        })

                if not rolled_rows:
                    st.info("No consecutive same-direction picks yet — rolled returns will appear here once the same pick repeats on back-to-back days.")
                else:
                    _df_rolled = pd.DataFrame(rolled_rows).sort_values("Days Rolled", ascending=False)
                    st.markdown(_ft_table(
                        _df_rolled,
                        pnl_cols=["Rolled P&L"],
                        badge_col="Trade",
                    ), unsafe_allow_html=True)

        # ── Breakdown ─────────────────────────────────────────────────────────
        with hist_tab_breakdown:
            if not graded:
                st.info("No graded picks to break down yet.")
            else:
                st.markdown('<div class="section-header">Per-Ticker Accuracy</div>', unsafe_allow_html=True)
                tickers_seen = sorted({p["ticker"] for p in graded})
                tk_rows = []
                for tk in tickers_seen:
                    tk_preds = [p for p in graded if p["ticker"] == tk]
                    tk_hits  = [p for p in tk_preds if p["outcome"] == "hit"]
                    tk_dir   = [p for p in tk_preds if p["outcome"] in ("hit", "directional")]
                    tk_call  = [p for p in tk_preds if p.get("direction") == "call"]
                    tk_put   = [p for p in tk_preds if p.get("direction") == "put"]
                    avg_dir = round(sum(p.get("direction_score") or p.get("confidence") or 0 for p in tk_preds)
                                    / max(len(tk_preds), 1), 1)
                    avg_actual = [p.get("actual_move_pct") for p in tk_preds if p.get("actual_move_pct") is not None]
                    tk_rows.append({
                        "Ticker":       tk,
                        "Picks":        len(tk_preds),
                        "Hit %":        f"{round(len(tk_hits)/len(tk_preds)*100,1)}%",
                        "Dir %":        f"{round(len(tk_dir)/len(tk_preds)*100,1)}%",
                        "Call / Put":   f"{len(tk_call)} / {len(tk_put)}",
                        "Avg Dir Score": f"{avg_dir:.1f}%",
                        "Avg Move %":   f"{sum(avg_actual)/len(avg_actual):+.2f}%" if avg_actual else "—",
                    })
                tk_df = pd.DataFrame(tk_rows).sort_values("Dir %", ascending=False)
                st.markdown(_ft_table(
                    tk_df,
                    rate_cols=["Hit %", "Dir %"],
                    pnl_cols=["Avg Move %"],
                ), unsafe_allow_html=True)

                st.markdown('<div class="section-header">Direction Score vs Accuracy</div>', unsafe_allow_html=True)
                conf_buckets = {"0–40%": [], "40–55%": [], "55–70%": [], "70%+": []}
                for p in graded:
                    c = p.get("direction_score") or p.get("confidence") or 0
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
                    st.markdown(_ft_table(
                        cb_rows,
                        rate_cols=["Directional %"],
                    ), unsafe_allow_html=True)

        # ── Portfolio Sim ──────────────────────────────────────────────────────
        with hist_tab_sim:
            import math as _math

            _SIM_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sim_settings.json")
            _SIM_DEFAULTS = {"account_size": 10_000.0}

            if "sim_settings" not in st.session_state:
                try:
                    with open(_SIM_FILE) as _sf:
                        _loaded = json.load(_sf)
                        st.session_state["sim_settings"] = {
                            "account_size": float(_loaded.get("account_size", 10_000.0))
                        }
                except Exception:
                    st.session_state["sim_settings"] = _SIM_DEFAULTS.copy()
            _ss = st.session_state["sim_settings"]

            # ── Account size — auto-saves on change ────────────────────────────
            def _on_acct_change():
                _v = st.session_state.get("sim_acct", 10_000.0)
                st.session_state["sim_settings"]["account_size"] = _v
                try:
                    with open(_SIM_FILE, "w") as _sf:
                        json.dump({"account_size": _v}, _sf)
                except Exception:
                    pass

            with st.expander("⚙️ Account Settings", expanded=not bool(scan_preds)):
                st.number_input(
                    "Starting account size ($)",
                    min_value=500.0, max_value=10_000_000.0,
                    value=float(_ss["account_size"]), step=500.0,
                    key="sim_acct", on_change=_on_acct_change,
                    help="Capital is split equally across all active picks.",
                )

            # ── Classify index picks ───────────────────────────────────────────
            def _is_index_pick(p: dict) -> bool:
                return (p.get("asset_class") == "index" or
                        p.get("ticker", "").upper() in INDEX_TICKERS)

            # ── Build sim rows ─────────────────────────────────────────────────
            _all_picks_unfiltered = sorted(
                pending + graded,
                key=lambda p: (p.get("entry_date") or p.get("graded_date") or ""),
            )
            _view_filter = st.radio(
                "Show",
                ["All", "📈 Equity only", "📊 Index only"],
                horizontal=True, key="sim_view_filter",
                label_visibility="collapsed",
            )
            # Position sizing always uses the TOTAL pick count regardless of view filter.
            # Switching the filter changes what's displayed, not how much was allocated.
            _acct     = float(st.session_state.get("sim_acct", _ss["account_size"]))
            _n_picks  = max(len(_all_picks_unfiltered), 1)
            _pos_each = _acct / _n_picks   # equal-weight: account ÷ total active picks

            if _view_filter == "📈 Equity only":
                _all_picks = [p for p in _all_picks_unfiltered if not _is_index_pick(p)]
            elif _view_filter == "📊 Index only":
                _all_picks = [p for p in _all_picks_unfiltered if _is_index_pick(p)]
            else:
                _all_picks = _all_picks_unfiltered
            _rows      = []
            _cum_pnl   = 0.0

            for _p in _all_picks:
                if not _p.get("outcome"):
                    _p = _enrich_pick(_p)

                _dir_score  = float(_p.get("direction_score") or _p.get("confidence") or 50)
                _prem       = float(_p.get("est_premium") or 0)
                # floor(pos_dollars / (premium × 100))
                _contracts  = int(_pos_each / (_prem * 100)) if _prem > 0 else 0
                _cost       = round(_contracts * _prem * 100, 2)

                _is_graded  = bool(_p.get("outcome"))
                _gain_pct   = _p.get("option_gain_pct") or _p.get("est_option_gain_pct")
                _cur_opt_px = float(_p.get("current_option_px") or _p.get("live_premium") or 0)

                if _is_graded and _gain_pct is not None:
                    _realized_dollar   = round(_cost * float(_gain_pct) / 100.0, 2)
                    _unrealized_dollar = None
                    _cur_value         = round(_cost + _realized_dollar, 2)
                    _pnl_raw           = _realized_dollar
                    _cum_pnl          += _realized_dollar
                    _status            = _p.get("outcome", "graded")
                else:
                    _realized_dollar = None
                    if _cur_opt_px and _prem:
                        _unrealized_dollar = round(_contracts * (_cur_opt_px - _prem) * 100, 2)
                        _cur_value         = round(_cost + _unrealized_dollar, 2)
                        _pnl_raw           = _unrealized_dollar
                        _cum_pnl          += _unrealized_dollar
                    else:
                        _unrealized_dollar = None
                        _cur_value         = _cost
                        _pnl_raw           = 0.0
                    _status = "pending"

                _rows.append({
                    "Date":         (_p.get("entry_date") or "")[:10],
                    "Ticker":       _p.get("ticker", ""),
                    "Profile":      "📊" if _is_index_pick(_p) else "📈",
                    "Direction":    (_p.get("direction") or "").upper(),
                    "Strike":       _p.get("strike_est", ""),
                    "Expiry":       (_p.get("expiry") or "")[:10],
                    "Dir Score":    f"{_dir_score:.1f}%",
                    "Contracts":    _contracts,
                    "Premium":      f"${_prem:.2f}",
                    "Cost Basis":   f"${_cost:,.2f}",
                    "Curr Value":   f"${_cur_value:,.2f}" if _cur_value else "—",
                    "Unrealized $": f"${_unrealized_dollar:+,.2f}" if _unrealized_dollar is not None else "—",
                    "Realized $":   f"${_realized_dollar:+,.2f}" if _realized_dollar is not None else "—",
                    "Status":       _status,
                    # raw fields
                    "_pnl_raw":     _pnl_raw,
                    "_cum_raw":     _cum_pnl,
                    "_date_raw":    (_p.get("graded_date") or _p.get("entry_date") or "")[:10],
                    "_ticker":      _p.get("ticker", ""),
                    "_prem_raw":    _prem,
                    "_stock_price": float(_p.get("stock_price") or 0),
                    "_delta":       float(_p.get("delta_est") or 0.30),
                    "_direction":   _p.get("direction", "call"),
                    "_contracts":   _contracts,
                })

            if not _rows:
                st.info("No picks to simulate yet — run a scan first.")
            else:
                # ── Single source of truth for all stats ───────────────────────
                _graded_rows   = [r for r in _rows if r["Status"] != "pending"]
                _n_graded      = len(_graded_rows)
                _total_pnl     = sum(r["_pnl_raw"] for r in _rows)
                _total_pnl_pct = round(_total_pnl / _acct * 100, 2) if _acct else 0
                _wins   = [r for r in _rows if r["_pnl_raw"] > 0]
                _losses = [r for r in _rows if r["_pnl_raw"] <= 0]
                _win_rate = round(len(_wins) / max(len(_rows), 1) * 100, 1)
                _avg_win  = round(sum(r["_pnl_raw"] for r in _wins)   / max(len(_wins), 1), 2)
                _avg_loss = round(sum(r["_pnl_raw"] for r in _losses) / max(len(_losses), 1), 2)

                _cum_series    = [r["_cum_raw"] for r in _rows]
                _max_dd_dollar = 0.0
                _peak_dd       = 0.0
                for _v in _cum_series:
                    _peak_dd       = max(_peak_dd, _v)
                    _max_dd_dollar = min(_max_dd_dollar, _v - _peak_dd)

                _sharpe = None
                if _n_graded >= 10:
                    _ret_s = [r["_pnl_raw"] / _acct * 100 for r in _graded_rows if r["_pnl_raw"] != 0]
                    if len(_ret_s) >= 2:
                        import numpy as _np_sim
                        _arr = _np_sim.array(_ret_s)
                        _std = _arr.std(ddof=1)
                        if _std > 0:
                            _sharpe = round(float(_arr.mean() / _std * _np_sim.sqrt(252)), 2)

                # ── Summary stats bar ──────────────────────────────────────────
                _st1, _st2, _st3, _st4, _st5 = st.columns(5)
                _st1.metric("Portfolio P&L", f"${_total_pnl:+,.2f}", f"{_total_pnl_pct:+.2f}%",
                            delta_color="normal",
                            help="Realized (graded) + Unrealized (pending) P&L combined.")
                _st2.metric("Win Rate", f"{_win_rate}%", f"{len(_wins)}W / {len(_losses)}L")
                _st3.metric("Avg Win / Loss", f"${_avg_win:+,.2f}", f"Loss: ${_avg_loss:,.2f}")
                if _n_graded == 0:
                    _st4.metric("Max Drawdown", "—", "No graded trades yet", delta_color="off")
                else:
                    _st4.metric("Max Drawdown",
                                f"${_max_dd_dollar:,.2f}",
                                f"{round(_max_dd_dollar / _acct * 100, 1)}%",
                                delta_color="inverse")
                if _sharpe is not None:
                    _st5.metric("Sharpe", f"{_sharpe:.2f}")
                else:
                    _st5.metric("Sharpe", "—",
                                f"Available after {max(0, 10 - _n_graded)} more graded trade{'s' if max(0,10-_n_graded)!=1 else ''}",
                                delta_color="off")

                st.markdown("---")

                # ── Equity curve — time-series via underlying stock + delta ────
                import pandas as _pd_sim
                st.markdown('<div class="section-header">Equity Curve</div>', unsafe_allow_html=True)

                _tf_opts = ["Intraday (1h)", "Intraday (5m)", "Daily"]
                _tf = st.radio("Timeframe", _tf_opts, horizontal=True,
                               key="sim_tf", label_visibility="collapsed")
                _tf_interval = {"Intraday (1h)": "1h", "Intraday (5m)": "5m", "Daily": "1d"}[_tf]
                _is_intraday = _tf.startswith("Intraday")

                # For daily: start from the earliest entry date so we only show
                # actual held period — never hypothetical prior history.
                _entry_dates_raw = [r["_date_raw"] for r in _rows if r["_date_raw"]]
                _earliest_entry  = min(_entry_dates_raw) if _entry_dates_raw else datetime.now().strftime("%Y-%m-%d")

                try:
                    import yfinance as _yf_sim
                    from zoneinfo import ZoneInfo as _ZI_sim

                    _ET_sim  = _ZI_sim("America/New_York")
                    _ts_list = []

                    for _r in _rows:
                        _tk        = _r["_ticker"]
                        _delta_raw = _r["_delta"]
                        _d_signed  = _delta_raw if _r["_direction"] == "call" else -abs(_delta_raw)
                        _ctrs      = _r["_contracts"]
                        _sp_entry  = _r["_stock_price"]
                        _pick_date = _r["_date_raw"]      # when THIS pick was entered
                        if not _tk or _ctrs == 0:
                            continue
                        try:
                            if _is_intraday:
                                _sh = _yf_sim.Ticker(_tk).history(
                                    period="1d", interval=_tf_interval
                                )["Close"].dropna()
                            else:
                                # Fetch from this pick's entry date so history never
                                # predates when the position was opened.
                                _sh = _yf_sim.Ticker(_tk).history(
                                    start=_pick_date, interval="1d"
                                )["Close"].dropna()
                            if len(_sh) < 1:
                                continue
                            _sh.index = _sh.index.tz_convert(_ET_sim)
                            # Base = actual stock price at entry.
                            # Fallback to first bar only if entry price missing.
                            _base = _sp_entry if _sp_entry > 0 else float(_sh.iloc[0])
                            # option P&L ≈ contracts × delta × Δstock × 100
                            _opt_ts = (_ctrs * _d_signed * (_sh - _base) * 100).rename(_tk)
                            _ts_list.append(_opt_ts)
                        except Exception:
                            continue

                    if _ts_list:
                        _combined = _pd_sim.concat(_ts_list, axis=1).sort_index().ffill().fillna(0)
                        _port_ts  = _combined.sum(axis=1).rename("Portfolio P&L ($)")

                        # Prepend a true $0 origin point
                        _bar_delta = (_port_ts.index[1] - _port_ts.index[0]
                                      if len(_port_ts) > 1 else _pd_sim.Timedelta("1h"))
                        _zero_idx  = _port_ts.index[0] - _bar_delta
                        _port_ts   = _pd_sim.concat([
                            _pd_sim.Series([0.0], index=[_zero_idx], name="Portfolio P&L ($)"),
                            _port_ts,
                        ])

                        # SPY benchmark — same date range as portfolio
                        _chart_df = _port_ts.to_frame()
                        try:
                            if _is_intraday:
                                _spy_h = _yf_sim.Ticker("SPY").history(
                                    period="1d", interval=_tf_interval
                                )["Close"].dropna()
                            else:
                                _spy_h = _yf_sim.Ticker("SPY").history(
                                    start=_earliest_entry, interval="1d"
                                )["Close"].dropna()
                            if len(_spy_h) >= 2:
                                _spy_h.index = _spy_h.index.tz_convert(_ET_sim)
                                # Clip SPY to same window as portfolio
                                _spy_h = _spy_h[_spy_h.index >= _port_ts.index[0]]
                                if len(_spy_h) >= 1:
                                    _spy_base2 = float(_spy_h.iloc[0])
                                    _spy_pnl   = ((_spy_h / _spy_base2 - 1) * _acct).rename("SPY Benchmark ($)")
                                    _spy_pnl   = _pd_sim.concat([
                                        _pd_sim.Series([0.0], index=[_zero_idx], name="SPY Benchmark ($)"),
                                        _spy_pnl,
                                    ])
                                    _chart_df  = _chart_df.join(_spy_pnl, how="outer").sort_index().ffill()
                        except Exception:
                            pass

                        # Format x-axis labels
                        _fmt = "%H:%M" if _is_intraday else "%m/%d"
                        _chart_df.index = _chart_df.index.strftime(_fmt)

                        st.line_chart(_chart_df, use_container_width=True)
                        _spy_note = " vs SPY benchmark" if "SPY Benchmark ($)" in _chart_df.columns else ""
                        st.caption(
                            f"Portfolio P&L{_spy_note} — estimated from underlying stock moves × delta × contracts. "
                            f"Start = $0 at entry. X-axis: {'time of day (ET)' if _is_intraday else 'date'}."
                        )

                        # Drawdown area (daily mode only to avoid noise)
                        if not _is_intraday:
                            _dd3 = []
                            _pk3 = 0.0
                            for _cv3 in _chart_df["Portfolio P&L ($)"].dropna():
                                _pk3 = max(_pk3, _cv3)
                                _dd3.append(min(0.0, _cv3 - _pk3))
                            if any(v < 0 for v in _dd3):
                                _dd_df3 = _pd_sim.DataFrame(
                                    {"Drawdown ($)": _dd3},
                                    index=_chart_df.index[:len(_dd3)]
                                )
                                st.area_chart(_dd_df3, use_container_width=True, color=["#f85149"])
                                st.caption("Drawdown from peak.")
                    else:
                        st.info("No ticker data available for chart — check your internet connection.")
                except Exception as _e_curve:
                    st.caption(f"Chart unavailable: {_e_curve}")

                st.markdown("---")

                # ── Trade-by-trade table ────────────────────────────────────────
                st.markdown('<div class="section-header">Trade-by-Trade P&L</div>', unsafe_allow_html=True)
                _display_cols = [
                    "Date", "Ticker", "Profile", "Direction", "Strike", "Expiry",
                    "Dir Score", "Contracts", "Premium", "Cost Basis",
                    "Curr Value", "Unrealized $", "Realized $", "Status",
                ]
                _display_df = pd.DataFrame([{c: r[c] for c in _display_cols} for r in _rows])
                st.markdown(_ft_table(
                    _display_df,
                    pnl_cols=["Unrealized $", "Realized $"],
                    mono_cols=["Premium", "Cost Basis", "Curr Value"],
                    dim_cols=["Dir Score"],
                ), unsafe_allow_html=True)

                # ── Export CSV ──────────────────────────────────────────────────
                st.download_button(
                    "⬇️ Export CSV",
                    data=pd.DataFrame([{c: r[c] for c in _display_cols} for r in _rows]).to_csv(index=False),
                    file_name=f"portfolio_sim_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key="sim_csv_export",
                )

                # ── Index vs Equity breakdown ───────────────────────────────────
                st.markdown("---")
                st.markdown('<div class="section-header">Index vs Equity Split</div>', unsafe_allow_html=True)
                _idx_rows = [r for r in _rows if r["Profile"] == "📊"]
                _eq_rows  = [r for r in _rows if r["Profile"] == "📈"]

                def _mini_stats(label: str, subset: list) -> None:
                    if not subset:
                        st.markdown(f"**{label}** — no picks yet")
                        return
                    _s_wins    = [r for r in subset if r["_pnl_raw"] > 0]
                    _s_losses  = [r for r in subset if r["_pnl_raw"] <= 0]
                    _s_pnl     = sum(r["_pnl_raw"] for r in subset)
                    _s_wr      = round(len(_s_wins) / len(subset) * 100, 1)
                    _s_avg_w   = round(sum(r["_pnl_raw"] for r in _s_wins)   / max(len(_s_wins), 1), 2)
                    _s_avg_l   = round(sum(r["_pnl_raw"] for r in _s_losses) / max(len(_s_losses), 1), 2)
                    _s_pending = sum(1 for r in subset if r["Status"] == "pending")
                    _s_graded  = len(subset) - _s_pending
                    st.markdown(f"**{label}** · {_s_graded} graded · {_s_pending} open")
                    _mc1, _mc2, _mc3 = st.columns(3)
                    _mc1.metric("Total P&L", f"${_s_pnl:+,.2f}")
                    _mc2.metric("Win Rate",  f"{_s_wr}%")
                    _loss_str = f"${_s_avg_l:,.2f}" if _s_losses else "—"
                    _mc3.metric("Avg W / L", f"${_s_avg_w:+,.2f} / {_loss_str}")

                _split_l, _split_r = st.columns(2)
                with _split_l:
                    _mini_stats("📊 Index Picks (QQQ/SPY/IWM/DIA/XLK)", _idx_rows)
                with _split_r:
                    _mini_stats("📈 Equity Picks (Single Stocks)", _eq_rows)

        # ── Sectors ────────────────────────────────────────────────────────────
        with hist_tab_sectors:
            _sector_dashboard()

            st.markdown("---")
            st.markdown('<div class="section-header">Performance by Sector</div>', unsafe_allow_html=True)
            st.caption("All daily scan predictions grouped by sector — graded and pending.")

            if not scan_preds:
                st.info("No predictions yet — run a scan to start tracking sector performance.")
            else:
                import yfinance as _yf_sec

                # ── Resolve sector for one pick (cached per ticker) ────────────
                def _resolve_sector(p: dict) -> str:
                    _tk = p.get("ticker", "").upper()
                    if _tk in INDEX_TICKERS:
                        return "Index ETF"
                    if p.get("sector"):
                        return p["sector"]
                    _ck = f"_sector_cache_{_tk}"
                    if _ck not in st.session_state:
                        try:
                            st.session_state[_ck] = (
                                _yf_sec.Ticker(_tk).info.get("sector") or "Unknown"
                            )
                        except Exception:
                            st.session_state[_ck] = "Unknown"
                    return st.session_state[_ck]

                # ── Group picks by sector ──────────────────────────────────────
                _sec_groups: dict = {}
                for _sp in scan_preds:
                    _sec_groups.setdefault(_resolve_sector(_sp), []).append(_sp)

                # ── Canonical sector order (matches sentiment dashboard) ────────
                _sec_order = [s for s, _ in _SECTORS] + ["Index ETF", "Unknown"]
                _extra     = [k for k in _sec_groups if k not in _sec_order]
                _seen_sec  = set()

                # ── Hit-rate colour helper ─────────────────────────────────────
                def _hr_cell(rate):
                    if rate is None:
                        return "<span style='color:var(--text-3)'>—</span>"
                    if rate >= 70:
                        return f"<span style='color:var(--green);font-weight:bold'>{rate}%</span>"
                    if rate >= 50:
                        return f"<span style='color:var(--amber);font-weight:bold'>{rate}%</span>"
                    return f"<span style='color:var(--red);font-weight:bold'>{rate}%</span>"

                def _pnl_cell(val):
                    if val is None:
                        return "<span style='color:var(--text-3)'>—</span>"
                    col = "var(--green)" if val >= 0 else "var(--red)"
                    return f"<span style='color:{col};font-weight:bold'>{val:+.1f}%</span>"

                # ── Build HTML table ───────────────────────────────────────────
                _perf_html = """
<table class="sent-table">
<thead><tr>
  <th>Sector</th>
  <th>Picks</th>
  <th>Graded</th>
  <th>Hit Rate&nbsp;<span style="font-weight:400;color:var(--text-2)">(dir+target)</span></th>
  <th>Full Hit&nbsp;<span style="font-weight:400;color:var(--text-2)">(target only)</span></th>
  <th>Avg Option P&amp;L</th>
  <th>Call / Put</th>
  <th>Avg Score</th>
</tr></thead><tbody>
"""
                _has_rows = False
                for _sn in _sec_order + _extra:
                    if _sn in _seen_sec or _sn not in _sec_groups:
                        continue
                    _seen_sec.add(_sn)
                    _picks = _sec_groups[_sn]
                    _g     = [p for p in _picks if p.get("outcome")]
                    _pend  = len(_picks) - len(_g)
                    _hits  = sum(1 for p in _g if p.get("outcome") in ("hit", "directional"))
                    _full  = sum(1 for p in _g if p.get("outcome") == "hit")
                    _hr    = round(_hits / len(_g) * 100, 1) if _g else None
                    _fr    = round(_full / len(_g) * 100, 1) if _g else None
                    _pnls  = [
                        float(p.get("option_gain_pct") or p.get("est_option_gain_pct"))
                        for p in _g
                        if (p.get("option_gain_pct") or p.get("est_option_gain_pct")) is not None
                    ]
                    _avg_pnl   = round(sum(_pnls) / len(_pnls), 1) if _pnls else None
                    _calls     = sum(1 for p in _picks if p.get("direction") == "call")
                    _puts      = len(_picks) - _calls
                    _scores    = [float(p.get("direction_score") or p.get("confidence") or 0)
                                  for p in _picks]
                    _avg_score = round(sum(_scores) / len(_scores), 1) if _scores else None
                    _pend_note = f" <span style='color:var(--text-3);font-size:0.82rem'>({_pend} open)</span>" if _pend else ""
                    _perf_html += (
                        f"<tr>"
                        f"<td><strong>{_sn}</strong></td>"
                        f"<td>{len(_picks)}{_pend_note}</td>"
                        f"<td>{len(_g)}</td>"
                        f"<td>{_hr_cell(_hr)}</td>"
                        f"<td>{_hr_cell(_fr)}</td>"
                        f"<td>{_pnl_cell(_avg_pnl)}</td>"
                        f"<td>{_calls}C / {_puts}P</td>"
                        f"<td>{'—' if _avg_score is None else f'{_avg_score:.1f}'}</td>"
                        f"</tr>"
                    )
                    _has_rows = True

                if _has_rows:
                    _perf_html += "</tbody></table>"
                    st.markdown(_perf_html, unsafe_allow_html=True)

                    # Summary breadth line
                    _all_sec_hrs = []
                    for _sn, _picks in _sec_groups.items():
                        _g2 = [p for p in _picks if p.get("outcome")]
                        if _g2:
                            _all_sec_hrs.append(
                                sum(1 for p in _g2 if p.get("outcome") in ("hit", "directional")) / len(_g2)
                            )
                    if _all_sec_hrs:
                        _top_sec = round(sum(1 for h in _all_sec_hrs if h >= 0.70) / len(_all_sec_hrs) * 100)
                        _bot_sec = round(sum(1 for h in _all_sec_hrs if h < 0.50) / len(_all_sec_hrs) * 100)
                        st.markdown(
                            f'<div style="margin-top:0.5rem;font-size:0.82rem;color:var(--text-2)">'
                            f'Sector hit rates: '
                            f'<span style="color:var(--green)">▲ {_top_sec}% of sectors ≥ 70%</span> · '
                            f'<span style="color:var(--red)">▼ {_bot_sec}% of sectors &lt; 50%</span>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
                else:
                    st.info("Picks are pending — sector performance will appear after grading.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: Strategy Lab  (Backtest · Optimizer)
# ══════════════════════════════════════════════════════════════════════════════
elif _nav == "🔬 Strategy Lab":
    import options_chatbot as _oc
    st.markdown(
        "<h3 style='margin-bottom:0'>🔬 Strategy Lab</h3>"
        "<p style='color:gray;margin-top:2px'>Inspect every parameter the brain uses to score trades. "
        "Run the optimizer to improve them. Changes apply instantly across Chat and all tools.</p>",
        unsafe_allow_html=True,
    )
    sub_brain, sub_opt = st.tabs(["🧠 Strategy Brain", "🎯 Optimizer"])


    # ── SUB-TAB: Strategy Brain ───────────────────────────────────────────────
    with sub_brain:
        # Profile toggle
        _brain_profile = st.radio(
            "Strategy Profile",
            options=["equity", "index"],
            format_func=lambda x: "📈 Equity (Single Stocks)" if x == "equity" else "📊 Index (ETFs)",
            horizontal=True,
            key="brain_profile_select",
            help="Each profile has independent parameters. Switching profiles loads that profile's saved values.",
        )
        st.caption("Adjust any parameter and hit **Save** to apply instantly across chat, scans, and backtests. Every save creates a version history entry.")

        _sp   = _oc.STRATEGY_PROFILES[_brain_profile]
        _tgt  = _sp["targets"]
        _risk = _sp["risk"]
        _filt = _sp["filters"]
        _entry = _sp.get("entry", {})

        # ── Direction Score Weights ────────────────────────────────────────────
        _dsw  = _sp.get("direction_score_weights", {})
        _rsioe = _sp.get("rsi_overextension", {})
        st.markdown('<div class="section-header">Direction Score Weights</div>', unsafe_allow_html=True)
        st.caption("How each signal component weighs into the headline Direction Score (0–100). Weights are normalized automatically.")
        _ds1, _ds2, _ds3 = st.columns(3)
        _ds_tech = _ds1.slider("Tech setup weight",  0.10, 0.80, float(_dsw.get("tech",     0.55)), 0.05, key=f"br_ds_tech_{_brain_profile}",
                               help="RSI/MACD/SMA directional alignment. Higher = fundamental technicals dominate the score.")
        _ds_reg  = _ds2.slider("SPY regime weight",  0.05, 0.60, float(_dsw.get("regime",   0.30)), 0.05, key=f"br_ds_reg_{_brain_profile}",
                               help="Is SPY moving in the same direction as the trade? Higher = market regime matters more.")
        _ds_mom  = _ds3.slider("Momentum weight",    0.00, 0.40, float(_dsw.get("momentum", 0.15)), 0.05, key=f"br_ds_mom_{_brain_profile}",
                               help="5-day underlying return in the trade direction. Higher = needs strong recent move to score well.")
        _ds_total = _ds_tech + _ds_reg + _ds_mom or 1.0
        _ds1.caption(f"{_ds_tech/_ds_total*100:.0f}% normalized")
        _ds2.caption(f"{_ds_reg/_ds_total*100:.0f}% normalized")
        _ds3.caption(f"{_ds_mom/_ds_total*100:.0f}% normalized")

        st.caption("RSI overextension penalty — penalises trades against overbought/oversold conditions.")
        _rsi1, _rsi2, _rsi3, _rsi4 = st.columns(4)
        _rsi_sev_t = _rsi1.slider("RSI severe threshold",    60, 80, int(_rsioe.get("severe_threshold",   72)), 1, key=f"br_rsi_sev_t_{_brain_profile}",
                                  help="RSI above this (bullish) or below its mirror (bearish) triggers the severe penalty.")
        _rsi_mod_t = _rsi2.slider("RSI moderate threshold",  55, 75, int(_rsioe.get("moderate_threshold", 68)), 1, key=f"br_rsi_mod_t_{_brain_profile}",
                                  help="RSI above this (bullish) or below its mirror (bearish) triggers the moderate penalty.")
        _rsi_sev_p = _rsi3.slider("Severe penalty pts",      5, 25,  int(_rsioe.get("severe_penalty",     15)), 1, key=f"br_rsi_sev_p_{_brain_profile}",
                                  help="Points deducted from Direction Score when RSI severe overextension is detected.")
        _rsi_mod_p = _rsi4.slider("Moderate penalty pts",    1, 15,  int(_rsioe.get("moderate_penalty",    8)), 1, key=f"br_rsi_mod_p_{_brain_profile}",
                                  help="Points deducted from Direction Score when RSI moderate overextension is detected.")

        st.markdown("---")

        # ── Quality Score Weights ──────────────────────────────────────────────
        _qsw = _sp.get("quality_score_weights", {})
        st.markdown('<div class="section-header">Quality Score Weights</div>', unsafe_allow_html=True)
        st.caption("How each factor contributes to the Quality Score — rates the option contract itself (not stock direction).")
        _qs1, _qs2, _qs3 = st.columns(3)
        _qs_iv  = _qs1.slider("IV Rank weight",  0.10, 0.70, float(_qsw.get("iv_rank", 0.40)), 0.05, key=f"br_qs_iv_{_brain_profile}",
                              help="Low IV rank = cheap premium = higher score. Higher weight = option cost dominates quality rating.")
        _qs_d   = _qs2.slider("Delta fit weight", 0.10, 0.60, float(_qsw.get("delta",   0.35)), 0.05, key=f"br_qs_delta_{_brain_profile}",
                              help="How precisely delta matches the target. Higher weight = strike selection precision matters more.")
        _qs_dte = _qs3.slider("DTE fit weight",   0.05, 0.50, float(_qsw.get("dte",     0.25)), 0.05, key=f"br_qs_dte_{_brain_profile}",
                              help="How precisely DTE matches the target. Higher weight = expiry timing matters more for quality.")
        _qs_total = _qs_iv + _qs_d + _qs_dte or 1.0
        _qs1.caption(f"{_qs_iv/_qs_total*100:.0f}% normalized")
        _qs2.caption(f"{_qs_d/_qs_total*100:.0f}% normalized")
        _qs3.caption(f"{_qs_dte/_qs_total*100:.0f}% normalized")

        st.markdown('<div class="section-header">Strike & Expiry Targets</div>', unsafe_allow_html=True)
        _t1, _t2, _t3, _t4 = st.columns(4)
        _delta_opt  = _t1.slider("Delta sweet spot", 0.15, 0.55, float(_tgt.get("delta_optimal", 0.30)), 0.05, key=f"br_delta_opt_{_brain_profile}",
                                 help="Ideal delta for entries. 0.30 = OTM momentum. 0.45 = near-ATM. Score peaks here.")
        _delta_fall = _t2.slider("Delta window ±",   0.05, 0.35, float(_tgt.get("delta_falloff", 0.20)), 0.05, key=f"br_delta_fall_{_brain_profile}",
                                 help="Tolerance around the sweet spot. Wider = more strikes qualify.")
        _dte_opt    = _t3.slider("DTE sweet spot",   DTE_MIN, DTE_MAX, max(DTE_MIN, min(DTE_MAX, int(_tgt.get("dte_optimal", 10)))),  1, key=f"br_dte_opt_{_brain_profile}",
                                 help=f"Ideal days-to-expiry ({DTE_MIN}–{DTE_MAX} system bounds enforced). Score peaks here.")
        _dte_fall   = _t4.slider("DTE window ±",     3,    15,   min(15, int(_tgt.get("dte_falloff",    10))),        1, key=f"br_dte_fall_{_brain_profile}",
                                 help="Tolerance around ideal DTE. Max ±15 keeps selections within the 5–35 DTE window.")

        st.markdown("---")

        # ── Section 2: Entry Gates ─────────────────────────────────────────────
        st.markdown('<div class="section-header">Entry Gates</div>', unsafe_allow_html=True)
        st.caption("A trade only fires when ALL gates pass.")
        _g1, _g2, _g3 = st.columns(3)
        _iv_max  = _g1.slider("Max IV rank",  20,  80, int(_tgt.get("iv_percentile_max", 50)), 5, key=f"br_iv_max_{_brain_profile}",
                              help="Options above this IV percentile are considered expensive. Score → 0 above this rank.")
        _min_ev  = _g2.slider("Min EV %",      3,  25, int(_filt.get("min_ev_return_pct", 10)), 1, key=f"br_min_ev_{_brain_profile}",
                              help="Trade only fires if Expected Value ≥ this. EV = P(win)×target − P(loss)×stop.")
        _liq_spd = _g3.slider("Max spread %",  0.5, 5.0, float(_filt.get("liquidity_spread_max_pct", 1.5)), 0.5, key=f"br_liq_spd_{_brain_profile}",
                              help="Bid-ask spread above this % of mid = flagged as illiquid, higher EV required.")

        st.markdown("---")

        # ── Section 3: Entry Gates ─────────────────────────────────────────────
        st.markdown('<div class="section-header">Momentum & Technical Gates</div>', unsafe_allow_html=True)
        st.caption("Minimum thresholds a setup must clear before a trade is emitted. Shared by scanner, optimizer, and chatbot.")
        _g1, _g2, _g3 = st.columns(3)
        _min_dir  = _g1.slider("Min Direction Score", 20, 65, int(_entry.get("min_direction_score", 35)), 5, key=f"br_min_dir_{_brain_profile}",
                               help="Minimum Direction Score (0–100) to emit a trade signal. Below this = AVOID. Shared by scan + WFO.")
        _min_tech = _g2.slider("Min Tech Score",      30, 75, int(_entry.get("min_tech_score",      55)), 5, key=f"br_min_tech_{_brain_profile}",
                               help="Minimum tech component score (RSI/MACD/SMA alignment). Weak setups are skipped before heavier scoring runs.")
        _entry_mom = _g3.slider("Momentum threshold %", 0.1, 1.5, float(_entry.get("entry_momentum_pct", 0.5)), 0.1, key=f"br_entry_mom_{_brain_profile}",
                                help="Minimum 5-day % price move needed to trigger a momentum signal. Higher = fewer but stronger signals.")

        st.markdown("---")

        # ── Section 4: Exit Rules ──────────────────────────────────────────────
        st.markdown('<div class="section-header">Exit Rules</div>', unsafe_allow_html=True)
        _e1, _e2, _e3 = st.columns(3)
        _sl  = _e1.slider("Stop-loss %",     20,  80, int(_risk.get("stop_loss_pct",      50)), 5, key=f"br_sl_{_brain_profile}",
                          help="Exit when the option loses this % of premium paid.")
        _tp  = _e2.slider("Profit target %", 50, 200, int(_risk.get("profit_target_pct", 100)), 10, key=f"br_tp_{_brain_profile}",
                          help="Take profit when the option gains this % of premium. 100% = double your money.")
        _time_exit = _e3.slider("Time exit % of DTE", 25, 90, int(_risk.get("time_exit_pct", 50)), 5, key=f"br_time_exit_{_brain_profile}",
                                help="Close the position when this % of original DTE has elapsed — regardless of P&L. Prevents theta bleed on sideways trades. At 50% on a 20-DTE trade, exit at day 10.")
        _e4, _e5 = st.columns(2)
        _dd  = _e4.slider("Max drawdown %",   5,  30, int(_risk.get("max_drawdown_pct",   15)), 5, key=f"br_dd_{_brain_profile}",
                          help="Pause all trading if total portfolio drops this % from its peak.")
        _0dte = _e5.slider("0DTE cap %",       1,  15, int(_risk.get("dte_0_max_pct",      5)),  1, key=f"br_0dte_{_brain_profile}",
                           help="Same-day expiry options are capped at this % of account size per trade.")

        st.markdown("---")

        # ── Section 4b: Smart Early Exit ──────────────────────────────────────
        st.markdown('<div class="section-header">Smart Early Exit</div>', unsafe_allow_html=True)
        st.caption("Automatically exits profitable trades when indicators turn against the position.")
        _ee = _sp.get("early_exit", {})

        _ee_enabled = st.toggle(
            "Enable smart early exit",
            value=bool(_ee.get("enabled", True)),
            key=f"br_ee_enabled_{_brain_profile}",
            help="When enabled, the auto-grader checks live indicators every 10 minutes and exits profitable trades if conditions deteriorate.",
        )

        if _ee_enabled:
            _ee1, _ee2, _ee3 = st.columns(3)
            _ee_min_hold = _ee1.slider("Min hold days", 1, 5, int(_ee.get("min_hold_days", 1)), 1,
                                        key=f"br_ee_hold_{_brain_profile}",
                                        help="Minimum days held before smart exit can trigger.")
            _ee_min_profit = _ee2.slider("Min profit to exit %", 0, 20, int(_ee.get("min_profit_to_exit_pct", 5)), 1,
                                          key=f"br_ee_min_profit_{_brain_profile}",
                                          help="Only trigger smart exit if current option P&L is at least this %.")
            _ee_tech_decay = _ee3.slider("Tech decay trigger %", 20, 60, int(_ee.get("tech_decay_pct", 35)), 5,
                                          key=f"br_ee_tech_decay_{_brain_profile}",
                                          help="Exit if tech score has fallen by this % from entry.")

            _ee4, _ee5, _ee6 = st.columns(3)
            _ee_dir_floor = _ee4.slider("Direction score floor", 15, 45, int(_ee.get("direction_floor", 30)), 5,
                                         key=f"br_ee_dir_floor_{_brain_profile}",
                                         help="Exit if live direction score drops below this absolute level.")
            _ee_mom_rev = _ee5.toggle("Momentum reversal exit", value=bool(_ee.get("momentum_reversal", True)),
                                       key=f"br_ee_mom_{_brain_profile}",
                                       help="Exit if 5-day momentum flips direction since entry.")
            _ee_rsi_ext = _ee6.toggle("RSI extreme exit", value=bool(_ee.get("rsi_extreme_exit", True)),
                                       key=f"br_ee_rsi_{_brain_profile}",
                                       help="Exit if RSI reaches extreme territory against the trade direction.")

            st.caption("Trailing profit protection — locks in gains when position gives back too much.")
            _ee7, _ee8 = st.columns(2)
            _ee_trail_pct = _ee7.slider("Trail activate at %", 20, 80, int(_ee.get("trailing_profit_pct", 40)), 5,
                                         key=f"br_ee_trail_pct_{_brain_profile}",
                                         help="Activate trailing protection once option gains reach this %.")
            _ee_giveback = _ee8.slider("Max giveback %", 30, 70, int(_ee.get("trailing_giveback_pct", 50)), 5,
                                        key=f"br_ee_giveback_{_brain_profile}",
                                        help="Exit if the option gives back this % of its peak unrealized gain.")
        else:
            _ee_min_hold    = int(_ee.get("min_hold_days", 1))
            _ee_min_profit  = int(_ee.get("min_profit_to_exit_pct", 5))
            _ee_tech_decay  = int(_ee.get("tech_decay_pct", 35))
            _ee_dir_floor   = int(_ee.get("direction_floor", 30))
            _ee_mom_rev     = bool(_ee.get("momentum_reversal", True))
            _ee_rsi_ext     = bool(_ee.get("rsi_extreme_exit", True))
            _ee_trail_pct   = int(_ee.get("trailing_profit_pct", 40))
            _ee_giveback    = int(_ee.get("trailing_giveback_pct", 50))

        st.markdown("---")

        # ── Section 5: Defense Filters ─────────────────────────────────────────
        st.markdown('<div class="section-header">Defense & IV Filters</div>', unsafe_allow_html=True)
        _d1, _d2, _d3, _d4 = st.columns(4)
        _vix_def  = _d1.slider("VIX defense level", 18, 40, int(_filt.get("vix_defense_threshold",   25)), 1, key=f"br_vix_{_brain_profile}",
                               help="VIX above this → Defense Mode: position sizes reduced.")
        _def_mult = _d2.slider("Defense size mult",  0.2, 0.9, float(_filt.get("defense_position_mult", 0.5)), 0.1, key=f"br_def_mult_{_brain_profile}",
                               help="In Defense Mode, multiply all position sizes by this. 0.5 = half size.")
        _iv_z     = _d3.slider("IV crush threshold", 1.0, 3.5, float(_filt.get("iv_crush_z_threshold",  2.0)), 0.5, key=f"br_iv_z_{_brain_profile}",
                               help="Flag IV crush risk when option IV exceeds HV by this many σ.")
        _iv_pen   = _d4.slider("IV crush penalty",   5,   30,  int(_filt.get("iv_crush_confidence_penalty", 20)), 5, key=f"br_iv_pen_{_brain_profile}",
                               help="Subtract this many points from Direction Score when IV crush risk detected.")

        _da1, _da2 = st.columns(2)
        _atr_mult  = _da1.slider("ATR stop multiplier", 0.5, 4.0, float(_filt.get("atr_expansion_stop_mult", 1.5)), 0.5, key=f"br_atr_mult_{_brain_profile}",
                                 help="Stop-loss placed at entry ± (ATR × this multiplier). Higher = wider stop, less noise sensitivity.")
        _illiq_mgn = _da2.slider("Illiquid margin %", 0.0, 30.0, float(_filt.get("illiquid_extra_margin_pct", 10.0)), 5.0, key=f"br_illiq_{_brain_profile}",
                                 help="Extra margin buffer (%) applied to illiquid options (wide spread). Reduces position size to compensate.")

        st.markdown('<div class="section-header">Position Sizing</div>', unsafe_allow_html=True)
        st.caption("Bounds on how much of the account any single position can occupy.")
        _ps1, _ps2 = st.columns(2)
        _min_pos   = _ps1.slider("Min position %", 1, 20, int(_risk.get("min_position_pct", 7)), 1, key=f"br_min_pos_{_brain_profile}",
                                 help="Minimum allocation per trade as % of account. Prevents micro-positions.")
        _max_pos   = _ps2.slider("Max position %", 10, 60, int(_risk.get("max_position_pct", 40)), 5, key=f"br_max_pos_{_brain_profile}",
                                 help="Maximum allocation per trade as % of account. Caps concentration risk.")

        st.markdown("---")

        # ── Save ───────────────────────────────────────────────────────────────
        _note_col, _btn_col = st.columns([3, 1])
        _brain_note = _note_col.text_input("Change note (optional)", placeholder="e.g. tightened stop-loss for high-VIX environment",
                                           key=f"br_note_{_brain_profile}", label_visibility="collapsed")
        if _btn_col.button("💾 Save Changes", use_container_width=True, type="primary", key=f"br_save_{_brain_profile}"):
            # Snapshot current values before applying changes
            _before = {
                "iv_percentile":            _cw["iv_percentile"],
                "delta (weight)":           _cw["delta"],
                "dte (weight)":             _cw["dte"],
                "technical (weight)":       _cw.get("technical", 0.0),
                "delta_optimal":            _tgt["delta_optimal"],
                "delta_falloff":            _tgt["delta_falloff"],
                "dte_optimal":              _tgt["dte_optimal"],
                "dte_falloff":              _tgt["dte_falloff"],
                "iv_percentile_max":        _tgt.get("iv_percentile_max", 50),
                "min_ev_return_pct":        _filt["min_ev_return_pct"],
                "liquidity_spread_max_pct": _filt["liquidity_spread_max_pct"],
                "vix_defense_threshold":    _filt["vix_defense_threshold"],
                "defense_position_mult":    _filt["defense_position_mult"],
                "iv_crush_z_threshold":     _filt["iv_crush_z_threshold"],
                "iv_crush_confidence_penalty": _filt["iv_crush_confidence_penalty"],
                "stop_loss_pct":            _risk["stop_loss_pct"],
                "profit_target_pct":        _risk["profit_target_pct"],
                "time_exit_pct":            _risk.get("time_exit_pct", 50),
                "max_drawdown_pct":         _risk["max_drawdown_pct"],
                "dte_0_max_pct":            _risk["dte_0_max_pct"],
                "min_direction_score":      _entry["min_direction_score"],
                "min_tech_score":           _entry["min_tech_score"],
                "entry_momentum_pct":       _entry.get("entry_momentum_pct", 0.5),
                "atr_expansion_stop_mult":  _filt.get("atr_expansion_stop_mult", 1.5),
                "illiquid_extra_margin_pct": _filt.get("illiquid_extra_margin_pct", 10.0),
                "min_position_pct":         _risk.get("min_position_pct", 7),
                "max_position_pct":         _risk.get("max_position_pct", 40),
                "ds_tech":                  _dsw.get("tech",     0.55),
                "ds_regime":                _dsw.get("regime",   0.30),
                "ds_momentum":              _dsw.get("momentum", 0.15),
                "rsi_severe_threshold":     _rsioe.get("severe_threshold",   72),
                "rsi_moderate_threshold":   _rsioe.get("moderate_threshold", 68),
                "rsi_severe_penalty":       _rsioe.get("severe_penalty",     15),
                "rsi_moderate_penalty":     _rsioe.get("moderate_penalty",    8),
                "qs_iv_rank":               _qsw.get("iv_rank", 0.40),
                "qs_delta":                 _qsw.get("delta",   0.35),
                "qs_dte":                   _qsw.get("dte",     0.25),
            }
            _after = {
                "iv_percentile":            _w_iv,
                "delta (weight)":           _w_delta,
                "dte (weight)":             _w_dte,
                "technical (weight)":       _w_tech,
                "delta_optimal":            _delta_opt,
                "delta_falloff":            _delta_fall,
                "dte_optimal":              _dte_opt,
                "dte_falloff":              _dte_fall,
                "iv_percentile_max":        _iv_max,
                "min_ev_return_pct":        _min_ev,
                "liquidity_spread_max_pct": _liq_spd,
                "vix_defense_threshold":    _vix_def,
                "defense_position_mult":    _def_mult,
                "iv_crush_z_threshold":     _iv_z,
                "iv_crush_confidence_penalty": _iv_pen,
                "stop_loss_pct":            _sl,
                "profit_target_pct":        _tp,
                "time_exit_pct":            _time_exit,
                "max_drawdown_pct":         _dd,
                "dte_0_max_pct":            _0dte,
                "min_direction_score":      _min_dir,
                "min_tech_score":           _min_tech,
                "entry_momentum_pct":       _entry_mom,
                "atr_expansion_stop_mult":  _atr_mult,
                "illiquid_extra_margin_pct": _illiq_mgn,
                "min_position_pct":         _min_pos,
                "max_position_pct":         _max_pos,
                "ds_tech":                  _ds_tech,
                "ds_regime":                _ds_reg,
                "ds_momentum":              _ds_mom,
                "rsi_severe_threshold":     _rsi_sev_t,
                "rsi_moderate_threshold":   _rsi_mod_t,
                "rsi_severe_penalty":       _rsi_sev_p,
                "rsi_moderate_penalty":     _rsi_mod_p,
                "qs_iv_rank":               _qs_iv,
                "qs_delta":                 _qs_d,
                "qs_dte":                   _qs_dte,
            }
            _diffs = [
                f"{k}: {_before[k]} → {_after[k]}"
                for k in _before
                if round(float(_before[k]), 4) != round(float(_after[k]), 4)
            ]

            _oc.STRATEGY_PROFILES[_brain_profile]["targets"].update({
                "delta_optimal":     _delta_opt,
                "delta_falloff":     _delta_fall,
                "dte_optimal":       _dte_opt,
                "dte_falloff":       _dte_fall,
                "iv_percentile_max": _iv_max,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["filters"].update({
                "min_ev_return_pct":          _min_ev,
                "liquidity_spread_max_pct":   _liq_spd,
                "vix_defense_threshold":      _vix_def,
                "defense_position_mult":      _def_mult,
                "iv_crush_z_threshold":       _iv_z,
                "iv_crush_confidence_penalty": _iv_pen,
                "atr_expansion_stop_mult":    _atr_mult,
                "illiquid_extra_margin_pct":  _illiq_mgn,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["risk"].update({
                "stop_loss_pct":      _sl,
                "profit_target_pct":  _tp,
                "time_exit_pct":      _time_exit,
                "max_drawdown_pct":   _dd,
                "dte_0_max_pct":      _0dte,
                "min_position_pct":   _min_pos,
                "max_position_pct":   _max_pos,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["entry"].update({
                "min_direction_score":  _min_dir,
                "min_tech_score":       _min_tech,
                "entry_momentum_pct":   _entry_mom,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["direction_score_weights"].update({
                "tech":     _ds_tech,
                "regime":   _ds_reg,
                "momentum": _ds_mom,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["rsi_overextension"].update({
                "severe_threshold":   _rsi_sev_t,
                "moderate_threshold": _rsi_mod_t,
                "severe_penalty":     float(_rsi_sev_p),
                "moderate_penalty":   float(_rsi_mod_p),
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["quality_score_weights"].update({
                "iv_rank": _qs_iv,
                "delta":   _qs_d,
                "dte":     _qs_dte,
            })
            _oc.STRATEGY_PROFILES[_brain_profile]["early_exit"] = {
                "enabled":                _ee_enabled,
                "min_hold_days":          _ee_min_hold,
                "tech_decay_pct":         float(_ee_tech_decay),
                "direction_floor":        float(_ee_dir_floor),
                "momentum_reversal":      _ee_mom_rev,
                "rsi_extreme_exit":       _ee_rsi_ext,
                "rsi_call_ceiling":       78,
                "rsi_put_floor":          22,
                "trailing_profit_pct":    float(_ee_trail_pct),
                "trailing_giveback_pct":  float(_ee_giveback),
                "min_profit_to_exit_pct": float(_ee_min_profit),
            }

            # Build note: user note + auto-detected diffs
            _user_note = _brain_note.strip()
            if _diffs:
                _changes_str = " | ".join(_diffs)
                _note_str = f"{_user_note} — {_changes_str}" if _user_note else _changes_str
            else:
                _note_str = _user_note or "No changes detected"

            _oc._save_profile(note=_note_str, profile=_brain_profile)
            st.success(f"✅ Saved — {_note_str}")
            st.rerun()

        # ── Brain Version History ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown('<div class="section-header">Brain Version History</div>', unsafe_allow_html=True)

        _changelog: list[dict] = []
        _cl_profile = st.session_state.get("brain_profile_select", "equity")
        _cl_file    = CHANGELOG_FILES.get(_cl_profile, CHANGELOG_FILE)
        if os.path.exists(_cl_file):
            try:
                with open(_cl_file) as _f:
                    _changelog = json.load(_f)
            except Exception:
                _changelog = []

        if not _changelog:
            st.info("No brain updates recorded yet — apply optimizer recommendations to start tracking.")
        else:
            # Most-recent entry summary
            _last = _changelog[-1]
            _last_ts_raw = _last.get("ts", "")
            try:
                from datetime import timezone as _tz, timedelta as _tds
                _last_dt = datetime.strptime(_last_ts_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_tz.utc)
                _et      = _last_dt.astimezone(_tz(_tds(hours=-5)))
                _last_ts = _et.strftime("%b %d, %Y  %I:%M %p ET").replace(" 0", " ")
            except Exception:
                _last_ts = _last_ts_raw

            _last_profile     = _last.get("profile", "equity")
            _last_profile_lbl = "📈 Equity" if _last_profile == "equity" else "📊 Index"
            st.markdown(
                f"<div style='background:rgba(255,255,255,0.04);border-radius:0.5rem;"
                f"padding:0.75rem 1rem;margin-bottom:0.75rem'>"
                f"<span style='color:var(--text-2);font-size:0.82rem'>Last updated</span>"
                f"<span style='font-size:0.72rem;color:var(--text-3);margin-left:0.5rem;background:var(--bg-3);"
                f"border:1px solid var(--border-subtle);border-radius:0.25rem;padding:0.125rem 0.5rem'>{_last_profile_lbl}</span><br>"
                f"<span style='font-size:1.0rem;font-weight:600'>{_last_ts}</span>"
                f"<span style='color:var(--text-3);font-size:0.82rem;margin-left:0.75rem'>{_last.get('note','')}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

            with st.expander(f"📜 Full history ({len(_changelog)} entries)", expanded=False):
                _log_rows = []
                for _entry in reversed(_changelog):
                    _ts_raw = _entry.get("ts", "")
                    try:
                        from datetime import timezone as _tz2, timedelta as _tds2
                        _dt  = datetime.strptime(_ts_raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_tz2.utc)
                        _et2 = _dt.astimezone(_tz2(_tds2(hours=-5)))
                        _ts_fmt = _et2.strftime("%Y-%m-%d  %I:%M %p ET")
                    except Exception:
                        _ts_fmt = _ts_raw
                    _ep = _entry.get("profile", "equity")
                    _log_rows.append({
                        "Timestamp": _ts_fmt,
                        "Profile":   "📈 Equity" if _ep == "equity" else "📊 Index",
                        "Details":   _entry.get("note", ""),
                    })
                st.markdown(_ft_table(_log_rows, dim_cols=["Timestamp"]), unsafe_allow_html=True)

    # ── SUB-TAB: Walk-Forward Optimizer ──────────────────────────────────────
    with sub_opt:
        st.markdown('<div class="section-header">Walk-Forward Optimizer</div>', unsafe_allow_html=True)
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
            _tgt   = _sp_ro["targets"]
            _risk  = _sp_ro["risk"]
            _filt  = _sp_ro["filters"]
            _dsw_ro = _sp_ro.get("direction_score_weights", {})
            _qsw_ro = _sp_ro.get("quality_score_weights", {})

            st.markdown("**Direction Score weights** *(normalized)*")
            ro1, ro2, ro3 = st.columns(3)
            _ds_sum = sum(_dsw_ro.values()) or 1.0
            ro1.metric("Tech setup",  f"{_dsw_ro.get('tech',0.55)/_ds_sum*100:.0f}%")
            ro2.metric("SPY regime",  f"{_dsw_ro.get('regime',0.30)/_ds_sum*100:.0f}%")
            ro3.metric("Momentum",    f"{_dsw_ro.get('momentum',0.15)/_ds_sum*100:.0f}%")

            st.markdown("**Quality Score weights** *(normalized)*")
            rq1, rq2, rq3 = st.columns(3)
            _qs_sum = sum(_qsw_ro.values()) or 1.0
            rq1.metric("IV Rank",  f"{_qsw_ro.get('iv_rank',0.40)/_qs_sum*100:.0f}%")
            rq2.metric("Delta fit", f"{_qsw_ro.get('delta',0.35)/_qs_sum*100:.0f}%")
            rq3.metric("DTE fit",   f"{_qsw_ro.get('dte',0.25)/_qs_sum*100:.0f}%")

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
**What this does**

The Historical Backtest replays the live daily scan on every trading day going back N years.
No Optuna, no parameter tuning — it uses your **current Brain settings** exactly as they are today and asks: *"what would the bot have predicted, and did those trades win?"*

**Pipeline**
1. Downloads price history for all watchlist tickers (equity + index ETFs)
2. Pre-computes indicators (HV30, RSI-14, MACD, SMA-20/50) for every ticker on every day
3. For each trading day, evaluates all tickers through the same entry gates the live scan uses:
   - Momentum gate (5-day return + SMA20 relationship)
   - Technical score gate (RSI + MACD + SMA trend stack ≥ min threshold)
   - Direction score gate (composite signal ≥ min confidence)
   - Expected-value gate (EV ≥ min EV %)
4. Picks the **top 5** candidates using the same sector-diversification logic as the live scan
5. Simulates each trade's outcome using actual subsequent price data (same stop/target/trailing-stop/time-exit logic as the live bot)
6. Aggregates: win rate, profit factor, Sharpe, max drawdown, equity curve

**Dual-profile (mirrors the live bot exactly)**
- Index ETFs (SPY, QQQ, IWM, DIA, XLK) are evaluated using the **Index Brain** settings
- All equity tickers are evaluated using the **Equity Brain** settings
- No profile selector needed — both run together, just like the live daily scan

**Technical score (RSI + MACD + SMA trend)**
40% SMA trend alignment (price/SMA20/SMA50 stack), 35% RSI positioning, 25% MACD momentum. Each ticker must clear the min_tech_score gate before direction scoring.

**What the results tell you**
- **Win rate** — % of simulated trades that moved in the predicted direction
- **Profit factor** — gross wins ÷ gross losses (> 1.0 = net profitable)
- **Avg P&L %** — average option gain/loss per trade (estimated via Black-Scholes)
- **Equity curve** — cumulative daily P&L assuming equal-weight across each day's picks
- **Avg picks/day** — how selective the gates were (lower = tighter filter)

Results are saved to `wfo_results.json`. The backtest is read-only — it never modifies your Brain settings.
""")

        st.markdown('<div class="section-header">Backtest Configuration</div>', unsafe_allow_html=True)
        # ── Last run summary ──────────────────────────────────────────────────
        _wfo_prev = None
        if os.path.exists(os.path.join(os.path.dirname(__file__), "wfo_results.json")):
            try:
                with open(os.path.join(os.path.dirname(__file__), "wfo_results.json")) as _wf:
                    _wfo_prev = json.load(_wf)
            except Exception:
                pass
        if _wfo_prev and _wfo_prev.get("mode") == "backtest":
            _bt = _wfo_prev
            st.success(
                f"Last backtest: **{_bt.get('win_rate_pct', 0):.1f}% win rate** over "
                f"{_bt.get('lookback_years', '?')} years  ·  "
                f"{_bt.get('total_trades', 0):,} trades  ·  "
                f"{_bt.get('avg_picks_per_day', 0):.1f}/day avg  ·  "
                f"PF {_bt.get('profit_factor', 0):.2f}"
            )

        st.markdown('<div class="section-header">Simulation Range</div>', unsafe_allow_html=True)
        from datetime import date as _date
        opt_years = st.slider(
            "Years of history",
            2, 7, 5, key="opt_years",
            format="%d yrs",
            help="How many years of daily history to replay.",
        )
        iv_adj_val = st.slider(
            "IV premium adjustment",
            min_value=1.00, max_value=1.50, value=1.20, step=0.05,
            key="bt_iv_adj",
            help=(
                "Real market implied volatility consistently trades 15–25% above 30-day historical vol "
                "(the 'volatility risk premium'). This makes options more expensive than a pure HV model predicts. "
                "1.20 = realistic baseline · 1.00 = optimistic (options too cheap, returns inflated) · "
                "1.40 = conservative. Does not affect entry gates — only option pricing."
            ),
        )

        _start_year = _date.today().year - opt_years
        st.caption(
            f"The simulator will replay every trading day from **{_start_year}** to today, "
            f"evaluating all {len(DEFAULT_WATCHLIST)} watchlist tickers and picking the top 5 each day "
            f"using the current Brain settings."
        )
        st.info(
            f"**Timeline:** {_start_year} → today · ~{opt_years * 252:,} trading days · "
            f"{len(DEFAULT_WATCHLIST)} tickers evaluated per day  \n"
            f"**Estimated runtime: 3–10 min** depending on years and hardware."
        )

        run_bt = st.button(
            "▶ Run Historical Backtest", type="primary",
            use_container_width=True,
        )

        if run_bt:
            progress_bar = st.progress(0.0)
            status_text  = st.empty()

            def _cb(msg: str, pct: float) -> None:
                progress_bar.progress(min(pct, 1.0))
                status_text.caption(msg)

            with st.spinner("Running historical backtest — this may take several minutes…"):
                wfo_data = run_historical_backtest(
                    lookback_years    = opt_years,
                    n_picks           = 5,
                    iv_adj            = iv_adj_val,
                    progress_callback = _cb,
                )
            progress_bar.empty()
            status_text.empty()

            if "error" in wfo_data:
                st.error(wfo_data["error"])
            else:
                st.session_state["wfo_results"] = wfo_data
                st.success(
                    f"Done — {wfo_data['total_trades']:,} trades simulated over {opt_years} years "
                    f"({wfo_data['avg_picks_per_day']:.1f}/day avg · "
                    f"{wfo_data['win_rate_pct']:.1f}% win rate · PF {wfo_data['profit_factor']:.2f})"
                )

        # ── Helper: format a YYYY-MM-DD date as "Mon 'YY" ───────────────────────
        def _fmt_d(d: str) -> str:
            try:
                from datetime import datetime as _dt
                return _dt.strptime(d, "%Y-%m-%d").strftime("%b '%y")
            except Exception:
                return d

        # ── Helper: render historical backtest results ────────────────────────
        def _render_backtest_result(result: dict, sim_capital: float = 10_000.0, sim_risk_pct: float = 10.0):
            all_trades = result.get("trades", [])
            if not all_trades:
                st.warning("No trades were simulated — check profile settings or increase history years.")
                return

            all_trades_sorted = sorted(all_trades, key=lambda t: t["date"])
            dates   = [t["date"] for t in all_trades_sorted]
            pnl_pts = [t["pnl_pct"] for t in all_trades_sorted]

            # Key metrics
            wins      = [p for p in pnl_pts if p > 0]
            losses    = [p for p in pnl_pts if p <= 0]
            n_total   = len(pnl_pts)
            win_rate  = len(wins) / n_total * 100
            gross_win = sum(wins)
            gross_loss= abs(sum(losses))
            pf_val    = gross_win / max(gross_loss, 0.01)

            # Account-level simulation (fixed-dollar risk per trade — no compounding)
            # Uses raw simulated P&L — no artificial capping — so losing trades have
            # their full impact (options that stop out via daily-close slippage can lose
            # more than the nominal stop_loss_pct).
            _fixed_pos   = sim_capital * sim_risk_pct / 100   # constant dollar risk per trade
            acct = sim_capital
            acct_hwm = sim_capital
            acct_max_dd_pct = 0.0
            acct_vals = []
            for t in all_trades_sorted:
                acct    += _fixed_pos * t["pnl_pct"] / 100   # full raw P&L, wins and losses
                acct_hwm = max(acct_hwm, acct)
                if acct_hwm > 0:
                    acct_max_dd_pct = max(acct_max_dd_pct, (acct_hwm - acct) / acct_hwm * 100)
                acct_vals.append(round(acct, 2))

            final_acct = acct_vals[-1] if acct_vals else sim_capital
            total_ret  = (final_acct - sim_capital) / sim_capital * 100
            _bt_years  = result.get("lookback_years", 1) or 1
            ann_ret    = (final_acct - sim_capital) / sim_capital / _bt_years * 100
            avg_pnl    = sum(pnl_pts) / n_total

            st.markdown('<div class="section-header">Account Growth</div>', unsafe_allow_html=True)
            st.caption(
                "Starting balance compounded trade-by-trade through the full historical period. "
                "Each day the simulator picks the top 5 trades from the full watchlist and simulates their outcomes."
            )

            kc1, kc2, kc3, kc4, kc5 = st.columns(5)
            kc1.metric("Win Rate",        f"{win_rate:.1f}%",
                       help=f"{len(wins)} wins / {n_total} total simulated trades")
            kc2.metric("Profit Factor",   f"{pf_val:.2f}",
                       help="Gross profit ÷ gross loss. >1.5 = solid, >2.0 = excellent")
            kc3.metric("Avg P&L / Trade", f"{avg_pnl:+.1f}%",
                       help="Average option return per trade across the entire backtest")
            kc4.metric("Annual Return on Capital", f"{ann_ret:+.1f}%/yr",
                       delta=f"${final_acct - sim_capital:+,.0f} total gain",
                       help=f"Fixed ${_fixed_pos:,.0f} risked per trade (non-compounding). "
                            f"Total gain ÷ starting capital ÷ {_bt_years} yrs.")
            kc5.metric("Max Drawdown",    f"{acct_max_dd_pct:.1f}%", delta_color="inverse",
                       help="Largest peak-to-trough drop in account value")

            # Account growth chart
            import altair as _alt
            _trade_dates = pd.to_datetime(dates)
            acct_series  = pd.Series(acct_vals, index=_trade_dates, name="Account Value ($)")
            _origin = pd.Series([sim_capital], index=[_trade_dates[0] - pd.Timedelta(days=1)])
            acct_full  = pd.concat([_origin, acct_series])
            acct_daily = acct_full.resample("D").last().ffill()
            _acct_df = acct_daily.reset_index()
            _acct_df.columns = ["date", "value"]
            _acct_df = _acct_df[_acct_df["value"] > 0].copy()
            _line = (
                _alt.Chart(_acct_df)
                .mark_line(color="#00c17c")
                .encode(
                    x=_alt.X("date:T", title="Date"),
                    y=_alt.Y("value:Q", title="Account Value ($)"),
                    tooltip=[
                        _alt.Tooltip("date:T", title="Date"),
                        _alt.Tooltip("value:Q", title="Account $", format="$,.0f"),
                    ],
                )
            )
            _baseline_df = pd.DataFrame({"y": [sim_capital]})
            _baseline = (
                _alt.Chart(_baseline_df)
                .mark_rule(color="#888888", strokeDash=[4, 4], opacity=0.6)
                .encode(y=_alt.Y("y:Q"))
            )
            _acct_chart = (_line + _baseline).properties(height=300)
            st.altair_chart(_acct_chart, use_container_width=True)
            st.caption(
                f"Starting ${sim_capital:,.0f} · fixed ${_fixed_pos:,.0f} risked per trade (non-compounding) · "
                f"{result.get('avg_picks_per_day', 0):.1f} avg picks/day · "
                f"{result.get('total_days', 0):,} trading days simulated"
            )

            # Per-trade P&L bar chart
            st.markdown('<div class="section-header">Per-Trade P&L</div>', unsafe_allow_html=True)
            bt_bar = pd.DataFrame({
                "Profit": [p if p > 0 else 0.0 for p in pnl_pts],
                "Loss":   [p if p <= 0 else 0.0 for p in pnl_pts],
            }, index=_trade_dates)
            st.bar_chart(bt_bar, color=["#00c17c", "#ff4b4b"])
            st.caption(
                f"Each bar = one trade's option return. {sim_risk_pct}% of account at risk per trade."
            )

            # Exit reason breakdown
            stops      = sum(1 for t in all_trades_sorted if "stop"      in t.get("exit_reason", ""))
            targets    = sum(1 for t in all_trades_sorted if "target"    in t.get("exit_reason", ""))
            expiry     = sum(1 for t in all_trades_sorted if "expir"     in t.get("exit_reason", ""))
            time_exits = sum(1 for t in all_trades_sorted if "time_exit" == t.get("exit_reason", ""))
            win_t  = [t for t in all_trades_sorted if t["pnl_pct"] > 0]
            loss_t = [t for t in all_trades_sorted if t["pnl_pct"] <= 0]
            avg_win_p  = sum(t["pnl_pct"] for t in win_t)  / max(len(win_t),  1)
            avg_loss_p = sum(t["pnl_pct"] for t in loss_t) / max(len(loss_t), 1)

            with st.expander("🔬 Exit breakdown", expanded=False):
                xl1, xl2, xl3, xl4 = st.columns(4)
                xl1.metric("Stop-outs",      stops)
                xl2.metric("Target hits",    targets)
                xl3.metric("Time exits ⌛",  time_exits)
                xl4.metric("Held to expiry", expiry)
                xa1, xa2 = st.columns(2)
                xa1.metric("Avg winning trade",  f"{avg_win_p:+.1f}%")
                xa2.metric("Avg losing trade",   f"{avg_loss_p:+.1f}%")

            # All-trades table
            with st.expander(f"📋 All trades ({n_total:,})", expanded=False):
                trade_rows = []
                for t in all_trades_sorted:
                    pnl = t["pnl_pct"]
                    er  = t.get("exit_reason", "")
                    ei  = ("🎯" if er == "target" else "📉" if er == "trailing_stop"
                           else "🛑" if er == "stop" else "⌛" if er == "time_exit" else "⏳")
                    trade_rows.append({
                        "Ticker":     t.get("ticker", "—"),
                        "Date":       t["date"][:10],
                        "Type":       ("📈 CALL" if t.get("type") == "call" else "📉 PUT"),
                        "Sector":     t.get("sector", "—"),
                        "Dir Score":  f"{t.get('direction_score', 0):.0f}",
                        "Tech":       f"{t.get('tech_score', 0):.0f}",
                        "EV":         f"{t.get('ev', 0):.1f}%",
                        "Strike":     f"${t.get('strike', 0):.2f}" if t.get("strike") else "—",
                        "Entry Px":   f"${t.get('entry_px', 0):.3f}" if t.get("entry_px") else "—",
                        "Exit Px":    f"${t.get('exit_px', 0):.3f}" if t.get("exit_px") else "—",
                        "P&L %":      f"{pnl:+.1f}%",
                        "Exit":       f"{ei} {er}",
                    })
                df_bt = pd.DataFrame(trade_rows)
                st.markdown(_ft_table(
                    df_bt,
                    pnl_cols=["P&L %", "EV"],
                    rate_cols=["Dir Score"],
                    mono_cols=["Entry Px", "Exit Px", "Strike"],
                    badge_col="Type",
                ), unsafe_allow_html=True)

            # Data audit trail (same as WFO renderer)
            with st.expander("🔍 Data Integrity Audit Trail", expanded=False):
                _bt_iv_adj = result.get("iv_adj", 1.20)
                st.markdown(
                    f"**Data sources:** stock open/close prices from yfinance historical OHLCV.  \n"
                    f"**Option pricing:** Black-Scholes using 30-day historical vol × **{_bt_iv_adj:.2f} IV adj** = effective IV used for entry & exit.  \n"
                    f"**Exit logic:** hard stop, time exit, or profit target — whichever triggers first.  \n"
                    f"**No look-ahead bias:** signal evaluated on day-N indicators (close-based); entry at day-N open price."
                )
                _audit = [t for t in all_trades_sorted if t.get("stock_px") and t.get("date") and t.get("ticker")]
                if _audit:
                    import random as _rnd
                    _sample = _rnd.sample(_audit, min(10, len(_audit)))
                    _sample.sort(key=lambda x: x["date"])
                    _fetch_errors: list[str] = []
                    _spot_rows = []
                    for _t in _sample:
                        _real_open = None
                        try:
                            _trade_ts  = pd.Timestamp(_t["date"]).normalize()
                            _days_back = max(10, (pd.Timestamp("today").normalize() - _trade_ts).days + 10)
                            _hist = yf.Ticker(_t["ticker"]).history(period=f"{_days_back}d")
                            if not _hist.empty:
                                # Remove timezone for clean date comparison
                                if _hist.index.tz is not None:
                                    _hist.index = _hist.index.tz_convert(None)
                                _hist.index = _hist.index.normalize()
                                _row = _hist[_hist.index == _trade_ts]
                                if not _row.empty:
                                    _real_open = float(_row["Open"].iloc[0])
                        except Exception as _e:
                            _fetch_errors.append(f"{_t['ticker']} {_t['date']}: {type(_e).__name__}: {_e}")
                            _real_open = None
                        _sim_px  = _t.get("stock_px", 0)
                        _diff    = round(_real_open - _sim_px, 4) if _real_open else None
                        _pct_err = round(abs(_diff) / _sim_px * 100, 3) if _diff is not None and _sim_px else None
                        _ok      = "✅" if (_pct_err is not None and _pct_err < 1.0) else ("⚠️" if _pct_err is not None else "❓")
                        _hv = _t.get("hv30", 0)
                        _spot_rows.append({
                            "Date": _t["date"][:10],
                            "Ticker": _t["ticker"],
                            "Type": _t.get("type", ""),
                            "Stock Open (sim)": f"${_sim_px:.2f}",
                            "Real Open $": f"${_real_open:.2f}" if _real_open else "N/A",
                            "Open Error %": f"{_pct_err:.3f}%" if _pct_err is not None else "N/A",
                            "HV30": f"{_hv*100:.1f}%",
                            "IV Adj": f"{_bt_iv_adj:.2f}×",
                            "Eff. IV": f"{_hv*_bt_iv_adj*100:.1f}%",
                            "Strike": f"${_t.get('strike', 0):.2f}",
                            "BS Entry $": f"${_t.get('entry_px', 0):.3f}",
                            "Exit $": f"${_t.get('exit_px', 0):.3f}",
                            "P&L %": f"{_t.get('pnl_pct', 0):+.1f}%",
                            "Exit": _t.get("exit_reason", ""),
                            "Match": _ok,
                        })
                    _verified   = [r for r in _spot_rows if r["Match"] != "❓"]
                    _mismatches = sum(1 for r in _spot_rows if r["Match"] == "⚠️")
                    _unverified = len(_spot_rows) - len(_verified)
                    if _unverified == len(_spot_rows):
                        st.error("❌ Could not verify any open prices — yfinance re-fetch failed. Backtest data integrity unconfirmed.")
                        if _fetch_errors:
                            with st.expander("Debug: fetch errors", expanded=False):
                                for _fe in _fetch_errors:
                                    st.code(_fe)
                    elif _mismatches == 0:
                        st.success(f"✅ All {len(_verified)} verified open prices match real yfinance data within 1%"
                                   + (f" ({_unverified} could not be re-fetched)" if _unverified else ""))
                    else:
                        st.warning(f"⚠️ {_mismatches}/{len(_verified)} open prices deviate >1% from real yfinance data — likely split/dividend adjustments")
                    st.markdown(_ft_table(
                        _spot_rows,
                        pnl_cols=["P&L %"],
                        mono_cols=["Stock Open (sim)", "Real Open $", "BS Entry $", "Exit $", "Strike"],
                    ), unsafe_allow_html=True)

                # CSV export
                _export_cols = ["date", "ticker", "type", "sector", "stock_px", "strike", "hv30", "iv_adj", "dte",
                                "direction_score", "tech_score", "ev", "entry_px", "exit_px", "pnl_pct", "exit_reason"]
                _export_rows = [{k: t.get(k, "") for k in _export_cols} for t in all_trades_sorted]
                if _export_rows:
                    st.download_button(
                        "⬇️ Download all trades as CSV",
                        data=pd.DataFrame(_export_rows).to_csv(index=False),
                        file_name="backtest_trades.csv",
                        mime="text/csv",
                    )

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

                st.markdown('<div class="section-header">Account Growth</div>', unsafe_allow_html=True)
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

                st.markdown('<div class="section-header">Per-Trade P&L</div>', unsafe_allow_html=True)
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
                        exit_icon = "🎯" if exit_r == "target" else ("📉" if exit_r == "trailing_stop" else ("🛑" if exit_r == "stop" else ("⌛" if exit_r == "time_exit" else "⏳")))
                        trade_rows.append({
                            "Ticker":     t.get("ticker", "—") or "—",
                            "Date":       t["date"][:10],
                            "Type":       ("📈 CALL" if t.get("type") == "call" else "📉 PUT") if t.get("type") else "—",
                            "Confidence": f"{t.get('direction_score') or t.get('confidence', 0):.0f}",
                            "Tech Score": f"{t.get('tech_score', 0):.0f}",
                            "EV":         f"{t.get('ev', 0):.1f}%",
                            "Strike":     f"${t.get('strike', 0):.2f}" if t.get("strike") else "—",
                            "Entry Px":   f"${t.get('entry_px', 0):.3f}" if t.get("entry_px") else "—",
                            "Exit Px":    f"${t.get('exit_px', 0):.3f}" if t.get("exit_px") else "—",
                            "P&L %":      f"{pnl:+.1f}%",
                            "Exit":       f"{exit_icon} {exit_r}",
                        })
                    df_trades = pd.DataFrame(trade_rows)
                    st.markdown(_ft_table(
                        df_trades,
                        pnl_cols=["P&L %"],
                        rate_cols=["Dir Score"],
                        mono_cols=["Entry Px", "Exit Px", "Strike"],
                        badge_col="Type",
                    ), unsafe_allow_html=True)

                # ── Data Integrity Audit Trail ────────────────────────────────
                with st.expander("🔍 Data Integrity Audit Trail", expanded=False):
                    st.markdown(
                        "Validates that backtest used **real historical prices**. "
                        "Stock prices are cross-checked against a fresh yfinance fetch. "
                        "Option prices are Black-Scholes estimates — the BS Slippage column shows "
                        "how far the simulated price deviated from a real mid-price where available."
                    )

                    # ── 1. Stock price spot-check ──────────────────────────────
                    st.markdown('<div class="section-header">Stock Price Verification</div>', unsafe_allow_html=True)
                    _audit_trades = [t for t in all_oos_trades if t.get("stock_px") and t.get("date") and t.get("ticker")]
                    if not _audit_trades:
                        st.warning("No auditable trades found — trades are missing stock_px or ticker fields. Re-run the optimizer to generate audit data.")
                    else:
                        import random as _rnd
                        _sample = _rnd.sample(_audit_trades, min(10, len(_audit_trades)))
                        _sample.sort(key=lambda x: x["date"])

                        _spot_rows = []
                        for _t in _sample:
                            try:
                                _hist = yf.Ticker(_t["ticker"]).history(
                                    start=_t["date"], end=pd.Timestamp(_t["date"]) + pd.Timedelta(days=3)
                                )
                                _real_px = float(_hist["Close"].iloc[0]) if not _hist.empty else None
                            except Exception:
                                _real_px = None

                            _sim_px  = _t.get("stock_px", 0)
                            _diff    = round(_real_px - _sim_px, 4) if _real_px else None
                            _pct_err = round(abs(_diff) / _sim_px * 100, 3) if _diff is not None and _sim_px else None
                            _ok      = "✅" if (_pct_err is not None and _pct_err < 0.5) else ("⚠️" if _pct_err is not None else "❓")

                            _spot_rows.append({
                                "Date":          _t["date"][:10],
                                "Ticker":        _t["ticker"],
                                "Simulated $":   f"${_sim_px:.2f}",
                                "Real Close $":  f"${_real_px:.2f}" if _real_px else "N/A",
                                "Difference $":  f"${_diff:+.4f}" if _diff is not None else "N/A",
                                "Error %":       f"{_pct_err:.3f}%" if _pct_err is not None else "N/A",
                                "Match":         _ok,
                            })

                        _spot_df = pd.DataFrame(_spot_rows)
                        _mismatches = sum(1 for r in _spot_rows if r["Match"] == "⚠️")
                        if _mismatches == 0:
                            st.success(f"✅ All {len(_spot_rows)} sampled stock prices match real yfinance data within 0.5%")
                        else:
                            st.warning(f"⚠️ {_mismatches} of {len(_spot_rows)} prices deviate >0.5% — may indicate data split/dividend adjustment differences")
                        st.markdown(_ft_table(
                            _spot_df,
                            mono_cols=["Simulated $", "Real Close $", "Difference $"],
                        ), unsafe_allow_html=True)

                    # ── 2. Option price sanity check ──────────────────────────
                    st.markdown('<div class="section-header">Option Price Sanity Check</div>', unsafe_allow_html=True)
                    _has_inputs = [t for t in all_oos_trades if t.get("hv30") and t.get("stock_px") and t.get("strike")]
                    if _has_inputs:
                        _hv_vals  = [t["hv30"]    for t in _has_inputs]
                        _spx_vals = [t["stock_px"] for t in _has_inputs]
                        _ep_vals  = [t["entry_px"] for t in _has_inputs]
                        _ep_pct   = [t["entry_px"] / t["stock_px"] * 100 for t in _has_inputs]
                        _ic1, _ic2, _ic3, _ic4 = st.columns(4)
                        _ic1.metric("HV Range",    f"{min(_hv_vals):.1%} – {max(_hv_vals):.1%}",
                                    help="Historical 30-day volatility used for BS pricing. Typical: 15–80% annualized.")
                        _ic2.metric("Stock $ Range", f"${min(_spx_vals):.0f} – ${max(_spx_vals):.0f}",
                                    help="Underlying stock close price on each entry day.")
                        _ic3.metric("Option $ Range", f"${min(_ep_vals):.2f} – ${max(_ep_vals):.2f}",
                                    help="BS-estimated option premium at entry. Reasonable if 0.5–8% of stock price.")
                        _ic4.metric("Premium as % of Stock", f"{min(_ep_pct):.2f}% – {max(_ep_pct):.2f}%",
                                    help="Option price / stock price. Should be 0.2–8% for OTM short-DTE options. Values >10% suggest deep ITM or wrong inputs.")

                        # Flag suspicious entries
                        _suspicious = [t for t in _has_inputs if t["entry_px"] / t["stock_px"] > 0.10]
                        _zero_entry = [t for t in all_oos_trades if t.get("entry_px", 1) < 0.01]
                        _neg_pnl_at_stop = [t for t in all_oos_trades
                                           if t.get("exit_reason") == "stop" and t.get("pnl_pct", 0) > 0]
                        if _suspicious:
                            st.error(f"❌ {len(_suspicious)} trade(s) have option premium >10% of stock price — likely BS input error. Check strike/HV/DTE.")
                        if _zero_entry:
                            st.error(f"❌ {len(_zero_entry)} trade(s) have entry_px < $0.01 — these should have been filtered.")
                        if _neg_pnl_at_stop:
                            st.error(f"❌ {len(_neg_pnl_at_stop)} trade(s) show positive P&L but exit reason = 'stop' — P&L/exit mismatch.")
                        if not _suspicious and not _zero_entry and not _neg_pnl_at_stop:
                            st.success("✅ All option prices are within realistic bounds. No BS input anomalies detected.")

                    # ── 3. No-look-ahead confirmation ─────────────────────────
                    st.markdown('<div class="section-header">Look-Ahead Bias Check</div>', unsafe_allow_html=True)
                    st.info(
                        "**How entries are timed:** Signal fires on day N using the day-N close price and the 5-day "
                        "return ending on day N. The option is entered at the day-N Black-Scholes price. "
                        "No future prices are used.\n\n"
                        "**What is estimated (not real market data):** Option entry and exit prices are Black-Scholes "
                        "theoretical values using 30-day historical volatility. Real options trade at IV premium above HV, "
                        "so actual fills will cost more than the simulated entry price — the backtest is **optimistic on "
                        "option cost** by approximately the IV-HV spread (typically 5–25% of premium).\n\n"
                        "**HV30 is frozen at entry** for the duration of each trade. This means the model doesn't "
                        "capture IV changes during the hold period."
                    )

                    # ── 4. Raw inputs export ───────────────────────────────────
                    st.markdown('<div class="section-header">Export Raw Trade Inputs</div>', unsafe_allow_html=True)
                    _export_cols = ["date", "ticker", "type", "stock_px", "strike", "hv30", "dte", "entry_px", "exit_px", "pnl_pct", "exit_reason"]
                    _export_rows = [{k: t.get(k, "") for k in _export_cols} for t in all_oos_trades]
                    if _export_rows:
                        _export_df = pd.DataFrame(_export_rows)
                        st.download_button(
                            "⬇️ Download trade inputs as CSV",
                            data=_export_df.to_csv(index=False),
                            file_name="wfo_audit_trail.csv",
                            mime="text/csv",
                            help="Download all OOS trade inputs so you can verify stock prices on any date using another data source (e.g., Yahoo Finance, TradingView).",
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
                st.markdown(_ft_table(
                    acc_rows,
                    rate_cols=["Win Rate"],
                ), unsafe_allow_html=True)

            # ── Trade learning breakdown (OOS) ────────────────────────────────
            if all_oos_trades:
                oos_stops     = sum(1 for t in all_oos_trades if "stop"      in t.get("exit_reason", ""))
                oos_targets   = sum(1 for t in all_oos_trades if "target"    in t.get("exit_reason", ""))
                oos_expiry    = sum(1 for t in all_oos_trades if "expir"     in t.get("exit_reason", ""))
                oos_time_exit = sum(1 for t in all_oos_trades if "time_exit" == t.get("exit_reason", ""))
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

                    ec1, ec2, ec3, ec4 = st.columns(4)
                    ec1.metric("Stop-outs",      oos_stops)
                    ec2.metric("Target hits",    oos_targets)
                    ec3.metric("Time exits ⌛",  oos_time_exit,
                               help="Closed at time_exit_pct% of DTE elapsed — theta protection rule")
                    ec4.metric("Held to expiry", oos_expiry)

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
                    st.markdown(_ft_table(
                        rows,
                        rate_cols=["Win Rate"],
                    ), unsafe_allow_html=True)

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
                sp       = _oc.STRATEGY_PROFILES.get(_opt_profile, _oc.STRATEGY_PROFILE)
                cur_tgt  = sp["targets"]
                cur_risk = sp["risk"]
                cur_filt = sp["filters"]
                cur_dsw  = sp.get("direction_score_weights", {})
                cur_rsi  = sp.get("rsi_overextension", {})
                cur_qsw  = sp.get("quality_score_weights", {})

                # Human-readable labels for each optimized param
                _PARAM_LABELS = {
                    "delta_target":      ("Delta target",           lambda: cur_tgt.get("delta_optimal", 0.30),            "",   1),
                    "entry_momentum":    ("Entry momentum %",       lambda: sp.get("entry", {}).get("entry_momentum_pct", 0.5), "%",  1),
                    "min_confidence":    ("Min confidence",         lambda: 50.0,                                          "",   1),
                    "min_ev_pct":        ("Min EV %",               lambda: cur_filt.get("min_ev_return_pct", 10.0),       "%",  1),
                    "stop_loss_pct":     ("Stop-loss %",            lambda: cur_risk.get("stop_loss_pct", 50.0),           "%",  1),
                    "profit_target_pct": ("Profit target %",        lambda: cur_risk.get("profit_target_pct", 100.0),      "%",  1),
                    "ds_w_tech":         ("Dir Score — tech wt",    lambda: round(cur_dsw.get("tech", 0.55), 4),           "",   1),
                    "ds_w_regime":       ("Dir Score — regime wt",  lambda: round(cur_dsw.get("regime", 0.30), 4),         "",   1),
                    "ds_w_momentum":     ("Dir Score — momentum wt",lambda: round(cur_dsw.get("momentum", 0.15), 4),       "",   1),
                    "rsi_sev_threshold": ("RSI severe threshold",   lambda: float(cur_rsi.get("severe_threshold", 72)),    "",   1),
                    "rsi_mod_threshold": ("RSI moderate threshold", lambda: float(cur_rsi.get("moderate_threshold", 68)),  "",   1),
                    "rsi_sev_penalty":   ("RSI severe penalty",     lambda: float(cur_rsi.get("severe_penalty", 15)),      "pts",1),
                    "rsi_mod_penalty":   ("RSI moderate penalty",   lambda: float(cur_rsi.get("moderate_penalty", 8)),     "pts",1),
                    "qs_w_iv":           ("Quality — IV rank wt",   lambda: round(cur_qsw.get("iv_rank", 0.40), 4),        "",   1),
                    "qs_w_delta":        ("Quality — delta wt",     lambda: round(cur_qsw.get("delta", 0.35), 4),          "",   1),
                    "qs_w_dte":          ("Quality — DTE wt",       lambda: round(cur_qsw.get("dte", 0.25), 4),            "",   1),
                }

                n_acc  = result.get("windows_passed", len(result.get("accepted", [])))
                for regime, params in final.items():
                    rlabel = "🛡️ Defense" if regime == "defense" else "📈 Normal"
                    with st.expander(f"{rlabel} — {n_acc} accepted windows", expanded=True):
                        st.markdown("**Before → After (9 optimized parameters)**")

                        col_left, col_right = st.columns(2)
                        with col_left:
                            st.markdown("**Entry & exit parameters**")
                            for key in ("delta_target", "entry_momentum", "min_confidence", "min_ev_pct", "stop_loss_pct", "profit_target_pct"):
                                if key not in params:
                                    continue
                                lbl, cur_fn, unit, scale = _PARAM_LABELS[key]
                                cur_v = round(cur_fn() * scale, 1)
                                new_v = round(params[key] * scale, 1)
                                delta_str = f"{new_v - cur_v:+.1f}{unit}"
                                st.metric(lbl, f"{new_v}{unit}", delta=delta_str)

                        # ── New param groups ──────────────────────────────────
                        _new_keys = ("ds_w_tech", "ds_w_regime", "ds_w_momentum",
                                     "rsi_sev_threshold", "rsi_mod_threshold",
                                     "rsi_sev_penalty", "rsi_mod_penalty",
                                     "qs_w_iv", "qs_w_delta", "qs_w_dte")
                        _new_present = [k for k in _new_keys if k in params]
                        if _new_present:
                            st.markdown("**Direction Score · RSI · Quality Score weights**")
                            _ng_cols = st.columns(min(len(_new_present), 5))
                            for _ni, _nk in enumerate(_new_present):
                                lbl, cur_fn, unit, scale = _PARAM_LABELS[_nk]
                                cur_v = round(cur_fn() * scale, 3)
                                new_v = round(params[_nk] * scale, 3)
                                delta_str = f"{new_v - cur_v:+.3f}{unit}"
                                _ng_cols[_ni % len(_ng_cols)].metric(lbl, f"{new_v}{unit}", delta=delta_str)

                        if st.button(
                            f"Apply {label} {regime.capitalize()} Recommendations",
                            key=f"apply_{apply_key_suffix}_{regime}",
                            type="primary",
                        ):
                            # ── Write to the selected profile (not always equity) ──
                            if "delta_target"      in params: sp["targets"]["delta_optimal"]                            = params["delta_target"]
                            if "stop_loss_pct"     in params: sp["risk"]["stop_loss_pct"]                               = params["stop_loss_pct"]
                            if "profit_target_pct" in params: sp["risk"]["profit_target_pct"]                           = params["profit_target_pct"]
                            if "min_ev_pct"        in params: sp["filters"]["min_ev_return_pct"]                        = params["min_ev_pct"]
                            if "entry_momentum"    in params: sp["entry"]["entry_momentum_pct"]                         = params["entry_momentum"]
                            if "min_confidence"    in params: sp["entry"]["min_direction_score"]                        = params["min_confidence"]
                            if "ds_w_tech"         in params: sp["direction_score_weights"]["tech"]                     = params["ds_w_tech"]
                            if "ds_w_regime"       in params: sp["direction_score_weights"]["regime"]                   = params["ds_w_regime"]
                            if "ds_w_momentum"     in params: sp["direction_score_weights"]["momentum"]                 = params["ds_w_momentum"]
                            if "rsi_sev_threshold" in params: sp["rsi_overextension"]["severe_threshold"]               = params["rsi_sev_threshold"]
                            if "rsi_mod_threshold" in params: sp["rsi_overextension"]["moderate_threshold"]             = params["rsi_mod_threshold"]
                            if "rsi_sev_penalty"   in params: sp["rsi_overextension"]["severe_penalty"]                 = params["rsi_sev_penalty"]
                            if "rsi_mod_penalty"   in params: sp["rsi_overextension"]["moderate_penalty"]               = params["rsi_mod_penalty"]
                            if "qs_w_iv"           in params: sp["quality_score_weights"]["iv_rank"]                    = params["qs_w_iv"]
                            if "qs_w_delta"        in params: sp["quality_score_weights"]["delta"]                      = params["qs_w_delta"]
                            if "qs_w_dte"          in params: sp["quality_score_weights"]["dte"]                        = params["qs_w_dte"]

                            _syms_str = ", ".join(wfo_display.get("symbols", [label]))
                            _note = (
                                f"Optimizer applied — {_syms_str} · {_opt_profile} · {regime} regime · "
                                f"{n_acc}/{wfo_display.get('windows_total', '?')} windows passed · "
                                f"stop {round(params.get('stop_loss_pct', 0))}% / "
                                f"target {round(params.get('profit_target_pct', 0))}%"
                            )
                            _save_profile(note=_note, profile=_opt_profile)
                            st.success(
                                f"✅ Applied {regime} recommendations to **{_opt_profile}** profile "
                                f"from {n_acc} accepted windows. "
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

            _mode = wfo_display.get("mode", "pooled")

            if _mode == "backtest":
                st.markdown(
                    f"**Last run:** {wfo_display['run_at']}  |  "
                    f"**History:** {wfo_display.get('lookback_years', '—')} yrs  |  "
                    f"**Trades:** {wfo_display.get('total_trades', 0):,}  |  "
                    f"**Equity + Index profiles**"
                )
                _render_backtest_result(wfo_display,
                                        sim_capital=wfo_capital, sim_risk_pct=wfo_risk_pct)

            elif _mode == "pooled":
                syms_str = ", ".join(wfo_display.get("symbols", []))
                st.markdown(
                    f"**Last run:** {wfo_display['run_at']}  |  "
                    f"**Mode:** pooled  |  "
                    f"**Tickers:** {syms_str}"
                )
                st.markdown(
                    f"**Windows:** {wfo_display['windows_passed']}/{wfo_display['windows_total']} "
                    f"passed ({wfo_display['pass_rate_pct']}%)"
                )
                _render_wfo_result(wfo_display, "Pooled", "pooled",
                                   sim_capital=wfo_capital, sim_risk_pct=wfo_risk_pct)

            else:  # per_ticker
                syms_str = ", ".join(wfo_display.get("symbols", []))
                st.markdown(
                    f"**Last run:** {wfo_display['run_at']}  |  "
                    f"**Mode:** per_ticker  |  "
                    f"**Tickers:** {syms_str}"
                )
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
