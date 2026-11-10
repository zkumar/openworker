// The agent-declared view (view contract v1.0.0, fabric CONTRACTS.md §13): the pack declares
// how a work item's record is laid out, against a closed vocabulary this file draws. Every label
// and value renders as plain text. The gate, the decision tone, the running and error states and
// Technical details are harness-reserved and live in RunPanel, never here.

import { useState, type CSSProperties } from "react";

type Rec = Record<string, unknown>;

// harness hygiene ids stay hidden in the Other fields group, as in the generic layout
const HIDDEN = new Set(["request_id", "capa_id", "slr_id"]);

export type ViewComponent = { component: string } & Rec;
export type ViewDoc = {
  view: "1.0.0";
  record?: ViewComponent[];
  checks?: { component: "list" | "timeline"; numbered?: boolean };
  decision_labels?: Record<string, string>;
};

// The closed vocabulary v1.0.0 (§13): every component's keys and their types. The check below
// covers names, required keys and key types only; field references and coverage are fabric's.
type KeyType = "string" | "strings" | "int" | "bool" | "number" | "tone" | "columns";
const VOCAB: Record<string, { required: string[]; keys: Record<string, KeyType> }> = {
  header: { required: ["title_field"], keys: { title_field: "string", subtitle_field: "string", badge_field: "string" } },
  field_group: { required: ["label", "fields"], keys: { label: "string", fields: "strings", columns: "int" } },
  key_value: { required: ["fields"], keys: { fields: "strings", demoted: "bool" } },
  callout: { required: ["tone"], keys: { text: "string", text_field: "string", tone: "tone" } },
  table: { required: ["rows_field", "columns"], keys: { rows_field: "string", columns: "columns" } },
  bar_chart: { required: ["label", "data_field", "x", "y"], keys: { label: "string", data_field: "string", x: "string", y: "string" } },
  line_chart: { required: ["label", "data_field", "x", "y"], keys: { label: "string", data_field: "string", x: "string", y: "string" } },
  gauge: { required: ["label", "value_field"], keys: { label: "string", value_field: "string", max: "number", max_field: "string" } },
};
const EXACTLY_ONE: Record<string, [string, string]> = { callout: ["text", "text_field"], gauge: ["max", "max_field"] };
// structurally checked here; drawn by the SVG primitives, which this build does not ship yet
const CHARTS = new Set(["bar_chart", "line_chart", "gauge"]);
const SECTIONS = new Set(["view", "record", "checks", "decision_labels"]);

// own keys only, so names like "constructor" or "toString" are unknown, not built-ins
function has(o: object, k: string): boolean {
  return Object.prototype.hasOwnProperty.call(o, k);
}

function isObj(v: unknown): v is Rec {
  return v !== null && typeof v === "object" && !Array.isArray(v);
}

function typeError(key: string, type: KeyType, v: unknown): string | null {
  switch (type) {
    case "string":
      return typeof v === "string" ? null : `key "${key}" must be text`;
    case "strings":
      return Array.isArray(v) && v.every((s) => typeof s === "string") ? null : `key "${key}" must be a list of strings`;
    case "int":
      return Number.isInteger(v) && (v as number) >= 1 ? null : `key "${key}" must be a positive integer`;
    case "bool":
      return typeof v === "boolean" ? null : `key "${key}" must be a boolean`;
    case "number":
      return typeof v === "number" && Number.isFinite(v) ? null : `key "${key}" must be a number`;
    case "tone":
      return v === "info" || v === "warn" ? null : `key "${key}" must be "info" or "warn"`;
    case "columns":
      return Array.isArray(v) && v.every((col) => isObj(col) && Object.keys(col).length === 2
        && typeof col.field === "string" && typeof col.label === "string")
        ? null : `key "${key}" must be a list of {field, label}`;
  }
}

