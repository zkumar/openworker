// The renderer app's work item: the answer bundle of a view-bound gateway tool, drawn through the
// shared core under the same RFC 0055 rules as the native RunPanel. Read-only
// (adr-read-only-renderer-v1): the gate footer shows state, never controls.
import {
  Checks, decisionOf, declaredLabel, LABEL, RecordSection, SignedLine, signoffWording, toneOf, WholeView,
  type Plan, type Signature, type Step, type ViewDoc,
} from "../workItem";
import type { Host, ToolResult } from "./host";

type Rec = Record<string, unknown>;

// the answer bundle's read-path fields the renderer draws (fabric owns the names)
type WorkItem = {
  agent?: string;
  decision?: string;
  awaiting_signoff: boolean;
  plan?: Plan;
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

// The one ingestion point: the answer bundle's field names map to what the renderer draws here
// and nowhere else.
function workItemOf(bundle: Rec): WorkItem {
  return {
    agent: str(bundle.agent_id),
    decision: str(bundle.decision),
    awaiting_signoff: bundle.awaiting_signoff === true,
    plan: isObj(bundle.plan) ? (bundle.plan as Plan) : undefined,
    signature: isObj(bundle.signature) ? (bundle.signature as Signature) : undefined,
    record: isObj(bundle.record) ? bundle.record : {},
    steps: Array.isArray(bundle.steps) ? (bundle.steps as Step[]) : [],
    view: bundle.view,
    app_url: str(bundle.app_url),
  };
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
  const item = answer.work;
  return (
    <WholeView view={item.view} record={item.record} render={(view) => <Panel item={item} view={view} host={host} />} />
  );
}

function Panel({ item, view, host }: { item: WorkItem; view: ViewDoc | null; host: Host }) {
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

      {/* the human gate as state only: signing stays in the GUI and Studio gate screens */}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
        {item.signature ? (
          <SignedLine signature={item.signature} steps={item.steps.length} />
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
