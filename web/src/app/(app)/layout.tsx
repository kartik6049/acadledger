"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { type ReactNode, useEffect } from "react";
import useSWR from "swr";
import { Alert, Button, Spinner } from "@/components/ui";
import { ApiError, api, fetcher, type Role, type User } from "@/lib/api";
import { NAV, ROLE_LABEL } from "@/lib/nav";
import { SessionContext } from "@/lib/session";

function NavLinks({ role }: { role: Role }) {
  const pathname = usePathname();
  return (
    <nav className="flex flex-wrap gap-1 text-sm">
      {NAV[role].map((item) => {
        const active = pathname.startsWith(item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            className={`rounded-md px-2.5 py-1.5 ${active ? "bg-accent-soft font-medium text-accent" : "text-muted hover:text-foreground"}`}
          >
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

// Signing in and out are full page loads, never client-side navigations. Next.js keeps
// recently visited pages alive (hidden) to preserve their state, and the data cache lives
// in memory; a page load is what guarantees none of that survives into another session.

export default function AppLayout({ children }: { children: ReactNode }) {
  const { data: user, error } = useSWR<User, ApiError>("/auth/me", fetcher, {
    // 401 means signed out, which retrying cannot fix; anything else may be a blip
    shouldRetryOnError: (err) => err.status !== 401,
    errorRetryInterval: 1500,
  });
  const signedOut = error?.status === 401;

  useEffect(() => {
    if (!signedOut) return;
    // Remember where they were heading. The #fragment matters: a verification link
    // carries its token there, so it must survive the detour through sign-in.
    const next = encodeURIComponent(window.location.pathname);
    window.location.replace(`/login?next=${next}${window.location.hash}`);
  }, [signedOut]);

  async function logout() {
    await api("/auth/logout", { method: "POST" });
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate full page load, see above
    window.location.assign("/login");
  }

  if (error && !signedOut) {
    return (
      <main className="mx-auto w-full max-w-md px-4 py-16">
        <Alert tone="danger">{error.message}</Alert>
      </main>
    );
  }
  if (!user) {
    return (
      <main className="mx-auto w-full max-w-5xl px-4 py-16">
        <Spinner label="Loading…" />
      </main>
    );
  }

  return (
    <SessionContext value={user}>
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <Link href={NAV[user.role][0].href} className="font-semibold tracking-tight">
            AcadLedger
          </Link>
          <NavLinks role={user.role} />
          <div className="ml-auto flex items-center gap-3 text-sm">
            <Link href="/account" className="group text-right leading-tight" title="Account">
              <div className="max-w-56 truncate group-hover:underline">{user.email}</div>
              <div className="text-xs text-muted">{ROLE_LABEL[user.role]}</div>
            </Link>
            <Button variant="secondary" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">{children}</main>
    </SessionContext>
  );
}