// A failure reason to follow "record[i]", or null when the component passes.
function checkComponent(c: unknown, record: Rec): string | null {
  if (!isObj(c) || typeof c.component !== "string") return " has no component name";
  if (!has(VOCAB, c.component)) return `: unknown component "${c.component}"`;
  const spec = VOCAB[c.component];
  const at = ` (${c.component}): `;
  for (const [k, v] of Object.entries(c)) {
    if (k === "component") continue;
    if (!has(spec.keys, k)) return `${at}unknown key "${k}"`;
    const err = typeError(k, spec.keys[k], v);
    if (err) return at + err;
  }
  for (const k of spec.required) if (!has(c, k)) return `${at}missing key "${k}"`;
  const one = has(EXACTLY_ONE, c.component) ? EXACTLY_ONE[c.component] : null;
  if (one && has(c, one[0]) === has(c, one[1])) return `${at}exactly one of "${one[0]}" or "${one[1]}"`;
  // bound data the harness alone sees at runtime: a mis-shaped table falls the whole view back
  if (c.component === "table") {
    const rows = record[c.rows_field as string];
    if (!Array.isArray(rows) || !rows.every(isObj)) return `${at}"${c.rows_field}" is not a list of objects`;
  }
  if (CHARTS.has(c.component)) return `${at}not rendered in this build`;
  return null;
}

// The structural check run before rendering. Reasons name sections, components, keys and field
// names only, never record values.
export function checkView(view: unknown, record: Rec): { view: ViewDoc } | { reason: string } {
  if (!isObj(view)) return { reason: "the view is not an object" };
  if (view.view !== "1.0.0") return { reason: 'view version must be "1.0.0"' };
  for (const k of Object.keys(view)) if (!SECTIONS.has(k)) return { reason: `unknown section "${k}"` };
  if (has(view, "record")) {
    if (!Array.isArray(view.record)) return { reason: "record must be a list of components" };
    for (const [i, c] of view.record.entries()) {
      const err = checkComponent(c, record);
      if (err) return { reason: `record[${i}]${err}` };
    }
  }
  if (has(view, "checks")) {
    const checks = view.checks;
    if (!isObj(checks) || (checks.component !== "list" && checks.component !== "timeline")) {
      return { reason: `checks: unknown component "${isObj(checks) ? String(checks.component) : ""}"` };
    }
    for (const k of Object.keys(checks)) {
      if (k !== "component" && k !== "numbered") return { reason: `checks: unknown key "${k}"` };
    }
    if (has(checks, "numbered") && typeof checks.numbered !== "boolean") return { reason: 'checks: key "numbered" must be a boolean' };
  }
  if (has(view, "decision_labels")) {
    const labels = view.decision_labels;
    if (!isObj(labels) || !Object.values(labels).every((l) => typeof l === "string")) {
      return { reason: "decision_labels must map states to text" };
    }
  }
  return { view: view as ViewDoc };
}

// a missing text value renders an em dash; it never falls the view back
export function text(v: unknown): string {
  return v === undefined || v === null || v === "" ? "—" : String(v);
}

function Header({ c, record }: { c: Rec; record: Rec }) {
  return (
    <div data-testid="view-header" className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <div className="min-w-0">
        <div className="text-heading font-semibold text-ink">{text(record[c.title_field as string])}</div>
        {typeof c.subtitle_field === "string" && (
          <div className="text-meta text-muted">{text(record[c.subtitle_field])}</div>
        )}
      </div>
      {typeof c.badge_field === "string" && (
        <span className="rounded-md bg-panel px-1.5 py-0.5 text-label font-medium text-muted">
          {text(record[c.badge_field])}
        </span>
      )}
    </div>
  );
}

// The record fields a component places: every *_field key and every fields[] entry.
function placedBy(c: Rec): string[] {
  const out: string[] = [];
  for (const [k, v] of Object.entries(c)) {
    if (k.endsWith("_field") && typeof v === "string") out.push(v);
    if (k === "fields" && Array.isArray(v)) out.push(...(v as string[]));
  }
  return out;
}

