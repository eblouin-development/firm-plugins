"use client";

import type { ReactNode } from "react";
import { Suspense, useEffect, useRef } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { verifyEmailAuthVerifyEmailPost } from "@repo/api-client";
import { ApiError, unwrap } from "@repo/web-shared";
import { AuthCard } from "../../../components/AuthCard";
import { Banner } from "../../../components/form";

/**
 * Consumes the single-use token from the emailed verification link
 * (`/verify-email?token=…`) and POSTs it once on mount. Port of the Vite SPA's
 * `VerifyEmailPage.tsx`; `useSearchParams` from react-router (a hook returning
 * `[URLSearchParams, setter]`) becomes `next/navigation`'s `useSearchParams`
 * (a hook returning `ReadonlyURLSearchParams` directly — no setter tuple).
 *
 * `next/navigation`'s `useSearchParams()` opts the whole subtree into
 * client-side rendering up to the nearest `<Suspense>` boundary at build time
 * (`next build` errors without one) — see `VerifyEmailScreen` below, which is
 * split out and wrapped here so the boundary is one component down from the
 * page's default export.
 */
export default function VerifyEmailPage(): ReactNode {
  return (
    <Suspense fallback={<VerifyingFallback />}>
      <VerifyEmailScreen />
    </Suspense>
  );
}

const VerifyingFallback = (): ReactNode => (
  <AuthCard title="Verifying your email">
    <Banner tone="info">Verifying…</Banner>
  </AuthCard>
);

const VerifyEmailScreen = (): ReactNode => {
  const params = useSearchParams();
  const token = params.get("token");
  const firedFor = useRef<string | null>(null);

  const mutation = useMutation({
    mutationFn: async (t: string) => unwrap(await verifyEmailAuthVerifyEmailPost({ token: t })),
  });
  const { mutate } = mutation;

  useEffect(() => {
    // Fire exactly once per token (guards against StrictMode's dev double-run).
    if (token && firedFor.current !== token) {
      firedFor.current = token;
      mutate(token);
    }
  }, [token, mutate]);

  const backToSignIn = (
    <Link className="text-primary hover:underline" href="/login">
      Back to sign in
    </Link>
  );

  if (!token) {
    return (
      <AuthCard title="Verify your email" footer={backToSignIn}>
        <Banner tone="error">This verification link is invalid or incomplete.</Banner>
      </AuthCard>
    );
  }

  if (mutation.isSuccess) {
    return (
      <AuthCard title="Email verified" footer={backToSignIn}>
        <Banner tone="success">Your email is verified. You can sign in now.</Banner>
      </AuthCard>
    );
  }

  if (mutation.isError) {
    const invalid = mutation.error instanceof ApiError && mutation.error.status === 401;
    return (
      <AuthCard
        title="Verification failed"
        footer={
          <Link className="text-primary hover:underline" href="/forgot-password">
            Request a new link
          </Link>
        }
      >
        <Banner tone="error">
          {invalid
            ? "This verification link is invalid or has expired."
            : "We couldn't verify your email. Please try again."}
        </Banner>
      </AuthCard>
    );
  }

  return <VerifyingFallback />;
};
