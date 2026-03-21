"""
Standalone daily scan — executed by Windows Task Scheduler at 10:10 AM ET.

Order of operations:
  1. Grade any predictions whose target_date has passed
  2. Append a daily performance snapshot to daily_performance.json
  3. Run today's watchlist scan and save top 5 picks
"""
import os
import sys
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _DIR)

logging.basicConfig(
    filename=os.path.join(_DIR, "auto_scan.log"),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
)

try:
    from options_chatbot import (
        roll_forward_daily_picks,
        log_prediction,
        _load_predictions,
        _save_predictions,
    )
except Exception as e:
    logging.error(f"Import failed: {e}")
    sys.exit(1)

ET        = ZoneInfo("America/New_York")
now_et    = datetime.now(ET)
today_str = now_et.strftime("%Y-%m-%d")

PERF_FILE = os.path.join(_DIR, "daily_performance.json")

# ── Skip weekends ──────────────────────────────────────────────────────────────
if now_et.weekday() >= 5:
    logging.info("Weekend — skipping.")
    sys.exit(0)

# ── Skip if before 10:00 AM ET ─────────────────────────────────────────────────
if now_et.hour < 10:
    logging.info(f"Before market window ({now_et.strftime('%H:%M')} ET) — skipping.")
    sys.exit(0)


# ── Step 1: Auto-grade expired predictions ────────────────────────────────────
logging.info("Running auto-grade on expired predictions…")
try:
    grade_result = json.loads(log_prediction(action="grade"))
    n_graded = grade_result.get("message", "")
    logging.info(f"Grade complete: {n_graded}")
except Exception as e:
    logging.error(f"Grading failed: {e}")


# ── Step 2: Daily performance snapshot ────────────────────────────────────────
def _build_perf_snapshot(date_str: str) -> dict | None:
    """
    After grading, compute summary stats for all picks graded on date_str.
    Also computes score-calibration buckets (high vs low Dir Score win rates).
    Returns None if nothing was graded today.
    """
    preds = _load_predictions()
    today_graded = [
        p for p in preds
        if p.get("graded_date", "")[:10] == date_str and p.get("outcome")
    ]
    if not today_graded:
        return None

    outcomes   = [p["outcome"] for p in today_graded]
    wins       = sum(1 for o in outcomes if o == "hit")
    dir_wins   = sum(1 for o in outcomes if o in ("hit", "directional"))
    n          = len(today_graded)

    # New-pick-only stats (exclude rolled picks for unbiased signal quality)
    new_graded   = [p for p in today_graded if p.get("pick_status", "new") == "new"]
    n_new        = len(new_graded)
    new_dir_wins = sum(1 for p in new_graded if p.get("outcome") in ("hit", "directional"))
    new_win_rate = round(new_dir_wins / n_new * 100, 1) if n_new else None

    # Average estimated option gain
    gains = [p.get("option_gain_pct") or p.get("est_option_gain_pct")
             for p in today_graded
             if p.get("option_gain_pct") is not None or p.get("est_option_gain_pct") is not None]
    avg_gain = round(sum(gains) / len(gains), 1) if gains else None

    # Score calibration: split by Dir Score threshold 80
    def _dir_score(p): return float(p.get("direction_score") or p.get("confidence") or 0)
    high_score = [p for p in today_graded if _dir_score(p) >= 80]
    low_score  = [p for p in today_graded if _dir_score(p) <  80]
    def _win_rate(lst):
        g = [p for p in lst if p.get("outcome")]
        return round(sum(1 for p in g if p["outcome"] in ("hit", "directional")) / len(g) * 100, 1) if g else None

    # Streak: look at all-time graded picks ordered by graded_date
    all_graded = sorted(
        [p for p in preds if p.get("outcome") and p.get("graded_date")],
        key=lambda p: p["graded_date"]
    )
    streak = 0
    streak_type = None
    for p in reversed(all_graded):
        result = "win" if p["outcome"] in ("hit", "directional") else "loss"
        if streak_type is None:
            streak_type = result
        if result == streak_type:
            streak += 1
        else:
            break

    # All-time stats
    all_graded_count = len(all_graded)
    all_dir_wins = sum(1 for p in all_graded if p.get("outcome") in ("hit", "directional"))
    all_time_win_rate = round(all_dir_wins / all_graded_count * 100, 1) if all_graded_count else None

    return {
        "date":                  date_str,
        "picks_graded":          n,
        "directional_wins":      dir_wins,
        "full_target_hits":      wins,
        "win_rate_pct":          round(dir_wins / n * 100, 1),
        "avg_est_option_gain_pct": avg_gain,
        "high_score_win_rate":   _win_rate(high_score),   # Dir Score >= 80
        "low_score_win_rate":    _win_rate(low_score),    # Dir Score < 80
        "current_streak":        streak,
        "current_streak_type":   streak_type,             # "win" or "loss"
        "all_time_win_rate_pct": all_time_win_rate,
        "all_time_graded":       all_graded_count,
        # New-pick-only hit rate (excludes rolled picks — cleaner signal quality measure)
        "new_picks_graded":      n_new,
        "new_pick_win_rate_pct": new_win_rate,
    }

