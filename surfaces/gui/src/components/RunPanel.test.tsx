// The generic RunPanel layout, pinned before the agent-declared view lands (OW-F-015 ticket 01).
// These tests describe the panel as it renders today, quirks included; with no view stored the
// panel must keep rendering exactly this.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RunPanel, type RunData } from "./RunPanel";

const steps: NonNullable<RunData["steps"]> = [
  { type: "transition", summary: "Member eligibility confirmed", state_before: "received", state_after: "checked", sha256: "aaaaaaaaaaaabbbbbbbbbbbb", at: "2026-11-10T09:00:00Z" },
  { type: "transition", state_before: "checked", state_after: "reviewed", sha256: "cccccccccccc0000", at: "2026-11-10T09:01:00Z" },
  { type: "transition", summary: "Units within the per-authorization limit", state_before: "reviewed", state_after: "awaiting_signature", sha256: "dddddddddddd1111", at: "2026-11-10T09:02:00Z" },
];

const pendingItem: RunData = {
  channel: "email",
  agent: "payor-prior-auth",
  decision: "awaiting_signature",
  awaiting_signoff: true,
  plan: { name: "prior_auth", signoff: "part11_single", states: ["received", "checked", "reviewed", "awaiting_signature", "approved"] },
  record: { request_id: "REQ-1", capa_id: "CAPA-1", slr_id: "SLR-1", procedure_code: "97110", units: 1, place_of_service: "office" },
  steps,
};

const signedItem: RunData = {
  ...pendingItem,
  decision: "awaiting_signature",
  signature: { approver: "Dr. Reviewer", at: "2026-11-10T10:00:00Z", state_before: "awaiting_signature", state_after: "approved", signoff: "part11_single", sha256: "eeee" },
  receipt: { request_id: "REQ-1", outcome: "approved" },
};

const manyFields: Record<string, unknown> = {
  request_id: "REQ-9", f1: "one", f2: "two", f3: "three", f4: "four", f5: "five", f6: "six", f7: "seven", f8: "eight",
};

function panel() {
  return screen.getByTestId("run-panel");
}

function headerStatus() {
  return panel().querySelector("header > span:last-child") as HTMLElement;
}

function decisionSpan() {
  return screen.getByText(/^Decision:/).querySelector("span") as HTMLElement;
}

function fieldLabels() {
  return Array.from(panel().querySelectorAll(".grid .uppercase")).map((n) => n.textContent);
}

function technicalDetails() {
  return screen.getByText("Technical details").closest("details") as HTMLDetailsElement;
}

