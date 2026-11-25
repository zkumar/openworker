// The shared input gate form (OW-F-018): drawn from the bundle's pending_input alone
// (adr-gate-form-from-pending-input), one control per declared type, all fields required
// client-side, a refusal shown under "Not accepted" with the values kept, never retried.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GateForm, type PendingInput } from "./GateForm";

const allTypes: PendingInput = {
  from: "step_therapy",
  to: "criteria",
  fields: [
    { name: "reason", type: "str" },
    { name: "count", type: "int" },
    { name: "ratio", type: "float" },
    { name: "confirmed", type: "bool" },
    { name: "items", type: "list" },
    { name: "meta", type: "dict" },
    { name: "note", type: null },
  ],
};

function control(name: string) {
  return screen.getByLabelText(name) as HTMLInputElement | HTMLTextAreaElement;
}

function submit() {
  return screen.getByRole("button", { name: "Answer & resume" }) as HTMLButtonElement;
}

function fillAll() {
  fireEvent.change(control("reason"), { target: { value: "Conservative therapy failed" } });
  fireEvent.change(control("count"), { target: { value: "3" } });
  fireEvent.change(control("ratio"), { target: { value: "0.5" } });
  fireEvent.click(control("confirmed"));
  fireEvent.change(control("items"), { target: { value: '["a", 2]' } });
  fireEvent.change(control("meta"), { target: { value: '{"k": 1}' } });
  fireEvent.change(control("note"), { target: { value: "42" } });
}

describe("GateForm", () => {
  afterEach(cleanup);

  it("says what it waits for and draws one labelled control per pending field", () => {
    render(<GateForm pending={allTypes} onSubmit={vi.fn()} />);
    expect(screen.getByText("Waiting for your input")).toBeTruthy();
    expect(screen.getByText("This run needs these answers before it continues.")).toBeTruthy();
    expect(submit()).toBeTruthy();
  });

  it("draws str as a one-row textarea, int and float as number inputs, bool as a checkbox", () => {
    render(<GateForm pending={allTypes} onSubmit={vi.fn()} />);
    const reason = control("reason");
    expect(reason.tagName).toBe("TEXTAREA");
    expect(reason.getAttribute("rows")).toBe("1");
    expect(control("count").getAttribute("type")).toBe("number");
    expect(control("count").getAttribute("step")).toBe("1");
    expect(control("ratio").getAttribute("type")).toBe("number");
    expect(control("ratio").getAttribute("step")).toBe("any");
    expect(control("confirmed").getAttribute("type")).toBe("checkbox");
  });

  it("draws list, dict and an undeclared type as textareas", () => {
    render(<GateForm pending={allTypes} onSubmit={vi.fn()} />);
    expect(control("items").tagName).toBe("TEXTAREA");
    expect(control("meta").tagName).toBe("TEXTAREA");
    expect(control("note").tagName).toBe("TEXTAREA");
  });

  it("submits each value as its declared type: numbers, a boolean, parsed JSON, a raw string", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ok: true });
    render(<GateForm pending={allTypes} onSubmit={onSubmit} />);
    fillAll();
    await act(async () => fireEvent.click(submit()));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    expect(onSubmit).toHaveBeenCalledWith({
      reason: "Conservative therapy failed",
      count: 3,
      ratio: 0.5,
      confirmed: true,
      items: ["a", 2],
      meta: { k: 1 },
      note: "42",
    });
  });

  it("submits an unticked bool as false", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ok: true });
    render(<GateForm pending={{ fields: [{ name: "confirmed", type: "bool" }] }} onSubmit={onSubmit} />);
    await act(async () => fireEvent.click(submit()));
    expect(onSubmit).toHaveBeenCalledWith({ confirmed: false });
  });

  it("requires every field and does not submit while one is empty", async () => {
    const onSubmit = vi.fn();
    render(<GateForm pending={allTypes} onSubmit={onSubmit} />);
    fillAll();
    fireEvent.change(control("reason"), { target: { value: "" } });
    fireEvent.change(control("count"), { target: { value: "" } });
    await act(async () => fireEvent.click(submit()));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getAllByText("Required")).toHaveLength(2);
  });

  it("refuses invalid JSON and the wrong JSON shape for list and dict client-side", async () => {
    const onSubmit = vi.fn();
    render(<GateForm pending={allTypes} onSubmit={onSubmit} />);
    fillAll();
    fireEvent.change(control("items"), { target: { value: "[1, 2" } });
    fireEvent.change(control("meta"), { target: { value: "[1]" } });
    await act(async () => fireEvent.click(submit()));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Not valid JSON")).toBeTruthy();
    expect(screen.getByText("Must be a JSON object")).toBeTruthy();
  });

  it("refuses a fractional int client-side", async () => {
    const onSubmit = vi.fn();
    render(<GateForm pending={{ fields: [{ name: "count", type: "int" }] }} onSubmit={onSubmit} />);
    fireEvent.change(control("count"), { target: { value: "2.5" } });
    await act(async () => fireEvent.click(submit()));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByText("Must be a whole number")).toBeTruthy();
  });

  it("disables submit only while the call is in flight", async () => {
    let finish: (v: { ok: true }) => void = () => {};
    const onSubmit = vi.fn(() => new Promise<{ ok: true }>((r) => { finish = r; }));
    render(<GateForm pending={{ fields: [{ name: "reason", type: "str" }] }} onSubmit={onSubmit} />);
    fireEvent.change(control("reason"), { target: { value: "x" } });
    expect(submit().disabled).toBe(false);
    await act(async () => fireEvent.click(submit()));
    expect(submit().disabled).toBe(true);
    await act(async () => finish({ ok: true }));
    expect(submit().disabled).toBe(false);
  });

  it("shows a refusal under Not accepted with its detail, keeps the values, and never retries", async () => {
    const onSubmit = vi.fn().mockResolvedValue({ ok: false, detail: "count must be at most 2" });
    render(<GateForm pending={allTypes} onSubmit={onSubmit} />);
    fillAll();
    await act(async () => fireEvent.click(submit()));
    expect(screen.getByText("Not accepted")).toBeTruthy();
    expect(screen.getByText("count must be at most 2")).toBeTruthy();
    expect(control("reason").value).toBe("Conservative therapy failed");
    expect(control("count").value).toBe("3");
    expect((control("confirmed") as HTMLInputElement).checked).toBe(true);
    expect(control("items").value).toBe('["a", 2]');
    expect(submit().disabled).toBe(false);
    await act(async () => {});
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("clears the refusal when the human resubmits", async () => {
    const onSubmit = vi.fn()
      .mockResolvedValueOnce({ ok: false, detail: "count must be at most 2" })
      .mockResolvedValueOnce({ ok: true });
    render(<GateForm pending={allTypes} onSubmit={onSubmit} />);
    fillAll();
    await act(async () => fireEvent.click(submit()));
    fireEvent.change(control("count"), { target: { value: "2" } });
    await act(async () => fireEvent.click(submit()));
    expect(screen.queryByText("Not accepted")).toBeNull();
    expect(onSubmit).toHaveBeenCalledTimes(2);
  });
});
