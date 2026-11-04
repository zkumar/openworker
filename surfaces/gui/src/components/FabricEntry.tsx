import { useEffect, useState } from "react";
import {
  fabricLogin,
  fabricLogout,
  getFabricKits,
  getFabricOrg,
  getFabricPersonas,
  isFabricSignedIn,
  type FabricKit,
  type FabricOrg,
  type FabricPersona,
} from "../fabric";

// Fabric entry (RFC 0052): the org the harness runs in, the personas the signed-in user is entitled
// to, and the domain kits those personas frame. Login authenticates against the fabric's IdP.
const CARD = "rounded-xl2 border border-line bg-panel p-6";
const INPUT =
  "w-full px-3 py-2 rounded-lg border border-line bg-paper text-[13px] text-ink outline-none focus:border-accent";
const BTN = "text-[13px] px-3 py-2 rounded-lg bg-accent text-white disabled:opacity-40";

export function FabricEntry() {
  const [signedIn, setSignedIn] = useState(isFabricSignedIn());
  const [username, setUsername] = useState("dr.md");
  const [password, setPassword] = useState("test");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [org, setOrg] = useState<FabricOrg | null>(null);
  const [personas, setPersonas] = useState<FabricPersona[]>([]);
  const [kits, setKits] = useState<FabricKit[]>([]);

  useEffect(() => {
    if (!signedIn) return; // the catalog needs an authenticated session
    getFabricOrg().then(setOrg).catch(() => {});
    getFabricPersonas().then((r) => setPersonas(r.personas)).catch(() => {});
    getFabricKits().then((r) => setKits(r.kits)).catch(() => {});
  }, [signedIn]);

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
    setKits([]);
  };

  if (!signedIn) {
    return (
      <div className={`${CARD} max-w-md space-y-3`}>
        <h2 className="text-[15px] font-semibold text-ink">Sign in</h2>
        <input
          className={INPUT}
          aria-label="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className={INPUT}
          type="password"
          aria-label="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && doLogin()}
        />
        <button className={BTN} disabled={busy} onClick={doLogin}>
          {busy ? "Signing in…" : "Sign in"}
        </button>
        {error && <p className="text-[13px] text-red-500">{error}</p>}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[15px] font-semibold text-ink">{org?.name ?? "Organization"}</h2>
          {org && <p className="text-[12px] text-muted">tenant {org.tenant}</p>}
        </div>
        <button className="text-[13px] px-2.5 py-1.5 rounded-lg border border-line" onClick={doLogout}>
          Sign out
        </button>
      </div>

      <div className={`${CARD} space-y-2`}>
        <h3 className="text-[13px] font-semibold text-ink">Personas</h3>
        <ul className="space-y-1">
          {personas.map((p) => (
            <li key={p.id} className="text-[13px] text-ink">
              {p.name} <span className="text-muted">· {p.tagline}</span>
            </li>
          ))}
          {!personas.length && <li className="text-[13px] text-muted">no entitled personas</li>}
        </ul>
      </div>

      <div className={`${CARD} space-y-2`}>
        <h3 className="text-[13px] font-semibold text-ink">Domain kits</h3>
        <ul className="space-y-1">
          {kits.map((k) => (
            <li key={k.name} className="text-[13px] text-ink">
              {k.label} <span className="text-muted">· {k.agents.length} agents</span>
            </li>
          ))}
          {!kits.length && <li className="text-[13px] text-muted">no kits installed</li>}
        </ul>
      </div>
    </div>
  );
}
