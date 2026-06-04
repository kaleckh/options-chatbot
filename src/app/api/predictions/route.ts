import { getPredictions } from "@/lib/python-bridge";
import { jsonError, jsonWithRouteLifecycle } from "../_utils";

export async function GET() {
  try {
    const predictions = await getPredictions();
    return jsonWithRouteLifecycle(predictions, "predictions_read");
  } catch (err) {
    return jsonError(err, "Failed to fetch predictions");
  }
}
