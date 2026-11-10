// The agent-declared view (view contract v1.0.0, fabric CONTRACTS.md §13) rendered in RunPanel:
// the layout vocabulary, the atomic fallback to the generic layout, decision_labels, and the
// harness-reserved regions that a view never changes (OW-F-015 ticket 03).
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPanel, type RunData } from "./RunPanel";

const steps: NonNullable<RunData["steps"]> = [
  { type: "transition", summary: "Member eligibility confirmed", state_before: "received", state_after: "checked", sha256: "aaaaaaaaaaaabbbbbbbbbbbb", at: "2026-11-10T09:00:00Z" },
  { type: "transition", state_before: "checked", state_after: "reviewed", sha256: "cccccccccccc0000", at: "2026-11-10T09:01:00Z" },
  { type: "transition", summary: "Units within the per-authorization limit", state_before: "reviewed", state_after: "awaiting_signature", sha256: "dddddddddddd1111", at: "2026-11-10T09:02:00Z" },
];

const record = {
  request_id: "REQ-1",
  procedure_code: "97110",
  member_id: "M-001",
  plan_tier: "gold",
  clinical_notes: "Post-op knee rehab",
  requested_units: 1,
  provider_npi: "1234567890",
  request_date: "2026-11-01",
};

const item: RunData = {
  channel: "email",
  agent: "payor-prior-auth",
  decision: "awaiting_signature",
  awaiting_signoff: true,
  plan: { name: "prior_auth", signoff: "part11_single", states: ["received", "checked", "reviewed", "awaiting_signature", "approved", "denied"] },
  record,
  steps,
};

function withView(view: unknown, extra: Partial<RunData> = {}): RunData {
  return { ...item, ...extra, view } as RunData;
}

function declared() {
  return screen.getByTestId("declared-record");
}

function technicalDetails() {
  return screen.getByText("Technical details").closest("details") as HTMLDetailsElement;
}

