import { useState } from "react";
import { App } from "./App";
import { FabricLogin } from "./components/FabricLogin";
import { isFabricSignedIn } from "./fabric";

// The app gate: OpenWorker's chat/workspace is only reachable after the fabric login.
// (Standalone local use is intentionally gone — every session runs against the governed kernel.)
export function Root() {
  const [signedIn, setSignedIn] = useState(isFabricSignedIn());
  if (!signedIn) return <FabricLogin onSignedIn={() => setSignedIn(true)} />;
  return <App />;
}
