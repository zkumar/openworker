import { App } from "./App";
import { FabricBar } from "./components/FabricBar";

// Chat is the product; identity is a bar above it. Signing in sets the org (fixed domain)
// and the person's role — the conversation runs inside that frame.
export function Root() {
  return (
    <div className="h-screen flex flex-col">
      <FabricBar />
      <div className="flex-1 min-h-0 app-shell">
        <App />
      </div>
    </div>
  );
}
