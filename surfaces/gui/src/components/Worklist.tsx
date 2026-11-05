import { useEffect, useMemo, useState } from "react";
import { getInbox, type InboxItem } from "../api";

// The list you open when you (re)start the harness: every work item the system has processed,
// with what it decided and whether anything is waiting on a human.

type RunData = {
  record?: Record<string, unknown>;
  agent?: string;
  decision?: string;
  not_found?: boolean;
  error?: string;
  retrying?: boolean;
  running?: boolean;
  awaiting_signoff?: boolean;
  signature?: { approver?: string; at?: string };
};

const REF_KEYS = ["request_id", "slr_id", "capa_id", "case_id", "ticket_id", "record_id", "ref"];
const SUBJECT = new Set(["member_id", "patient_id", "provider_id", "provider_npi", "user_id"]);

function refOf(d: RunData): string {
  const rec = d.record ?? {};
  for (const k of REF_KEYS) if (typeof rec[k] === "string" && rec[k]) return rec[k] as string;
  for (const [k, v] of Object.entries(rec)) {
    if (k.endsWith("_id") && !SUBJECT.has(k) && typeof v === "string" && v) return v;
  }
  return "—";
}

type Status = { label: string; tone: string; tab: Tab };
type Tab = "all" | "todo" | "sealed" | "rejected" | "failed";

function statusOf(item: InboxItem): Status {
  const d = (item.data ?? {}) as RunData;
  if (d.running) return { label: "in progress", tone: "text-accent", tab: "todo" };
  if (d.not_found) return { label: "not found · rejected", tone: "text-warn", tab: "rejected" };
  if (d.error) {
    return d.retrying
      ? { label: "retrying", tone: "text-warn", tab: "failed" }
      : { label: "failed", tone: "text-danger", tab: "failed" };
  }
  if (d.signature) return { label: `sealed · ${d.decision ?? ""}`.trim(), tone: "text-ok", tab: "sealed" };
  if (d.awaiting_signoff || item.state === "pending")
    return { label: "needs your signature", tone: "text-warn", tab: "todo" };
  return { label: String(d.decision ?? "done"), tone: "text-ink", tab: "sealed" };
}

const TABS: { id: Tab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "todo", label: "Needs you" },
  { id: "sealed", label: "Sealed" },
  { id: "rejected", label: "Rejected" },
  { id: "failed", label: "Failed" },
];

export function Worklist({ onOpen }: { onOpen: (item: InboxItem) => void }) {
  const [items, setItems] = useState<InboxItem[]>([]);
  const [tab, setTab] = useState<Tab>("all");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getInbox()
        .then((all) => alive && setItems((all ?? []).filter((i) => ((i.data ?? {}) as RunData).record)))
        .catch(() => alive && setItems([]))
        .finally(() => alive && setLoading(false));
    load();
    const t = setInterval(load, 4000);          // stay current without a socket
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const rows = useMemo(() => {
    const withStatus = items.map((i) => ({ item: i, status: statusOf(i) }));
    const filtered = tab === "all" ? withStatus : withStatus.filter((r) => r.status.tab === tab);
    const needle = q.trim().toLowerCase();
    const searched = needle
      ? filtered.filter((r) => refOf((r.item.data ?? {}) as RunData).toLowerCase().includes(needle))
      : filtered;
    return searched.sort((a, b) =>
      String(b.item.resolved_at ?? b.item.created_at ?? "").localeCompare(
        String(a.item.resolved_at ?? a.item.created_at ?? ""),
      ),
    );
  }, [items, tab, q]);

  const count = (t: Tab) =>
    t === "all" ? items.length : items.filter((i) => statusOf(i).tab === t).length;

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-6">
      <div className="mb-4 flex flex-wrap items-baseline gap-3">
        <h1 className="text-[18px] font-semibold text-ink">Work</h1>
        <span className="text-[13px] text-muted">
          {items.length} work item{items.length === 1 ? "" : "s"} processed
        </span>
        <span className="flex-1" />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search a reference…"
          className="rounded-lg border border-line bg-paper px-3 py-1.5 text-[13px] outline-none focus:border-accent"
        />
      </div>

      <div className="mb-3 flex flex-wrap gap-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={
              "rounded-lg px-2.5 py-1 text-[12px] font-medium " +
              (tab === t.id ? "bg-chromeHover text-ink" : "text-muted hover:bg-chromeHover")
            }
          >
            {t.label} <span className="text-faint">{count(t.id)}</span>
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-line">
        <table className="w-full text-left text-[13px]">
          <thead className="bg-panel text-[11px] uppercase tracking-wide text-faint">
            <tr>
              <th className="px-3 py-2 font-medium">Reference</th>
              <th className="px-3 py-2 font-medium">Channel</th>
              <th className="px-3 py-2 font-medium">Handled by</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">When</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ item, status }) => {
              const d = (item.data ?? {}) as RunData;
              return (
                <tr
                  key={item.id}
                  className="cursor-pointer border-t border-line hover:bg-panel"
                  onClick={() => onOpen(item)}
                >
                  <td className="px-3 py-2 font-mono text-[12px] text-ink">{refOf(d)}</td>
                  <td className="px-3 py-2 text-muted">{String((d.record as Record<string, unknown> | undefined)?.channel ?? "webhook")}</td>
                  <td className="px-3 py-2 font-mono text-[12px] text-muted">{d.agent ?? "—"}</td>
                  <td className={"px-3 py-2 font-medium " + status.tone}>{status.label}</td>
                  <td className="px-3 py-2 text-faint">
                    {String(item.resolved_at ?? item.created_at ?? "").replace("T", " ").slice(0, 16)}
                  </td>
                </tr>
              );
            })}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-[13px] text-muted">
                  Nothing here yet. Send a work item to a channel and it will appear.
                </td>
              </tr>
            )}
            {loading && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-[13px] text-muted">Loading…</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
