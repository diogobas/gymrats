import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import RefreshPanel, { runLabel } from "../src/components/RefreshPanel";
import { parseRoute, routeHref } from "../src/router";

describe("manual refresh", () => {
  it("opens the hidden route in the public build", () => {
    vi.stubGlobal("__LOCAL__", false);
    expect(parseRoute("#/atualizar")).toEqual({ view: "refresh" });
    expect(parseRoute("#/apurar")).toEqual({ view: "refresh" });
    expect(routeHref({ view: "refresh" })).toBe("#/atualizar");
    expect(parseRoute("#/admin")).toEqual({ view: "month", month: null });
    vi.unstubAllGlobals();
  });
  it("shows a configuration message when the service has not been connected", () => {
    const html = renderToStaticMarkup(createElement(RefreshPanel));
    expect(html).toContain("ainda não foi configurada");
    expect(html).not.toContain("Atualizar agora");
  });
  it("shows username and password fields when the service is connected", async () => {
    vi.stubEnv("VITE_REFRESH_URL", "https://refresh.example");
    vi.resetModules();
    try {
      const { default: ConfiguredPanel } = await import("../src/components/RefreshPanel");
      const html = renderToStaticMarkup(createElement(ConfiguredPanel));
      expect(html.toLowerCase()).toContain('autocomplete="username"');
      expect(html).toContain('type="password"');
      expect(html.toLowerCase()).toContain('autocomplete="current-password"');
      expect(html).not.toContain("Atualizar agora");
    } finally { vi.unstubAllEnvs(); vi.resetModules(); }
  });
  it("distinguishes accepted, running, successful and failed workflows", () => {
    const run = { id: 1, url: "", created_at: "", conclusion: null };
    expect(runLabel({ ...run, status: "queued" })).toContain("Aguardando");
    expect(runLabel({ ...run, status: "in_progress" })).toContain("Atualizando");
    expect(runLabel({ ...run, status: "completed", conclusion: "success" })).toBe("Atualização concluída");
    expect(runLabel({ ...run, status: "completed", conclusion: "failure" })).toContain("não foi concluída");
  });
});
