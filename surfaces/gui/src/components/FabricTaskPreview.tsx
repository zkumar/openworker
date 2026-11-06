import { useEffect, useState } from "react";

// The fabric's governed agents are called over MCP (`regagent_run_agent`), so the harness
// would show the raw args JSON. This renders the SAME four-part record the fabric's own
// approval uses: the agent, the record it will run on, and the process plan with its
// human sign-off gate — so the approver judges the work, not a JSON blob.
const BASE = (globalThis as { __FABRIC_HTTP__?: string }).__FABRIC_HTTP__ ?? "http://127.0.0.1:8767";

type Plan = {
  name: string;
  states: { name: string; terminal: boolean }[];
  transitions: { to: string; actor: string; signoff?: string }[];
};

const HIDDEN = new Set(["capa_id", "request_id", "slr_id"]);

export function FabricTaskPreview({ args }: { args: unknown }) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const record = (args as { agent_id?: string; inputs?: Record<string, unknown> }) ?? {};
  const agentId = String(record.agent_id ?? "");
  const inputs = record.inputs ?? {};
  const fields = Object.entries(inputs).filter(([key]) => !HIDDEN.has(key));

  useEffect(() => {
    if (!agentId) return;
    fetch(`${BASE}/_agent-native/context?agent=${encodeURIComponent(agentId)}`)
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => body && setPlan(body.plan as Plan))
      .catch(() => {});
  }, [agentId]);

  const signoff = plan?.transitions.find((transition) => transition.signoff);

  return (
    <div className="mt-2 space-y-3 rounded-lg border border-line bg-paper p-3 text-[13px]">
      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">Agent</div>
        <div className="font-medium text-ink">{agentId || "(unknown agent)"}</div>
      </div>

      <div>
        <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
          Record it will run on
        </div>
        <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-0.5">
          {fields.slice(0, 8).map(([key, value]) => (
            <div key={key} className="contents">
              <dt className="truncate text-muted">{key.replace(/_/g, " ")}</dt>
              <dd className="min-w-0 truncate text-ink">{String(value)}</dd>
            </div>
          ))}
        </dl>
        {fields.length > 8 && (
          <div className="mt-1 text-[12px] text-muted">+{fields.length - 8} more fields</div>
        )}
      </div>

      {plan && (
        <div>
          <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
            Plan · {plan.name}
          </div>
          <ol className="flex flex-wrap items-center gap-x-1.5 gap-y-1">
            {plan.states
              .filter((state) => !state.terminal || state.name === signoff?.to)
              .map((state, index, list) => (
                <li key={state.name} className="flex items-center gap-1.5">
                  <span
                    className={
                      state.name === signoff?.to ? "font-medium text-ink" : "text-muted"
                    }
                  >
                    {state.name.replace(/_/g, " ")}
                  </span>
                  {state.name === signoff?.to && (
                    <span className="rounded bg-muted px-1 text-[10px] uppercase tracking-wide">
                      signed: {signoff?.actor}
                    </span>
                  )}
                  {index < list.length - 1 && <span className="text-muted">→</span>}
                </li>
              ))}
          </ol>
        </div>
      )}
    </div>
  );
}
