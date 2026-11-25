// The renderer app's work item: the answer bundle of a view-bound gateway tool, drawn through the
// shared core under the same RFC 0055 rules as the native RunPanel. The signature gate is state
// only; an input gate draws the shared gate form, whose submit is the view's one tool call
// (adr-view-calls-one-tool).
import { useState } from "react";

import {
  Checks, decisionOf, declaredLabel, GateForm, LABEL, RecordSection, SignedLine, signoffWording, toneOf, WholeView,
  type AnswerOutcome, type PendingInput, type Plan, type Signature, type Step, type ViewDoc,
} from "../workItem";
import type { Host, ToolResult } from "./host";

type Rec = Record<string, unknown>;

// the bundle's plan (fabric CONTRACTS.md §14): states are objects, not the sidecar's strings
type BundlePlan = Omit<Plan, "states"> & { states?: { name: string; terminal: boolean }[] };

// the answer bundle's read-path fields the renderer draws (fabric owns the names)
type WorkItem = {
  session_id: string;
  agent?: string;
  decision?: string;
  awaiting_signoff: boolean;
  awaiting_input: boolean;
  pending_input?: PendingInput;
  plan?: BundlePlan;
  signature?: Signature;
  record: Rec;
  steps: Step[];
  view?: unknown;
  app_url?: string;
};

