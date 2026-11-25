// The input gate form both surfaces draw (OW-F-018): the native RunPanel footer and the renderer
// app. It binds to the bundle's pending_input alone (adr-gate-form-from-pending-input); only the
// submit wiring differs per surface. Every field is required client-side, but the server stays the
// authority: its refusal is shown under "Not accepted" with the values kept, and never retried.

import { useId, useState, type FormEvent } from "react";

// fabric CONTRACTS.md §14 v1.1.0 pending_input; the type is the card input_contract vocabulary,
// null when the transition declared none
export type PendingField = { name: string; type?: string | null };
export type PendingInput = { from?: string; to?: string; fields: PendingField[] };

export type AnswerOutcome = { ok: true } | { ok: false; detail: string };

type Values = Record<string, string | boolean>;

// one value as its declared type, or the reason it cannot be submitted
function parsed(type: PendingField["type"], raw: string | boolean): { value: unknown } | { error: string } {
  if (type === "bool") return { value: raw === true };
  const text = String(raw ?? "");
  if (text.trim() === "") return { error: "Required" };
  if (type === "int" || type === "float") {
    const n = Number(text);
    if (!Number.isFinite(n)) return { error: "Must be a number" };
    if (type === "int" && !Number.isInteger(n)) return { error: "Must be a whole number" };
    return { value: n };
  }
  if (type === "list" || type === "dict") {
    let value: unknown;
    try {
      value = JSON.parse(text);
    } catch {
      return { error: "Not valid JSON" };
    }
    if (type === "list" && !Array.isArray(value)) return { error: "Must be a JSON list" };
    if (type === "dict" && (value === null || typeof value !== "object" || Array.isArray(value))) {
      return { error: "Must be a JSON object" };
    }
    return { value };
  }
  // str and an undeclared type go as the raw string
  return { value: text };
}

// a one-row textarea that grows with what is typed
function grow(el: HTMLTextAreaElement) {
  el.style.height = "auto";
  el.style.height = `${el.scrollHeight}px`;
}

export function GateForm({
  pending, onSubmit,
}: {
  pending: PendingInput;
  onSubmit: (answers: Record<string, unknown>) => Promise<AnswerOutcome>;
}) {
  const id = useId();
  const [values, setValues] = useState<Values>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [refusal, setRefusal] = useState<string | null>(null);
  const [inFlight, setInFlight] = useState(false);

  const set = (name: string, value: string | boolean) => setValues((v) => ({ ...v, [name]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const answers: Record<string, unknown> = {};
    const problems: Record<string, string> = {};
    for (const f of pending.fields) {
      const r = parsed(f.type, values[f.name] ?? (f.type === "bool" ? false : ""));
      if ("error" in r) problems[f.name] = r.error;
      else answers[f.name] = r.value;
    }
    setErrors(problems);
    if (Object.keys(problems).length) return;
    setRefusal(null);
    setInFlight(true);
    try {
      const outcome = await onSubmit(answers);
      if (!outcome.ok) setRefusal(outcome.detail);
    } finally {
      setInFlight(false);
    }
  };

  return (
    <form className="min-w-0 flex-1" onSubmit={(e) => void submit(e)} noValidate data-testid="gate-form">
      <div className="text-[13px] font-medium text-ink">Waiting for your input</div>
      <div className="text-[12px] text-muted">This run needs these answers before it continues.</div>
      {refusal !== null && (
        <div className="mt-2 rounded-md border border-danger px-2 py-1.5 text-[12px]" role="alert">
          <div className="font-semibold text-danger">Not accepted</div>
          <div className="text-muted">{refusal}</div>
        </div>
      )}
      <div className="mt-2 space-y-2">
        {pending.fields.map((f, i) => {
          const fid = `${id}-${i}`;
          const value = values[f.name];
          const label = f.name.replace(/_/g, " ");
          return (
            <div key={f.name}>
              {f.type === "bool" ? (
                <label className="flex items-center gap-2 text-[12px] text-ink" htmlFor={fid}>
                  <input
                    id={fid}
                    type="checkbox"
                    checked={value === true}
                    onChange={(e) => set(f.name, e.target.checked)}
                  />
                  {label}
                </label>
              ) : (
                <>
                  <label className="block text-[12px] text-muted" htmlFor={fid}>{label}</label>
                  {f.type === "int" || f.type === "float" ? (
                    <input
                      id={fid}
                      type="number"
                      step={f.type === "int" ? "1" : "any"}
                      required
                      className="w-full rounded-md border border-line bg-paper px-2 py-1 text-[13px] text-ink"
                      value={String(value ?? "")}
                      onChange={(e) => set(f.name, e.target.value)}
                    />
                  ) : (
                    <textarea
                      id={fid}
                      rows={1}
                      required
                      className={
                        "w-full resize-none rounded-md border border-line bg-paper px-2 py-1 text-[13px] text-ink" +
                        (f.type === "list" || f.type === "dict" ? " font-mono" : "")
                      }
                      value={String(value ?? "")}
                      onChange={(e) => {
                        set(f.name, e.target.value);
                        grow(e.target);
                      }}
                    />
                  )}
                </>
              )}
              {errors[f.name] && <div className="mt-0.5 text-[12px] text-danger">{errors[f.name]}</div>}
            </div>
          );
        })}
      </div>
      <button type="submit" className="btn approval-primary mt-3" disabled={inFlight}>
        Answer &amp; resume
      </button>
    </form>
  );
}
