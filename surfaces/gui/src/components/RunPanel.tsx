import { useState } from "react";

// One channel work item, rendered as the professional surface for the whole run:
// what arrived → what was decided by whom → what is waiting on a human → what was sealed.
// Built from the inbox item's data, so it survives a reload and needs no transcript parsing.

type Plan = { name?: string; signoff?: string; states?: string[]; gate_state?: string };

export interface RunData {
  channel?: string;
  agent?: string;
  decision?: string;
  envelopes?: number;
  awaiting_signoff?: boolean;
  plan?: Plan;
  receipt?: Record<string, unknown>;
  steps?: {
    type?: string; summary?: string; state_before?: string; state_after?: string;
    sha256?: string; at?: string;
  }[];
  record?: Record<string, unknown>;
  fabric_run?: string;
  running?: boolean;
  error?: string;
  signature?: {
    approver?: string;
    at?: string;
    state_before?: string;
    state_after?: string;
    signoff?: string;
    sha256?: string;
  };
}

const HIDDEN = new Set(["request_id", "capa_id", "slr_id"]);
const TONE: Record<string, string> = {
  approved: "text-ok",
  closed: "text-ok",
  denied: "text-danger",
  escalated: "text-warn",
  pended: "text-warn",
  revise: "text-warn",
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
  data,
  pending,
  onDecide,
}: {
  data: RunData;
  pending: boolean;
  onDecide: (decision: "once" | "deny") => void;
}) {
  const [all, setAll] = useState(false);
  const fields = Object.entries(data.record ?? {}).filter(([k]) => !HIDDEN.has(k));
  const shown = all ? fields : fields.slice(0, 6);
  const decision = data.signature?.state_after ?? data.decision;
  const tone = TONE[String(decision)] ?? "text-ink";
  const states = data.plan?.states ?? [];
  const gate = data.plan?.gate_state;

  return (
    <section className="mb-3 rounded-xl border border-line bg-paper" data-testid="run-panel">
      {/* what arrived, and who owns it */}
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="rounded-md bg-panel px-1.5 py-0.5 text-[11px] font-medium text-muted">
          {data.channel ?? "channel"}
        </span>
        <span className="font-mono text-[12px] text-ink">{data.agent}</span>
        <span className="text-[12px] text-faint">chosen from its capability card</span>
        <span className="flex-1" />
        {data.running ? (
          <span className="flex items-center gap-1.5 text-[13px] font-medium text-accent">
            <span className="h-2 w-2 animate-pulse rounded-full bg-accent" aria-hidden />
            running…
          </span>
        ) : (
          <span className={"text-[13px] font-semibold " + tone}>{decision}</span>
        )}
      </header>

      {/* the record */}
      <div className="px-4 py-3">
        <div className="mb-2 flex items-center justify-between">
          <h3 className="text-[12px] font-semibold uppercase tracking-wide text-muted">
            Work item <span className="normal-case text-faint">· {fields.length} fields</span>
          </h3>
          {fields.length > 6 && (
            <button className="text-[12px] text-accent hover:underline" onClick={() => setAll((v) => !v)}>
              {all ? "Show fewer fields" : `Show all ${fields.length} fields`}
            </button>
          )}
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3">
          {shown.map(([k, v]) => (
            <Field key={k} label={k} value={String(v)} />
          ))}
        </div>
      </div>

      {/* the process it runs, with the human gate marked */}
      {states.length > 0 && (
        <div className="border-t border-line px-4 py-3">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">
            Declared process · {data.plan?.name}
          </h3>
          <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px]">
            {states.map((s, i) => (
              <li key={s} className="flex items-center gap-1.5">
                <span
                  className={
                    s === gate
                      ? "rounded bg-accentSoft px-1.5 py-0.5 font-medium text-accent"
                      : "text-muted"
                  }
                  title={s === gate ? `human signature required (${data.plan?.signoff})` : undefined}
                >
                  {s.replace(/_/g, " ")}
                </span>
                {i < states.length - 1 && <span className="text-faint">→</span>}
              </li>
            ))}
          </ol>
        </div>
      )}

      {/* what actually happened between arrival and this point */}
      {(data.steps?.length ?? 0) > 0 && (
        <div className="border-t border-line px-4 py-3">
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-muted">
            Executed · {data.steps?.length} sealed steps
          </h3>
          <ol className="space-y-1.5">
            {data.steps?.map((s, i) => (
              <li key={`${s.sha256}-${i}`} className="flex items-baseline gap-2 text-[12px]">
                <span className="w-4 shrink-0 text-right text-faint">{i + 1}</span>
                <span className="shrink-0 text-ink">
                  {s.state_before ?? "?"} <span className="text-faint">→</span> {s.state_after ?? "?"}
                </span>
                <span className="min-w-0 truncate text-muted" title={s.summary}>{s.summary ?? s.type}</span>
                <span className="flex-1" />
                {s.sha256 && (
                  <span className="shrink-0 font-mono text-[11px] text-faint">{s.sha256.slice(0, 8)}</span>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}

      {data.error && (
        <div className="border-t border-line px-4 py-3 text-[13px] text-danger">
          <strong>Run failed.</strong> {data.error}
        </div>
      )}

      {/* what leaves the system: the outbound JSON contract */}
      {data.receipt && (
        <details className="border-t border-line px-4 py-3">
          <summary className="cursor-pointer text-[12px] font-semibold uppercase tracking-wide text-muted">
            Output · JSON
          </summary>
          <pre className="mt-2 max-h-56 overflow-auto rounded-md bg-panel p-2 text-[11px] leading-snug text-ink">
{JSON.stringify(data.receipt, null, 2)}
          </pre>
        </details>
      )}

      {/* the gate, or the signed receipt */}
      <footer className="flex flex-wrap items-center gap-3 border-t border-line px-4 py-3">
        {data.running ? (
          <div className="text-[12px] text-muted">
            The governed run is executing — steps appear as they seal.
          </div>
        ) : pending ? (
          <>
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-ink">
                Human signature required to seal this decision
              </div>
              <div className="text-[12px] text-muted">
                {data.plan?.signoff ?? "sign-off"} · {data.envelopes ?? 0} steps already sealed ·
                irreversible once signed
              </div>
            </div>
            <button className="btn approval-primary" onClick={() => onDecide("once")}>
              Sign &amp; seal
            </button>
            <button className="btn" onClick={() => onDecide("deny")}>
              Decline
            </button>
          </>
        ) : (
          <div className="flex flex-wrap items-center gap-2 text-[12px] text-muted">
            <span className="font-medium text-ok">✓ Sealed</span>
            <span>
              signed by <strong className="text-ink">{data.signature?.approver ?? "a human approver"}</strong>
              {data.signature?.at ? ` at ${data.signature.at}` : ""}
            </span>
            {data.signature?.sha256 && (
              <span className="font-mono text-faint">evidence {data.signature.sha256.slice(0, 12)}…</span>
            )}
            <span className="text-faint">· {data.envelopes ?? 0} steps sealed</span>
          </div>
        )}
      </footer>
    </section>
  );
}