// A grid of record fields; `collapse` folds it to six with a toggle (demoted groups).
function FieldGrid({ fields, record, collapse, style }: {
  fields: string[]; record: Rec; collapse?: boolean; style?: CSSProperties;
}) {
  const [all, setAll] = useState(false);
  const folds = Boolean(collapse) && fields.length > 6;
  const shown = folds && !all ? fields.slice(0, 6) : fields;
  return (
    <>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3" style={style}>
        {shown.map((f) => {
          const value = text(record[f]);
          return (
            <div key={f} className="min-w-0">
              <dt className="text-label uppercase tracking-wide text-faint">{f.replace(/_/g, " ")}</dt>
              <dd className="truncate text-ui text-ink" title={value}>{value}</dd>
            </div>
          );
        })}
      </dl>
      {folds && (
        <button className="mt-2 text-meta text-accent hover:underline" onClick={() => setAll((v) => !v)}>
          {all ? "Show fewer" : `Show all ${fields.length}`}
        </button>
      )}
    </>
  );
}

function FieldGroup({ c, record }: { c: Rec; record: Rec }) {
  const columns = c.columns as number | undefined;
  return (
    <section role="group" aria-label={c.label as string}>
      <h3 className="mb-2 text-meta font-semibold uppercase tracking-wide text-muted">{c.label as string}</h3>
      <FieldGrid
        fields={c.fields as string[]}
        record={record}
        style={columns ? { gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` } : undefined}
      />
    </section>
  );
}

function KeyValue({ c, record }: { c: Rec; record: Rec }) {
  return (
    <div data-testid={c.demoted ? "view-key-value-demoted" : "view-key-value"}>
      <FieldGrid fields={c.fields as string[]} record={record} collapse={Boolean(c.demoted)} />
    </div>
  );
}

const CALLOUT_TONE: Record<string, string> = {
  info: "bg-accentSoft text-ink",
  warn: "bg-warnSoft text-warnInk",
};

function Callout({ c, record }: { c: Rec; record: Rec }) {
  const line = typeof c.text_field === "string" ? text(record[c.text_field]) : text(c.text);
  return (
    <div role="note" className={"rounded-md px-3 py-2 text-ui " + CALLOUT_TONE[c.tone as string]}>
      {line}
    </div>
  );
}

// rows_field holds an array of objects; the structural and data checks guarantee the shape
function Table({ c, record }: { c: Rec; record: Rec }) {
  const columns = c.columns as { field: string; label: string }[];
  const rows = record[c.rows_field as string] as Rec[];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-ui">
        <thead>
          <tr className="border-b border-line">
            {columns.map((col) => (
              <th key={col.field} className="py-1 pr-4 text-label font-medium uppercase tracking-wide text-faint">{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              {columns.map((col) => <td key={col.field} className="py-1 pr-4 text-ink">{text(row[col.field])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Component({ c, record }: { c: ViewComponent; record: Rec }) {
  switch (c.component) {
    case "header":
      return <Header c={c} record={record} />;
    case "field_group":
      return <FieldGroup c={c} record={record} />;
    case "key_value":
      return <KeyValue c={c} record={record} />;
    case "callout":
      return <Callout c={c} record={record} />;
    case "table":
      return <Table c={c} record={record} />;
    default:
      throw new Error(`component ${c.component} has no renderer`);
  }
}

// The declared record section: components in declared order, demoted key_value groups after
// them, then the automatic Other fields group for whatever no component placed.
export function DeclaredRecord({ view, record }: { view: ViewDoc; record: Rec }) {
  const components = view.record ?? [];
  const demoted = (c: ViewComponent) => c.component === "key_value" && c.demoted === true;
  const ordered = [...components.filter((c) => !demoted(c)), ...components.filter(demoted)];
  const placed = new Set(components.flatMap(placedBy));
  const other = Object.keys(record).filter((k) => !placed.has(k) && !HIDDEN.has(k));
  return (
    <div className="space-y-4 border-t border-line px-4 py-3" data-testid="declared-record">
      {ordered.map((c, i) => <Component key={i} c={c} record={record} />)}
      {other.length > 0 && (
        <section data-testid="view-other-fields">
          <h3 className="mb-2 text-meta font-semibold uppercase tracking-wide text-muted">Other fields</h3>
          <FieldGrid fields={other} record={record} collapse />
        </section>
      )}
    </div>
  );
}
