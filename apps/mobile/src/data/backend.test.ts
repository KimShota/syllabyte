import { describe, expect, it } from "vitest";
import { backendBase } from "./backend";

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
