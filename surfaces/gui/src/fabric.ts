// Fabric catalog client (RFC 0052): the OpenWorker harness is the UI; the fabric is the governed
// kernel behind it. `fabricLogin` authenticates against the fabric's IdP (Keycloak) and stores the
// bearer token; the catalog (org, entitled personas, domain kits) is what the harness shows the user.
const fabricBase = (): string =>
  (globalThis as any).__FABRIC_HTTP__ ||
  (import.meta as any).env?.VITE_FABRIC_HTTP ||
  "http://127.0.0.1:8766";

const TOKEN_KEY = "openworker.fabricToken";

// Storage may be absent (node/test env); treat it as "not signed in" rather than throwing.
const store = (): Storage | null => {
  try { return (globalThis as any).localStorage ?? null; } catch { return null; }
};

export const fabricToken = (): string | null => store()?.getItem(TOKEN_KEY) ?? null;
export const isFabricSignedIn = (): boolean => !!fabricToken();

export async function fabricLogin(username: string, password: string): Promise<void> {
  const res = await globalThis.fetch(`${fabricBase()}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!res.ok) {
    let msg = "login failed";
    try { msg = (await res.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  const data = (await res.json()) as { access_token: string };
  store()?.setItem(TOKEN_KEY, data.access_token);
  // Let mounted surfaces (the new-session worklist) re-read the catalog now that we're signed in.
  try { (globalThis as any).dispatchEvent?.(new Event("fabric:signed-in")); } catch { /* no window */ }
}

export function fabricLogout(): void {
  store()?.removeItem(TOKEN_KEY);
}

async function get<T>(path: string): Promise<T> {
  const token = fabricToken();
  const res = await globalThis.fetch(`${fabricBase()}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error((await res.text()) || `${path} -> ${res.status}`);
  return (await res.json()) as T;
}

export interface FabricPersona {
  id: string; name: string; domain: string; tagline: string; icon: string;
  enabled: boolean; default: boolean; scope: string[]; skills: string[];
}
export interface FabricKit {
  name: string; label: string; description: string; agents: string[]; personas: string[];
}
export interface FabricOrg { id: string; name: string; tenant: string; domain: string; entitled_personas: string[] }

export const getFabricOrg = (): Promise<FabricOrg> => get<FabricOrg>("/api/org");
export const getFabricPersonas = () =>
  get<{ org: { id: string; name: string; tenant: string }; personas: FabricPersona[] }>("/api/personas");
export const getFabricKits = () => get<{ kits: FabricKit[] }>("/api/kits");

// --- the role's governed task list (the domain kit's agents) ---------------------------------
export interface FabricAgent {
  agent_id: string;
  label: string;
  description: string;
  sample_inputs: Record<string, unknown>[];
}
export const getFabricAgents = () => get<{ agents: FabricAgent[] }>("/api/agents");

export const fabricRole = (): string | null => {
  try { return localStorage.getItem("fabricRole"); } catch { return null; }
};

// A role's declared agent-id scope (glob over agent ids) — the same rule the fabric applies.
export function matchesScope(agentId: string, scope: string[]): boolean {
  return scope.some((pattern) => {
    const re = new RegExp("^" + pattern.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*") + "$");
    return re.test(agentId);
  });
}
