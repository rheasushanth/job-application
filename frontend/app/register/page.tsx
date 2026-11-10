"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/auth-provider";
import { Field, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";

const MIN_PASSWORD = 10;

export default function RegisterPage() {
  const { register, user, ready } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (ready && user) router.replace("/dashboard");
  }, [ready, user, router]);

  const tooShort = password.length > 0 && password.length < MIN_PASSWORD;

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setFieldErrors({});
    setBusy(true);
    try {
      await register(email.trim(), password, fullName.trim() || undefined);
      router.push("/upload");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
        // Surface server-side field errors next to the inputs.
        const mapped: Record<string, string> = {};
        for (const [key, value] of Object.entries(err.fields ?? {})) {
          mapped[key.split(".").pop() ?? key] = value;
        }
        setFieldErrors(mapped);
      } else {
        setError("Could not create your account. Try again.");
      }
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
            Create your account
          </h1>
          <p className="mt-1.5 text-sm text-ink-400">
            Next step is uploading your resume.
          </p>

          <form onSubmit={onSubmit} className="mt-8 space-y-5" noValidate>
            <Field label="Full name" hint="Optional" error={fieldErrors.full_name}>
              <input
                type="text"
                className="field"
                value={fullName}
                onChange={(event) => setFullName(event.target.value)}
                autoComplete="name"
                autoFocus
              />
            </Field>

            <Field label="Email" required error={fieldErrors.email}>
              <input
                type="email"
                className="field"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                autoComplete="email"
                required
              />
            </Field>

            <Field
              label="Password"
              required
              hint={`At least ${MIN_PASSWORD} characters. A short phrase works well.`}
              error={
                fieldErrors.password ??
                (tooShort ? `Use at least ${MIN_PASSWORD} characters.` : undefined)
              }
            >
              <input
                type="password"
                className="field"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="new-password"
                required
                minLength={MIN_PASSWORD}
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
              disabled={busy || !email || password.length < MIN_PASSWORD}
            >
              {busy ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
              {busy ? "Creating account" : "Create account"}
            </button>
          </form>

          <p className="mt-6 text-sm text-ink-400">
            Already registered?{" "}
            <Link href="/login" className="link">
              Sign in
            </Link>
          </p>
        </div>
      </main>
    </div>
  );
}
