"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  ScoreBadge,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  APPLICATION_LABEL,
  formatDateTime,
  formatLocation,
  sourceName,
} from "@/lib/format";
import type { Application, ApplicationBoard, ApplicationStatus } from "@/lib/types";

const STATUSES: ApplicationStatus[] = [
  "interested",
  "applied",
  "assessment",
  "interview",
  "offer",
  "rejected",
];

const STATUS_ACCENT: Record<ApplicationStatus, string> = {
  interested: "border-t-stage-interested",
  applied: "border-t-stage-applied",
  assessment: "border-t-stage-assessment",
  interview: "border-t-stage-interview",
  offer: "border-t-stage-offer",
  rejected: "border-t-stage-rejected",
};

const STATUS_TEXT: Record<ApplicationStatus, string> = {
  interested: "text-ink-200",
  applied: "text-stage-applied",
  assessment: "text-stage-assessment",
  interview: "text-stage-interview",
  offer: "text-stage-offer",
  rejected: "text-stage-rejected",
};

export default function TrackerPage() {
  return (
    <AppShell>
      <Tracker />
    </AppShell>
  );
}

function Tracker() {
  const [board, setBoard] = useState<ApplicationBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setBoard(await api.applications.board());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load your tracker.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function move(application: Application, status: ApplicationStatus) {
    setBusyId(application.id);
    try {
      await api.applications.update(application.id, { status });
      await load();
    } catch {
      /* ignore; the board reloads on next action */
    } finally {
      setBusyId(null);
    }
  }

  async function remove(application: Application) {
    setBusyId(application.id);
    try {
      await api.applications.remove(application.id);
      await load();
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <LoadingBlock label="Loading tracker" />;
  if (error) {
    return (
      <>
        <PageHeader title="Application tracker" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }
  if (!board) return null;

  const total = Object.values(board.counts).reduce((sum, count) => sum + count, 0);

  if (total === 0) {
    return (
      <>
        <PageHeader title="Application tracker" />
        <EmptyState
          title="No applications tracked yet"
          description="Use Track on any job to add it here, then move it through the stages as you progress."
          action={
            <Link href="/jobs" className="btn-primary">
              Find jobs to apply for
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Application tracker"
        description="Move each application through the stages. Every change is recorded with a timestamp."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
        {STATUSES.map((status) => {
          const column = board.columns[status] ?? [];
          return (
            <section
              key={status}
              className={cx(
                "surface border-t-2 px-3 py-3",
                STATUS_ACCENT[status],
              )}
            >
              <div className="mb-3 flex items-baseline justify-between">
                <h2 className={cx("text-xs font-semibold", STATUS_TEXT[status])}>
                  {APPLICATION_LABEL[status]}
                </h2>
                <span className="num text-2xs text-ink-500">{column.length}</span>
              </div>

              {column.length === 0 ? (
                <p className="py-4 text-center text-2xs text-ink-600">Empty</p>
              ) : (
                <ul className="space-y-2">
                  {column.map((application) => (
                    <li
                      key={application.id}
                      className={cx(
                        "rounded border border-ink-700 bg-ink-850 px-2.5 py-2.5 transition-colors hover:border-ink-600",
                        busyId === application.id && "opacity-50",
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <Link
                          href={`/jobs/${application.job.id}`}
                          className="min-w-0 flex-1 text-xs font-medium text-ink-50 hover:underline"
                        >
                          {application.job.title}
                        </Link>
                        {application.match ? (
                          <ScoreBadge
                            score={application.match.score}
                            band={application.match.band}
                            size="sm"
                          />
                        ) : null}
                      </div>

                      <p className="mt-1 truncate text-2xs text-ink-400">
                        {application.job.company}
                      </p>
                      <p className="mt-0.5 truncate text-2xs text-ink-500">
                        {formatLocation(application.job)} ·{" "}
                        {sourceName(application.job.source)}
                      </p>

                      <div className="mt-2.5">
                        <select
                          className="w-full border border-ink-700 bg-ink-900 px-1.5 py-1 text-2xs text-ink-100"
                          value={application.status}
                          disabled={busyId === application.id}
                          onChange={(event) =>
                            move(application, event.target.value as ApplicationStatus)
                          }
                          aria-label={`Change status of ${application.job.title}`}
                        >
                          {STATUSES.map((option) => (
                            <option key={option} value={option}>
                              {APPLICATION_LABEL[option]}
                            </option>
                          ))}
                        </select>
                      </div>

                      <div className="mt-2 flex items-center justify-between gap-2 text-2xs">
                        <button
                          type="button"
                          className="text-ink-500 hover:text-ink-200"
                          onClick={() =>
                            setExpanded(
                              expanded === application.id ? null : application.id,
                            )
                          }
                        >
                          {expanded === application.id ? "Hide" : "History"}
                        </button>
                        <a
                          href={application.job.apply_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-ink-500 hover:text-ink-200"
                        >
                          Open
                        </a>
                        <button
                          type="button"
                          className="text-ink-600 hover:text-signal-danger"
                          onClick={() => remove(application)}
                          aria-label="Remove from tracker"
                        >
                          Remove
                        </button>
                      </div>

                      {expanded === application.id ? (
                        <ul className="mt-2 space-y-1 border-t border-ink-700 pt-2 text-2xs text-ink-500">
                          {application.events.length ? (
                            application.events.map((event) => (
                              <li key={event.id}>
                                {event.from_status
                                  ? `${APPLICATION_LABEL[event.from_status] ?? event.from_status} → `
                                  : "Added as "}
                                {APPLICATION_LABEL[event.to_status] ?? event.to_status}
                                <span className="block text-ink-600">
                                  {formatDateTime(event.created_at)}
                                </span>
                              </li>
                            ))
                          ) : (
                            <li>No history recorded.</li>
                          )}
                        </ul>
                      ) : null}
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </>
  );
}
