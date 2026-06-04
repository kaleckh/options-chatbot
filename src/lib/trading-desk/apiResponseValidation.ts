import type { TradingDeskRouteContractId } from "@/lib/trading-desk/storeOwnership";

export type TradingDeskResponseValidationResult =
  | { ok: true }
  | { ok: false; reason: string; path: string };

function pass(): TradingDeskResponseValidationResult {
  return { ok: true };
}

function fail(path: string, reason: string): TradingDeskResponseValidationResult {
  return { ok: false, path, reason };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key);
}

function validateNoKeys(
  record: Record<string, unknown>,
  keys: string[],
  path: string
): TradingDeskResponseValidationResult {
  for (const key of keys) {
    if (hasOwn(record, key)) {
      return fail(`${path}.${key}`, `${key} is not valid for this Trading Desk route envelope`);
    }
  }
  return pass();
}

function validatePage(value: unknown, path: string): TradingDeskResponseValidationResult {
  if (value == null) return pass();
  if (!isRecord(value)) return fail(path, "page must be an object");
  for (const key of ["limit", "offset", "returned"]) {
    if (typeof value[key] !== "number" || !Number.isFinite(value[key])) {
      return fail(`${path}.${key}`, "page metadata must use finite numbers");
    }
  }
  return pass();
}

function validateRow(value: unknown, path: string): TradingDeskResponseValidationResult {
  if (!isRecord(value)) return fail(path, "row must be an object");
  if (typeof value.id !== "number" || !Number.isFinite(value.id)) {
    return fail(`${path}.id`, "row id must be a finite number");
  }
  if (value.status !== "open" && value.status !== "closed") {
    return fail(`${path}.status`, "row status must be open or closed");
  }
  return pass();
}

function validateRows(value: unknown, path: string): TradingDeskResponseValidationResult {
  if (!Array.isArray(value)) return fail(path, "rows must be an array");
  for (let index = 0; index < value.length; index += 1) {
    const result = validateRow(value[index], `${path}[${index}]`);
    if (!result.ok) return result;
  }
  return pass();
}

function validatePositionEventPersistence(
  value: unknown,
  path: string
): TradingDeskResponseValidationResult {
  if (!isRecord(value)) {
    return fail(path, "tracked mutation responses must include object-shaped position_event_persistence");
  }
  return pass();
}

function validateTrackedRead(record: Record<string, unknown>): TradingDeskResponseValidationResult {
  const wrongEnvelope = validateNoKeys(record, ["trade", "trades", "position_event_persistence"], "body");
  if (!wrongEnvelope.ok) return wrongEnvelope;
  if (hasOwn(record, "positions")) {
    const rows = validateRows(record.positions, "body.positions");
    if (!rows.ok) return rows;
    return validatePage(record.page, "body.page");
  }
  const openRows = validateRows(record.open, "body.open");
  if (!openRows.ok) return openRows;
  const closedRows = validateRows(record.closed, "body.closed");
  if (!closedRows.ok) return closedRows;
  if (!isRecord(record.summary)) return fail("body.summary", "grouped response summary must be an object");
  return validatePage(record.page, "body.page");
}

function validateSuggestedRead(record: Record<string, unknown>): TradingDeskResponseValidationResult {
  const wrongEnvelope = validateNoKeys(record, ["position", "positions", "position_event_persistence"], "body");
  if (!wrongEnvelope.ok) return wrongEnvelope;
  if (hasOwn(record, "trades")) {
    const rows = validateRows(record.trades, "body.trades");
    if (!rows.ok) return rows;
    return validatePage(record.page, "body.page");
  }
  const openRows = validateRows(record.open, "body.open");
  if (!openRows.ok) return openRows;
  const closedRows = validateRows(record.closed, "body.closed");
  if (!closedRows.ok) return closedRows;
  if (!isRecord(record.summary)) return fail("body.summary", "grouped response summary must be an object");
  return validatePage(record.page, "body.page");
}

function validateTrackedPositionMutation(
  record: Record<string, unknown>,
  envelope: "position" | "positions"
): TradingDeskResponseValidationResult {
  const wrongEnvelope = validateNoKeys(record, ["trade", "trades"], "body");
  if (!wrongEnvelope.ok) return wrongEnvelope;
  const rows = envelope === "position"
    ? validateRow(record.position, "body.position")
    : validateRows(record.positions, "body.positions");
  if (!rows.ok) return rows;
  return validatePositionEventPersistence(
    record.position_event_persistence,
    "body.position_event_persistence"
  );
}

function validateSuggestedMutation(
  record: Record<string, unknown>,
  envelope: "trade" | "trades"
): TradingDeskResponseValidationResult {
  const wrongEnvelope = validateNoKeys(
    record,
    ["position", "positions", "position_event_persistence"],
    "body"
  );
  if (!wrongEnvelope.ok) return wrongEnvelope;
  return envelope === "trade"
    ? validateRow(record.trade, "body.trade")
    : validateRows(record.trades, "body.trades");
}

export function validateTradingDeskApiResponse(
  contractId: TradingDeskRouteContractId,
  body: unknown
): TradingDeskResponseValidationResult {
  if (!isRecord(body)) return fail("body", "response must be an object");
  if (typeof body.error === "string") return pass();

  switch (contractId) {
    case "tracked_positions_read":
      return validateTrackedRead(body);
    case "tracked_positions_create":
    case "tracked_positions_close":
      return validateTrackedPositionMutation(body, "position");
    case "tracked_positions_review":
      return validateTrackedPositionMutation(body, "positions");
    case "suggested_trades_read":
      return validateSuggestedRead(body);
    case "suggested_trades_create":
    case "suggested_trades_close":
      return validateSuggestedMutation(body, "trade");
    case "suggested_trades_review":
      return validateSuggestedMutation(body, "trades");
    default:
      return fail("contractId", "unknown Trading Desk route contract");
  }
}
