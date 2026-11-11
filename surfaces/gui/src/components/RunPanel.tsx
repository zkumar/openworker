import {
  Checks, decisionOf, declaredLabel, LABEL, RecordSection, SignedLine, signoffWording, toneOf, WholeView,
  type Plan, type Signature, type Step, type ViewDoc,
} from "../workItem";

// One channel work item, written for the person who has to ACT on it.
// Plain language first; hashes, the declared graph and the JSON payload are demoted to
// "Technical details" so a QA/complaint reviewer never has to read a wire format.

export interface RunData {
  channel?: string;
  agent?: string;
  decision?: string;
  envelopes?: number;
  awaiting_signoff?: boolean;
  running?: boolean;
  error?: string;
  retrying?: boolean;
  not_found?: boolean;
  reason?: string | null;
  plan?: Plan;
  record?: Record<string, unknown>;
  fabric_run?: string;
  receipt?: Record<string, unknown>;
  signature?: Signature;
  steps?: Step[];
  // the declared view document stored on the work item at dispatch (view contract v1.0.0)
  view?: unknown;
}

type PanelProps = {
  data: RunData;
  pending: boolean;
  onDecide: (decision: "once" | "deny") => void;
};

// The declared view applies whole or not at all (the shared core's WholeView); the reason it
// was not rendered goes to Technical details.
export function RunPanel(props: PanelProps) {
  return (
    <WholeView
      view={props.data.view}
      record={props.data.record ?? {}}
      render={(view, notRendered) => <Panel {...props} view={view} notRendered={notRendered} />}
    />
  );
}

function Panel({
  data, pending, onDecide, view, notRendered,
}: PanelProps & { view: ViewDoc | null; notRendered: string | null }) {
  const steps = data.steps ?? [];
  const decision = decisionOf(data);
  const tone = toneOf(decision);
  const label = declaredLabel(view, decision);
  // the last executed step usually explains WHY, in the pack's own words
  const reason = steps.length ? steps[steps.length - 1]?.summary : "";
  const signLabel = signoffWording(data.plan);

  return (
    <section className="mb-3 rounded-xl border border-line bg-paper" data-testid="run-panel">
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="rounded-md bg-panel px-1.5 py-0.5 text-[11px] font-medium text-muted">
          {data.channel ?? "channel"}
        </span>
        <span className="text-[12px] text-faint">handled by</span>
        <span className="font-mono text-[12px] text-ink">{data.agent}</span>
        <span className="flex-1" />
        {data.running ? (
          <span className="flex items-center gap-1.5 text-[13px] font-medium text-accent">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" aria-hidden />
            in progress…
          </span>
        ) : (
          <span className={"text-[13px] font-semibold " + tone}>
            {label ?? LABEL[String(decision)] ?? decision}
          </span>
        )}
      </header>

      {/* the answer, in one sentence a non-technical reviewer can act on */}
      {!data.running && (
        <div className={"px-4 py-3 " + (data.error ? "text-danger" : "")}>
          {data.not_found ? (
            <>
              <div className="text-[14px] font-semibold text-ink">
                Decision: <span className="text-warn">{LABEL.not_found}</span>
              </div>
              <div className="mt-0.5 text-[13px] text-muted">
                This request is not in the record system, so it was rejected. Nothing needs to be
                signed.
              </div>
            </>
          ) : data.error ? (
            <>
              <div className="text-[14px] font-semibold">
                {data.retrying === false ? "This request was rejected" : "This request could not run"}
              </div>
              <div className="mt-0.5 text-[13px] text-muted">{data.error}</div>
              {data.retrying !== false && (
                <div className="mt-1 text-[12px] text-faint">Retrying automatically.</div>
              )}
            </>
          ) : (
            <>
              <div className="text-[14px] font-semibold text-ink">
                Decision: <span className={tone}>{label ?? decision}</span>
              </div>
              {reason && <div className="mt-0.5 text-[13px] text-muted">{reason}</div>}
            </>
          )}
        </div>
      )}

      {/* who it is about: the pack's declared layout, or the generic grid */}
      <RecordSection view={view} record={data.record ?? {}} />

      {/* what was checked, in the pack's words */}
      <Checks view={view} steps={steps} />

      {/* the human gate, or the signature that closed it */}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
        {pending ? (
          <>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-ink">Waiting for your signature</div>
              <div className="text-[12px] text-muted">
                This decision needs {signLabel}. Signing is final.
              </div>
            </div>
            <button className="btn approval-primary" onClick={() => onDecide("once")}>Sign &amp; seal</button>
            <button className="btn" onClick={() => onDecide("deny")}>Decline</button>
          </>
        ) : data.signature ? (
          <SignedLine signature={data.signature} steps={steps.length} />
        ) : null}
      </footer>

      {/* everything a technical audience needs, folded away */}
      <details className="border-t border-line px-4 py-3" open>
        <summary className="cursor-pointer text-[12px] text-muted">Technical details</summary>
        <div className="mt-2 space-y-3 text-[12px]">
          {notRendered && <div className="text-muted">Declared view not rendered: {notRendered}</div>}
          {steps.length > 0 && (
            <div>
              <div className="mb-1 font-semibold uppercase tracking-wide text-faint">Sealed steps</div>
              <ol className="space-y-0.5 font-mono text-[11px] text-muted">
                {steps.map((s, i) => (
                  <li key={`h-${i}`}>
                    {i + 1}. {s.state_before} → {s.state_after}
                    <span className="text-faint"> · {(s.sha256 ?? "").slice(0, 12)}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
          {data.plan?.states?.length ? (
            <div>
              <div className="mb-1 font-semibold uppercase tracking-wide text-faint">Declared process · {data.plan.name}</div>
              <div className="font-mono text-[11px] text-muted">{data.plan.states.join(" → ")}</div>
            </div>
          ) : null}
          {data.receipt ? (
            <div>
              <div className="mb-1 font-semibold uppercase tracking-wide text-faint">Output (JSON)</div>
              <pre className="max-h-56 overflow-auto rounded-md bg-panel p-2 text-[11px] leading-snug text-ink">
{JSON.stringify(data.receipt, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>
      </details>
    </section>
  );
}
