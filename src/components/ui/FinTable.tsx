"use client";

import { isValidElement, memo, useEffect, useMemo, useState, type ReactNode } from "react";

type FinTableRenderMode = "auto" | "desktop" | "mobile";
const EMPTY_STRING_ARRAY: string[] = [];
const DEFAULT_OUTCOME_COLS = ["Outcome", "Result"];

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
  mobileTitleCol?: string;
  mobileSubtitleCol?: string;
  mobilePriorityCols?: string[];
  mobileHiddenCols?: string[];
  mobileActionCol?: string;
  renderMode?: FinTableRenderMode;
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

function useMobileTableMode(renderMode: FinTableRenderMode): boolean {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (renderMode !== "auto") return;
    const query = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, [renderMode]);

  if (renderMode === "mobile") return true;
  if (renderMode === "desktop") return false;
  return isMobile;
}

function FinTable({
  data,
  pnlCols = EMPTY_STRING_ARRAY,
  rateCols = EMPTY_STRING_ARRAY,
  monoCols = EMPTY_STRING_ARRAY,
  badgeCol,
  outcomeCols = DEFAULT_OUTCOME_COLS,
  maxHeight = "460px",
  label = "Data table",
  density = "default",
  emptyMessage = "No data",
  mobileTitleCol,
  mobileSubtitleCol,
  mobilePriorityCols = EMPTY_STRING_ARRAY,
  mobileHiddenCols = EMPTY_STRING_ARRAY,
  mobileActionCol = "Action",
  renderMode = "auto",
}: FinTableProps) {
  const showMobileCards = useMobileTableMode(renderMode);
  const pnlSet = useMemo(() => new Set(pnlCols), [pnlCols]);
  const rateSet = useMemo(() => new Set(rateCols), [rateCols]);
  const monoSet = useMemo(() => new Set(monoCols), [monoCols]);
  const outcomeSet = useMemo(() => new Set(outcomeCols), [outcomeCols]);
  const columns = useMemo(
    () => data?.[0] ? Object.keys(data[0]).filter((col) => !col.startsWith("__")) : [],
    [data]
  );
  const mobileHiddenSet = useMemo(() => new Set(mobileHiddenCols), [mobileHiddenCols]);

  const mobileLayout = useMemo(() => {
    const pickMobileColumn = (
      preferred: string | undefined,
      fallback: string | undefined,
      excluded: Set<string>
    ): string | undefined => {
      if (preferred && columns.includes(preferred) && !mobileHiddenSet.has(preferred)) return preferred;
      if (fallback && columns.includes(fallback) && !mobileHiddenSet.has(fallback)) return fallback;
      return columns.find((col) => col !== mobileActionCol && !mobileHiddenSet.has(col) && !excluded.has(col));
    };

    const titleCol = pickMobileColumn(mobileTitleCol, columns[0], new Set());
    const subtitleCol = pickMobileColumn(
      mobileSubtitleCol,
      columns.find((col) => col !== titleCol && col !== mobileActionCol),
      new Set(titleCol ? [titleCol] : [])
    );
    const excluded = new Set([titleCol, subtitleCol, mobileActionCol].filter(Boolean) as string[]);
    const priority = mobilePriorityCols.filter(
      (col) => columns.includes(col) && !mobileHiddenSet.has(col) && !excluded.has(col)
    );
    const rest = columns.filter(
      (col) => col !== mobileActionCol && !mobileHiddenSet.has(col) && !excluded.has(col) && !priority.includes(col)
    );
    return { titleCol, subtitleCol, fields: [...priority, ...rest] };
  }, [columns, mobileActionCol, mobileHiddenSet, mobilePriorityCols, mobileSubtitleCol, mobileTitleCol]);

  if (!data || data.length === 0) {
    return (
      <div className="ft-wrap p-4 text-text-2 text-sm" role="status">{emptyMessage}</div>
    );
  }

  return (
    <div
      className="ft-wrap"
      style={{ maxHeight }}
      role="region"
      aria-label={label}
      tabIndex={0}
    >
      {showMobileCards ? (
        <div className="ft-mobile-cards ft-mobile-cards-rendered">
          {data.map((row, i) => {
            const key = rowKey(row, i);
            const { titleCol, subtitleCol, fields } = mobileLayout;
            return (
              <article key={key} className="ft-mobile-card">
                <div className="ft-mobile-card-head">
                  {titleCol ? (
                    <div>
                      <div className="ft-mobile-label">{titleCol}</div>
                      <div className="ft-mobile-title">{renderCellValue(titleCol, row[titleCol], badgeCol, outcomeSet)}</div>
                    </div>
                  ) : null}
                  {subtitleCol ? (
                    <div className="text-right">
                      <div className="ft-mobile-label">{subtitleCol}</div>
                      <div className="ft-mobile-subtitle">{renderCellValue(subtitleCol, row[subtitleCol], badgeCol, outcomeSet)}</div>
                    </div>
                  ) : null}
                </div>
                <div className="ft-mobile-grid">
                  {fields.map((col) => {
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
                {columns.includes(mobileActionCol) ? (
                  <div className="ft-mobile-actions">
                    {renderCellValue(mobileActionCol, row[mobileActionCol], badgeCol, outcomeSet)}
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <table className={`ft-table ${density === "compact" ? "ft-table-compact" : ""}`.trim()} aria-label={label}>
          <thead>
            <tr>
              {columns.map((col) => {
                return <th key={col} scope="col" className={col === "Action" ? "ft-action-cell" : undefined}>{col}</th>;
              })}
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
      )}
    </div>
  );
}

export default memo(FinTable);
