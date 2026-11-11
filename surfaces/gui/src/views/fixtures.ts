// Answer bundles for the renderer app's tests, in the shape the cited fabric view-bound tool
// answers (OW-F-016 Decisions): the payor demo work item from the gallery (synthetic, OW-F-015
// ticket 05) as a bundle, the same item with no view, and with an invalid view.
import { payorDemoView, workItemStates } from "../gallery/states/work-item";
import type { ToolResult } from "./host";

const demo = workItemStates.find((s) => s.id === "payor-demo")!.payload as Record<string, unknown>;

export const payorBundle = {
  session_id: "run-payor-demo",
  agent_id: demo.agent,
  decision: demo.decision,
  final_state: "approved",
  awaiting_signoff: true,
  envelopes: demo.envelopes,
  verified: true,
  plan: demo.plan,
  record: demo.record,
  signature: null,
  steps: demo.steps,
  view: payorDemoView,
};

export const noViewBundle = { ...payorBundle, view: null };

export const invalidViewBundle = {
  ...payorBundle,
  view: { ...payorDemoView, record: [...payorDemoView.record, { component: "sparkline", data_field: "units" }] },
};

// a CallToolResult as the host passes it: the text answer is the whole contract, the
// structured content carries the same bundle
export function toolResult(bundle: unknown, structured = true): ToolResult {
  return {
    content: [{ type: "text", text: JSON.stringify(bundle) }],
    ...(structured ? { structuredContent: bundle } : {}),
  };
}
