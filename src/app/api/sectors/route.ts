import { getSectorSentiments } from "@/lib/python-bridge";
import { jsonError, jsonWithRouteLifecycle } from "../_utils";

export async function GET() {
  try {
    const sectors = await getSectorSentiments();
    return jsonWithRouteLifecycle(sectors, "sectors_read");
  } catch (err) {
    return jsonError(err, "Failed");
  }
}