function isObj(v: unknown): v is Rec {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

const str = (v: unknown) => (typeof v === "string" ? v : undefined);

// a §14 signature in the shared core's names
function signatureOf(sig: Rec): Signature {
  return { approver: str(sig.signer), at: str(sig.signed_at), signoff: str(sig.signoff_type) };
}

// a §14 v1.1.0 pending_input, when it names its fields
function pendingOf(v: unknown): PendingInput | undefined {
  return isObj(v) && Array.isArray(v.fields) ? (v as PendingInput) : undefined;
}

// The one ingestion point: the answer bundle's field names (work-item bundle v1.0.0 and v1.1.0,
// fabric CONTRACTS.md §14) map to what the renderer draws here and nowhere else. `envelopes` is
// the per-step list; `steps` is only its count.
function workItemOf(bundle: Rec): WorkItem {
  return {
    session_id: bundle.session_id as string,
    agent: str(bundle.agent_id),
    decision: str(bundle.decision),
    awaiting_signoff: bundle.awaiting_signoff === true,
    awaiting_input: bundle.awaiting_input === true,
    pending_input: pendingOf(bundle.pending_input),
    plan: isObj(bundle.plan) ? (bundle.plan as BundlePlan) : undefined,
    signature: isObj(bundle.signature) ? signatureOf(bundle.signature) : undefined,
    record: isObj(bundle.record) ? bundle.record : {},
    steps: Array.isArray(bundle.envelopes) ? (bundle.envelopes as Step[]) : [],
    view: bundle.view,
    app_url: str(bundle.app_url),
  };
}

// The answer tool's reply (CONTRACTS.md §14, regagent_answer_input, ok true) as the run's next
// stop, mapped here and nowhere else: another input gate, the signature gate, or the decision.
// The reply names the next gate's fields but not their types, so they draw undeclared. An
// idempotent reply (answers the gate already sealed) only closes the gate.
function nextStopOf(item: WorkItem, reply: Rec): WorkItem {
  const answered: WorkItem = { ...item, awaiting_input: false, pending_input: undefined };
  switch (reply.status) {
    case "awaiting_input": {
      const names = Array.isArray(reply.fields) ? reply.fields.filter((n): n is string => typeof n === "string") : [];
      return {
        ...answered,
        awaiting_input: true,
        pending_input: { from: str(reply.from_state), to: str(reply.to_state), fields: names.map((name) => ({ name, type: null })) },
      };
    }
    case "awaiting_signoff":
      return { ...answered, awaiting_signoff: true };
    case "complete":
      return { ...answered, awaiting_signoff: false, decision: str(reply.decision) };
    default:
      return answered;
  }
}

type Answer = { work: WorkItem } | { error: string[] } | null;

// a refusal names its error; an answer bundle names its work item's session
const isRefusal = (v: unknown): v is Rec => isObj(v) && v.ok === false;
const isBundle = (v: unknown): v is Rec => isObj(v) && typeof v.session_id === "string";

function parse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

// a tool result's body: an isError result is its text; otherwise structured content, else the
// text parsed as JSON
function bodyOf(result: ToolResult): { text: string; body: unknown } {
  const text = (result.content ?? []).filter((c) => c.type === "text").map((c) => c.text ?? "").join("");
  if (result.isError) return { text, body: null };
  return { text, body: isObj(result.structuredContent) ? result.structuredContent : parse(text) };
}

// What the answer is, in the fallback order of adr-text-answer-whole-contract: an isError answer
// is its text; otherwise structured content, else the text answer parsed as JSON; else nothing
// the renderer can draw.
function answerOf(result: ToolResult): Answer {
  const text = (result.content ?? []).filter((c) => c.type === "text").map((c) => c.text ?? "").join("");
  if (result.isError) return text ? { error: [text] } : null;
  const body = isRefusal(result.structuredContent) || isBundle(result.structuredContent)
    ? result.structuredContent
    : parse(text);
  if (isRefusal(body)) {
    const lines = [str(body.error), str(body.detail)].filter((s): s is string => !!s);
    return lines.length ? { error: lines } : null;
  }
  return isBundle(body) ? { work: workItemOf(body) } : null;
}

export function WorkItemView({ result, host }: { result: ToolResult | undefined; host: Host }) {
  // the run's next stop once the human answered this work item's gate, drawn in place of it
  const [after, setAfter] = useState<{ of: ToolResult; item: WorkItem } | null>(null);
  if (!result) return null;
  const answer = answerOf(result);
  if (!answer) {
    return (
      <p className="px-4 py-3 text-[13px] text-ink">
        This work item can't be drawn here. The text answer above is complete.
      </p>
    );
  }
  // an error renders as text only: no decision, no tone, no declared view
  if ("error" in answer) {
    return (
      <div className="px-4 py-3 text-[13px] text-ink" data-testid="work-item-error">
        {answer.error.map((line, i) => <p key={i} className={i ? "mt-0.5 text-muted" : "font-semibold"}>{line}</p>)}
      </div>
    );
  }
  const item = after?.of === result ? after.item : answer.work;

  // The view's one tool call (adr-view-calls-one-tool). ok true, idempotent or not, flips the gate
  // to the run's next stop; anything else is a refusal the form shows. Nothing here retries.
  async function answerGate(answers: Record<string, unknown>): Promise<AnswerOutcome> {
    let reply: ToolResult;
    try {
      reply = await host.answerInput(item.session_id, answers);
    } catch (e) {
      return { ok: false, detail: e instanceof Error ? e.message : String(e) };
    }
    const { text, body } = bodyOf(reply);
    if (isObj(body) && body.ok === true) {
      setAfter({ of: result!, item: nextStopOf(item, body) });
      return { ok: true };
    }
    const refusal = isObj(body) ? str(body.detail) ?? str(body.error) : undefined;
    return { ok: false, detail: refusal ?? text };
  }

  return (
    <WholeView
      view={item.view}
      record={item.record}
      render={(view) => <Panel item={item} view={view} host={host} onAnswer={answerGate} />}
    />
  );
}

function Panel({ item, view, host, onAnswer }: {
  item: WorkItem;
  view: ViewDoc | null;
  host: Host;
  onAnswer: (answers: Record<string, unknown>) => Promise<AnswerOutcome>;
}) {
  const decision = decisionOf(item);
  const tone = toneOf(decision);
  const label = declaredLabel(view, decision);
  const reason = item.steps.length ? item.steps[item.steps.length - 1]?.summary : "";

  return (
    <section className="rounded-xl border border-line bg-paper" data-testid="work-item-view">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-[12px] text-faint">handled by</span>
        <span className="font-mono text-[12px] text-ink">{item.agent}</span>
        <span className="flex-1" />
        {decision && (
          <span className={"text-[13px] font-semibold " + tone}>{label ?? LABEL[decision] ?? decision}</span>
        )}
      </header>

      {/* the answer's decision only; the renderer never shows a decision the answer does not carry */}
      {decision && (
        <div className="px-4 py-3">
          <div className="text-[14px] font-semibold text-ink">
            Decision: <span className={tone}>{label ?? decision}</span>
          </div>
          {reason && <div className="mt-0.5 text-[13px] text-muted">{reason}</div>}
        </div>
      )}

      <RecordSection view={view} record={item.record} />
      <Checks view={view} steps={item.steps} />

      {/* the human gate: an input gate's form, or the signature gate as state only (signing stays
          in the GUI and Studio gate screens) */}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
        {item.signature ? (
          <SignedLine signature={item.signature} steps={item.steps.length} />
        ) : item.awaiting_input && item.pending_input ? (
          <GateForm
            key={`${item.pending_input.from}>${item.pending_input.to}`}
            pending={item.pending_input}
            onSubmit={onAnswer}
          />
        ) : item.awaiting_signoff ? (
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-medium text-ink">Awaiting signature</div>
            <div className="text-[12px] text-muted">This decision needs {signoffWording(item.plan)}.</div>
          </div>
        ) : null}
      </footer>

      {/* the only outbound action (adr-read-only-renderer-v1) */}
      {item.app_url && (
        <div className="border-t border-line px-4 py-3">
          <button type="button" className="text-[13px] text-accent hover:underline" onClick={() => host.openLink(item.app_url!)}>
            Open in openworker
          </button>
        </div>
      )}
    </section>
  );
}
