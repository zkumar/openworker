// The renderer app's work-item view (OW-F-016 ticket 02): the answer bundle drawn through the
// shared core with RunPanel semantics, the fallback order of adr-text-answer-whole-contract, the
// signature gate as state only, and (OW-F-018) the input gate answered through the host's one
// tool call (adr-view-calls-one-tool).
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPanel, type RunData } from "../components/RunPanel";
import { workItemStates } from "../gallery/states/work-item";
import { invalidViewBundle, noViewBundle, parkedBundle, payorBundle, toolResult } from "./fixtures";
import type { ToolResult } from "./host";
import { WorkItemView } from "./WorkItemView";

const NOTICE = "This work item can't be drawn here. The text answer above is complete.";
// a host whose answer tool replies with `reply`
const host = (reply: ToolResult = {}) => ({
  openLink: vi.fn(async () => undefined),
  answerInput: vi.fn(async (_session: string, _answers: Record<string, unknown>) => reply),
});
const demo = workItemStates.find((s) => s.id === "payor-demo")!.payload as RunData;

// the native panel's rendering of the same work item, for content comparison
function nativeHtml(testId: string): string {
  const { unmount } = render(<RunPanel data={demo} pending={false} onDecide={vi.fn()} />);
  const html = screen.getByTestId(testId).innerHTML;
  unmount();
  return html;
}

