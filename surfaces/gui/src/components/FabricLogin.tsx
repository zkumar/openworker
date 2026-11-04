import { useState } from "react";
import { fabricLogin } from "../fabric";

// Full-screen sign-in gate: OpenWorker is only usable once the fabric identity is proven
// (the harness is a client of the governed kernel, not a standalone local app).
const INPUT =
  "w-full px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";

export function FabricLogin({ onSignedIn }: { onSignedIn: () => void }) {
  const [username, setUsername] = useState("dr.md");
  const [password, setPassword] = useState("test");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await fabricLogin(username, password);
      onSignedIn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-paper p-6">
      <form
        className="w-full max-w-sm rounded-xl2 border border-line bg-panel p-6 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <div>
          <h1 className="text-[16px] font-semibold text-ink">Sign in</h1>
          <p className="text-[13px] text-muted mt-1">Sign in to your organization to use OpenWorker.</p>
        </div>
        <input
          className={INPUT}
          aria-label="username"
          placeholder="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />
        <input
          className={INPUT}
          aria-label="password"
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button
          type="submit"
          className="w-full text-[13px] px-3 py-2 rounded-lg bg-accent text-white disabled:opacity-40"
          disabled={busy}
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p className="text-[13px] text-red-500">{error}</p>}
      </form>
    </div>
  );
}
