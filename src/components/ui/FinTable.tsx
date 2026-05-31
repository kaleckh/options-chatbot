"use client";

import { isValidElement, memo, type ReactNode } from "react";

interface FinTableProps {
  data: Record<string, unknown>[];
  pnlCols?: string[];
  rateCols?: string[];
  monoCols?: string[];
  badgeCol?: string;
  outcomeCols?: string[];
  maxHeight?: string;
  label?: string;
  density?: "default" | "compact";
  emptyMessage?: string;
}

function cellClass(
  col: string,
  val: string,
  pnlCols: Set<string>,
  rateCols: Set<string>,
  monoCols: Set<string>
): string {
  const classes: string[] = [];
  if (monoCols.has(col) || pnlCols.has(col) || rateCols.has(col)) {
    classes.push("mono");
  }

  if (pnlCols.has(col)) {
    const raw = val.replace(/%/g, "").replace(/\+/g, "").replace(/\$/g, "").replace(/,/g, "").replace(/\u2014/g, "").trim();
    const n = parseFloat(raw);
    if (!isNaN(n)) {
      if (n > 0) classes.push("pos");
      else if (n < 0) classes.push("neg");
      else classes.push("dim");
    }
  } else if (rateCols.has(col)) {
    const raw = val.replace(/%/g, "").replace(/\u2014/g, "").trim();
    const n = parseFloat(raw);
    if (!isNaN(n)) {
      if (n >= 60) classes.push("pos");
      else if (n >= 40) classes.push("warn");
      else classes.push("neg");
    }
  }

  if (col === "Action") classes.push("ft-action-cell");
  return classes.join(" ");
}

function rowKey(row: Record<string, unknown>, index: number): string {
  const explicitKey = row.__rowKey;
  if (
    typeof explicitKey === "string" ||
    typeof explicitKey === "number" ||
    typeof explicitKey === "boolean"
  ) {
    return String(explicitKey);
  }
  const cols = Object.keys(row);
  const parts = cols.slice(0, 3).map((c) => {
    const value = row[c];
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }
    return "";
  });
  const key = parts.join("-");
  return key || String(index);
}

function isOutcomeColumn(col: string, outcomeCols: Set<string>): boolean {
  if (outcomeCols.has(col)) return true;
  const normalized = col.trim().toLowerCase();
  return normalized === "outcome" || normalized === "result" || normalized.endsWith(" outcome");
}

function renderCellValue(
  col: string,
  raw: unknown,
  badgeCol: string | undefined,
  outcomeSet: Set<string>
): ReactNode {
  if (isValidElement(raw)) return raw;

  const val = raw == null ? "" : String(raw);

  if (badgeCol && col === badgeCol) {
    const v = val.toUpperCase();
    if (v.includes("CALL")) {
      return <span className="badge-call" aria-label="Call option">CALL</span>;
    }
    if (v.includes("PUT")) {
      return <span className="badge-put" aria-label="Put option">PUT</span>;
    }
  }

  const isOutcome = isOutcomeColumn(col, outcomeSet);
  const lower = val.toLowerCase();
  if (isOutcome && lower.includes("hit") && !lower.includes("miss")) {
    return <span className="badge-hit" aria-label="Hit">{val}</span>;
  }
  if (isOutcome && lower.includes("miss")) {
    return <span className="badge-miss" aria-label="Miss">{val}</span>;
  }
  if (isOutcome && (lower.includes("directional") || lower.includes("dir")) && !lower.includes("score")) {
    return <span className="badge-dir" aria-label="Directional">{val}</span>;
  }

  return val;
}

function FinTable({
  data,
  pnlCols = [],
  rateCols = [],
  monoCols = [],
  badgeCol,
  outcomeCols = ["Outcome", "Result"],
  maxHeight = "460px",
  label = "Data table",
  density = "default",
  emptyMessage = "No data",
}: FinTableProps) {
  if (!data || data.length === 0) {
    return (
      <div className="ft-wrap p-4 text-text-2 text-sm" role="status">{emptyMessage}</div>
    );
  }

  const pnlSet = new Set(pnlCols);
  const rateSet = new Set(rateCols);
  const monoSet = new Set(monoCols);
  const outcomeSet = new Set(outcomeCols);
  const columns = Object.keys(data[0]).filter((col) => !col.startsWith("__"));

  return (
    <div
      className="ft-wrap"
      style={{ maxHeight }}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      <div className="ft-mobile-cards">
        {data.map((row, i) => {
          const key = rowKey(row, i);
          const titleCol = columns[0];
          const subtitleCol = columns.find((col) => col !== titleCol && col !== "Action");
          return (
            <article key={key} className="ft-mobile-card">
              <div className="ft-mobile-card-head">
                <div>
                  <div className="ft-mobile-label">{titleCol}</div>
                  <div className="ft-mobile-title">{renderCellValue(titleCol, row[titleCol], badgeCol, outcomeSet)}</div>
                </div>
                {subtitleCol ? (
                  <div className="text-right">
                    <div className="ft-mobile-label">{subtitleCol}</div>
                    <div className="ft-mobile-subtitle">{renderCellValue(subtitleCol, row[subtitleCol], badgeCol, outcomeSet)}</div>
                  </div>
                ) : null}
              </div>
              <div className="ft-mobile-grid">
                {columns
                  .filter((col) => col !== titleCol && col !== subtitleCol && col !== "Action")
                  .map((col) => {
                    const raw = row[col];
                    const val = raw == null || isValidElement(raw) ? "" : String(raw);
                    return (
                      <div key={col} className="ft-mobile-field">
                        <div className="ft-mobile-label">{col}</div>
                        <div className={cellClass(col, val, pnlSet, rateSet, monoSet) || undefined}>
                          {renderCellValue(col, raw, badgeCol, outcomeSet)}
                        </div>
                      </div>
                    );
                  })}
              </div>
              {columns.includes("Action") ? (
                <div className="ft-mobile-actions">
                  {renderCellValue("Action", row.Action, badgeCol, outcomeSet)}
                </div>
              ) : null}
            </article>
          );
        })}
      </div>

      <table className={`ft-table ${density === "compact" ? "ft-table-compact" : ""}`.trim()} aria-label={label}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col} scope="col" className={col === "Action" ? "ft-action-cell" : undefined}>{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={rowKey(row, i)}>
              {columns.map((col) => {
                const raw = row[col];
                const val = raw == null || isValidElement(raw) ? "" : String(raw);
                const cls = cellClass(col, val, pnlSet, rateSet, monoSet);
                return (
                  <td key={col} className={cls || undefined}>
                    {renderCellValue(col, raw, badgeCol, outcomeSet)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default memo(FinTable);
