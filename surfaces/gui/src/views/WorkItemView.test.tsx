// The renderer app's work-item view (OW-F-016 ticket 02): the answer bundle drawn through the
// shared core with RunPanel semantics, the fallback order of adr-text-answer-whole-contract, and
// the read-only gate of adr-read-only-renderer-v1.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPanel, type RunData } from "../components/RunPanel";
import { workItemStates } from "../gallery/states/work-item";
import { invalidViewBundle, noViewBundle, payorBundle, toolResult } from "./fixtures";
import type { ToolResult } from "./host";
import { WorkItemView } from "./WorkItemView";

const NOTICE = "This work item can't be drawn here. The text answer above is complete.";
const host = () => ({ openLink: vi.fn(async () => undefined) });
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
      approver: "Dr. Reviewer", at: "2026-11-10T10:00:00Z", state_before: "approved", state_after: "approved",
      signoff: "part11_single", sha256: "e".repeat(64),
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
