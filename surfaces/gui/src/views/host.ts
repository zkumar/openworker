// The renderer app's line to its host (MCP Apps, protocol 2026-01-26): JSON-RPC 2.0 over
// postMessage with the parent window, written out here rather than taken from an SDK, so the
// self-contained renderer adds no runtime dependency (after MAUDE EWS host.ts).
//
// The view sends ui/initialize and then ui/notifications/initialized; the host sends the tool
// result (ui/notifications/tool-result, a CallToolResult) and its theme. The view reports its
// size so the host can fit the frame, answers ping and ui/resource-teardown, and asks the host
// to open a link. Read-only (adr-read-only-renderer-v1): opening a link is its only request.

/** A CallToolResult as the host passes it. */
export interface ToolResult {
  content?: { type: string; text?: string }[];
  structuredContent?: unknown;
  isError?: boolean;
}

/** What the view asks of its host. */
export interface Host {
  openLink(url: string): Promise<void>;
}

export type Theme = "light" | "dark";

interface Handlers {
  onToolResult(result: ToolResult): void;
  onTheme(theme: Theme): void;
}

const PROTOCOL_VERSION = "2026-01-26";

type Pending = { resolve: (v: unknown) => void; reject: (e: Error) => void };

/** Connect to the host in `parent`; returns the Host the view calls. */
export function connect(name: string, handlers: Handlers, parent: Window = window.parent): Host {
  let nextId = 1;
  const pending = new Map<number, Pending>();

  const post = (message: object) => parent.postMessage({ jsonrpc: "2.0", ...message }, "*");
  function request(method: string, params: object): Promise<unknown> {
    const id = nextId++;
    post({ id, method, params });
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  }
  const notify = (method: string, params: object) => post({ method, params });

  function hostContext(context: unknown) {
    const theme = (context as { theme?: unknown } | null | undefined)?.theme;
    if (theme === "light" || theme === "dark") handlers.onTheme(theme);
  }

  window.addEventListener("message", (event: MessageEvent) => {
    if (event.source !== parent) return;
    const msg = event.data;
    if (!msg || msg.jsonrpc !== "2.0") return;
    if (msg.method === undefined && typeof msg.id === "number" && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id)!;
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message ?? "The host refused the request."));
      else resolve(msg.result);
      return;
    }
    switch (msg.method) {
      case "ui/notifications/tool-result":
        handlers.onToolResult(msg.params ?? {});
        break;
      case "ui/notifications/host-context-changed":
        hostContext(msg.params);
        break;
      case "ui/resource-teardown":
      case "ping":
        post({ id: msg.id, result: {} });
        break;
    }
  });

  // The frame's size follows the view's content.
  let last = "";
  new ResizeObserver(() => {
    const el = document.documentElement;
    const size = { width: Math.ceil(el.scrollWidth), height: Math.ceil(el.scrollHeight) };
    const key = `${size.width}x${size.height}`;
    if (key === last) return;
    last = key;
    notify("ui/notifications/size-changed", size);
  }).observe(document.documentElement);

  request("ui/initialize", {
    protocolVersion: PROTOCOL_VERSION,
    appInfo: { name, version: "1.0.0" },
    appCapabilities: { availableDisplayModes: ["inline"] },
  }).then((result) => {
    hostContext((result as { hostContext?: unknown } | undefined)?.hostContext);
    notify("ui/notifications/initialized", {});
  });

  return {
    openLink: (url) => request("ui/open-link", { url }).then(() => undefined),
  };
}
