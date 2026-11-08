import { describe, expect, it } from "vitest";
import { canExploreBeforeBaseline, sessionRedirect } from "./sessionRoutes";

describe("public landing and email sign-in routes", () => {
  it.each(["/", "/welcome", "/profile", "/course/c1", "/player/ku-a"])("opens the landing page instead of a protected route: %s", (pathname) => {
    expect(sessionRedirect("signedOut", pathname)).toBe("/landing");
  });

  it.each(["/landing", "/signin"])("allows signed-out users through the public flow: %s", (pathname) => {
    // usePathname excludes query parameters, so /signin?mode=signup and emailed tickets remain accessible.
    expect(sessionRedirect("signedOut", pathname)).toBeNull();
    expect(sessionRedirect("signedIn", pathname)).toBe("/");
  });

  it("waits for saved-session loading and keeps signed-in users on their course", () => {
    expect(sessionRedirect("loading", "/")).toBeNull();
    expect(sessionRedirect("loading", "/signin")).toBeNull();
    expect(sessionRedirect("signedIn", "/course/c1")).toBeNull();
  });
});

describe("exploring while uploaded materials finish processing", () => {
  it.each(["/", "/profile", "/course/c1", "/course/c1/files"])("does not interrupt browsing when the baseline becomes ready: %s", (pathname) => {
    expect(canExploreBeforeBaseline(pathname)).toBe(true);
  });

  it.each(["/player/ku-a", "/course/c1/feed", "/course/c1/lecture/1"])("still requires the baseline before learning: %s", (pathname) => {
    expect(canExploreBeforeBaseline(pathname)).toBe(false);
  });
});
