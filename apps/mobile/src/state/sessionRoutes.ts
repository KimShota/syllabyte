import type { Session } from "./session";

export const isAuthPage = (pathname: string): boolean => pathname === "/landing" || pathname === "/signin";

/** Keep public entry pages accessible, including the emailed /signin link, and protect the rest of the app. */
export function sessionRedirect(status: Session["status"], pathname: string): "/landing" | "/" | null {
  if (status === "signedOut" && !isAuthPage(pathname)) return "/landing";
  if (status === "signedIn" && isAuthPage(pathname)) return "/";
  return null;
}
