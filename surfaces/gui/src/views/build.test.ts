// The build seam: the committed renderer app (npm run build:views) is one self-contained
// document, so the host's sandbox, which has no network, can draw it. CI rebuilds it and fails on
// any diff, so this file always matches the shared components.
import { describe, expect, it } from "vitest";

import html from "../../../views/work-item.html?raw";

describe("committed renderer app", () => {
  it("is one HTML document with its script and style inline", () => {
    expect(html.startsWith("<!doctype html>")).toBe(true);
    expect(html).toMatch(/<script type="module">[^]+<\/script>/);
    expect(html).toMatch(/<style>[^]+<\/style>/);
    expect(html).toContain('<div id="root"></div>');
  });

  it("has no external script src, link href or other fetchable URL", () => {
    expect(html).not.toMatch(/<script[^>]*\ssrc=/i);
    expect(html).not.toMatch(/<link[^>]*\shref=/i);
    expect(html).not.toMatch(/<(img|iframe|source|video|audio|embed|object)\b/i);
    expect(html).not.toMatch(/@import/i);
    expect(html).not.toMatch(/url\(\s*["']?(?!data:)/i);
    expect(html).not.toMatch(/\b(fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(/);
    expect(html).not.toMatch(/\bimport\s*\(/);
  });
});