describe("RunPanel generic layout", () => {
  afterEach(cleanup);

  it("names the channel and the handling agent in the header", () => {
    render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
    const header = panel().querySelector("header")!;
    expect(header.textContent).toContain("email");
    expect(header.textContent).toContain("handled by");
    expect(header.textContent).toContain("payor-prior-auth");
  });

  it("falls back to the word channel when the item names no channel", () => {
    render(<RunPanel data={{ ...pendingItem, channel: undefined }} pending onDecide={vi.fn()} />);
    expect(panel().querySelector("header")!.textContent).toContain("channel");
  });

  describe("record grid", () => {
    it("hides the hygiene ids and shows every other record field with spaced labels", () => {
      render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
      expect(fieldLabels()).toEqual(["procedure code", "units", "place of service"]);
      expect(panel().textContent).not.toContain("REQ-1");
      expect(panel().textContent).not.toContain("CAPA-1");
      expect(panel().textContent).not.toContain("SLR-1");
      expect(screen.getByText("97110").getAttribute("title")).toBe("97110");
    });

    it("counts the shown fields against the visible fields and offers no toggle at six or fewer", () => {
      render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
      expect(screen.getByText(/fields shown/).textContent).toBe("· 3 of 3 fields shown");
      expect(screen.queryByText(/Show (all|fewer)/)).toBeNull();
    });

    it("shows all fields at first past six, and the toggle folds them to six and back", () => {
      render(<RunPanel data={{ ...pendingItem, record: manyFields }} pending onDecide={vi.fn()} />);
      expect(fieldLabels()).toHaveLength(8);
      expect(screen.getByText(/fields shown/).textContent).toBe("· 8 of 8 fields shown");
      fireEvent.click(screen.getByText("Show fewer"));
      expect(fieldLabels()).toEqual(["f1", "f2", "f3", "f4", "f5", "f6"]);
      expect(screen.getByText(/fields shown/).textContent).toBe("· 6 of 8 fields shown");
      fireEvent.click(screen.getByText("Show all 8"));
      expect(fieldLabels()).toHaveLength(8);
    });

    it("renders the request block with zero fields when the item has no record", () => {
      render(<RunPanel data={{ ...pendingItem, record: undefined }} pending onDecide={vi.fn()} />);
      expect(screen.getByText(/fields shown/).textContent).toBe("· 0 of 0 fields shown");
    });
  });

  describe("steps list", () => {
    it("lists every step numbered, in the pack's words, falling back to the transition", () => {
      render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
      const block = screen.getByText(/What was checked/).closest("div")!;
      expect(screen.getByText(/What was checked/).textContent).toBe("What was checked · 3 steps");
      const rows = Array.from(block.querySelectorAll("ol > li")).map((li) => li.textContent);
      expect(rows).toEqual([
        "1Member eligibility confirmed",
        "2checked → reviewed",
        "3Units within the per-authorization limit",
      ]);
    });

    it("omits the steps block when there are no steps", () => {
      render(<RunPanel data={{ ...pendingItem, steps: [] }} pending onDecide={vi.fn()} />);
      expect(screen.queryByText(/What was checked/)).toBeNull();
    });
  });

  describe("decision text and tone", () => {
    it("labels the header status but shows the raw decision name in the answer block", () => {
      render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("awaiting signature");
      expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: awaiting_signature");
    });

    it("explains the decision with the last step's summary", () => {
      render(<RunPanel data={pendingItem} pending onDecide={vi.fn()} />);
      expect(screen.getByText(/^Decision:/).nextElementSibling!.textContent).toBe("Units within the per-authorization limit");
    });

    it("prefers the signature's resulting state over the run decision", () => {
      render(<RunPanel data={signedItem} pending={false} onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("approved");
      expect(decisionSpan().textContent).toBe("approved");
    });

    it.each([
      ["approved", "text-ok"],
      ["closed", "text-ok"],
      ["denied", "text-danger"],
      ["escalated", "text-warn"],
      ["pended", "text-warn"],
      ["revise", "text-warn"],
      ["awaiting_signature", "text-ink"],
      ["some_pack_state", "text-ink"],
    ])("tones the %s decision %s in the header and the answer", (decision, tone) => {
      render(<RunPanel data={{ ...pendingItem, decision }} pending onDecide={vi.fn()} />);
      expect(headerStatus().className).toBe("text-[13px] font-semibold " + tone);
      expect(decisionSpan().className).toBe(tone);
    });
  });

  describe("gate footer", () => {
    it("asks for the named signature and offers sign and decline while pending", () => {
      const onDecide = vi.fn();
      render(<RunPanel data={pendingItem} pending onDecide={onDecide} />);
      const footer = panel().querySelector("footer")!;
      expect(footer.textContent).toContain("Waiting for your signature");
      expect(footer.textContent).toContain("This decision needs electronic signature (21 CFR Part 11). Signing is final.");
      const buttons = Array.from(footer.querySelectorAll("button")).map((b) => b.textContent);
      expect(buttons).toEqual(["Sign & seal", "Decline"]);
      fireEvent.click(screen.getByText("Sign & seal"));
      fireEvent.click(screen.getByText("Decline"));
      expect(onDecide.mock.calls).toEqual([["once"], ["deny"]]);
    });

    it("names an unknown signoff as declared, and says sign-off when the plan has none", () => {
      render(<RunPanel data={{ ...pendingItem, plan: { ...pendingItem.plan, signoff: "dual_control" } }} pending onDecide={vi.fn()} />);
      expect(panel().querySelector("footer")!.textContent).toContain("This decision needs dual_control. Signing is final.");
      cleanup();
      render(<RunPanel data={{ ...pendingItem, plan: undefined }} pending onDecide={vi.fn()} />);
      expect(panel().querySelector("footer")!.textContent).toContain("This decision needs sign-off. Signing is final.");
    });

    it("shows who signed, when, and how many steps were sealed once signed", () => {
      render(<RunPanel data={signedItem} pending={false} onDecide={vi.fn()} />);
      const footer = panel().querySelector("footer")!;
      expect(footer.textContent).toBe("✓ Signed by Dr. Reviewer on 2026-11-10T10:00:00Z · 3 steps sealed");
      expect(footer.querySelector("button")).toBeNull();
    });

    it("leaves the date out of the signed line when the signature has none", () => {
      render(<RunPanel data={{ ...signedItem, signature: { ...signedItem.signature, at: undefined } }} pending={false} onDecide={vi.fn()} />);
      expect(panel().querySelector("footer")!.textContent).toBe("✓ Signed by Dr. Reviewer · 3 steps sealed");
    });

    it("renders an empty footer when neither pending nor signed", () => {
      render(<RunPanel data={pendingItem} pending={false} onDecide={vi.fn()} />);
      expect(panel().querySelector("footer")!.textContent).toBe("");
    });
  });

  describe("Technical details", () => {
    it("opens by default with the sealed steps, the declared process and the output JSON", () => {
      render(<RunPanel data={signedItem} pending={false} onDecide={vi.fn()} />);
      const details = technicalDetails();
      expect(details.open).toBe(true);
      const sealed = Array.from(details.querySelectorAll("ol > li")).map((li) => li.textContent);
      expect(sealed).toEqual([
        "1. received → checked · aaaaaaaaaaaa",
        "2. checked → reviewed · cccccccccccc",
        "3. reviewed → awaiting_signature · dddddddddddd",
      ]);
      expect(details.textContent).toContain("Declared process · prior_auth");
      expect(details.textContent).toContain("received → checked → reviewed → awaiting_signature → approved");
      expect(details.textContent).toContain("Output (JSON)");
      expect(details.querySelector("pre")!.textContent).toBe('{\n  "request_id": "REQ-1",\n  "outcome": "approved"\n}');
    });

    it("shows only the summary when there are no steps, plan states or receipt", () => {
      render(<RunPanel data={{ ...pendingItem, steps: [], plan: undefined }} pending onDecide={vi.fn()} />);
      const details = technicalDetails();
      expect(details.textContent).toBe("Technical details");
    });
  });

  describe("running state", () => {
    it("shows in progress in the header and no answer block", () => {
      render(<RunPanel data={{ ...pendingItem, running: true, steps: [] }} pending={false} onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("in progress…");
      expect(headerStatus().className).toContain("text-accent");
      expect(screen.queryByText(/^Decision:/)).toBeNull();
      expect(screen.getByText(/fields shown/)).toBeTruthy();
    });
  });

  describe("error state", () => {
    const failed: RunData = { channel: "email", agent: "payor-prior-auth", error: "fabric unreachable", record: { units: 1 } };

    it("says the request could not run and that it will retry", () => {
      render(<RunPanel data={failed} pending={false} onDecide={vi.fn()} />);
      const answer = screen.getByText("This request could not run").parentElement!;
      expect(answer.className).toContain("text-danger");
      expect(answer.textContent).toContain("fabric unreachable");
      expect(answer.textContent).toContain("Retrying automatically.");
      expect(screen.queryByText(/^Decision:/)).toBeNull();
    });

    it("says the request was rejected and does not promise a retry when retrying is false", () => {
      render(<RunPanel data={{ ...failed, retrying: false, error: "refused: 422" }} pending={false} onDecide={vi.fn()} />);
      const answer = screen.getByText("This request was rejected").parentElement!;
      expect(answer.textContent).toContain("refused: 422");
      expect(screen.queryByText("Retrying automatically.")).toBeNull();
    });
  });

  describe("not_found state", () => {
    it("decides not found in warn tone and says nothing needs signing", () => {
      render(<RunPanel data={{ channel: "email", agent: "payor-prior-auth", decision: "not_found", not_found: true, record: { units: 1 } }} pending={false} onDecide={vi.fn()} />);
      expect(headerStatus().textContent).toBe("not found");
      expect(headerStatus().className).toContain("text-warn");
      expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: not found");
      expect(decisionSpan().className).toBe("text-warn");
      expect(panel().textContent).toContain("This request is not in the record system, so it was rejected. Nothing needs to be signed.");
    });
  });
});
