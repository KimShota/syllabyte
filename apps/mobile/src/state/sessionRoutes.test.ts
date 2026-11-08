import { describe, expect, it } from "vitest";
import { sessionRedirect } from "./sessionRoutes";

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