describe("WorkItemView", () => {
  afterEach(cleanup);

  it("work-item view renders the payor demo bundle", () => {
    const declared = nativeHtml("declared-record");
    const timeline = nativeHtml("view-timeline");

    render(<WorkItemView result={toolResult(payorBundle)} host={host()} />);
    const view = screen.getByTestId("work-item-view");

    expect(within(view).getByTestId("declared-record").innerHTML).toBe(declared);
    expect(within(view).getByTestId("view-timeline").innerHTML).toBe(timeline);
    expect(within(view).getByTestId("view-header").textContent).toContain("27447");
    expect(within(view).getByRole("group", { name: "Clinical" })).toBeTruthy();
    expect(within(view).getByRole("figure", { name: "Units against per-authorization limit" })).toBeTruthy();
    expect(within(view).getByText(/^Decision:/).textContent).toBe("Decision: Authorized");
    expect(within(view).getAllByText("Authorized").map((n) => n.className.includes("text-ok"))).toEqual([true, true]);
  });

  it("invalid view falls back atomically", () => {
    render(<WorkItemView result={toolResult(invalidViewBundle)} host={host()} />);
    expect(screen.queryByTestId("declared-record")).toBeNull();
    expect(screen.queryByTestId("view-timeline")).toBeNull();
    expect(screen.getByText(/fields shown/).textContent).toBe("· 7 of 7 fields shown");
    // the decision labels go with the rest of the view; the tone stays keyed to the state
    expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: approved");
    expect(screen.getAllByText("approved").map((n) => n.className.includes("text-ok"))).toEqual([true, true]);
  });

  it("renders the generic layout for a bundle with no view", () => {
    render(<WorkItemView result={toolResult(noViewBundle)} host={host()} />);
    expect(screen.queryByTestId("declared-record")).toBeNull();
    expect(screen.getByText(/fields shown/).textContent).toBe("· 7 of 7 fields shown");
    expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: approved");
  });

  it("text answer alone renders identically", () => {
    const { container: structured } = render(<WorkItemView result={toolResult(payorBundle)} host={host()} />);
    const expected = structured.innerHTML;
    cleanup();
    const { container } = render(<WorkItemView result={toolResult(payorBundle, false)} host={host()} />);
    expect(screen.getByTestId("declared-record")).toBeTruthy();
    expect(container.innerHTML).toBe(expected);
  });

  it("reads the step list from envelopes, not the steps count", () => {
    render(<WorkItemView result={toolResult(noViewBundle)} host={host()} />);
    const checks = screen.getByText(/^What was checked/).closest("div")!;
    expect(checks.querySelector("h3")!.textContent).toBe("What was checked · 9 steps");
    expect(checks.querySelectorAll("li")).toHaveLength(9);
  });

  it("no envelopes list draws no checks", () => {
    const { envelopes: _omit, ...missing } = payorBundle;
    for (const bundle of [missing, { ...payorBundle, envelopes: 9 }]) {
      render(<WorkItemView result={toolResult(bundle)} host={host()} />);
      expect(screen.getByTestId("work-item-view")).toBeTruthy();
      expect(screen.queryByText(/What was checked/)).toBeNull();
      expect(screen.queryByTestId("view-timeline")).toBeNull();
      cleanup();
    }
  });

  it.each<[string, ToolResult]>([
    ["text that is not JSON", { content: [{ type: "text", text: "Work item PA-2026-001: approved" }] }],
    ["JSON that is not an object", { content: [{ type: "text", text: "[1, 2]" }] }],
    ["JSON that is not an answer bundle", { content: [{ type: "text", text: '{"items": []}' }] }],
    ["no content at all", {}],
  ])("unparseable answer shows only the notice: %s", (_case, result) => {
    const { container } = render(<WorkItemView result={result} host={host()} />);
    expect(container.textContent).toBe(NOTICE);
    expect(screen.queryByTestId("work-item-view")).toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  describe("gate footer is read-only state", () => {
    const signature = {
      signer: "Dr. Reviewer", signoff_type: "part11_single", signed_at: "2026-11-10T10:00:00Z",
    };

    function footer() {
      return screen.getByTestId("work-item-view").querySelector("footer")!;
    }

    it("shows an awaiting gate with the plan's signoff wording and no control", () => {
      render(<WorkItemView result={toolResult(payorBundle)} host={host()} />);
      expect(within(footer()).getByText("Awaiting signature")).toBeTruthy();
      expect(within(footer()).getByText("This decision needs electronic signature (21 CFR Part 11).")).toBeTruthy();
      expect(screen.queryByRole("button")).toBeNull();
      expect(screen.queryByText(/Sign & seal|Decline/)).toBeNull();
    });

    it("words a signoff kind it does not spell out as the plan names it", () => {
      const plan = { ...payorBundle.plan as object, signoff: "dual_review" };
      render(<WorkItemView result={toolResult({ ...payorBundle, plan })} host={host()} />);
      expect(within(footer()).getByText("This decision needs dual_review.")).toBeTruthy();
    });

    it("shows a signed run's signature and no control", () => {
      render(<WorkItemView result={toolResult({ ...payorBundle, awaiting_signoff: false, signature })} host={host()} />);
      expect(footer().textContent).toBe("✓ Signed by Dr. Reviewer on 2026-11-10T10:00:00Z · 9 steps sealed");
      expect(screen.queryByRole("button")).toBeNull();
    });

    it("shows no gate when the answer neither awaits nor carries a signature", () => {
      render(<WorkItemView result={toolResult({ ...payorBundle, awaiting_signoff: false })} host={host()} />);
      expect(footer().textContent).toBe("");
      expect(screen.queryByRole("button")).toBeNull();
    });
  });

  describe("input gate (bundle v1.1.0)", () => {
    function footer() {
      return screen.getByTestId("work-item-view").querySelector("footer")!;
    }

    it("draws the gate form from pending_input in the footer, not the signature state", () => {
      render(<WorkItemView result={toolResult(parkedBundle)} host={host()} />);
      const form = within(footer()).getByTestId("gate-form");
      expect(within(form).getByText("Waiting for your input")).toBeTruthy();
      expect(within(form).getByText("This run needs these answers before it continues.")).toBeTruthy();
      expect(within(form).getByLabelText("prior trial drug").tagName).toBe("TEXTAREA");
      expect(within(form).getByLabelText("trial weeks").getAttribute("type")).toBe("number");
      expect(within(form).getByRole("button", { name: "Answer & resume" })).toBeTruthy();
      expect(screen.queryByText("Awaiting signature")).toBeNull();
      expect(screen.queryByText(/^Decision:/)).toBeNull();
    });

    it("draws no form when the bundle is not parked", () => {
      render(<WorkItemView result={toolResult({ ...parkedBundle, awaiting_input: false, pending_input: null })} host={host()} />);
      expect(screen.queryByTestId("gate-form")).toBeNull();
    });

    const answered = { from: "step_therapy", to: "criteria", fields: ["prior_trial_drug", "trial_weeks"] };

    async function answer(h: ReturnType<typeof host>) {
      render(<WorkItemView result={toolResult(parkedBundle)} host={h} />);
      fireEvent.change(screen.getByLabelText("prior trial drug"), { target: { value: "metformin" } });
      fireEvent.change(screen.getByLabelText("trial weeks"), { target: { value: "12" } });
      fireEvent.click(screen.getByRole("button", { name: "Answer & resume" }));
      await act(async () => {});
    }

    it("submits the session and the typed answers to the host's answer tool", async () => {
      const h = host(toolResult({ ok: true, status: "awaiting_signoff", session_id: "run-payor-demo", answered }));
      await answer(h);
      expect(h.answerInput.mock.calls).toEqual([["run-payor-demo", { prior_trial_drug: "metformin", trial_weeks: 12 }]]);
    });

    it("flips to the signature gate when the run parks for signature next", async () => {
      await answer(host(toolResult({
        ok: true, status: "awaiting_signoff", requires_human_signature: true, session_id: "run-payor-demo", answered,
      })));
      expect(screen.queryByTestId("gate-form")).toBeNull();
      expect(within(footer()).getByText("Awaiting signature")).toBeTruthy();
      expect(within(footer()).getByText("This decision needs electronic signature (21 CFR Part 11).")).toBeTruthy();
    });

    it("flips to the decision when the run completes", async () => {
      await answer(host(toolResult({
        ok: true, status: "complete", session_id: "run-payor-demo", answered,
        paused: false, decision: "approved", final_state: "approved", state: "approved", steps: 10,
      })));
      expect(screen.queryByTestId("gate-form")).toBeNull();
      expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: Authorized");
      expect(footer().textContent).toBe("");
    });

    it("flips to the next gate's form when the run parks for input again", async () => {
      await answer(host(toolResult({
        ok: true, status: "awaiting_input", requires_human_input: true, session_id: "run-payor-demo", answered,
        detail: "transition 'criteria' -> 'approved' awaits human input: ['reviewer_note']",
        tenant_id: "demo", from_state: "criteria", to_state: "approved", fields: ["reviewer_note"],
      })));
      const form = within(footer()).getByTestId("gate-form");
      expect(within(form).queryByLabelText("prior trial drug")).toBeNull();
      expect((within(form).getByLabelText("reviewer note") as HTMLTextAreaElement).value).toBe("");
    });

    it("treats an idempotent reply as success and closes the gate", async () => {
      await answer(host(toolResult({ ok: true, session_id: "run-payor-demo", answered, idempotent: true, state: "approved" })));
      expect(screen.queryByTestId("gate-form")).toBeNull();
      expect(screen.queryByRole("alert")).toBeNull();
    });

    it("shows a refusal under Not accepted with the teaching detail, keeps the values and calls once", async () => {
      const detail = "answers refused, nothing sealed: trial_weeks must be at least 1";
      const h = host(toolResult({ ok: false, error: "ContractViolation", detail }));
      await answer(h);
      expect(screen.getByRole("alert").textContent).toBe(`Not accepted${detail}`);
      expect((screen.getByLabelText("prior trial drug") as HTMLTextAreaElement).value).toBe("metformin");
      expect((screen.getByLabelText("trial weeks") as HTMLInputElement).value).toBe("12");
      expect(h.answerInput).toHaveBeenCalledTimes(1);
    });

    it("shows a refusal that names only its error", async () => {
      await answer(host(toolResult({ ok: false, error: "WrongIdKind" }, false)));
      expect(screen.getByRole("alert").textContent).toBe("Not acceptedWrongIdKind");
    });

    it("shows an isError reply's text as the refusal", async () => {
      await answer(host({ isError: true, content: [{ type: "text", text: "The gateway could not reach fabric." }] }));
      expect(screen.getByRole("alert").textContent).toBe("Not acceptedThe gateway could not reach fabric.");
      expect(screen.getByTestId("gate-form")).toBeTruthy();
    });

    it("disables submit only while the call is in flight", async () => {
      let reply!: (r: ToolResult) => void;
      const h = host();
      h.answerInput.mockImplementation(() => new Promise<ToolResult>((r) => { reply = r; }));
      await answer(h);
      expect(screen.getByRole("button", { name: "Answer & resume" }).hasAttribute("disabled")).toBe(true);
      await act(async () => reply(toolResult({ ok: false, error: "InputGateConflict", detail: "not parked" })));
      expect(screen.getByRole("button", { name: "Answer & resume" }).hasAttribute("disabled")).toBe(false);
      expect(h.answerInput).toHaveBeenCalledTimes(1);
    });

    it("draws a new tool result fresh, not the earlier answer's next stop", async () => {
      const h = host(toolResult({ ok: true, status: "awaiting_signoff", session_id: "run-payor-demo", answered }));
      await answer(h);
      cleanup();
      render(<WorkItemView result={toolResult({ ...parkedBundle })} host={h} />);
      expect(screen.getByTestId("gate-form")).toBeTruthy();
    });
  });

  describe("app_url link", () => {
    it("renders Open in openworker wired to the host's open-link when the answer carries app_url", () => {
      const h = host();
      const url = "https://openworker.example/inbox/run-payor-demo";
      render(<WorkItemView result={toolResult({ ...payorBundle, app_url: url })} host={h} />);
      fireEvent.click(screen.getByRole("button", { name: "Open in openworker" }));
      expect(h.openLink).toHaveBeenCalledWith(url);
    });

    it("renders no link when the answer carries no app_url", () => {
      render(<WorkItemView result={toolResult(payorBundle)} host={host()} />);
      expect(screen.queryByText("Open in openworker")).toBeNull();
    });
  });

  it("never shows a decision the answer does not carry", () => {
    const { decision: _omit, ...undecided } = payorBundle;
    render(<WorkItemView result={toolResult(undecided)} host={host()} />);
    expect(screen.queryByText(/Decision/)).toBeNull();
    expect(screen.getByTestId("work-item-view").querySelector("header")!.textContent).not.toMatch(/approved|Authorized/);
  });

  describe("error answers render plainly", () => {
    const refusal = { ok: false, error: "RunNotComplete", detail: "session run-payor-demo has not finished" };

    function expectPlain(...lines: string[]) {
      const shown = screen.getByTestId("work-item-error");
      expect(Array.from(shown.children).map((n) => n.textContent)).toEqual(lines);
      expect(screen.queryByText(/Decision/)).toBeNull();
      expect(screen.queryByTestId("declared-record")).toBeNull();
      expect(screen.queryByText(/fields shown/)).toBeNull();
      expect(document.querySelector(".text-ok, .text-warn, .text-danger")).toBeNull();
    }

    it("shows an isError answer's text", () => {
      render(<WorkItemView result={{ isError: true, content: [{ type: "text", text: "The gateway could not reach fabric." }], structuredContent: payorBundle }} host={host()} />);
      expectPlain("The gateway could not reach fabric.");
    });

    it("shows an ok:false answer's error and detail from structured content", () => {
      render(<WorkItemView result={toolResult(refusal)} host={host()} />);
      expectPlain("RunNotComplete", "session run-payor-demo has not finished");
    });

    it("shows an ok:false text answer the same way", () => {
      render(<WorkItemView result={toolResult({ ok: false, error: "WrongIdKind" }, false)} host={host()} />);
      expectPlain("WrongIdKind");
    });
  });
});