describe("RunPanel declared view", () => {
  afterEach(cleanup);

  describe("header", () => {
    it("renders the title, subtitle and badge from record values", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "header", title_field: "procedure_code", subtitle_field: "member_id", badge_field: "plan_tier" }] })} pending onDecide={vi.fn()} />);
      const header = within(declared()).getByTestId("view-header");
      expect(within(header).getByText("97110").className).toContain("text-heading");
      expect(within(header).getByText("M-001")).toBeTruthy();
      expect(within(header).getByText("gold")).toBeTruthy();
    });
  });

  describe("field_group", () => {
    it("renders a labelled group of fields across the declared columns", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "field_group", label: "Clinical", fields: ["clinical_notes", "requested_units"], columns: 2 }] })} pending onDecide={vi.fn()} />);
      const group = within(declared()).getByRole("group", { name: "Clinical" });
      expect(within(group).getByText("clinical notes")).toBeTruthy();
      expect(within(group).getByText("Post-op knee rehab")).toBeTruthy();
      expect(within(group).getByText("requested units")).toBeTruthy();
      expect(within(group).getByText("1")).toBeTruthy();
      const grid = within(group).getByText("Post-op knee rehab").parentElement!.parentElement!;
      expect(grid.style.gridTemplateColumns).toBe("repeat(2, minmax(0, 1fr))");
    });
  });

  describe("callout", () => {
    it("renders declared text in the info tone and a record value in the warn tone", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [
        { component: "callout", text: "Check the units against the limit", tone: "info" },
        { component: "callout", text_field: "clinical_notes", tone: "warn" },
      ] })} pending onDecide={vi.fn()} />);
      const [info, warn] = within(declared()).getAllByRole("note");
      expect(info.textContent).toBe("Check the units against the limit");
      expect(info.className).toContain("bg-accentSoft");
      expect(warn.textContent).toBe("Post-op knee rehab");
      expect(warn.className).toContain("bg-warnSoft");
      expect(warn.className).toContain("text-warnInk");
    });

    it("renders text as plain text, never HTML", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "callout", text: "<b>bold</b>", tone: "info" }] })} pending onDecide={vi.fn()} />);
      const note = within(declared()).getByRole("note");
      expect(note.textContent).toBe("<b>bold</b>");
      expect(note.querySelector("b")).toBeNull();
    });
  });

  describe("missing text values", () => {
    it("renders an em dash for a missing text value without falling back", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [
        { component: "header", title_field: "absent_title", subtitle_field: "member_id" },
        { component: "callout", text_field: "absent_note", tone: "warn" },
        { component: "field_group", label: "Clinical", fields: ["absent_field"] },
      ] })} pending onDecide={vi.fn()} />);
      expect(within(screen.getByTestId("view-header")).getByText("—")).toBeTruthy();
      expect(within(declared()).getByRole("note").textContent).toBe("—");
      expect(within(within(declared()).getByRole("group", { name: "Clinical" })).getByText("—")).toBeTruthy();
      expect(technicalDetails().textContent).not.toContain("Declared view not rendered");
    });
  });

  describe("table", () => {
    it("renders an array-of-objects record field as rows under the declared column labels", () => {
      const lines = [{ code: "97110", units: 1 }, { code: "97140" }];
      render(<RunPanel data={withView({ view: "1.0.0", record: [
        { component: "table", rows_field: "lines", columns: [{ field: "code", label: "Code" }, { field: "units", label: "Units" }] },
      ] }, { record: { ...record, lines } })} pending onDecide={vi.fn()} />);
      const table = within(declared()).getByRole("table");
      const rows = Array.from(table.querySelectorAll("tr")).map((tr) => Array.from(tr.children).map((c) => c.textContent));
      expect(rows).toEqual([["Code", "Units"], ["97110", "1"], ["97140", "—"]]);
      expect(screen.getByTestId("view-other-fields").textContent).not.toContain("lines");
    });
  });

  describe("checks", () => {
    function checkRows() {
      const block = screen.getByText(/What was checked/).closest("div")!;
      return Array.from(block.querySelectorAll("ol > li")).map((li) => li.textContent);
    }

    it("keeps today's numbered list for the list style", () => {
      render(<RunPanel data={withView({ view: "1.0.0", checks: { component: "list" } })} pending onDecide={vi.fn()} />);
      expect(screen.getByText(/What was checked/).textContent).toBe("What was checked · 3 steps");
      expect(checkRows()).toEqual(["1Member eligibility confirmed", "2checked → reviewed", "3Units within the per-authorization limit"]);
      expect(screen.queryByTestId("view-timeline")).toBeNull();
    });

    it("drops the numbers when numbered is false", () => {
      render(<RunPanel data={withView({ view: "1.0.0", checks: { component: "list", numbered: false } })} pending onDecide={vi.fn()} />);
      expect(checkRows()).toEqual(["Member eligibility confirmed", "checked → reviewed", "Units within the per-authorization limit"]);
    });

    it("draws the timeline variant, numbered or not, with the step text verbatim", () => {
      render(<RunPanel data={withView({ view: "1.0.0", checks: { component: "timeline", numbered: true } })} pending onDecide={vi.fn()} />);
      expect(screen.getByTestId("view-timeline")).toBeTruthy();
      expect(checkRows()).toEqual(["1Member eligibility confirmed", "2checked → reviewed", "3Units within the per-authorization limit"]);
      cleanup();
      render(<RunPanel data={withView({ view: "1.0.0", checks: { component: "timeline", numbered: false } })} pending onDecide={vi.fn()} />);
      expect(checkRows()).toEqual(["Member eligibility confirmed", "checked → reviewed", "Units within the per-authorization limit"]);
    });

    it("keeps the generic record grid when the view declares no record section", () => {
      render(<RunPanel data={withView({ view: "1.0.0", checks: { component: "timeline" } })} pending onDecide={vi.fn()} />);
      expect(screen.queryByTestId("declared-record")).toBeNull();
      expect(screen.getByText(/fields shown/)).toBeTruthy();
    });
  });

  describe("decision_labels", () => {
    const labels = { view: "1.0.0", decision_labels: { approved: "Authorized", denied: "Not authorized", pended: "Pended for review" } };

    function headerStatus() {
      return screen.getByTestId("run-panel").querySelector("header > span:last-child") as HTMLElement;
    }

    function decisionSpan() {
      return screen.getByText(/^Decision:/).querySelector("span") as HTMLElement;
    }

    it.each([
      ["approved", "Authorized", "text-ok"],
      ["denied", "Not authorized", "text-danger"],
      ["pended", "Pended for review", "text-warn"],
    ])("re-words %s as %s in the header and the answer, tone still %s", (decision, label, tone) => {
      render(<RunPanel data={withView(labels, { decision })} pending={false} onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe(label);
      expect(headerStatus().className).toBe("text-[13px] font-semibold " + tone);
      expect(screen.getByText(/^Decision:/).textContent).toBe(`Decision: ${label}`);
      expect(decisionSpan().className).toBe(tone);
    });

    it("re-words the signature's resulting state on a signed item", () => {
      render(<RunPanel data={withView(labels, { signature: { approver: "Dr. Reviewer", state_after: "approved" } })} pending={false} onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("Authorized");
      expect(decisionSpan().textContent).toBe("Authorized");
    });

    it("leaves an unlabelled state worded as without a view, and an unknown state neutral", () => {
      render(<RunPanel data={withView(labels)} pending onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("awaiting signature");
      expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: awaiting_signature");
      cleanup();
      render(<RunPanel data={withView(labels, { decision: "some_pack_state" })} pending onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("some_pack_state");
      expect(headerStatus().className).toBe("text-[13px] font-semibold text-ink");
    });

    it("never re-words the gate footer or the signed line", () => {
      render(<RunPanel data={withView(labels, { signature: { approver: "Dr. Reviewer", at: "2026-11-10T10:00:00Z", state_after: "approved" } })} pending={false} onDecide={vi.fn()} />);
      expect(screen.getByTestId("run-panel").querySelector("footer")!.textContent).toBe("✓ Signed by Dr. Reviewer on 2026-11-10T10:00:00Z · 3 steps sealed");
    });
  });

  describe("atomic fallback", () => {
    const header = { component: "header", title_field: "procedure_code" };
    const labelled = { approved: "Authorized" };

    function expectGenericWith(reason: string) {
      expect(screen.queryByTestId("declared-record")).toBeNull();
      expect(screen.queryByTestId("view-timeline")).toBeNull();
      expect(screen.getByText(/fields shown/).textContent).toBe("· 7 of 7 fields shown");
      const lines = Array.from(technicalDetails().querySelectorAll("*"))
        .filter((n) => n.children.length === 0 && n.textContent?.startsWith("Declared view not rendered"));
      expect(lines.map((n) => n.textContent)).toEqual([`Declared view not rendered: ${reason}`]);
    }

    it.each<[string, unknown, string]>([
      ["a view that is not an object", ["header"], "the view is not an object"],
      ["a wrong version", { view: "2.0.0", record: [header] }, 'view version must be "1.0.0"'],
      ["a missing version", { record: [header] }, 'view version must be "1.0.0"'],
      ["an unknown section", { view: "1.0.0", record: [header], layout: {} }, 'unknown section "layout"'],
      ["a record that is not a list", { view: "1.0.0", record: header }, "record must be a list of components"],
      ["a component with no name", { view: "1.0.0", record: [header, { title_field: "x" }] }, "record[1] has no component name"],
      ["an unknown component", { view: "1.0.0", record: [header, { component: "sparkline", data_field: "x" }] }, 'record[1]: unknown component "sparkline"'],
      ["an unknown key", { view: "1.0.0", record: [{ ...header, colour: "red" }] }, 'record[0] (header): unknown key "colour"'],
      ["a component named after an object built-in", { view: "1.0.0", record: [{ component: "constructor" }] }, 'record[0]: unknown component "constructor"'],
      ["a key named after an object built-in", { view: "1.0.0", record: [{ ...header, toString: "x" }] }, 'record[0] (header): unknown key "toString"'],
      ["a missing required key", { view: "1.0.0", record: [{ component: "field_group", fields: ["units"] }] }, 'record[0] (field_group): missing key "label"'],
      ["a string where a list belongs", { view: "1.0.0", record: [{ component: "key_value", fields: "units" }] }, 'record[0] (key_value): key "fields" must be a list of strings'],
      ["a non-integer column count", { view: "1.0.0", record: [{ component: "field_group", label: "L", fields: [], columns: "2" }] }, 'record[0] (field_group): key "columns" must be a positive integer'],
      ["a non-boolean demoted flag", { view: "1.0.0", record: [{ component: "key_value", fields: [], demoted: "yes" }] }, 'record[0] (key_value): key "demoted" must be a boolean'],
      ["an unknown callout tone", { view: "1.0.0", record: [{ component: "callout", text: "x", tone: "error" }] }, 'record[0] (callout): key "tone" must be "info" or "warn"'],
      ["a callout with both text and text_field", { view: "1.0.0", record: [{ component: "callout", text: "x", text_field: "y", tone: "info" }] }, 'record[0] (callout): exactly one of "text" or "text_field"'],
      ["a callout with neither text nor text_field", { view: "1.0.0", record: [{ component: "callout", tone: "info" }] }, 'record[0] (callout): exactly one of "text" or "text_field"'],
      ["table columns without labels", { view: "1.0.0", record: [{ component: "table", rows_field: "lines", columns: [{ field: "code" }] }] }, 'record[0] (table): key "columns" must be a list of {field, label}'],
      ["a chart missing a key", { view: "1.0.0", record: [{ component: "bar_chart", label: "L", data_field: "d", x: "x" }] }, 'record[0] (bar_chart): missing key "y"'],
      ["a gauge with both max and max_field", { view: "1.0.0", record: [{ component: "gauge", label: "L", value_field: "v", max: 1, max_field: "m" }] }, 'record[0] (gauge): exactly one of "max" or "max_field"'],
      ["a gauge max that is not a number", { view: "1.0.0", record: [{ component: "gauge", label: "L", value_field: "v", max: "1" }] }, 'record[0] (gauge): key "max" must be a number'],
      ["an unknown checks style", { view: "1.0.0", record: [header], checks: { component: "grid" } }, 'checks: unknown component "grid"'],
      ["an unknown checks key", { view: "1.0.0", checks: { component: "list", reverse: true } }, 'checks: unknown key "reverse"'],
      ["a non-boolean numbered flag", { view: "1.0.0", checks: { component: "list", numbered: 1 } }, 'checks: key "numbered" must be a boolean'],
      ["a non-text decision label", { view: "1.0.0", decision_labels: { approved: 1 } }, "decision_labels must map states to text"],
    ])("falls back whole on %s", (_case, view, reason) => {
      render(<RunPanel data={withView(view, { decision: "approved" })} pending={false} onDecide={vi.fn()} />);
      expectGenericWith(reason);
    });

    it("drops the checks style and the decision labels too when one component fails", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [header, { component: "sparkline" }], checks: { component: "timeline", numbered: false }, decision_labels: labelled }, { decision: "approved" })} pending={false} onDecide={vi.fn()} />);
      expectGenericWith('record[1]: unknown component "sparkline"');
      expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: approved");
    });

    it.each<[string, unknown]>([
      ["missing", undefined],
      ["not a list", { code: "97110" }],
      ["a list of non-objects", ["97110", "97140"]],
    ])("falls back whole when a table's rows are %s", (_case, lines) => {
      const view = { view: "1.0.0", record: [header, { component: "table", rows_field: "lines", columns: [{ field: "code", label: "Code" }] }] };
      const data = withView(view, { record: lines === undefined ? record : { ...record, lines } });
      render(<RunPanel data={data} pending={false} onDecide={vi.fn()} />);
      expect(screen.queryByTestId("declared-record")).toBeNull();
      expect(technicalDetails().textContent).toContain('Declared view not rendered: record[1] (table): "lines" is not a list of objects');
    });

    it("falls back whole while a structurally valid chart has no renderer yet", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [header, { component: "gauge", label: "Units", value_field: "requested_units", max: 1 }] })} pending onDecide={vi.fn()} />);
      expect(screen.queryByTestId("declared-record")).toBeNull();
      expect(technicalDetails().textContent).toContain("Declared view not rendered: record[1] (gauge): not rendered in this build");
    });

    it("falls back whole on a render-time exception", () => {
      const quiet = vi.spyOn(console, "error").mockImplementation(() => {});
      // a hidden hygiene id the generic layout never prints, holding a value that cannot be printed
      const data = withView({ view: "1.0.0", record: [{ component: "header", title_field: "request_id" }] }, { record: { ...record, request_id: Object.create(null) } });
      render(<RunPanel data={data} pending onDecide={vi.fn()} />);
      quiet.mockRestore();
      expectGenericWith("render-time error");
    });

    it("adds no line to Technical details when the view renders", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [header] })} pending onDecide={vi.fn()} />);
      expect(screen.getByTestId("declared-record")).toBeTruthy();
      expect(technicalDetails().textContent).not.toContain("Declared view not rendered");
    });
  });

  describe("harness-reserved regions", () => {
    const full = {
      view: "1.0.0",
      record: [
        { component: "header", title_field: "procedure_code", subtitle_field: "member_id" },
        { component: "field_group", label: "Clinical", fields: ["clinical_notes", "requested_units"] },
        { component: "callout", text: "Check the units", tone: "warn" },
      ],
      checks: { component: "timeline", numbered: true },
      decision_labels: { approved: "Authorized" },
    };
    const signed: Partial<RunData> = {
      signature: { approver: "Dr. Reviewer", at: "2026-11-10T10:00:00Z", state_before: "awaiting_signature", state_after: "approved", signoff: "part11_single", sha256: "eeee" },
      receipt: { request_id: "REQ-1", outcome: "approved" },
    };

    // the reserved regions of one render: gate footer, decision tones, Technical details
    function reserved() {
      const root = screen.getByTestId("run-panel");
      const answer = screen.queryByText(/^Decision:/);
      const out = {
        footer: root.querySelector("footer")!.outerHTML,
        statusTone: (root.querySelector("header > span:last-child") as HTMLElement).className,
        answerTone: answer?.querySelector("span")?.className ?? null,
        details: technicalDetails().outerHTML,
      };
      cleanup();
      return out;
    }

    function both(data: RunData, pending: boolean) {
      render(<RunPanel data={data} pending={pending} onDecide={vi.fn()} />);
      const without = reserved();
      render(<RunPanel data={{ ...data, view: full } as RunData} pending={pending} onDecide={vi.fn()} />);
      expect(screen.getByTestId("declared-record")).toBeTruthy();
      return [without, reserved()];
    }

    it.each<[string, Partial<RunData>, boolean]>([
      ["pending", {}, true],
      ["signed", signed, false],
      ["approved", { decision: "approved" }, false],
      ["running", { running: true }, false],
      ["not signed and not pending", {}, false],
    ])("renders the %s item's gate, tones and Technical details identically", (_state, extra, pending) => {
      const [without, withIt] = both({ ...item, ...extra }, pending);
      expect(withIt).toEqual(without);
    });

    it("keeps the sign and decline actions with a view", () => {
      const onDecide = vi.fn();
      render(<RunPanel data={withView(full)} pending onDecide={onDecide} />);
      fireEvent.click(screen.getByText("Sign & seal"));
      fireEvent.click(screen.getByText("Decline"));
      expect(onDecide.mock.calls).toEqual([["once"], ["deny"]]);
    });

    it("keeps the running indicator and the error states with a view", () => {
      render(<RunPanel data={withView(full, { running: true })} pending={false} onDecide={vi.fn()} />);
      expect((screen.getByTestId("run-panel").querySelector("header > span:last-child") as HTMLElement).textContent).toBe("in progress…");
      expect(screen.queryByText(/^Decision:/)).toBeNull();
      cleanup();
      for (const retrying of [undefined, false]) {
        const failed = { error: "fabric unreachable", retrying };
        render(<RunPanel data={{ ...item, ...failed }} pending={false} onDecide={vi.fn()} />);
        const without = screen.getByText(/This request (could not run|was rejected)/).parentElement!.outerHTML;
        cleanup();
        render(<RunPanel data={withView(full, failed)} pending={false} onDecide={vi.fn()} />);
        expect(screen.getByText(/This request (could not run|was rejected)/).parentElement!.outerHTML).toBe(without);
        cleanup();
      }
    });
  });

  describe("key_value and Other fields", () => {
    it("renders a key_value grid in place, and a demoted one after every other component", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [
        { component: "key_value", fields: ["provider_npi", "request_date"], demoted: true },
        { component: "key_value", fields: ["member_id"] },
        { component: "header", title_field: "procedure_code" },
      ] })} pending onDecide={vi.fn()} />);
      const order = Array.from(declared().children).map((n) => n.getAttribute("data-testid"));
      expect(order).toEqual(["view-key-value", "view-header", "view-key-value-demoted", "view-other-fields"]);
      expect(within(screen.getByTestId("view-key-value-demoted")).getByText("1234567890")).toBeTruthy();
    });

    it("collapses a demoted key_value past six fields behind a toggle", () => {
      const many = { f1: 1, f2: 2, f3: 3, f4: 4, f5: 5, f6: 6, f7: 7, f8: 8 };
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "key_value", fields: Object.keys(many), demoted: true }] }, { record: many })} pending onDecide={vi.fn()} />);
      const group = screen.getByTestId("view-key-value-demoted");
      expect(within(group).queryByText("f7")).toBeNull();
      fireEvent.click(within(group).getByText("Show all 8"));
      expect(within(group).getByText("f8")).toBeTruthy();
    });

    it("puts record fields no component placed in an Other fields group last, hygiene ids hidden", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "header", title_field: "procedure_code", subtitle_field: "member_id" }] })} pending onDecide={vi.fn()} />);
      const other = screen.getByTestId("view-other-fields");
      expect(declared().lastElementChild).toBe(other);
      expect(within(other).getByText("Other fields")).toBeTruthy();
      const labels = Array.from(other.querySelectorAll("dt")).map((n) => n.textContent);
      expect(labels).toEqual(["plan tier", "clinical notes", "requested units", "provider npi", "request date"]);
      expect(other.textContent).not.toContain("REQ-1");
      expect(other.textContent).not.toContain("request id");
    });

    it("collapses Other fields past six behind a toggle", () => {
      const many = { request_id: "REQ-9", f1: 1, f2: 2, f3: 3, f4: 4, f5: 5, f6: 6, f7: 7, f8: 8 };
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "header", title_field: "f1" }] }, { record: many })} pending onDecide={vi.fn()} />);
      const other = screen.getByTestId("view-other-fields");
      expect(Array.from(other.querySelectorAll("dt")).map((n) => n.textContent)).toEqual(["f2", "f3", "f4", "f5", "f6", "f7"]);
      fireEvent.click(within(other).getByText("Show all 7"));
      expect(other.querySelectorAll("dt")).toHaveLength(7);
    });

    it("omits Other fields when the components placed every record field", () => {
      render(<RunPanel data={withView({ view: "1.0.0", record: [{ component: "key_value", fields: ["units"] }] }, { record: { request_id: "R", units: 1 } })} pending onDecide={vi.fn()} />);
      expect(screen.queryByTestId("view-other-fields")).toBeNull();
    });
  });
});
