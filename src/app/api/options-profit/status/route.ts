import { getOptionsProfitStatusWithBackendHeaders } from "@/lib/python-bridge";
import { jsonError, jsonWithRouteLifecycle } from "../../_utils";

export async function GET() {
  try {
    const result = await getOptionsProfitStatusWithBackendHeaders();
    return jsonWithRouteLifecycle(result.body, "options_profit_status_read", { headers: result.headers });
  } catch (err) {
    return jsonError(err, "Failed to fetch options profit status");
  }
}
