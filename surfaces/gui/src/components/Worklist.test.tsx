// OW-F-018: a run parked on an input gate (fabric §15) is surfaced as needing your answers,
// in the "Needs you" tab beside the runs waiting on a signature.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { Worklist } from "./Worklist";

const parked = {
  id: "w1",
  state: "pending",
  created_at: "2026-11-25T09:00:00",
  data: {
    record: { request_id: "PA-2026-001" },
    agent: "payor.demo.prior_auth",
    awaiting_signoff: false,
    awaiting_input: true,
    pending_input: { from: "step_therapy", to: "criteria", fields: [{ name: "clinical_notes", type: "str" }] },
  },
};
const sealed = {
  id: "w2",
  state: "resolved",
  created_at: "2026-11-25T08:00:00",
  data: { record: { request_id: "PA-2026-002" }, decision: "approved", signature: { approver: "a" } },
};

vi.mock("../api", () => ({
  getInbox: vi.fn(async () => [parked, sealed]),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Worklist parked run", () => {
  it("shows a run parked on input as needing your answers", async () => {
    render(<Worklist onOpen={() => {}} />);
    const row = await screen.findByTestId("worklist-row-w1");
    expect(row.textContent).toContain("needs your answers");
    expect(row.textContent).not.toContain("needs your signature");
  });

  it("lists it in the Needs you tab", async () => {
    render(<Worklist onOpen={() => {}} />);
    await screen.findByTestId("worklist-row-w1");
    fireEvent.click(screen.getByRole("button", { name: /Needs you/ }));
    await waitFor(() => expect(screen.queryByTestId("worklist-row-w2")).toBeNull());
    expect(screen.getByTestId("worklist-row-w1")).toBeTruthy();
  });
});
