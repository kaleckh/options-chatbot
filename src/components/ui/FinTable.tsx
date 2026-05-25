"use client";

import { isValidElement, memo } from "react";

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
    const raw = val.replace(/%/g, "").replace(/\+/g, "").replace(/\$/g, "").replace(/,/g, "").replace(/—/g, "").trim();
    const n = parseFloat(raw);
    if (!isNaN(n)) {
      if (n > 0) classes.push("pos");
      else if (n < 0) classes.push("neg");
      else classes.push("dim");
    }
  } else if (rateCols.has(col)) {
    const raw = val.replace(/%/g, "").replace(/—/g, "").trim();
    const n = parseFloat(raw);
    if (!isNaN(n)) {
      if (n >= 60) classes.push("pos");
      else if (n >= 40) classes.push("warn");
      else classes.push("neg");
    }
  }

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
}: FinTableProps) {
  if (!data || data.length === 0) {
    return (
      <div className="ft-wrap p-4 text-text-2 text-sm" role="status">No data</div>
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
      <table className={`ft-table ${density === "compact" ? "ft-table-compact" : ""}`.trim()} aria-label={label}>
        <thead>
          <tr>
            {columns.map((col) => (
              <th key={col} scope="col">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={rowKey(row, i)}>
              {columns.map((col) => {
                const raw = row[col];

                if (isValidElement(raw)) {
                  return (
                    <td key={col}>
                      {raw}
                    </td>
                  );
                }

                const val = raw == null ? "" : String(raw);

                // Badge rendering
                if (badgeCol && col === badgeCol) {
                  const v = val.toUpperCase();
                  if (v.includes("CALL")) {
                    return (
                      <td key={col}>
                        <span className="badge-call" aria-label="Call option">CALL</span>
                      </td>
                    );
                  }
                  if (v.includes("PUT")) {
                    return (
                      <td key={col}>
                        <span className="badge-put" aria-label="Put option">PUT</span>
                      </td>
                    );
                  }
                }

                // Outcome badges
                const isOutcome = isOutcomeColumn(col, outcomeSet);
                if (isOutcome && val.toLowerCase().includes("hit") && !val.toLowerCase().includes("miss")) {
                  return (
                    <td key={col}>
                      <span className="badge-hit" aria-label="Hit">{val}</span>
                    </td>
                  );
                }
                if (isOutcome && val.toLowerCase().includes("miss")) {
                  return (
                    <td key={col}>
                      <span className="badge-miss" aria-label="Miss">{val}</span>
                    </td>
                  );
                }
                if (isOutcome && (val.toLowerCase().includes("directional") || val.toLowerCase().includes("dir"))) {
                  if (!val.toLowerCase().includes("score")) {
                    return (
                      <td key={col}>
                        <span className="badge-dir" aria-label="Directional">{val}</span>
                      </td>
                    );
                  }
                }

                const cls = cellClass(col, val, pnlSet, rateSet, monoSet);
                return (
                  <td key={col} className={cls || undefined}>
                    {val}
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
