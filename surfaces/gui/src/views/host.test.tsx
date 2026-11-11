// The renderer app inside a (mocked) MCP Apps host, protocol 2026-01-26: the parent window is a
// real frame whose postMessage is spied, and the host's messages arrive as window messages from it.
import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { payorBundle, toolResult } from "./fixtures";
import { mount } from "./mount";

let parent: Window;
let sent: ReturnType<typeof vi.fn>;
let resized: () => void;

/** A message from the host, as the parent window posts it to the view. */
function fromHost(data: object, source: Window = parent) {
  act(() => {
    window.dispatchEvent(new MessageEvent("message", { data: { jsonrpc: "2.0", ...data }, source }));
  });
}

const messages = () => sent.mock.calls.map(([m]) => m);
const byMethod = (method: string) => messages().filter((m) => m.method === method);

async function initialized(hostContext: object = {}) {
  const init = byMethod("ui/initialize")[0];
  fromHost({ id: init.id, result: { protocolVersion: "2026-01-26", hostContext } });
  await act(async () => {});
}

describe("host bridge protocol", () => {
  beforeEach(() => {
    const frame = document.createElement("iframe");
    document.body.appendChild(frame);
    parent = frame.contentWindow!;
    sent = vi.fn();
    parent.postMessage = sent as unknown as Window["postMessage"];
    vi.stubGlobal("ResizeObserver", class {
      constructor(cb: () => void) { resized = cb; }
      observe() {}
      disconnect() {}
    });
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    delete document.documentElement.dataset.theme;
    act(() => mount(root, parent));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("sends ui/initialize for protocol 2026-01-26, then initialized once the host answers", async () => {
    expect(messages()[0]).toEqual({
      jsonrpc: "2.0", id: expect.any(Number), method: "ui/initialize",
      params: {
        protocolVersion: "2026-01-26",
        appInfo: { name: "regagentic-work-item", version: "1.0.0" },
        appCapabilities: { availableDisplayModes: ["inline"] },
      },
    });
    expect(byMethod("ui/notifications/initialized")).toEqual([]);
    await initialized();
    expect(byMethod("ui/notifications/initialized")).toEqual([
      { jsonrpc: "2.0", method: "ui/notifications/initialized", params: {} },
    ]);
  });

  it("draws the work item from the host's tool-result", () => {
    expect(screen.queryByTestId("work-item-view")).toBeNull();
    fromHost({ method: "ui/notifications/tool-result", params: toolResult(payorBundle) });
    expect(screen.getByTestId("declared-record")).toBeTruthy();
    expect(screen.getByText(/^Decision:/).textContent).toBe("Decision: Authorized");
  });

  it("starts light, takes the theme from hostContext and follows host-context-changed", async () => {
    expect(document.documentElement.dataset.theme).toBe("light");
    await initialized({ theme: "dark" });
    expect(document.documentElement.dataset.theme).toBe("dark");
    fromHost({ method: "ui/notifications/host-context-changed", params: { theme: "light" } });
    expect(document.documentElement.dataset.theme).toBe("light");
    fromHost({ method: "ui/notifications/host-context-changed", params: { theme: "dark" } });
    expect(document.documentElement.dataset.theme).toBe("dark");
    fromHost({ method: "ui/notifications/host-context-changed", params: { theme: "sepia" } });
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("notifies size-changed when the content's size changes, once per size", () => {
    resized();
    resized();
    expect(byMethod("ui/notifications/size-changed")).toEqual([
      { jsonrpc: "2.0", method: "ui/notifications/size-changed", params: { width: 0, height: 0 } },
    ]);
  });

  it("answers ping and ui/resource-teardown", () => {
    fromHost({ id: 41, method: "ping", params: {} });
    fromHost({ id: 42, method: "ui/resource-teardown", params: {} });
    expect(messages().filter((m) => m.id === 41 || m.id === 42)).toEqual([
      { jsonrpc: "2.0", id: 41, result: {} },
      { jsonrpc: "2.0", id: 42, result: {} },
    ]);
  });

  it("asks the host to open app_url through ui/open-link", () => {
    const url = "https://openworker.example/inbox/run-payor-demo";
    fromHost({ method: "ui/notifications/tool-result", params: toolResult({ ...payorBundle, app_url: url }) });
    fireEvent.click(screen.getByRole("button", { name: "Open in openworker" }));
    expect(byMethod("ui/open-link")).toEqual([
      { jsonrpc: "2.0", id: expect.any(Number), method: "ui/open-link", params: { url } },
    ]);
  });

  it("ignores messages that do not come from its host", () => {
    fromHost({ method: "ui/notifications/tool-result", params: toolResult(payorBundle) }, window);
    fromHost({ id: 7, method: "ping", params: {} }, window);
    expect(screen.queryByTestId("work-item-view")).toBeNull();
    expect(messages().filter((m) => m.id === 7)).toEqual([]);
  });
});
