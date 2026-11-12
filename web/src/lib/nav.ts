import type { Role } from "@/lib/api";

/** The pages each role can use. The first one is where that role lands after signing in. */
export const NAV: Record<Role, { href: string; label: string }[]> = {
  institute_admin: [
    { href: "/uploads", label: "Uploads" },
    { href: "/students", label: "Students" },
  ],
  aicte_officer: [
    { href: "/dashboard", label: "Dashboard" },
    { href: "/institutes", label: "Institutes" },
    { href: "/uploads", label: "Uploads" },
    { href: "/verifiers", label: "Verifiers" },
    { href: "/audit", label: "Audit log" },
  ],
  verifier: [{ href: "/verify", label: "Verify a student" }],
};

export const ROLE_LABEL: Record<Role, string> = {
  institute_admin: "Institute admin",
  aicte_officer: "AICTE officer",
  verifier: "Verifier",
};

/**
 * Where to send someone after sign-in. `next` is the page they were on when they
 * were asked to sign in; it is honoured only if it is one of this role's own pages,
 * which also rules out redirects to other sites.
 */
export function landingFor(role: Role, next: string | null): string {
  const allowed = NAV[role].some(
    (item) => next === item.href || next?.startsWith(`${item.href}/`),
  );
  return allowed && next ? next : NAV[role][0].href;
}
