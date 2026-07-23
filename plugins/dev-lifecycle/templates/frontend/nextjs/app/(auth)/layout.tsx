import type { ReactNode } from "react";

// The public auth route group's layout: deliberately EMPTY app chrome. Each
// screen below renders its own centered `<AuthCard>` (see
// `components/AuthCard.tsx`), the same "no shell/header" posture as the Vite
// SPA's auth routes, which render standalone outside `App.tsx`'s authenticated
// shell (see router.tsx). No auth check here — these ARE the public
// login/register/verify/forgot/reset screens.
export default function AuthLayout({ children }: { children: ReactNode }) {
  return children;
}
