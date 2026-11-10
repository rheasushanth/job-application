"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { BandDistribution } from "@/components/charts";
import { JobCard } from "@/components/job-card";
import {
  Callout,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  Progress,
  Section,
  SkeletonRows,
  Stat,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatDateTime, pluralise, sourceName } from "@/lib/format";
import { BAND_HEX, STATUS_HEX } from "@/lib/palette";
import type { DashboardSummary, DiscoveryRun } from "@/lib/types";

const POLL_MS = 2000;

export default function DashboardPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingBlock />}>
        <Dashboard />
      </Suspense>
    </AppShell>
  );
}

function Dashboard() {
  const params = useSearchParams();
  const autoDiscover = params.get("discover") === "1";

  const [summary, setSummary] = useState<DashboardSummary | null>(null);
  const [run, setRun] = useState<DiscoveryRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const autoStarted = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await api.jobs.summary();
      setSummary(data);
      setRun(data.last_discovery);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your dashboard.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startDiscovery = useCallback(async () => {
    setStarting(true);
    setActionError(null);
    try {
      setRun(await api.discovery.run({}));
    } catch (err) {
      setActionError(
        err instanceof ApiError ? err.message : "Could not start job discovery.",
      );
    } finally {
      setStarting(false);
    }
  }, []);

  // Kick off discovery once, immediately after the profile is confirmed.
  useEffect(() => {
    if (!autoDiscover || autoStarted.current || !summary?.has_profile) return;
    autoStarted.current = true;
    startDiscovery();
  }, [autoDiscover, summary?.has_profile, startDiscovery]);

  // Poll only while a run is actually in flight.
  useEffect(() => {
    if (!run || (run.status !== "queued" && run.status !== "running")) return;
    const timer = setInterval(async () => {
      try {
        const detail = await api.discovery.run_detail(run.id);
        setRun(detail.run);
        if (detail.run.status !== "queued" && detail.run.status !== "running") {
          load();
        }
      } catch {
        /* transient; the next tick retries */
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [run, load]);

  if (loading) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <div className="mb-10 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {Array.from({ length: 6 }).map((_, index) => (
            <div key={index} className="skeleton h-24 border border-ink-700" />
          ))}
        </div>
        <SkeletonRows rows={3} />
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }
  if (!summary) return null;

  if (!summary.has_profile) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <EmptyState
          title="Upload a resume to get started"
          description="Job discovery and matching both work from your confirmed profile, so that is the first step."
          action={
            <Link href="/upload" className="btn-primary">
              Upload your resume
            </Link>
          }
        />
      </>
    );
  }

  const running = run?.status === "queued" || run?.status === "running";
  const noJobsYet = summary.total_jobs === 0;
  const scoredTotal =
    summary.excellent + summary.good + summary.moderate + summary.low;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Everything discovered for your profile, ranked by how well it matches."
        actions={
          <button
            type="button"
            className="btn-primary btn-sm"
            onClick={startDiscovery}
            disabled={starting || running}
          >
            {running ? "Discovering…" : starting ? "Starting…" : "Find new jobs"}
          </button>
        }
      />

      {actionError ? (
        <div className="mb-6">
          <Callout tone="danger" title="Discovery could not start">
            {actionError}
          </Callout>
        </div>
      ) : null}

      {running && run ? (
        <section className="surface mb-8 px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm font-medium text-ink-50">
                Searching job platforms
              </p>
              <p className="mt-1 text-xs text-ink-400">
                {run.queries.length
                  ? `Looking for: ${run.queries.join(", ")}`
                  : "Preparing searches…"}
              </p>
            </div>
            <span className="num text-sm text-ink-300">{run.progress}%</span>
          </div>
          <div className="mt-3">
            <Progress value={run.progress} />
          </div>
        </section>
      ) : null}

      {run && !running ? <RunReport run={run} /> : null}

      <Section title="Overview">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Stat label="Jobs discovered" value={summary.total_jobs} href="/jobs" />
          <Stat
            label="Eligible"
            value={summary.eligible}
            hint="Meets all stated hard requirements"
            href="/jobs?eligibility=eligible"
            swatch={STATUS_HEX.ok}
          />
          <Stat label="Saved" value={summary.saved} href="/saved" />
          <Stat label="Applications" value={summary.tracked} href="/tracker" />
        </div>

        {/* Part-to-whole across the bands, which a row of four separate
            counters cannot show. The per-band counts stay clickable below. */}
        <div className="mt-3 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
          <BandDistribution
            total={scoredTotal}
            data={[
              { band: "excellent", count: summary.excellent },
              { band: "good", count: summary.good },
              { band: "moderate", count: summary.moderate },
              { band: "low", count: summary.low },
            ]}
          />

          <div className="grid grid-cols-2 gap-3">
            <Stat
              label="Excellent 85%+"
              value={summary.excellent}
              href="/jobs?band=excellent"
              swatch={BAND_HEX.excellent}
            />
            <Stat
              label="Good 70–84%"
              value={summary.good}
              href="/jobs?band=good"
              swatch={BAND_HEX.good}
            />
            <Stat
              label="Moderate 50–69%"
              value={summary.moderate}
              href="/jobs?band=moderate"
              swatch={BAND_HEX.moderate}
            />
            <Stat
              label="Partially eligible"
              value={summary.partially_eligible}
              href="/jobs?eligibility=partially_eligible"
              swatch={STATUS_HEX.warn}
            />
          </div>
        </div>
      </Section>

      <Section
        title="Recommended jobs"
        description={
          summary.top_matches.length
            ? "Your strongest matches right now."
            : undefined
        }
        actions={
          summary.top_matches.length ? (
            <Link href="/jobs" className="btn-secondary btn-sm">
              View all jobs
            </Link>
          ) : undefined
        }
      >
        {noJobsYet ? (
          <EmptyState
            title={running ? "Searching for jobs" : "No jobs discovered yet"}
            description={
              running
                ? "This takes a moment while each job platform is queried."
                : "Run a discovery pass to search every connected job platform for roles matching your profile."
            }
            action={
              running ? undefined : (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={startDiscovery}
                  disabled={starting}
                >
                  Find jobs now
                </button>
              )
            }
          />
        ) : summary.top_matches.length === 0 ? (
          <EmptyState
            title="Jobs found, but none scored yet"
            description="Try a rescore from Settings, or run discovery again."
          />
        ) : (
          <div className="grid gap-3 lg:grid-cols-2">
            {summary.top_matches.map((entry) => (
              <JobCard key={entry.job.id} entry={entry} onChanged={load} compact />
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Job sources"
        description="Which platforms are currently contributing listings."
      >
        <div className="surface px-4 py-4">
          <div className="flex flex-wrap items-center gap-2">
            {summary.sources_live.map((key) => (
              <span
                key={key}
                className="chip border-signal-ok/30 text-signal-ok"
                title="Connected and returning listings"
              >
                {sourceName(key)}
              </span>
            ))}
            {summary.sources_unavailable.map((key) => (
              <span
                key={key}
                className="chip text-ink-500"
                title="Requires an API integration — see Settings"
              >
                {sourceName(key)}
              </span>
            ))}
          </div>
          <p className="mt-3 text-2xs leading-relaxed text-ink-500">
            {pluralise(summary.sources_live.length, "source")} active.{" "}
            {summary.sources_unavailable.length
              ? `${summary.sources_unavailable.length} need an API key or have no public API — `
              : ""}
            <Link href="/settings" className="link">
              see Settings
            </Link>{" "}
            for details.
          </p>
        </div>
      </Section>
    </>
  );
}

function RunReport({ run }: { run: DiscoveryRun }) {
  const failed = run.sources_failed ?? [];
  const tone =
    run.status === "failed" ? "danger" : failed.length ? "warn" : "ok";

  return (
    <div className="mb-8">
      <Callout
        tone={tone}
        title={
          run.status === "failed"
            ? "Last discovery failed"
            : failed.length
              ? "Last discovery finished with some sources unavailable"
              : "Last discovery complete"
        }
      >
        <p>
          {run.jobs_fetched} listings fetched · {run.jobs_new} new ·{" "}
          {run.jobs_duplicate} duplicates merged · {run.matches_computed} scored.
          Finished {formatDateTime(run.finished_at)}.
        </p>
        {run.sources_succeeded?.length ? (
          <p className="mt-1.5 text-ink-400">
            Contributed: {run.sources_succeeded.map(sourceName).join(", ")}
          </p>
        ) : null}
        {failed.length ? (
          <ul className="mt-2 space-y-1 text-ink-400">
            {failed.map((entry) => (
              <li key={entry.source}>
                <span className="text-ink-200">{sourceName(entry.source)}</span>:{" "}
                {entry.error}
              </li>
            ))}
          </ul>
        ) : null}
        {run.error ? <p className="mt-1.5 text-ink-300">{run.error}</p> : null}
      </Callout>
    </div>
  );
}
