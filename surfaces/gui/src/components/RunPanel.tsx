import { useState } from "react";

// One channel work item, written for the person who has to ACT on it.
// Plain language first; hashes, the declared graph and the JSON payload are demoted to
// "Technical details" so a QA/complaint reviewer never has to read a wire format.

type Plan = { name?: string; signoff?: string; states?: string[]; gate_state?: string };

export interface RunData {
  channel?: string;
  agent?: string;
  decision?: string;
  envelopes?: number;
  awaiting_signoff?: boolean;
  running?: boolean;
  error?: string;
  retrying?: boolean;
  plan?: Plan;
  record?: Record<string, unknown>;
  fabric_run?: string;
  receipt?: Record<string, unknown>;
  signature?: {
    approver?: string; at?: string; state_before?: string; state_after?: string;
    signoff?: string; sha256?: string;
  };
  steps?: {
    type?: string; summary?: string; state_before?: string; state_after?: string;
    sha256?: string; at?: string;
  }[];
}

const HIDDEN = new Set(["request_id", "capa_id", "slr_id"]);
const TONE: Record<string, string> = {
  approved: "text-ok", closed: "text-ok", denied: "text-danger",
  escalated: "text-warn", pended: "text-warn", revise: "text-warn",
};

// "part11_single" is a CFR term; say what it means.
const SIGN_LABEL: Record<string, string> = {
  part11_single: "electronic signature (21 CFR Part 11)",
};

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[11px] uppercase tracking-wide text-faint">{label.replace(/_/g, " ")}</div>
      <div className="truncate text-[13px] text-ink" title={value}>{value}</div>
    </div>
  );
}

export function RunPanel({
  data, pending, onDecide,
}: {
  data: RunData;
  pending: boolean;
  onDecide: (decision: "once" | "deny") => void;
}) {
  const [all, setAll] = useState(true);
  const fields = Object.entries(data.record ?? {}).filter(([k]) => !HIDDEN.has(k));
  const shown = all ? fields : fields.slice(0, 6);
  const steps = data.steps ?? [];
  const decision = data.signature?.state_after ?? data.decision;
  const tone = TONE[String(decision)] ?? "text-ink";
  // the last executed step usually explains WHY, in the pack's own words
  const reason = steps.length ? steps[steps.length - 1]?.summary : "";
  const signLabel = SIGN_LABEL[String(data.plan?.signoff)] ?? (data.plan?.signoff || "sign-off");

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
          <span className={"text-[13px] font-semibold " + tone}>{decision}</span>
        )}
      </header>

      {/* the answer, in one sentence a non-technical reviewer can act on */}
      {!data.running && (
        <div className={"px-4 py-3 " + (data.error ? "text-danger" : "")}>
          {data.error ? (
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
                Decision: <span className={tone}>{decision}</span>
              </div>
              {reason && <div className="mt-0.5 text-[13px] text-muted">{reason}</div>}
            </>
          )}
        </div>
      )}

      {/* who it is about */}
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

      {/* what was checked, in the pack's words */}
      {steps.length > 0 && (
        <div className="border-t border-line px-4 py-3">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">
            What was checked <span className="normal-case text-faint">· {steps.length} steps</span>
          </h3>
          <ol className="space-y-1">
            {steps.map((s, i) => (
              <li key={`${s.sha256}-${i}`} className="flex items-baseline gap-2 text-[13px]">
                <span className="w-4 shrink-0 text-right text-faint">{i + 1}</span>
                <span className="min-w-0 text-muted">{s.summary ?? `${s.state_before} → ${s.state_after}`}</span>
              </li>
            ))}
          </ol>
        </div>
      )}

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
          <div className="text-[13px] text-muted">
            <span className="font-medium text-ok">✓ Signed</span> by{" "}
            <strong className="text-ink">{data.signature.approver}</strong>
            {data.signature.at ? ` on ${data.signature.at}` : ""} · {steps.length} steps sealed
          </div>
        ) : null}
      </footer>

      {/* everything a technical audience needs, folded away */}
      <details className="border-t border-line px-4 py-3" open>
        <summary className="cursor-pointer text-[12px] text-muted">Technical details</summary>
        <div className="mt-2 space-y-3 text-[12px]">
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
