from __future__ import annotations

from typing import Any, Iterable


def build_perf_snapshot_from_predictions(predictions: Iterable[dict[str, Any]], date_str: str) -> dict[str, Any] | None:
    preds = list(predictions)
    today_graded = [
        p
        for p in preds
        if str(p.get("graded_date", ""))[:10] == date_str
        and p.get("outcome")
        and p.get("type") == "daily_scan"
    ]
    if not today_graded:
        return None

    outcomes = [p["outcome"] for p in today_graded]
    full_hits = sum(1 for outcome in outcomes if outcome == "hit")
    directional_hits = sum(1 for outcome in outcomes if outcome in ("hit", "directional"))
    n = len(today_graded)

    new_graded = [p for p in today_graded if p.get("pick_status", "new") == "new"]
    n_new = len(new_graded)
    new_full_hits = sum(1 for p in new_graded if p.get("outcome") == "hit")
    new_directional_hits = sum(1 for p in new_graded if p.get("outcome") in ("hit", "directional"))
    new_win_rate = round(new_full_hits / n_new * 100, 1) if n_new else None
    new_directional_accuracy = round(new_directional_hits / n_new * 100, 1) if n_new else None

    gains = [
        p.get("option_gain_pct") if p.get("option_gain_pct") is not None else p.get("est_option_gain_pct")
        for p in today_graded
        if p.get("option_gain_pct") is not None or p.get("est_option_gain_pct") is not None
    ]
    avg_gain = round(sum(gains) / len(gains), 1) if gains else None

    def _dir_score(p: dict[str, Any]) -> float:
        return float(p.get("direction_score") or p.get("confidence") or 0)

    high_score = [p for p in today_graded if _dir_score(p) >= 80]
    low_score = [p for p in today_graded if _dir_score(p) < 80]

    def _win_rate(rows: list[dict[str, Any]]) -> float | None:
        graded = [p for p in rows if p.get("outcome")]
        return round(sum(1 for p in graded if p["outcome"] == "hit") / len(graded) * 100, 1) if graded else None

    def _directional_accuracy(rows: list[dict[str, Any]]) -> float | None:
        graded = [p for p in rows if p.get("outcome")]
        return (
            round(sum(1 for p in graded if p["outcome"] in ("hit", "directional")) / len(graded) * 100, 1)
            if graded
            else None
        )

    all_graded = sorted(
        [p for p in preds if p.get("type") == "daily_scan" and p.get("outcome") and p.get("graded_date")],
        key=lambda p: p["graded_date"],
    )
    streak = 0
    streak_type = None
    for p in reversed(all_graded):
        result = "win" if p["outcome"] == "hit" else "loss"
        if streak_type is None:
            streak_type = result
        if result == streak_type:
            streak += 1
        else:
            break

    all_graded_count = len(all_graded)
    all_directional_hits = sum(1 for p in all_graded if p.get("outcome") in ("hit", "directional"))
    all_full_hits = sum(1 for p in all_graded if p.get("outcome") == "hit")
    all_time_win_rate = round(all_full_hits / all_graded_count * 100, 1) if all_graded_count else None
    all_time_directional_accuracy = (
        round(all_directional_hits / all_graded_count * 100, 1) if all_graded_count else None
    )

    return {
        "date": date_str,
        "picks_graded": n,
        "directional_wins": directional_hits,
        "full_target_hits": full_hits,
        "win_rate_pct": round(full_hits / n * 100, 1),
        "directional_accuracy_pct": round(directional_hits / n * 100, 1),
        "avg_est_option_gain_pct": avg_gain,
        "high_score_win_rate": _win_rate(high_score),
        "low_score_win_rate": _win_rate(low_score),
        "high_score_directional_accuracy_pct": _directional_accuracy(high_score),
        "low_score_directional_accuracy_pct": _directional_accuracy(low_score),
        "current_streak": streak,
        "current_streak_type": streak_type,
        "all_time_win_rate_pct": all_time_win_rate,
        "all_time_directional_accuracy_pct": all_time_directional_accuracy,
        "all_time_graded": all_graded_count,
        "new_picks_graded": n_new,
        "new_pick_win_rate_pct": new_win_rate,
        "new_pick_directional_accuracy_pct": new_directional_accuracy,
    }