try:
    snap = _build_perf_snapshot(today_str)
    if snap:
        perf = []
        if os.path.exists(PERF_FILE):
            with open(PERF_FILE) as f:
                perf = json.load(f)
        # Replace entry for today if it already exists
        perf = [e for e in perf if e.get("date") != today_str]
        perf.append(snap)
        with open(PERF_FILE, "w") as f:
            json.dump(perf, f, indent=2)
        logging.info(
            f"Performance snapshot: {snap['picks_graded']} graded, "
            f"win_rate={snap['win_rate_pct']}%, "
            f"avg_gain={snap['avg_est_option_gain_pct']}%, "
            f"streak={snap['current_streak_type']} x{snap['current_streak']}, "
            f"all-time={snap['all_time_win_rate_pct']}%"
        )
    else:
        logging.info("No picks graded today — skipping performance snapshot.")
except Exception as e:
    logging.error(f"Performance snapshot failed: {e}")


# ── Step 3: Roll-forward daily picks ─────────────────────────────────────────
existing = _load_predictions()

# All currently pending (ungraded) daily_scan picks
pending = [
    p for p in existing
    if p.get("type") == "daily_scan" and not p.get("outcome")
]

# Already ran today if any pending pick carries today's rolled date OR entry date
_already = any(
    (p.get("last_rolled_date") or p.get("entry_date", ""))[:10] == today_str
    for p in pending
)
if _already:
    logging.info(f"Picks already processed for {today_str} — skipping roll-forward.")
    sys.exit(0)

logging.info(f"Starting roll-forward scan for {today_str} ({len(pending)} pending picks)…")
try:
    result = roll_forward_daily_picks(pending, n_picks=5)
except Exception as e:
    logging.error(f"Roll-forward scan failed: {e}")
    sys.exit(1)

rolled  = result["rolled"]
new     = result["new"]
dropped = result["dropped"]

# Assign IDs to new picks only (rolled picks keep their original IDs)
new_id = max((p.get("id", 0) for p in existing), default=0)
for p in new:
    new_id += 1
    p["id"] = new_id

# Rebuild predictions list: remove old pending, insert rolled + new
non_pending   = [p for p in existing if not (p.get("type") == "daily_scan" and not p.get("outcome"))]
final_pending = rolled + new

_save_predictions(non_pending + final_pending)

_active = sorted(rolled + new, key=lambda x: x.get("direction_score", 0), reverse=True)
if dropped:
    logging.info(
        "Dropped (no longer in top 5): "
        + ", ".join(f"{p['ticker']} {p['direction'].upper()}" for p in dropped)
    )
if _active:
    logging.info(
        f"Roll-forward complete: {len(rolled)} rolled, {len(new)} new, {len(dropped)} dropped. "
        + "Active: "
        + ", ".join(
            f"{p['ticker']} {p['direction'].upper()} "
            f"[{'rolled×' + str(p.get('roll_count', 0)) if p.get('pick_status') == 'rolled' else 'NEW'}] "
            f"dir={p.get('direction_score', 0):.1f}%"
            for p in _active
        )
    )
else:
    logging.warning("No active picks after roll-forward — no qualifying setups found.")
