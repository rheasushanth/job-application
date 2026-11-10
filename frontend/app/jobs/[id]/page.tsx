"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { CategoryBars, CompanyMark, ScoreMeter } from "@/components/charts";
import {
  Callout,
  ErrorState,
  LoadingBlock,
  ScoreBadge,
  Section,
  SkillChip,
  SourceTag,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  APPLICATION_LABEL,
  ELIGIBILITY_CLASS,
  ELIGIBILITY_LABEL,
  EXPERIENCE_LEVEL_LABEL,
  JOB_TYPE_LABEL,
  WORK_MODE_LABEL,
  formatDate,
  formatExperienceRequirement,
  formatLocation,
  formatMonths,
  formatRelativeDate,
  formatSalary,
  sourceName,
} from "@/lib/format";
import type { JobWithMatch, MatchAnalysis } from "@/lib/types";

export default function JobDetailPage() {
  return (
    <AppShell>
      <JobDetail />
    </AppShell>
  );
}

function JobDetail() {
  const params = useParams<{ id: string }>();
  const jobId = params?.id;

  const [entry, setEntry] = useState<JobWithMatch | null>(null);
  const [analysis, setAnalysis] = useState<MatchAnalysis | null>(null);
  const [notScored, setNotScored] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!jobId) return;
    setLoading(true);
    try {
      const jobEntry = await api.jobs.get(jobId);
      setEntry(jobEntry);
      setError(null);

      // The analysis endpoint 404s with a specific code when the job has not
      // been scored for this user; that is a state, not an error.
      try {
        setAnalysis(await api.jobs.analysis(jobId));
        setNotScored(false);
      } catch (err) {
        if (err instanceof ApiError && err.code === "not_scored") {
          setNotScored(true);
          setAnalysis(null);
        } else {
          throw err;
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load this job.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  async function toggleSave() {
    if (!entry) return;
    setBusy(true);
    try {
      if (entry.is_saved) await api.saved.remove(entry.job.id);
      else await api.saved.add(entry.job.id);
      setEntry({ ...entry, is_saved: !entry.is_saved });
    } catch {
      /* leave state unchanged on failure */
    } finally {
      setBusy(false);
    }
  }

  async function track() {
    if (!entry || entry.application_status) return;
    setBusy(true);
    try {
      await api.applications.create(entry.job.id, "interested");
      setEntry({ ...entry, application_status: "interested" });
    } catch {
      /* ignore */
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading match analysis" />;
  if (error) return <ErrorState message={error} onRetry={load} />;
  if (!entry) return null;

  const { job } = entry;

  return (
    <article className="mx-auto max-w-4xl">
      <Link href="/jobs" className="text-xs text-ink-400 hover:text-ink-100">
        ← Back to jobs
      </Link>

      {/* Header */}
      <header className="mt-5 border-b border-ink-700 pb-6">
        <div className="flex flex-wrap items-start justify-between gap-5">
          <div className="min-w-0 flex-1">
            <div className="flex items-start gap-3">
              <CompanyMark name={job.company} size={40} />
              <div className="min-w-0">
                <h1 className="text-xl font-semibold tracking-tightest text-ink-50">
                  {job.title}
                </h1>
                <p className="mt-1 text-sm text-ink-200">{job.company}</p>
              </div>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-400">
              <span>{formatLocation(job)}</span>
              <span aria-hidden>·</span>
              <span>{WORK_MODE_LABEL[job.work_mode] ?? job.work_mode}</span>
              <span aria-hidden>·</span>
              <span>{JOB_TYPE_LABEL[job.job_type] ?? job.job_type}</span>
              <span aria-hidden>·</span>
              <span>Posted {formatRelativeDate(job.posted_at)}</span>
            </div>

            <div className="mt-3 flex flex-wrap items-center gap-2">
              <SourceTag source={sourceName(job.source)} />
              {job.also_seen_on?.length ? (
                <span className="text-2xs text-ink-500">
                  also listed on {job.also_seen_on.map(sourceName).join(", ")}
                </span>
              ) : null}
            </div>
          </div>

          {analysis ? (
            <div className="flex shrink-0 flex-col items-center">
              <ScoreMeter
                score={analysis.score}
                band={analysis.band}
                label={analysis.band_label}
                size={168}
              />
              <p
                className={cx(
                  "mt-1 text-xs font-medium",
                  ELIGIBILITY_CLASS[analysis.eligibility_status],
                )}
              >
                {ELIGIBILITY_LABEL[analysis.eligibility_status]}
              </p>
            </div>
          ) : null}
        </div>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <a
            href={job.apply_url}
            target="_blank"
            rel="noopener noreferrer"
            className="btn-primary btn-sm"
          >
            Apply on {sourceName(job.source)}
          </a>
          <button
            type="button"
            onClick={toggleSave}
            disabled={busy}
            className={cx(
              "btn btn-sm",
              entry.is_saved
                ? "border-ink-400 bg-ink-800 text-ink-50"
                : "border-ink-600 text-ink-300 hover:border-ink-400 hover:text-ink-100",
            )}
          >
            {entry.is_saved ? "Saved" : "Save job"}
          </button>
          {entry.application_status ? (
            <Link href="/tracker" className="chip">
              {APPLICATION_LABEL[entry.application_status]} — view tracker
            </Link>
          ) : (
            <button
              type="button"
              onClick={track}
              disabled={busy}
              className="btn-secondary btn-sm"
            >
              Add to tracker
            </button>
          )}
        </div>
      </header>

      {notScored ? (
        <div className="mt-6">
          <Callout tone="warn" title="Not scored yet">
            This job has not been matched against your profile. Confirm a resume
            and run discovery, or trigger a rescore from{" "}
            <Link href="/settings" className="link">
              Settings
            </Link>
            .
          </Callout>
        </div>
      ) : null}

      {analysis ? <AnalysisBody analysis={analysis} /> : null}

      {/* Job facts + description */}
      <Section title="Role details" className="mt-10">
        <dl className="grid gap-x-8 gap-y-3 border-y border-ink-700 py-4 text-sm sm:grid-cols-2">
          <Fact label="Experience required" value={formatExperienceRequirement(job.experience_min_years, job.experience_max_years)} />
          <Fact label="Seniority" value={EXPERIENCE_LEVEL_LABEL[job.experience_level] ?? job.experience_level} />
          <Fact label="Compensation" value={formatSalary(job.salary_min, job.salary_max, job.salary_currency)} />
          <Fact
            label="Education"
            value={
              (job.education_requirement as { min_level?: number })?.min_level
                ? ["", "High school", "Diploma", "Bachelor's", "Master's", "Doctorate"][
                    (job.education_requirement as { min_level?: number }).min_level ?? 0
                  ] ?? "Stated"
                : "Not stated"
            }
          />
          <Fact label="Application deadline" value={job.deadline_at ? formatDate(job.deadline_at) : "Not stated"} />
          <Fact label="First seen" value={formatDate(job.first_seen_at)} />
        </dl>

        {job.required_skills.length || job.preferred_skills.length ? (
          <div className="mt-6 space-y-4">
            {job.required_skills.length ? (
              <div>
                <p className="label">Required skills</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {job.required_skills.map((skill) => (
                    <SkillChip key={skill} skill={skill} />
                  ))}
                </div>
              </div>
            ) : null}
            {job.preferred_skills.length ? (
              <div>
                <p className="label">Preferred skills</p>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {job.preferred_skills.map((skill) => (
                    <SkillChip key={skill} skill={skill} tone="missing" />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        ) : null}
      </Section>

      <Section title="Original description">
        <div className="prose-none max-w-none space-y-2.5 text-sm leading-relaxed text-ink-300">
          {job.description
            .split("\n")
            .filter((line) => line.trim())
            .map((line, index) =>
              line.trim().startsWith("- ") ? (
                <p key={index} className="pl-4 before:mr-2 before:text-ink-500 before:content-['—']">
                  {line.replace(/^-\s*/, "")}
                </p>
              ) : (
                <p key={index}>{line}</p>
              ),
            )}
        </div>
        <p className="mt-6 text-2xs text-ink-500">
          Sourced from {sourceName(job.source)}.{" "}
          <a href={job.apply_url} target="_blank" rel="noopener noreferrer" className="link">
            View the original posting
          </a>{" "}
          — always confirm the requirements there before applying.
        </p>
      </Section>
    </article>
  );
}

function AnalysisBody({ analysis }: { analysis: MatchAnalysis }) {
  const { calculation } = analysis;
  const mandatory = new Set(analysis.missing_mandatory_skills);

  return (
    <>
      {/* Plain-language explanation */}
      {analysis.explanation ? (
        <Section title="Why this score" className="mt-8">
          <p className="max-w-prose text-sm leading-relaxed text-ink-200">
            {analysis.explanation}
          </p>
          <p className="mt-2 text-2xs text-ink-500">
            {analysis.explanation_source === "llm"
              ? "Written by an AI model from the computed score components. The percentage itself is produced by the scoring algorithm, not the model."
              : "Generated from the score components."}
          </p>
        </Section>
      ) : null}

      {/* Blockers first — these are what actually stop an application */}
      {analysis.blockers.length ? (
        <Section title="Eligibility blockers">
          <div className="space-y-2">
            {analysis.blockers.map((blocker, index) => (
              <Callout
                key={index}
                tone={blocker.severity === "high" ? "danger" : "warn"}
                title={blocker.message}
              >
                {blocker.multiplier_applied !== undefined &&
                blocker.multiplier_applied !== null ? (
                  <span className="num text-2xs">
                    Score multiplied by {blocker.multiplier_applied} because of this.
                  </span>
                ) : null}
              </Callout>
            ))}
          </div>
        </Section>
      ) : null}

      {analysis.eligibility_warnings?.length ? (
        <Section title="Worth knowing">
          <ul className="space-y-1.5 text-sm text-ink-300">
            {analysis.eligibility_warnings.map((warning, index) => (
              <li key={index}>— {warning.message}</li>
            ))}
          </ul>
        </Section>
      ) : null}

      {/* The arithmetic */}
      <Section
        title="How the percentage was calculated"
        description="Each category is scored 0–1, multiplied by its weight, then normalised. Eligibility penalties are applied last."
      >
        <CategoryBars
          data={calculation.steps.map((step) => ({
            key: step.category,
            label: step.label,
            subscore: step.subscore,
            weight: step.weight,
            points: step.contribution_points,
            description: analysis.category_descriptions?.[step.category],
          }))}
        />

        <details className="group mt-3">
          <summary className="cursor-pointer text-xs text-ink-400 hover:text-ink-100">
            Show the full arithmetic as a table
          </summary>
          <div className="surface mt-3 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[34rem] text-sm">
              <thead>
                <tr className="border-b border-ink-700 text-left">
                  <th className="px-4 py-2.5 font-medium text-ink-300">Category</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">Score</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">Weight</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">Points</th>
                </tr>
              </thead>
              <tbody>
                {calculation.steps.map((step) => (
                  <tr key={step.category} className="border-b border-ink-800">
                    <td className="px-4 py-2.5">
                      <span className="text-ink-100">{step.label}</span>
                      {analysis.category_descriptions?.[step.category] ? (
                        <span className="mt-0.5 block max-w-md text-2xs leading-relaxed text-ink-500">
                          {analysis.category_descriptions[step.category]}
                        </span>
                      ) : null}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-ink-200">
                      {step.subscore.toFixed(3)}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-ink-300">
                      {step.weight.toFixed(2)}
                      {step.configured_weight !== undefined &&
                      step.configured_weight !== step.weight ? (
                        <span className="block text-2xs text-ink-500">
                          of {step.configured_weight.toFixed(2)}
                        </span>
                      ) : null}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-ink-50">
                      {step.contribution_points.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-ink-600">
                  <td className="px-4 py-2.5 text-ink-200" colSpan={3}>
                    Weighted subtotal
                  </td>
                  <td className="num px-4 py-2.5 text-right text-ink-50">
                    {calculation.pre_gate_percentage.toFixed(2)}
                  </td>
                </tr>
                <tr>
                  <td className="px-4 py-2.5 text-ink-200" colSpan={3}>
                    Eligibility multiplier
                  </td>
                  <td className="num px-4 py-2.5 text-right text-ink-50">
                    × {calculation.eligibility_multiplier}
                  </td>
                </tr>
                <tr className="border-t border-ink-600 bg-ink-850">
                  <td className="px-4 py-3 font-semibold text-ink-50" colSpan={3}>
                    Final match score
                  </td>
                  <td className="num px-4 py-3 text-right font-semibold text-ink-50">
                    {calculation.final_percentage.toFixed(2)}%
                  </td>
                </tr>
                </tfoot>
              </table>
            </div>
          </div>
        </details>

        <p className="num mt-3 text-2xs text-ink-500">{calculation.formula}</p>

        {calculation.weight_adjustments?.length ? (
          <div className="mt-4 space-y-2">
            {calculation.weight_adjustments.map((adjustment) => (
              <Callout key={adjustment.category} tone="info" title="Weight adjusted">
                {adjustment.reason}
              </Callout>
            ))}
          </div>
        ) : null}

        <p className="mt-4 text-2xs leading-relaxed text-ink-500">
          Raw semantic similarity (cosine) was{" "}
          <span className="num">{calculation.semantic_cosine_raw}</span>.{" "}
          {calculation.job_skills_parsed !== undefined
            ? `${calculation.job_skills_parsed} skills were parsed from this posting.`
            : ""}
        </p>
      </Section>

      {/* Eligibility checks */}
      {analysis.eligibility_checks?.length ? (
        <Section title="Requirement checks">
          <ul className="divide-y divide-ink-700 border-y border-ink-700">
            {analysis.eligibility_checks.map((check, index) => (
              <li key={index} className="flex items-start justify-between gap-4 py-2.5">
                <span className="text-sm text-ink-200">{check.detail}</span>
                <span
                  className={cx(
                    "shrink-0 text-2xs font-medium",
                    check.passed ? "text-signal-ok" : "text-signal-danger",
                  )}
                >
                  {check.passed ? "Met" : "Not met"}
                </span>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}

      {/* Skills */}
      <Section title="Skills">
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <p className="label">
              Matched ({analysis.matched_skills.length})
            </p>
            {analysis.matched_skills.length ? (
              <ul className="mt-2.5 space-y-1.5">
                {analysis.matched_skills.map((skill) => (
                  <li key={skill.skill} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-signal-ok">{skill.skill}</span>
                    <span className="text-ink-500">
                      {skill.via === "exact"
                        ? skill.kind === "mandatory"
                          ? "required"
                          : "preferred"
                        : skill.via === "related"
                          ? `via ${skill.candidate_skill} (partial credit)`
                          : `close match to ${skill.candidate_skill}`}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-ink-500">
                None of this role&apos;s listed skills were found in your profile.
              </p>
            )}
          </div>

          <div>
            <p className="label">Missing ({analysis.missing_skills.length})</p>
            {analysis.missing_skills.length ? (
              <ul className="mt-2.5 space-y-1.5">
                {analysis.missing_skills.map((skill) => (
                  <li key={skill.skill} className="flex items-center justify-between gap-2 text-xs">
                    <span
                      className={
                        mandatory.has(skill.skill) ? "text-signal-danger" : "text-ink-300"
                      }
                    >
                      {skill.skill}
                    </span>
                    <span className="text-ink-500">
                      {mandatory.has(skill.skill) ? "mandatory" : "preferred"}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-2 text-xs text-signal-ok">
                You cover every skill listed on this posting.
              </p>
            )}
          </div>
        </div>

        {analysis.extra_skills.length ? (
          <div className="mt-6">
            <p className="label">Your other skills, not asked for here</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {analysis.extra_skills.slice(0, 18).map((skill) => (
                <SkillChip key={skill} skill={skill} />
              ))}
            </div>
          </div>
        ) : null}
      </Section>

      {/* Evidence */}
      {analysis.relevant_projects.length || analysis.relevant_experience.length ? (
        <Section
          title="Your most relevant evidence"
          description="What the engine treated as supporting evidence for this role."
        >
          <div className="grid gap-6 sm:grid-cols-2">
            {analysis.relevant_projects.length ? (
              <div>
                <p className="label">Projects</p>
                <ul className="mt-2.5 space-y-3">
                  {analysis.relevant_projects.map((item, index) => (
                    <li key={index} className="border-l border-ink-700 pl-3">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-sm text-ink-100">{item.name}</span>
                        <span className="num text-2xs text-ink-400">
                          {Math.round(item.relevance * 100)}%
                        </span>
                      </div>
                      {item.shared_technologies.length ? (
                        <p className="mt-1 text-2xs text-ink-500">
                          Shared: {item.shared_technologies.join(", ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {analysis.relevant_experience.length ? (
              <div>
                <p className="label">Experience</p>
                <ul className="mt-2.5 space-y-3">
                  {analysis.relevant_experience.map((item, index) => (
                    <li key={index} className="border-l border-ink-700 pl-3">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-sm text-ink-100">{item.name}</span>
                        <span className="num text-2xs text-ink-400">
                          {Math.round(item.relevance * 100)}%
                        </span>
                      </div>
                      <p className="mt-1 text-2xs text-ink-500">
                        {[
                          item.company,
                          item.duration_months ? formatMonths(item.duration_months) : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </p>
                      {item.shared_technologies.length ? (
                        <p className="mt-0.5 text-2xs text-ink-500">
                          Shared: {item.shared_technologies.join(", ")}
                        </p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </Section>
      ) : null}

      {/* Reasons & recommendations */}
      <div className="grid gap-6 sm:grid-cols-2">
        {analysis.reasons.length ? (
          <Section title="What drove this score">
            <ul className="space-y-2 text-sm leading-relaxed text-ink-300">
              {analysis.reasons.map((reason, index) => (
                <li key={index}>— {reason}</li>
              ))}
            </ul>
          </Section>
        ) : null}

        {analysis.recommendations.length ? (
          <Section title="How to improve your chances">
            <ul className="space-y-2 text-sm leading-relaxed text-ink-300">
              {analysis.recommendations.map((recommendation, index) => (
                <li key={index}>— {recommendation}</li>
              ))}
            </ul>
          </Section>
        ) : null}
      </div>
    </>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 sm:block">
      <dt className="label">{label}</dt>
      <dd className="text-ink-100 sm:mt-1">{value}</dd>
    </div>
  );
}
