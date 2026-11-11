// The payor demo view, fabric CONTRACTS.md §13's worked example (view v1.0.0, commit 5ec0600),
// rendered from the gallery fixture the ux and ui lenses screenshot (OW-F-015 ticket 05).
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { statePayload } from "../gallery/states";
import { RunPanel, type RunData } from "./RunPanel";

const demo = statePayload("work-item", "payor-demo") as RunData;

describe("RunPanel payor demo view", () => {
  afterEach(cleanup);

  it("carries the §13 worked example verbatim", () => {
    expect(demo.view).toEqual({
      view: "1.0.0",
      record: [
        { component: "header", title_field: "procedure_code", subtitle_field: "member_id" },
        { component: "field_group", label: "Clinical", fields: ["clinical_notes", "requested_units"] },
        { component: "gauge", label: "Units against per-authorization limit", value_field: "requested_units", max: 1 },
        { component: "key_value", fields: ["provider_npi", "member_id", "request_date", "requested_service_date"], demoted: true },
      ],
      checks: { component: "timeline", numbered: true },
      decision_labels: { approved: "Authorized", denied: "Not authorized", pended: "Pended for review" },
    });
  });

  it("renders the header, the Clinical group, the gauge against max 1 and the demoted key_value group", () => {
    const record = demo.record as Record<string, unknown>;
    render(<RunPanel data={demo} pending onDecide={vi.fn()} />);
    const declared = screen.getByTestId("declared-record");

    const header = within(declared).getByTestId("view-header");
    expect(within(header).getByText(String(record.procedure_code))).toBeTruthy();
    expect(within(header).getByText(String(record.member_id))).toBeTruthy();

    const clinical = within(declared).getByRole("group", { name: "Clinical" });
    expect(within(clinical).getByText(String(record.clinical_notes))).toBeTruthy();
    expect(within(clinical).getByText("requested units")).toBeTruthy();

    const gauge = within(declared).getByRole("figure", { name: "Units against per-authorization limit" });
    const rows = Array.from(within(gauge).getByRole("table").querySelectorAll("tr")).map((tr) =>
      Array.from(tr.children).map((c) => c.textContent),
    );
    expect(rows).toEqual([["requested_units", "max"], [String(record.requested_units), "1"]]);

    const order = Array.from(declared.children).map((n) => n.getAttribute("data-testid"));
    expect(order[order.length - 1]).toBe("view-key-value-demoted");
    const demoted = screen.getByTestId("view-key-value-demoted");
    for (const field of ["provider_npi", "member_id", "request_date", "requested_service_date"])
      expect(within(demoted).getByText(String(record[field]))).toBeTruthy();

    expect(screen.getByTestId("view-timeline")).toBeTruthy();
    expect(screen.getByText("Technical details").closest("details")!.textContent).not.toContain("Declared view not rendered");
  });
});
