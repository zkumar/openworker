import { useEffect, useState } from "react";
import {
  fabricLogin,
  fabricLogout,
  getFabricOrg,
  getFabricPersonas,
  isFabricSignedIn,
  type FabricOrg,
  type FabricPersona,
} from "../fabric";

// The identity bar above the chat: the org (whose DOMAIN is fixed by the deployment) and the
// person's ROLE within it (QA, complaint handling, …) — set at sign-in, not by the chat.
const ROLE_KEY = "fabricRole";
const CONTROL =
  "h-7 px-2 rounded-md border border-line bg-paper text-[12px] text-ink outline-none focus:border-accent";

export function FabricBar() {
  const [signedIn, setSignedIn] = useState(isFabricSignedIn());
  const [org, setOrg] = useState<FabricOrg | null>(null);
  const [personas, setPersonas] = useState<FabricPersona[]>([]);
  const [role, setRole] = useState<string>(() => {
    try { return localStorage.getItem(ROLE_KEY) || ""; } catch { return ""; }
  });
  const [username, setUsername] = useState("dr.md");
  const [password, setPassword] = useState("test");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!signedIn) return;
    getFabricOrg().then(setOrg).catch(() => {});
    getFabricPersonas()
      .then((r) => {
        setPersonas(r.personas);
        setRole((cur) => cur || r.personas.find((p) => p.default)?.id || r.personas[0]?.id || "");
      })
      .catch(() => {});
  }, [signedIn]);

  useEffect(() => {
    if (!role) return;
    try { localStorage.setItem(ROLE_KEY, role); } catch { /* storage may be absent */ }
  }, [role]);

  const doLogin = async () => {
    setBusy(true);
    setError(null);
    try {
      await fabricLogin(username, password);
      setSignedIn(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const doLogout = () => {
    fabricLogout();
    setSignedIn(false);
    setOrg(null);
    setPersonas([]);
  };

  return (
    <header className="h-11 shrink-0 flex items-center gap-3 px-4 border-b border-line bg-panel text-[13px]">
      <span className="font-semibold text-ink">{org?.name ?? "Organization"}</span>
      {org?.domain && <span className="text-muted">· {org.domain}</span>}
      <span className="flex-1" />
      {signedIn ? (
        <>
          <span className="text-muted">role</span>
          <select
            aria-label="role"
            className={CONTROL}
            value={role}
            onChange={(e) => setRole(e.target.value)}
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button
            className="h-7 px-2 rounded-md border border-line bg-paper text-[12px]"
            onClick={doLogout}
          >
            Sign out
          </button>
        </>
      ) : (
        <>
          <input
            aria-label="username"
            className={CONTROL + " w-36"}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="username"
          />
          <input
            aria-label="password"
            type="password"
            className={CONTROL + " w-32"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && doLogin()}
            placeholder="password"
          />
          <button
            className="h-7 px-2 rounded-md bg-accent text-white text-[12px] disabled:opacity-40"
            disabled={busy}
            onClick={doLogin}
          >
            {busy ? "…" : "Sign in"}
          </button>
          {error && <span className="text-red-500 text-[12px]">{error}</span>}
        </>
      )}
    </header>
  );
}
