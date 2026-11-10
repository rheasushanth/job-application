"use client";

import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { useAuth } from "@/components/auth-provider";
import {
  Callout,
  ErrorState,
  Field,
  LoadingBlock,
  PageHeader,
  Section,
  Spinner,
  Toggle,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatDateTime, sourceName } from "@/lib/format";
import type { Health, SourceInfo, Weights } from "@/lib/types";

export default function SettingsPage() {
  return (
    <AppShell>
      <Settings />
    </AppShell>
  );
}

function Settings() {
  const { user, setUser } = useAuth();

  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [weights, setWeights] = useState<Weights | null>(null);
  const [draftWeights, setDraftWeights] = useState<Record<string, number>>({});
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [savingWeights, setSavingWeights] = useState(false);
  const [rescoring, setRescoring] = useState(false);

  const [alertEnabled, setAlertEnabled] = useState(user?.alert_enabled ?? true);
  const [alertThreshold, setAlertThreshold] = useState(user?.alert_min_match ?? 70);
  const [savingAlerts, setSavingAlerts] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [sourceList, weightData, healthData] = await Promise.all([
        api.sources.list(),
        api.weights.get(),
        api.health(),
      ]);
      setSources(sourceList);
      setWeights(weightData);
      setDraftWeights(weightData.weights);
      setHealth(healthData);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load settings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleSource(source: SourceInfo) {
    try {
      const updated = await api.sources.setEnabled(source.key, !source.is_enabled);
      setSources((prev) =>
        prev.map((item) => (item.key === updated.key ? updated : item)),
      );
    } catch {
      /* ignore */
    }
  }

  async function saveWeights() {
    setSavingWeights(true);
    setNotice(null);
    try {
      const updated = await api.weights.set(draftWeights);
      setWeights(updated);
      setDraftWeights(updated.weights);
      setNotice("Weights saved. Every job has been rescored.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not save weights.");
    } finally {
      setSavingWeights(false);
    }
  }

  async function resetWeights() {
    setSavingWeights(true);
    try {
      const updated = await api.weights.reset();
      setWeights(updated);
      setDraftWeights(updated.weights);
      setNotice("Weights reset to the defaults and jobs rescored.");
    } finally {
      setSavingWeights(false);
    }
  }

  async function saveAlerts() {
    setSavingAlerts(true);
    setNotice(null);
    try {
      await api.alerts.set(alertEnabled, alertThreshold);
      const me = await api.auth.me();
      setUser(me);
      setNotice("Alert settings saved.");
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not save alerts.");
    } finally {
      setSavingAlerts(false);
    }
  }

  async function rescore() {
    setRescoring(true);
    setNotice(null);
    try {
      const result = await api.discovery.rescore();
      setNotice(`Rescored ${result.matches_computed} jobs against your profile.`);
    } catch (err) {
      setNotice(err instanceof ApiError ? err.message : "Could not rescore.");
    } finally {
      setRescoring(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading settings" />;
  if (error) {
    return (
      <>
        <PageHeader title="Settings" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }

  const weightsDirty =
    weights &&
    Object.keys(draftWeights).some(
      (key) => draftWeights[key] !== weights.weights[key],
    );
  const weightTotal = Object.values(draftWeights).reduce((sum, value) => sum + value, 0);

  const live = sources.filter((source) => source.available);
  const unavailable = sources.filter((source) => !source.available);

  return (
    <>
      <PageHeader
        title="Settings"
        description="Job sources, how matches are scored, and alert thresholds."
      />

      {notice ? (
        <div className="mb-6">
          <Callout tone="info">{notice}</Callout>
        </div>
      ) : null}

      {/* Weights */}
      <Section
        title="Match scoring weights"
        description="Adjust how much each category contributes. Saving rescores every job immediately."
      >
        <div className="surface px-4 py-4">
          <div className="space-y-5">
            {Object.entries(draftWeights).map(([key, value]) => (
              <div key={key}>
                <div className="flex items-baseline justify-between gap-4">
                  <label htmlFor={`weight-${key}`} className="text-sm text-ink-100">
                    {weights?.labels[key] ?? key}
                  </label>
                  <span className="num text-sm text-ink-300">
                    {(weightTotal > 0 ? (value / weightTotal) * 100 : 0).toFixed(0)}%
                    <span className="ml-2 text-2xs text-ink-500">
                      ({value.toFixed(2)})
                    </span>
                  </span>
                </div>
                <input
                  id={`weight-${key}`}
                  type="range"
                  min={0}
                  max={1}
                  step={0.01}
                  value={value}
                  onChange={(event) =>
                    setDraftWeights((prev) => ({
                      ...prev,
                      [key]: Number(event.target.value),
                    }))
                  }
                  className="mt-2 w-full accent-ink-50"
                />
                {weights?.descriptions[key] ? (
                  <p className="mt-1.5 text-2xs leading-relaxed text-ink-500">
                    {weights.descriptions[key]}
                  </p>
                ) : null}
              </div>
            ))}
          </div>

          {weightTotal <= 0 ? (
            <p className="mt-4 text-xs text-signal-danger">
              At least one weight must be above zero.
            </p>
          ) : null}

          <div className="mt-6 flex flex-wrap gap-2 border-t border-ink-800 pt-4">
            <button
              type="button"
              className="btn-primary btn-sm"
              onClick={saveWeights}
              disabled={savingWeights || !weightsDirty || weightTotal <= 0}
            >
              {savingWeights ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
              Save and rescore
            </button>
            <button
              type="button"
              className="btn-secondary btn-sm"
              onClick={resetWeights}
              disabled={savingWeights}
            >
              Reset to defaults
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm"
              onClick={rescore}
              disabled={rescoring}
            >
              {rescoring ? "Rescoring…" : "Rescore without changes"}
            </button>
          </div>
        </div>
      </Section>

      {/* Alerts */}
      <Section
        title="Job alerts"
        description="Get a notification when newly discovered jobs beat your threshold."
      >
        <div className="surface px-4 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <p className="text-sm text-ink-100">Enable job alerts</p>
              <p className="mt-0.5 text-2xs text-ink-500">
                Created during each discovery run.
              </p>
            </div>
            <Toggle
              checked={alertEnabled}
              onChange={setAlertEnabled}
              label="Enable job alerts"
            />
          </div>

          <div className="mt-5 max-w-xs">
            <Field
              label="Minimum match to alert on"
              hint={`Only jobs scoring ${alertThreshold}% or higher.`}
            >
              <div className="flex items-center gap-3">
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={alertThreshold}
                  onChange={(event) => setAlertThreshold(Number(event.target.value))}
                  className="w-full accent-ink-50"
                  disabled={!alertEnabled}
                />
                <span className="num w-10 text-right text-sm text-ink-100">
                  {alertThreshold}%
                </span>
              </div>
            </Field>
          </div>

          <button
            type="button"
            className="btn-primary btn-sm mt-5"
            onClick={saveAlerts}
            disabled={savingAlerts}
          >
            {savingAlerts ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
            Save alert settings
          </button>
        </div>
      </Section>

      {/* Sources */}
      <Section
        title="Job sources"
        description="Each source is a self-contained integration. Disable one to exclude it from future discovery runs."
      >
        <div className="space-y-2">
          {live.map((source) => (
            <SourceRow key={source.key} source={source} onToggle={toggleSource} />
          ))}
        </div>

        {unavailable.length ? (
          <div className="mt-6">
            <h3 className="label mb-3">
              Not currently available ({unavailable.length})
            </h3>
            <div className="space-y-2">
              {unavailable.map((source) => (
                <SourceRow key={source.key} source={source} onToggle={toggleSource} />
              ))}
            </div>
            <p className="mt-3 max-w-prose text-2xs leading-relaxed text-ink-500">
              These are listed deliberately. Sources marked &ldquo;needs
              credentials&rdquo; activate as soon as the named environment
              variables are set. Sources marked &ldquo;no public API&rdquo; have
              no lawful programmatic access for this use case, and are never
              populated with placeholder listings.
            </p>
          </div>
        ) : null}
      </Section>

      {/* System */}
      {health ? (
        <Section title="System" description="What is actually running behind the matching engine.">
          <dl className="surface grid gap-x-8 gap-y-3 px-4 py-4 text-sm sm:grid-cols-2">
            <SystemRow label="API status" value={health.status} />
            <SystemRow label="Database" value={health.database} />
            <SystemRow label="Embedding model" value={health.embedding_backend} />
            <SystemRow label="LLM provider" value={health.llm_provider} />
            <SystemRow label="Background tasks" value={health.task_backend} />
            <SystemRow label="Active jobs indexed" value={String(health.jobs_indexed)} />
          </dl>
          <p className="mt-3 max-w-prose text-2xs leading-relaxed text-ink-500">
            Without an LLM key, resume structuring falls back to rule-based
            parsing and explanations are generated from the score components.
            Match percentages are unaffected — they are always computed by the
            deterministic algorithm.
          </p>
        </Section>
      ) : null}
    </>
  );
}

function SourceRow({
  source,
  onToggle,
}: {
  source: SourceInfo;
  onToggle: (source: SourceInfo) => void;
}) {
  const kindLabel = {
    public_api: "Public API",
    licensed_api: "Needs credentials",
    gated: "No public API",
  }[source.kind];

  return (
    <div className="surface px-4 py-3.5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-ink-50">
              {source.display_name}
            </span>
            <span
              className={cx(
                "chip",
                source.available
                  ? "border-signal-ok/30 text-signal-ok"
                  : "text-ink-500",
              )}
            >
              {source.available ? "Active" : kindLabel}
            </span>
          </div>

          {source.notes ? (
            <p className="mt-1.5 max-w-prose text-xs leading-relaxed text-ink-400">
              {source.notes}
            </p>
          ) : null}

          {!source.available && source.reason && source.reason !== source.notes ? (
            <p className="mt-1.5 max-w-prose text-xs leading-relaxed text-signal-warn">
              {source.reason}
            </p>
          ) : null}

          {source.missing_env.length ? (
            <p className="num mt-1.5 text-2xs text-ink-500">
              Set: {source.missing_env.join(", ")}
            </p>
          ) : null}

          {source.last_run_at ? (
            <p className="mt-1.5 text-2xs text-ink-500">
              Last run {formatDateTime(source.last_run_at)} ·{" "}
              {source.jobs_last_run} listings
              {source.last_error ? ` · ${source.last_error}` : ""}
            </p>
          ) : null}
        </div>

        <div className="shrink-0">
          <Toggle
            checked={source.is_enabled}
            onChange={() => onToggle(source)}
            label={`Enable ${source.display_name}`}
            disabled={!source.available}
          />
        </div>
      </div>
    </div>
  );
}

function SystemRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 sm:block">
      <dt className="label">{label}</dt>
      <dd className="num truncate text-xs text-ink-200 sm:mt-1">{value}</dd>
    </div>
  );
}
