"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { BAND_BAR, BAND_CLASS, BAND_LABEL, formatScore } from "@/lib/format";
import type { Band } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------- page shell */

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-col gap-4 border-b border-ink-700 pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-tightest text-ink-50">
          {title}
        </h1>
        {description ? (
          <p className="mt-1.5 max-w-prose text-sm leading-relaxed text-ink-300">
            {description}
          </p>
        ) : null}
      </div>
      {actions ? <div className="flex shrink-0 gap-2">{actions}</div> : null}
    </header>
  );
}

export function Section({
  title,
  description,
  actions,
  children,
  className,
}: {
  title?: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cx("mb-10", className)}>
      {title ? (
        <div className="mb-4 flex items-end justify-between gap-4">
          <div>
            <h2 className="label">{title}</h2>
            {description ? (
              <p className="mt-1.5 max-w-prose text-sm text-ink-300">
                {description}
              </p>
            ) : null}
          </div>
          {actions}
        </div>
      ) : null}
      {children}
    </section>
  );
}

/* ----------------------------------------------------------------- states */

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      role="status"
      aria-label="Loading"
      className={cx(
        "inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-ink-600 border-t-accent-400",
        className,
      )}
    />
  );
}

export function LoadingBlock({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2.5 py-16 text-sm text-ink-400">
      <Spinner />
      <span>{label}…</span>
    </div>
  );
}

export function SkeletonRows({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-3" aria-hidden>
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="skeleton h-24 border border-ink-700" />
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="surface flex flex-col items-center px-6 py-14 text-center">
      <p className="text-sm font-medium text-ink-100">{title}</p>
      {description ? (
        <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-400">
          {description}
        </p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div className="surface border-signal-danger/30 border-l-2 border-l-signal-danger px-5 py-6">
      <p className="text-sm font-medium text-signal-danger">
        Something went wrong
      </p>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-300">{message}</p>
      {onRetry ? (
        <button type="button" onClick={onRetry} className="btn-secondary btn-sm mt-4">
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
}: {
  tone?: "info" | "warn" | "danger" | "ok";
  title?: string;
  children: ReactNode;
}) {
  // A tinted fill plus a left rule so the tone registers before the text.
  const shell = {
    info: "border-accent-line bg-accent-soft border-l-accent-500",
    warn: "border-signal-warn/30 bg-signal-warn/[0.07] border-l-signal-warn",
    danger: "border-signal-danger/30 bg-signal-danger/[0.07] border-l-signal-danger",
    ok: "border-signal-ok/30 bg-signal-ok/[0.07] border-l-signal-ok",
  }[tone];
  const heading = {
    info: "text-accent-300",
    warn: "text-signal-warn",
    danger: "text-signal-danger",
    ok: "text-signal-ok",
  }[tone];

  return (
    <div className={cx("rounded border border-l-2 px-4 py-3", shell)}>
      {title ? (
        <p className={cx("text-xs font-semibold", heading)}>{title}</p>
      ) : null}
      <div className="mt-1 text-sm leading-relaxed text-ink-300">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------- match bits */

export function ScoreBadge({
  score,
  band,
  size = "md",
}: {
  score: number;
  band: Band;
  size?: "sm" | "md" | "lg";
}) {
  const sizing = {
    sm: "text-sm px-2 py-0.5",
    md: "text-base px-2.5 py-1",
    lg: "text-2xl px-3 py-1.5",
  }[size];

  return (
    <span
      className={cx(
        "num inline-flex items-baseline rounded border font-semibold",
        BAND_CLASS[band],
        sizing,
      )}
      title={BAND_LABEL[band]}
    >
      {formatScore(score)}
    </span>
  );
}

export function ScoreBar({
  score,
  band,
  className,
}: {
  score: number;
  band: Band;
  className?: string;
}) {
  return (
    <div
      className={cx("h-1 w-full bg-ink-800", className)}
      role="meter"
      aria-valuenow={Math.round(score)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Match score ${formatScore(score)}`}
    >
      <div
        className={cx("h-full rounded-r transition-all", BAND_BAR[band])}
        style={{ width: `${Math.max(1, Math.min(100, score))}%` }}
      />
    </div>
  );
}

export function SkillChip({
  skill,
  tone = "neutral",
  title,
}: {
  skill: string;
  tone?: "neutral" | "matched" | "missing" | "mandatory";
  title?: string;
}) {
  const classes = {
    neutral: "border-ink-700 bg-ink-850 text-ink-200",
    matched: "border-signal-ok/35 bg-signal-ok/10 text-signal-ok",
    missing: "border-ink-600 bg-ink-850 text-ink-300",
    mandatory: "border-signal-danger/40 bg-signal-danger/10 text-signal-danger",
  }[tone];

  return (
    <span
      className={cx("inline-flex items-center rounded-sm border px-2 py-0.5 text-2xs", classes)}
      title={title}
    >
      {skill}
    </span>
  );
}

export function SourceTag({ source }: { source: string }) {
  return (
    <span className="chip font-medium uppercase tracking-[0.08em]">
      {source}
    </span>
  );
}

/* --------------------------------------------------------------- controls */

export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        "relative h-5 w-9 shrink-0 rounded-full border transition-colors disabled:opacity-40",
        checked ? "border-accent-600 bg-accent-600" : "border-ink-600 bg-ink-800",
      )}
    >
      <span
        className={cx(
          "absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all",
          checked ? "left-[1.1rem] bg-white" : "left-0.5 bg-ink-400",
        )}
      />
    </button>
  );
}

export function Stat({
  label,
  value,
  hint,
  href,
  emphasis,
  swatch,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  href?: string;
  /** Inline colour for the identity dot, e.g. a band hex. */
  swatch?: string;
  /** @deprecated kept so existing call sites compile; prefer `swatch`. */
  emphasis?: string;
  /** @deprecated superseded by `swatch`. */
  accent?: string;
}) {
  /**
   * The figure stays in ink. Values, labels and legends wear text tokens; a
   * coloured mark *beside* the text carries identity. Colouring the number
   * itself turns a KPI row into a rainbow and makes the lighter ramp steps
   * illegible as text.
   */
  const body = (
    <>
      <div className="flex items-center gap-1.5">
        {swatch ? (
          <span
            aria-hidden
            className="h-2 w-2 shrink-0 rounded-sm"
            style={{ background: swatch }}
          />
        ) : null}
        <p className="label">{label}</p>
      </div>
      <p className="figure mt-2 text-[1.75rem] font-semibold leading-none text-ink-50">
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-2xs text-ink-400">{hint}</p> : null}
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="surface block px-4 py-4 transition-colors hover:border-accent-line hover:bg-ink-850"
      >
        {body}
      </Link>
    );
  }
  return <div className="surface px-4 py-4">{body}</div>;
}

export function Field({
  label,
  hint,
  error,
  children,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {required ? <span className="text-signal-danger"> *</span> : null}
      </span>
      <div className="mt-1.5">{children}</div>
      {error ? (
        <span className="mt-1.5 block text-xs text-signal-danger">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-xs text-ink-400">{hint}</span>
      ) : null}
    </label>
  );
}

export function Progress({ value }: { value: number }) {
  return (
    <div className="h-0.5 w-full overflow-hidden bg-ink-800">
      <div
        className="h-full bg-accent-500 transition-all duration-500"
        style={{ width: `${Math.max(2, Math.min(100, value))}%` }}
      />
    </div>
  );
}
