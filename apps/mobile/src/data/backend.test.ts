import { describe, expect, it } from "vitest";
import { PRODUCTION_API, backendBase, backendLabel } from "./backend";

describe("backendBase", () => {
  it("uses the override, without a trailing slash", () => {
    expect(backendBase("https://api.example.com/", undefined, "192.168.1.5:8081")).toBe("https://api.example.com");
  });
  it("uses the Metro host on the server port when asked to", () => {
    expect(backendBase(undefined, "1", "192.168.1.5:8081")).toBe("http://192.168.1.5:8788");
  });
  it("is off by default, so the app runs on its own", () => {
    expect(backendBase(undefined, undefined, "192.168.1.5:8081")).toBeNull();
    expect(backendBase(undefined, "0", "192.168.1.5:8081")).toBeNull();
  });
  it("is off when the host is unknown", () => {
    expect(backendBase(undefined, "1", undefined)).toBeNull();
  });
});

describe("an installed build (not a development session)", () => {
  it("talks to the production server when nothing is set, never the mock", () => {
    expect(backendBase(undefined, undefined, undefined, false)).toBe(PRODUCTION_API);
    expect(backendBase("", undefined, undefined, false)).toBe(PRODUCTION_API);
  });
  it("never talks to a laptop or a plain-HTTP server", () => {
    expect(backendBase("http://10.0.0.5:8788", undefined, "10.0.0.5:8081", false)).toBe(PRODUCTION_API);
    expect(backendBase(undefined, "1", "10.0.0.5:8081", false)).toBe(PRODUCTION_API);
  });
  it("takes another HTTPS server when one is given (a staging server)", () => {
    expect(backendBase("https://staging.example.org/", undefined, undefined, false)).toBe("https://staging.example.org");
  });
});

describe("backendLabel", () => {
  it("says which setup the app is in", () => {
    expect(backendLabel(null)).toMatch(/^Demo mode/);
    expect(backendLabel("http://10.0.0.5:8788")).toBe("Development server · 10.0.0.5:8788");
    expect(backendLabel(PRODUCTION_API, false)).toBe("Study server · api.syllabyte.app");
    expect(backendLabel(PRODUCTION_API, true)).toMatch(/from a development session/);
  });
});
