import { getRiskSettings } from "@/lib/python-bridge";
import { jsonError, jsonWithRouteLifecycle } from "../_utils";

export async function GET() {
  try {
    const result = await getRiskSettings();
    const equityRisk = (result?.equity as Record<string, unknown> | undefined) || {};
    return jsonWithRouteLifecycle({
      current_settings: equityRisk,
      profiles: result,
    }, "risk_settings_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch risk settings");
  }
}
