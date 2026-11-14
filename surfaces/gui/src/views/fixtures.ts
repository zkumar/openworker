// Answer bundles for the renderer app's tests, in the shape of fabric's work-item bundle v1.0.0
// (CONTRACTS.md §14): the payor demo work item from the gallery (synthetic, OW-F-015 ticket 05)
// as a bundle, the same item with no view, and with an invalid view.
import { payorDemoView, workItemStates } from "../gallery/states/work-item";
import type { ToolResult } from "./host";

const demo = workItemStates.find((s) => s.id === "payor-demo")!.payload as Record<string, unknown>;
const demoPlan = demo.plan as { states: string[] } & Record<string, unknown>;
const demoSteps = demo.steps as unknown[];

// the demo graph's outcome states
const TERMINAL = new Set(["approved", "denied", "pended"]);

export const payorBundle = {
  session_id: "run-payor-demo",
  agent_id: demo.agent,
  decision: demo.decision,
  final_state: "approved",
  awaiting_signoff: true,
  envelopes: demoSteps,
  verified: true,
  plan: { ...demoPlan, states: demoPlan.states.map((name) => ({ name, terminal: TERMINAL.has(name) })) },
  record: demo.record,
  signature: null,
  steps: demoSteps.length,
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
