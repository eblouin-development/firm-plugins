"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@repo/web-shared";
import { ProtectedGate } from "../../components/auth/ProtectedGate";

/**
 * The authenticated app shell — port of the Vite SPA's `App.tsx` (a
 * react-router layout route element rendering `<Outlet/>`) to a Next App
 * Router layout rendering `{children}`. Wraps `{children}` in
 * `<ProtectedGate>` (the analog of the SPA mounting `App` BEHIND
 * `ProtectedRoute` in router.tsx) so every route under `app/(app)/` — this
 * layout plus its children — only ever renders for a logged-in session.
 * `useAuth().principal` (from `GET /auth/me`) is expected to be present,
 * though it may briefly be null right after login while that query resolves.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <ProtectedGate>
      <AppShell>{children}</AppShell>
    </ProtectedGate>
  );
}

const AppShell = ({ children }: { children: ReactNode }): ReactNode => {
  const { principal, logout, isPending, hasRole } = useAuth();
  const router = useRouter();

  const onLogout = async (): Promise<void> => {
    await logout();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen bg-bg text-text">
      <header className="border-b border-border bg-surface">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3">
          <nav className="flex items-center gap-4 text-sm font-medium">
            <Link href="/dashboard" className="hover:text-primary">
              Dashboard
            </Link>
            {hasRole("admin") && (
              <Link href="/admin" className="hover:text-primary">
                Admin
              </Link>
            )}
          </nav>
          <div className="flex items-center gap-3 text-sm">
            {principal && <span className="text-muted">{principal.email}</span>}
            <button
              type="button"
              onClick={() => void onLogout()}
              disabled={isPending}
              className="rounded-md border border-border px-3 py-1.5 font-medium hover:bg-bg disabled:opacity-60"
            >
              Log out
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-3xl px-4 py-8">{children}</main>
    </div>
  );
};
