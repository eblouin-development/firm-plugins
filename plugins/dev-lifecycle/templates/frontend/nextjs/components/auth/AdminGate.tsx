"use client";

import { useEffect } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import { RequireRole } from "@repo/web-shared";

/**
 * Thin Next.js adapter over web-shared's `RequireRole` render-gate, pinned to
 * the `"admin"` role — the analog of the Vite SPA's `AdminRoute.tsx`. Same
 * contract as `ProtectedGate`: the guard renders `children` when the decoded
 * access-token `roles` claim includes `admin`, else redirects. This is UX
 * gating on an UNVERIFIED claim — the authoritative check is the backend's
 * 403 on `GET /admin/ping`, which the admin screen also renders (see
 * `app/(app)/admin/page.tsx`).
 */
export const AdminGate = ({ children }: { children: ReactNode }): ReactNode => (
  <RequireRole role="admin" fallback={<RedirectHome />}>
    {children}
  </RequireRole>
);

const RedirectHome = (): ReactNode => {
  const router = useRouter();
  useEffect(() => {
    router.replace("/");
  }, [router]);
  return null;
};
