// The shared work-item rendering core: the read path the native RunPanel and the renderer app
// both draw from, so the two surfaces apply one set of RFC 0055 rules. Only read-path rendering
// lives here; the pending gate controls and the live running and retrying states stay with the
// surface that owns them.

import { Component, useState, type ReactNode } from "react";

import { checkView, DeclaredRecord, HIDDEN, type ViewDoc } from "./DeclaredView";

type Rec = Record<string, unknown>;

export type Plan = { name?: string; signoff?: string; states?: string[]; gate_state?: string };

export type Signature = {
  approver?: string; at?: string; state_before?: string; state_after?: string;
  signoff?: string; sha256?: string;
};

export type Step = {
  type?: string; summary?: string; state_before?: string; state_after?: string;
  sha256?: string; at?: string;
};

// never show a raw enum to a person
export const LABEL: Record<string, string> = {
  not_found: "not found",
  awaiting_signature: "awaiting signature",
};
const TONE: Record<string, string> = {
  approved: "text-ok", closed: "text-ok", denied: "text-danger",
  escalated: "text-warn", pended: "text-warn", revise: "text-warn",
  not_found: "text-warn",
};

// "part11_single" is a CFR term; say what it means.
const SIGN_LABEL: Record<string, string> = {
  part11_single: "electronic signature (21 CFR Part 11)",
};

// the decision a work item shows: the signed state when there is one, else the run's decision
export function decisionOf(data: { decision?: string; signature?: Signature }): string | undefined {
  return data.signature?.state_after ?? data.decision;
}

// the decision tone is harness-reserved and keyed to the underlying state; unknown states are neutral
export function toneOf(decision: string | undefined): string {
  return TONE[String(decision)] ?? "text-ink";
}

// decision_labels re-word the decision only; the tone stays keyed to the underlying state
export function declaredLabel(view: ViewDoc | null, decision: string | undefined): string | undefined {
  const labels = view?.decision_labels;
  return labels && Object.prototype.hasOwnProperty.call(labels, String(decision)) ? labels[String(decision)] : undefined;
}

// the gate's sign-off wording, from the plan's signoff kind
export function signoffWording(plan: Plan | undefined): string {
  return SIGN_LABEL[String(plan?.signoff)] ?? (plan?.signoff || "sign-off");
}

// A render-time exception inside the declared view falls the whole panel back to the generic
// layout; a new stored view gets a fresh attempt.
class ViewBoundary extends Component<
  { view: unknown; fallback: ReactNode; children: ReactNode },
  { failed: boolean; view: unknown }
> {
  state = { failed: false, view: this.props.view };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  static getDerivedStateFromProps(props: { view: unknown }, state: { view: unknown }) {
    return props.view !== state.view ? { failed: false, view: props.view } : null;
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

// The declared view applies whole or not at all: a structural failure, a mis-shaped binding or a
// render-time exception renders the generic layout, with the reason passed on as notRendered.
export function WholeView({ view, record, render }: {
  view: unknown;
  record: Rec;
  render: (view: ViewDoc | null, notRendered: string | null) => ReactNode;
}) {
  if (view == null) return <>{render(null, null)}</>;
  const checked = checkView(view, record);
  if ("reason" in checked) return <>{render(null, checked.reason)}</>;
  return (
    <ViewBoundary view={view} fallback={render(null, "render-time error")}>
      {render(checked.view, null)}
    </ViewBoundary>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-faint">{label.replace(/_/g, " ")}</div>
      <div className="truncate text-[13px] text-ink" title={value}>{value}</div>
    </div>
  );
}

// the generic record grid: every field but the hygiene ids, foldable to six
function GenericRecord({ record }: { record: Rec }) {
  const [all, setAll] = useState(true);
  const fields = Object.entries(record).filter(([k]) => !HIDDEN.has(k));
  const shown = all ? fields : fields.slice(0, 6);
  return (
    <div className="border-t border-line px-4 py-3">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted">
          Request <span className="normal-case text-faint">· {shown.length} of {fields.length} fields shown</span>
        </h3>
        {fields.length > 6 && (
          <button className="text-[12px] text-accent hover:underline" onClick={() => setAll((v) => !v)}>
            {all ? "Show fewer" : `Show all ${fields.length}`}
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
        {shown.map(([k, v]) => <Field key={k} label={k} value={String(v)} />)}
      </div>
    </div>
  );
}

// who the work item is about: the pack's declared layout, or the generic grid
export function RecordSection({ view, record }: { view: ViewDoc | null; record: Rec }) {
  return view?.record ? <DeclaredRecord view={view} record={record} /> : <GenericRecord record={record} />;
}

// what was checked, in the pack's words; checks restyles the block, step text stays the
// verbatim chain summaries
export function Checks({ view, steps }: { view: ViewDoc | null; steps: Step[] }) {
  if (steps.length === 0) return null;
  const numbered = view?.checks?.numbered !== false;
  return (
    <div className="border-t border-line px-4 py-3">
      <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">
        What was checked <span className="normal-case text-faint">· {steps.length} steps</span>
      </h3>
      {view?.checks?.component === "timeline" ? (
        <ol className="ml-1.5 space-y-2 border-l border-line" data-testid="view-timeline">
          {steps.map((s, i) => (
            <li key={`${s.sha256}-${i}`} className="relative flex items-baseline gap-2 pl-4 text-ui">
              <span className="absolute -left-1 top-1.5 h-2 w-2 rounded-full bg-lineStrong" aria-hidden />
              {numbered && <span className="shrink-0 text-faint">{i + 1}</span>}
              <span className="min-w-0 text-muted">{s.summary ?? `${s.state_before} → ${s.state_after}`}</span>
            </li>
          ))}
        </ol>
      ) : (
        <ol className="space-y-1">
          {steps.map((s, i) => (
            <li key={`${s.sha256}-${i}`} className="flex items-baseline gap-2 text-[13px]">
              {numbered && <span className="w-4 shrink-0 text-right text-faint">{i + 1}</span>}
              <span className="min-w-0 text-muted">{s.summary ?? `${s.state_before} → ${s.state_after}`}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

// the signature that closed the gate
export function SignedLine({ signature, steps }: { signature: Signature; steps: number }) {
  return (
    <div className="text-[13px] text-muted">
      <span className="font-medium text-ok">✓ Signed</span> by{" "}
      <strong className="text-ink">{signature.approver}</strong>
      {signature.at ? ` on ${signature.at}` : ""} · {steps} steps sealed
    </div>
  );
}
