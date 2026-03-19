"""
Standalone daily scan — executed by Windows Task Scheduler at 10:10 AM.
Saves top 5 picks to predictions.json independently of the Streamlit app.
"""
import os
import sys
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
    from options_chatbot import scan_daily_top_trades, _load_predictions, _save_predictions
except Exception as e:
    logging.error(f"Import failed: {e}")
    sys.exit(1)

ET        = ZoneInfo("America/New_York")
now_et    = datetime.now(ET)
today_str = now_et.strftime("%Y-%m-%d")

# Skip weekends
if now_et.weekday() >= 5:
    logging.info("Weekend — skipping scan.")
    sys.exit(0)

# Skip if before 10:00 AM ET
if now_et.hour < 10:
    logging.info(f"Before market window ({now_et.strftime('%H:%M')} ET) — skipping.")
    sys.exit(0)

# Skip if today's picks already saved
existing = _load_predictions()
already  = any(
    p.get("entry_date", "")[:10] == today_str and p.get("type") == "daily_scan"
    for p in existing
)
if already:
    logging.info(f"Picks already saved for {today_str} — nothing to do.")
    sys.exit(0)

# Run scan
logging.info(f"Starting daily watchlist scan for {today_str}…")
try:
    picks = scan_daily_top_trades(n_picks=5)
except Exception as e:
    logging.error(f"Scan failed: {e}")
    sys.exit(1)

if not picks:
    logging.warning("Scan returned 0 picks — no qualifying setups found today.")
    sys.exit(0)

new_id = max((p.get("id", 0) for p in existing), default=0)
for p in picks:
    new_id += 1
    rec       = dict(p)
    rec["id"] = new_id
    existing.append(rec)

_save_predictions(existing)
logging.info(
    f"Saved {len(picks)} pick(s) for {today_str}: "
    + ", ".join(f"{p['ticker']} {p['direction'].upper()} {p['confidence']:.1f}%" for p in picks)
)
