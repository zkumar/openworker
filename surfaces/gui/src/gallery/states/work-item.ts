// A channel work item's `data` as the server stores it on the Inbox item and RunPanel renders it.
// Demo data only, after the payor pack's sample request (regagentic-fabric packs/payor_um).
import type { CardState } from "../types";

// fabric CONTRACTS.md §13 "The view document", verbatim (view v1.0.0, commit 5ec0600): the
// contract's worked example, not a harness invention.
export const payorDemoView = {
  view: "1.0.0",
  record: [
    { component: "header", title_field: "procedure_code", subtitle_field: "member_id" },
    { component: "field_group", label: "Clinical", fields: ["clinical_notes", "requested_units"] },
    { component: "gauge", label: "Units against per-authorization limit", value_field: "requested_units", max: 1 },
    { component: "key_value", fields: ["provider_npi", "member_id", "request_date", "requested_service_date"], demoted: true },
  ],
  checks: { component: "timeline", numbered: true },
  decision_labels: { approved: "Authorized", denied: "Not authorized", pended: "Pended for review" },
};

const steps = [
  ["requested", "eligibility", "Member eligible on the requested service date"],
  ["eligibility", "coverage", "Procedure covered under the member's plan"],
  ["coverage", "provider", "Provider in network"],
  ["provider", "duplicate", "No duplicate request on file"],
  ["duplicate", "quantity", "Units within the per-authorization limit"],
  ["quantity", "frequency", "Within the frequency limit"],
  ["frequency", "step_therapy", "Conservative treatment documented"],
  ["step_therapy", "criteria", "Clinical criteria met"],
  ["criteria", "approved", "Meets medical necessity; recommend approval"],
].map(([before, after, summary], i) => ({
  type: "transition",
  summary,
  state_before: before,
  state_after: after,
  sha256: (i + 1).toString(16).repeat(64),
  at: `2026-11-10T09:0${i}:00Z`,
}));

export const workItemStates: CardState[] = [
  {
    id: "payor-demo",
    title: "Payor prior auth · declared view",
    note: "The §13 worked example: header, Clinical group, units gauge against max 1, demoted key-value group, numbered timeline, decision labels.",
    payload: {
      channel: "email",
      agent: "payor.demo.prior_auth",
      decision: "approved",
      awaiting_signoff: true,
      running: false,
      fabric_run: "run-payor-demo",
      plan: {
        name: "payor-prior-auth",
        signoff: "part11_single",
        states: ["requested", "eligibility", "coverage", "provider", "duplicate", "quantity", "frequency", "step_therapy", "criteria", "approved", "denied", "pended"],
        gate_state: "approved",
      },
      record: {
        request_id: "PA-2026-001",
        member_id: "MEM001",
        procedure_code: "27447",
        provider_npi: "1497758544",
        request_date: "2026-01-20",
        requested_service_date: "2026-02-15",
        requested_units: 1,
        clinical_notes: "Severe right knee osteoarthritis. Failed 12 weeks of physical therapy, NSAIDs and corticosteroid injections. X-ray shows bone-on-bone contact.",
      },
      steps,
      envelopes: steps.length,
      view: payorDemoView,
    },
  },
];
