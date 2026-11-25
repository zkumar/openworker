// Answer bundles for the renderer app's tests, in the shape of fabric's work-item bundle v1.0.0
// and v1.1.0 (CONTRACTS.md §14): the payor demo work item from the gallery (synthetic, OW-F-015
// ticket 05) as a bundle, the same item with no view, with an invalid view, and parked at an
// input gate.
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

// the same work item parked at an input gate (bundle v1.1.0, RFC 0056): no decision yet, the
// gate's fields with their declared types as the pending-input read serves them
export const parkedBundle = {
  ...payorBundle,
  bundle_version: "1.1.0",
  decision: null,
  final_state: null,
  awaiting_signoff: false,
  awaiting_input: true,
  pending_input: {
    from: "step_therapy",
    to: "criteria",
    fields: [{ name: "prior_trial_drug", type: "str" }, { name: "trial_weeks", type: "int" }],
  },
};

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
