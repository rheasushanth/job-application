"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Field, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, user, ready } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email.trim(), password);
      router.push("/dashboard");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not sign in. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-ink-700">
        <div className="mx-auto flex h-14 max-w-shell items-center px-5">
          <Link href="/" className="text-sm font-semibold tracking-tightest text-ink-50">
            JobMatch
          </Link>
        </div>
      </header>

      <main className="flex flex-1 items-center justify-center px-5 py-14">
        <div className="w-full max-w-sm">
          <h1 className="text-xl font-semibold tracking-tightest text-ink-50">
            Sign in
          </h1>
          <p className="mt-1.5 text-sm text-ink-400">
            Continue to your dashboard.
          </p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
            <Field label="Email" required>
              <input
                type="email"
                className="field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
                autoFocus
              />
            </Field>

            <Field label="Password" required>
              <input
                type="password"
                className="field"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </Field>

            {error ? (
              <p
                role="alert"
                className="border border-signal-danger/30 bg-ink-900 px-3 py-2 text-xs text-signal-danger"
              >
                {error}
              </p>
            ) : null}

            <button
              type="submit"
              className="btn-primary w-full"
              disabled={busy || !email || !password}
            >
              {busy ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
              {busy ? "Signing in" : "Sign in"}
            </button>
          </form>

          <p className="mt-6 text-sm text-ink-400">
            No account?{" "}
            <Link href="/register" className="link">
              Create one
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
