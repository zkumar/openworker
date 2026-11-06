import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { fabricLogin, fabricToken, getFabricPersonas } from "./fabric";

const store = new Map<string, string>();
beforeEach(() => {
  store.clear();
  vi.stubGlobal("localStorage", {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v); },
    removeItem: (k: string) => { store.delete(k); },
    clear: () => { store.clear(); },
    key: () => null,
    length: 0,
  } as Storage);
});
afterEach(() => {
  vi.unstubAllGlobals();
});

it("logs in against the fabric and sends the Bearer on catalog reads", async () => {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    calls.push({ url, init });
    if (url.endsWith("/api/auth/login")) {
      return { ok: true, json: async () => ({ access_token: "tok", token_type: "Bearer" }) } as Response;
    }
    return {
      ok: true,
      json: async () => ({ org: { id: "humana", name: "Humana", tenant: "humana" }, personas: [] }),
    } as Response;
  }));

  await fabricLogin("dr.md", "test");
  expect(fabricToken()).toBe("tok");
  await getFabricPersonas();
  expect(new Headers(calls[1].init?.headers).get("Authorization")).toBe("Bearer tok");
});

it("surfaces the IdP error on a bad login", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({
    ok: false,
    json: async () => ({ detail: "invalid username or password" }),
  }) as Response));
  await expect(fabricLogin("dr.md", "nope")).rejects.toThrow("invalid username or password");
  expect(fabricToken()).toBeNull();
});
