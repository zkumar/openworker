// The RunPanel input gate footer (OW-F-018 ticket 03): a run parked on an input gate shows the
// shared gate form where the signature gate sits, wired to the panel's answer submit.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPanel, type RunData } from "./RunPanel";

const parked: RunData = {
  channel: "email",
  agent: "payor-prior-auth",
  decision: "step_therapy",
  awaiting_signoff: false,
  awaiting_input: true,
  pending_input: { from: "step_therapy", to: "criteria", fields: [{ name: "clinical_notes", type: "str" }, { name: "units", type: "int" }] },
  plan: { name: "prior_auth", signoff: "part11_single", states: ["received", "step_therapy", "criteria", "approved"] },
  record: { request_id: "REQ-1", units: 1 },
  steps: [],
};

function footer() {
  return screen.getByTestId("run-panel").querySelector("footer")!;
}

describe("RunPanel input gate footer", () => {
  afterEach(cleanup);

  it("shows the gate form with the agreed copy instead of the signature buttons", () => {
    render(<RunPanel data={parked} pending onDecide={vi.fn()} onAnswer={vi.fn()} />);
    expect(footer().textContent).toContain("Waiting for your input");
    expect(footer().textContent).toContain("This run needs these answers before it continues.");
    const buttons = Array.from(footer().querySelectorAll("button")).map((b) => b.textContent);
    expect(buttons).toEqual(["Answer & resume"]);
    expect(screen.getByLabelText("clinical notes").tagName).toBe("TEXTAREA");
    expect(screen.getByLabelText("units").getAttribute("type")).toBe("number");
  });

  it("hands the typed answers to the panel's answer submit once", async () => {
    const onAnswer = vi.fn().mockResolvedValue({ ok: true });
    render(<RunPanel data={parked} pending onDecide={vi.fn()} onAnswer={onAnswer} />);
    fireEvent.change(screen.getByLabelText("clinical notes"), { target: { value: "PT failed" } });
    fireEvent.change(screen.getByLabelText("units"), { target: { value: "2" } });
    await act(async () => fireEvent.click(screen.getByText("Answer & resume")));
    expect(onAnswer.mock.calls).toEqual([[{ clinical_notes: "PT failed", units: 2 }]]);
  });

  it("shows a refusal as Not accepted with its detail and keeps the values", async () => {
    const onAnswer = vi.fn().mockResolvedValue({ ok: false, detail: "units: must be at most 1" });
    render(<RunPanel data={parked} pending onDecide={vi.fn()} onAnswer={onAnswer} />);
    fireEvent.change(screen.getByLabelText("clinical notes"), { target: { value: "PT failed" } });
    fireEvent.change(screen.getByLabelText("units"), { target: { value: "2" } });
    await act(async () => fireEvent.click(screen.getByText("Answer & resume")));
    expect(footer().textContent).toContain("Not accepted");
    expect(footer().textContent).toContain("units: must be at most 1");
    expect((screen.getByLabelText("clinical notes") as HTMLTextAreaElement).value).toBe("PT failed");
    expect(onAnswer).toHaveBeenCalledTimes(1);
  });

  it("flips to the signature gate when the refreshed item is the run's next stop", () => {
    const { rerender } = render(<RunPanel data={parked} pending onDecide={vi.fn()} onAnswer={vi.fn()} />);
    rerender(
      <RunPanel
        data={{ ...parked, awaiting_input: false, pending_input: null, awaiting_signoff: true, decision: "awaiting_signature" }}
        pending
        onDecide={vi.fn()}
        onAnswer={vi.fn()}
      />,
    );
    expect(footer().textContent).toContain("Waiting for your signature");
    expect(footer().textContent).not.toContain("Waiting for your input");
  });

  it("draws the next gate's fields when the run parks again", () => {
    const { rerender } = render(<RunPanel data={parked} pending onDecide={vi.fn()} onAnswer={vi.fn()} />);
    rerender(
      <RunPanel
        data={{ ...parked, pending_input: { from: "criteria", to: "approved", fields: [{ name: "reviewer_note", type: null }] } }}
        pending
        onDecide={vi.fn()}
        onAnswer={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("reviewer note")).toBeTruthy();
    expect(screen.queryByLabelText("clinical notes")).toBeNull();
  });
});
