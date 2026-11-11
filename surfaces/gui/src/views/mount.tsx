// Starts the renderer app: connects to the host, follows its theme (light until the host says
// otherwise) and draws the work item from the tool result the host sends.
import { useSyncExternalStore } from "react";
import { createRoot } from "react-dom/client";

import { connect, type ToolResult } from "./host";
import { WorkItemView } from "./WorkItemView";

export function mount(root: HTMLElement, parent: Window = window.parent) {
  document.documentElement.dataset.theme = "light";
  let latest: ToolResult | undefined;
  const listeners = new Set<() => void>();
  const host = connect("regagentic-work-item", {
    onToolResult(result) {
      latest = result;
      listeners.forEach((l) => l());
    },
    onTheme(theme) {
      document.documentElement.dataset.theme = theme;
    },
  }, parent);
  const subscribe = (l: () => void) => {
    listeners.add(l);
    return () => { listeners.delete(l); };
  };
  function App() {
    return <WorkItemView result={useSyncExternalStore(subscribe, () => latest)} host={host} />;
  }
  createRoot(root).render(<App />);
}
