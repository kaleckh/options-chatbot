from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_WORKFLOW = Path(
    r"C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\workflows\wf_d686b8fe-26c.json"
)
DEFAULT_JOURNAL = Path(
    r"C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\subagents\workflows\wf_d686b8fe-26c\journal.jsonl"
)
DEFAULT_TRANSCRIPT = Path(
    r"C:\Users\kalec\.claude\projects\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e.jsonl"
)
DEFAULT_TASK_OUTPUT = Path(
    r"C:\Users\kalec\AppData\Local\Temp\claude\C--Users-kalec\1d85d233-7324-4b97-b706-f8c75116ce3e\tasks\wjwzqslef.output"
)

REPORT_PATH = Path("docs/options-strategy-deep-research-recovery-2026-07-07.md")
SUMMARY_PATH = Path("data/profitability-lab/options-strategy-deep-research-recovery/latest.json")

FOCUSED_REVIEWER_SYNTHESIS = [
    {
        "family": "defined_risk_index_vrp_credit_spreads",
        "verdict": "top_research_candidate_unproven_for_bot",
        "summary": (
            "Historical S&P 500 VRP and put-writing evidence is real and better supported than the other "
            "families, but it does not prove a retail put-credit-spread bot earns positive expectancy after "
            "NBBO fills, spread crossing, commissions, margin, and tail events."
        ),
        "recommended_action": (
            "Run the first preregistered falsification test on SPY index-VRP put credit spreads, with "
            "QQQ/IWM/DIA as secondary holdouts and optional predeclared IV/skew filters."
        ),
        "source_urls": [
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=375784",
            "https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf",
            "https://www.aqr.com/-/media/AQR/Documents/Whitepapers/Understanding-the-Volatility-Risk-Premium.pdf",
            "https://cdn.cboe.com/api/global/us_indices/governance/Cboe_SP_500_PutWrite_Indices_Methodology.pdf",
        ],
    },
    {
        "family": "earnings_event_volatility",
        "verdict": "conditional_research_candidate_only",
        "summary": (
            "The recovered workflow did not verify earnings/event claims, but primary sources support two "
            "cautions: naive retail event-vol buying loses badly around earnings, and naive pre-earnings "
            "short-vol 'IV crush' is not cleanly supported. Conditional post-event or implied-vs-historical "
            "move tests are plausible but cost-sensitive."
        ),
        "recommended_action": (
            "Test only as a narrow conditional branch with a fixed event calendar, fixed entry/exit windows, "
            "liquidity filters, matched non-event controls, and no midpoint fills."
        ),
        "source_urls": [
            "https://academic.oup.com/rof/article-abstract/30/2/489/8301159",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2204549",
            "https://www.mdpi.com/1911-8074/16/5/270",
            "https://www.sciencedirect.com/science/article/abs/pii/S0927539816300743",
            "https://academic.oup.com/rof/article/29/4/963/8079062",
        ],
    },
    {
        "family": "short_dte_0dte_premium_selling",
        "verdict": "defer_as_primary_strategy",
        "summary": (
            "Cboe evidence supports 0DTE liquidity and market-structure relevance, not a durable retail "
            "expectancy edge. The recovered workflow did not verify 0DTE profitability claims, and practitioner "
            "evidence remains vulnerable to selection, tail loss, and execution assumptions."
        ),
        "recommended_action": (
            "Defer behind VRP. If tested, make it paper/research-only with explicit gamma, max-loss, "
            "event-day, no-price-improvement, and late-day slippage stress."
        ),
        "source_urls": [
            "https://www.cboe.com/insights/posts/the-state-of-the-options-industry-2025/",
            "https://www.cboe.com/insights/posts/henry-schwartzs-zero-day-spx-iron-condor-strategy-a-deep-dive/",
            "https://cdn.cboe.com/resources/education/research_publications/PutWriteCBOE19_v14_by_Prof_Oleg_Bondarenko_as_of_June_14.pdf",
        ],
    },
    {
        "family": "directional_option_buying_momentum_debit_spreads",
        "verdict": "reject_for_live_capital",
        "summary": (
            "No credible live positive-expectancy case remains for the bot's directional momentum debit-spread "
            "branch after realistic costs. Retail long short-dated option buying loses after spreads, fees, and "
            "decay; academic option-momentum evidence is not the same as this branch."
        ),
        "recommended_action": (
            "Disable for live capital and keep only shadow telemetry unless a new preregistered test beats "
            "stock/ETF momentum after NBBO fills, commissions, slippage, and untouched OOS data."
        ),
        "source_urls": [
            "https://academic.oup.com/rof/article-abstract/30/2/489/8301159",
            "https://onlinelibrary.wiley.com/doi/10.1111/jofi.13285",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4065019",
        ],
    },
    {
        "family": "methodology_backtest_contract",
        "verdict": "strict_falsification_required",
        "summary": (
            "The recovered Claude run is useful as methodology evidence, not a final strategy conclusion. "
            "Any candidate must be preregistered, replayed from point-in-time OPRA/NBBO, filled side-aware, "
            "fee-adjusted, stress-tested, and controlled for multiple testing."
        ),
        "recommended_action": (
            "Use a fail-closed contract with fixed parameters, quote-evidence rows for every trade, "
            "realistic multi-leg execution, PBO/CSCV or equivalent multiple-testing controls, and explicit kill criteria."
        ),
        "source_urls": [
            "https://orats.com/university/backtesting-methodology",
            "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253",
            "https://www.finra.org/rules-guidance/rulebooks/finra-rules/5310",
            "https://www.theocc.com/company-information/documents-and-archives/options-disclosure-document",
        ],
    },
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return _clean_text(json.load(fh))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(_clean_text(json.loads(line)))
    return rows


def _clean_text(value: Any) -> Any:
    if isinstance(value, str):
        if any(token in value for token in ("â", "Â", "Γ")):
            try:
                return value.encode("cp1252").decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                return value
        return value
    if isinstance(value, list):
        return [_clean_text(item) for item in value]
    if isinstance(value, dict):
        return {key: _clean_text(item) for key, item in value.items()}
    return value


def _family_for_text(text: str) -> str:
    lower = text.lower()
    if any(token in lower for token in ("earnings", "announcement", "eav", "event", "iv crush")):
        return "earnings_event_volatility"
    if any(token in lower for token in ("0dte", "zero day", "zero-day", "short-dte", "same-day")):
        return "short_dte_0dte"
    if any(token in lower for token in ("retail", "buyer", "buyers lose", "directional", "momentum", "lottery")):
        return "directional_buying_retail_losses"
    if any(token in lower for token in ("term structure", "calendar", "vix futures", "roll-down", "contango")):
        return "term_structure_calendar"
    if any(token in lower for token in ("skew", "left-tail", "tail", "jump", "otm put")):
        return "index_skew_tail_risk"
    if any(token in lower for token in ("put", "putwrite", "vrp", "volatility risk premium", "variance risk")):
        return "vrp_put_writing"
    if any(token in lower for token in ("backtest", "overfit", "slippage", "bid-ask", "fill", "commission")):
        return "methodology_costs"
    return "other"


def _extract_journal(rows: list[dict[str, Any]]) -> dict[str, Any]:
    event_types = Counter(row.get("type", "unknown") for row in rows)
    search_results: list[dict[str, Any]] = []
    extracted_claims: list[dict[str, Any]] = []
    verdicts: list[dict[str, Any]] = []
    angle_plan: dict[str, Any] | None = None
    result_shapes = Counter()

    for idx, row in enumerate(rows, start=1):
        if row.get("type") != "result":
            continue
        result = row.get("result") or {}
        if not isinstance(result, dict):
            continue
        shape = tuple(sorted(result.keys()))
        result_shapes[str(shape)] += 1

        if {"question", "angles", "summary"}.issubset(result):
            angle_plan = result
            continue

        if "results" in result and isinstance(result["results"], list):
            for item in result["results"]:
                if isinstance(item, dict):
                    search_results.append(item)
            continue

        if "claims" in result and isinstance(result["claims"], list):
            source_quality = result.get("sourceQuality", "unknown")
            publish_date = result.get("publishDate")
            for item in result["claims"]:
                if not isinstance(item, dict):
                    continue
                claim_text = item.get("claim", "")
                extracted_claims.append(
                    {
                        "journal_line": idx,
                        "claim": claim_text,
                        "quote": item.get("quote"),
                        "importance": item.get("importance"),
                        "source_quality": source_quality,
                        "publish_date": publish_date,
                        "strategy_family": _family_for_text(claim_text),
                    }
                )
            continue

        if "refuted" in result and "evidence" in result:
            evidence = result.get("evidence", "")
            verdicts.append(
                {
                    "journal_line": idx,
                    "refuted": bool(result.get("refuted")),
                    "confidence": result.get("confidence"),
                    "evidence": evidence,
                    "counter_source": result.get("counterSource"),
                    "strategy_family": _family_for_text(evidence + " " + str(result.get("counterSource", ""))),
                }
            )

    started_keys = {row.get("key") for row in rows if row.get("type") == "started"}
    result_keys = {row.get("key") for row in rows if row.get("type") == "result"}
    incomplete_keys = sorted(k for k in started_keys - result_keys if k)

    return {
        "event_types": dict(event_types),
        "result_shapes": dict(result_shapes),
        "angle_plan": angle_plan,
        "search_results": search_results,
        "extracted_claims": extracted_claims,
        "verdicts": verdicts,
        "incomplete_started_count": len(incomplete_keys),
        "incomplete_started_keys_sample": incomplete_keys[:20],
        "claim_family_counts": dict(Counter(c["strategy_family"] for c in extracted_claims)),
        "verdict_family_counts": dict(Counter(v["strategy_family"] for v in verdicts)),
        "verdict_refuted_count": sum(1 for v in verdicts if v["refuted"]),
        "verdict_not_refuted_count": sum(1 for v in verdicts if not v["refuted"]),
    }


def _workflow_summary(workflow: dict[str, Any]) -> dict[str, Any]:
    result = workflow.get("result") or {}
    stats = result.get("stats") or {}
    return {
        "run_id": workflow.get("runId"),
        "task_id": workflow.get("taskId"),
        "workflow_name": workflow.get("workflowName"),
        "status": workflow.get("status"),
        "timestamp": workflow.get("timestamp"),
        "duration_ms": workflow.get("durationMs"),
        "agent_count": workflow.get("agentCount"),
        "total_tokens": workflow.get("totalTokens"),
        "total_tool_calls": workflow.get("totalToolCalls"),
        "result_summary": result.get("summary"),
        "question": result.get("question") or workflow.get("args"),
        "stats": stats,
        "confirmed": result.get("confirmed") or [],
        "unverified": result.get("unverified") or [],
        "sources": result.get("sources") or [],
        "refuted": result.get("refuted") or [],
    }


def _md_escape(text: Any) -> str:
    return str(text).replace("\n", " ").strip()


def _render_markdown(summary: dict[str, Any]) -> str:
    workflow = summary["workflow"]
    journal = summary["journal"]
    stats = workflow.get("stats") or {}
    confirmed = workflow.get("confirmed") or []
    unverified = workflow.get("unverified") or []
    sources = workflow.get("sources") or []
    verdicts = journal.get("verdicts") or []
    refuted_verdicts = [v for v in verdicts if v.get("refuted")]

    lines = [
        "# Options Strategy Deep Research Recovery - 2026-07-07",
        "",
        "This report preserves the recovered Claude deep-research run as research-only context. It does not authorize scanner changes, quote import, evidence mutation, proof-bar changes, live validation, auto-track, broker action, protected-holdout use, or promotion.",
        "",
        "## Provenance",
        "",
        f"- Claude session title: `Audit options bot progress and local changes`",
        f"- Session ID: `1d85d233-7324-4b97-b706-f8c75116ce3e`",
        f"- Workflow run: `{workflow.get('run_id')}`",
        f"- Workflow task: `{workflow.get('task_id')}`",
        f"- Workflow status: `{workflow.get('status')}`",
        f"- Failure mode: verifier and synthesis agents hit the Claude session limit; no completed final synthesis payload was recovered.",
        "",
        "Source files:",
    ]
    for name, info in summary["input_files"].items():
        lines.append(f"- `{name}`: `{info['path']}` (`sha256={info['sha256']}`)")

    lines += [
        "",
        "## Run Stats",
        "",
        f"- Agent count: `{workflow.get('agent_count')}`",
        f"- Duration ms: `{workflow.get('duration_ms')}`",
        f"- Total tokens: `{workflow.get('total_tokens')}`",
        f"- Total tool calls: `{workflow.get('total_tool_calls')}`",
        f"- Search angles: `{stats.get('angles')}`",
        f"- Workflow sources: `{stats.get('sources')}`",
        f"- Workflow claims: `{stats.get('claims')}`",
        f"- Claims sent to workflow verification: `{stats.get('verified')}`",
        f"- Workflow confirmed claims: `{stats.get('confirmed')}`",
        f"- Workflow killed/refuted panels: `{stats.get('killed')}`",
        f"- Workflow unverified claims: `{stats.get('unverified')}`",
        f"- Journal events: `{sum(journal.get('event_types', {}).values())}`",
        f"- Journal result records: `{journal.get('event_types', {}).get('result')}`",
        f"- Journal started-without-result records: `{journal.get('incomplete_started_count')}`",
        f"- Extracted claims in journal: `{len(journal.get('extracted_claims', []))}`",
        f"- Verifier verdict records in journal: `{len(verdicts)}` (`{journal.get('verdict_not_refuted_count')}` not refuted, `{journal.get('verdict_refuted_count')}` refuted)",
        "",
        "## Confirmed Claims From Workflow",
        "",
    ]

    for idx, item in enumerate(confirmed, start=1):
        lines += [
            f"{idx}. `{item.get('vote', 'n/a')}` - {_md_escape(item.get('claim'))}",
            f"   Source: {item.get('source')}",
        ]

    lines += [
        "",
        "## Unverified Claims Requiring Follow-Up",
        "",
        "These claims were not refuted by the final workflow result; they are unverified because verifier agents errored under session limits.",
        "",
    ]
    for idx, item in enumerate(unverified, start=1):
        lines += [
            f"{idx}. valid votes `{item.get('validVotes')}`, errored votes `{item.get('erroredVotes')}` - {_md_escape(item.get('claim'))}",
            f"   Source: {item.get('source')}",
        ]

    lines += [
        "",
        "## Journal Refutations To Preserve",
        "",
        "The workflow-level `killed` count was zero, but the raw journal contains individual refutation verdicts. All three refute over-strong interpretations that retail cost, margin, and current implementability are solved by historical put-overpricing evidence.",
        "",
    ]
    if refuted_verdicts:
        for idx, item in enumerate(refuted_verdicts, start=1):
            evidence = _md_escape(item.get("evidence"))
            lines += [
                f"{idx}. confidence `{item.get('confidence')}`, family `{item.get('strategy_family')}`",
                f"   Evidence: {evidence[:700]}{'...' if len(evidence) > 700 else ''}",
                f"   Counter-source: {item.get('counter_source')}",
            ]
    else:
        lines.append("- None found in journal.")

    lines += [
        "",
        "## Source Leads",
        "",
    ]
    for item in sources:
        lines.append(f"- `{item.get('quality')}` ({item.get('claimCount')} claims): {item.get('url')}")

    lines += [
        "",
        "## Focused Reviewer Synthesis",
        "",
        "Five focused read-only reviewer agents checked the recovered run by strategy family. Their integrated verdict is below.",
        "",
    ]
    for item in summary["focused_reviewer_synthesis"]:
        lines += [
            f"### {item['family']}",
            "",
            f"- Verdict: `{item['verdict']}`",
            f"- Summary: {item['summary']}",
            f"- Recommended action: {item['recommended_action']}",
            "- Source anchors:",
        ]
        for url in item["source_urls"]:
            lines.append(f"  - {url}")
        lines.append("")

    lines += [
        "",
        "## Recovered Research Interpretation",
        "",
        "1. The strongest supported family is defined-risk index volatility-risk-premium harvesting, especially SPY/QQQ/IWM/DIA put-credit-spread style tests conditioned on volatility and skew. The evidence supports a persistent index option insurance premium, but not automatic retail profitability.",
        "2. Retail execution costs, bid/ask crossing, margin/collateral, and tail clustering are gating uncertainties. The recovered verifier refutations specifically warn against treating historical put buyer losses or index benchmark returns as direct proof of current retail spread profitability.",
        "3. Earnings/event volatility has source support but remains less settled for the bot's ultra-liquid 13-symbol universe. The recovered claims point to high retail losses around expected announcement volatility and to high spread costs; the bot should only test this with a strict event calendar, liquidity filters, and cost stress.",
        "4. 0DTE/short-DTE evidence is mostly flow/practitioner evidence, not enough to outrank the VRP family. Treat it as a deferred branch unless a separate SPX/SPY 0DTE dataset and tail-loss controls are available.",
        "5. Directional option buying and momentum debit spreads should remain low-priority after the bot's falsified out-of-sample result unless a new independent signal is pre-registered and tested under full costs.",
        "",
        "## Plan To Finish The Research Work",
        "",
        "1. Use this recovery artifact as the frozen evidence bundle, not the chat transcript.",
        "2. Verify the decision-critical unverified claims by family: VRP/skew, earnings/event vol, 0DTE/short-DTE, directional buying/retail losses, and methodology/costs.",
        "3. Draft a final cited synthesis that ranks strategy families and separates supported findings from unverified or refuted overreach.",
        "4. Convert the top recommendation into a preregistered options-bot falsification contract for defined-risk index VRP spreads: fixed universe, quote source, entry/exit formulas, cost model, stress model, train/test split, and kill criteria.",
        "5. Do not implement scanner changes, quote import, live validation, broker actions, or promotion from this literature review alone.",
        "",
        "## Recommended Falsification Contract",
        "",
        "- Candidate family: `defined_risk_index_vrp_credit_spread_v1`.",
        "- Universe: SPY, QQQ, IWM, DIA first; single-name equities only after index results are known.",
        "- Structures: put credit spreads or iron condors with explicit max loss; no naked options.",
        "- Data: point-in-time OPRA/NBBO one-minute bid/ask quotes; no midpoint-only fills.",
        "- Fill model: side-aware executable bid/ask plus stress cases. At minimum test optimistic natural/improved fills, realistic bid/ask-width travel, and adverse fill stress.",
        "- Costs: include commission per contract-leg and all spread crossing; report net USD and percent P&L.",
        "- Risk gates: max drawdown, left-tail clustering, gap-through-short-strike behavior, assignment/expiration handling, and collateral utilization.",
        "- Validation: pre-register all parameters before scoring; use strict out-of-sample/fresh windows; account for every tried configuration to control backtest overfitting.",
        "- Kill criteria: fail if net PF lower bound is not above 1.0 after costs, if stress PF is not above 1.0, if tail drawdown exceeds preset risk budget, if exact quote coverage is incomplete, or if performance depends on post-hoc symbol/date filtering.",
        "",
        "## Immediate Next Build Step",
        "",
        "Create or refresh a preregistered design-only contract for `defined_risk_index_vrp_credit_spread_v1` that consumes this recovery artifact as literature context. That contract should be read-only and should name the exact data, fill, cost, validation, and kill criteria before any replay or scanner implementation work.",
    ]
    return "\n".join(lines) + "\n"


def build(args: argparse.Namespace) -> dict[str, Any]:
    workflow_path = Path(args.workflow)
    journal_path = Path(args.journal)
    transcript_path = Path(args.transcript)
    task_output_path = Path(args.task_output)

    for path in (workflow_path, journal_path, transcript_path, task_output_path):
        if not path.exists():
            raise FileNotFoundError(path)

    workflow = _workflow_summary(_read_json(workflow_path))
    journal = _extract_journal(_read_jsonl(journal_path))
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "research_recovery_ready_with_focused_reviewer_synthesis",
        "no_authority": {
            "does_not_authorize_trading_or_evidence_mutation": True,
            "does_not_authorize_scanner_or_strategy_changes": True,
            "does_not_authorize_broker_action": True,
            "does_not_authorize_live_validation_or_promotion": True,
        },
        "input_files": {
            "workflow": {"path": str(workflow_path), "sha256": _sha256(workflow_path)},
            "journal": {"path": str(journal_path), "sha256": _sha256(journal_path)},
            "transcript": {"path": str(transcript_path), "sha256": _sha256(transcript_path)},
            "task_output": {"path": str(task_output_path), "sha256": _sha256(task_output_path)},
        },
        "workflow": workflow,
        "journal": journal,
        "focused_reviewer_synthesis": FOCUSED_REVIEWER_SYNTHESIS,
    }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover the interrupted Claude options strategy deep-research run.")
    parser.add_argument("--workflow", default=str(DEFAULT_WORKFLOW))
    parser.add_argument("--journal", default=str(DEFAULT_JOURNAL))
    parser.add_argument("--transcript", default=str(DEFAULT_TRANSCRIPT))
    parser.add_argument("--task-output", default=str(DEFAULT_TASK_OUTPUT))
    parser.add_argument("--json", action="store_true", help="Print compact status JSON after writing artifacts.")
    args = parser.parse_args()

    summary = build(args)
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(_render_markdown(summary), encoding="utf-8")

    if args.json:
        status = {
            "status": summary["status"],
            "report": str(REPORT_PATH),
            "summary": str(SUMMARY_PATH),
            "confirmed": summary["workflow"]["stats"].get("confirmed"),
            "unverified": summary["workflow"]["stats"].get("unverified"),
            "journal_claims": len(summary["journal"]["extracted_claims"]),
            "journal_verdicts": len(summary["journal"]["verdicts"]),
        }
        print(json.dumps(status, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
