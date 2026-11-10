"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { DemandBars, MiniMeter } from "@/components/charts";
import {
  Callout,
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  Section,
  SkillChip,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { SENIORITY_LABEL, bandOf, formatScore, pluralise } from "@/lib/format";
import type { AlternativeRole, ResumeFeedback, SkillGap } from "@/lib/types";

type Tab = "gap" | "roles" | "resume";

const TABS: { id: Tab; label: string }[] = [
  { id: "gap", label: "Skill gap" },
  { id: "roles", label: "Alternative roles" },
  { id: "resume", label: "Resume feedback" },
];

export default function InsightsPage() {
  return (
    <AppShell>
      <Insights />
    </AppShell>
  );
}

function Insights() {
  const [tab, setTab] = useState<Tab>("gap");
  const [gap, setGap] = useState<SkillGap | null>(null);
  const [roles, setRoles] = useState<{ seniority: string; roles: AlternativeRole[] } | null>(null);
  const [feedback, setFeedback] = useState<ResumeFeedback | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [noProfile, setNoProfile] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [gapResult, rolesResult, feedbackResult] = await Promise.all([
        api.insights.skillGap(),
        api.insights.alternativeRoles(),
        api.insights.resumeFeedback(),
      ]);
      setGap(gapResult);
      setRoles(rolesResult);
      setFeedback(feedbackResult);
      setError(null);
      setNoProfile(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "no_profile") {
        setNoProfile(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load insights.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) return <LoadingBlock label="Analysing your profile" />;

  if (noProfile) {
    return (
      <>
        <PageHeader title="Insights" />
        <EmptyState
          title="Confirm a resume first"
          description="Skill gaps, alternative roles and resume feedback are all derived from your confirmed profile."
          action={
            <Link href="/upload" className="btn-primary">
              Upload your resume
            </Link>
          }
        />
      </>
    );
  }

  if (error) {
    return (
      <>
        <PageHeader title="Insights" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Insights"
        description="Derived from the jobs actually discovered for you, not generic advice."
      />

      <div className="mb-8 flex gap-1 border-b border-ink-700">
        {TABS.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cx(
              "-mb-px border-b px-3 py-2 text-sm transition-colors",
              tab === item.id
                ? "border-ink-50 text-ink-50"
                : "border-transparent text-ink-400 hover:text-ink-100",
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === "gap" && gap ? <SkillGapView gap={gap} /> : null}
      {tab === "roles" && roles ? <RolesView data={roles} /> : null}
      {tab === "resume" && feedback ? <FeedbackView feedback={feedback} /> : null}
    </>
  );
}

function SkillGapView({ gap }: { gap: SkillGap }) {
  if (gap.message) {
    return (
      <EmptyState
        title="Not enough data yet"
        description={gap.message}
        action={
          <Link href="/dashboard" className="btn-primary">
            Run job discovery
          </Link>
        }
      />
    );
  }

  return (
    <>
      <Section
        title="Learn these first"
        description={`Ranked by how often they are demanded across the ${pluralise(gap.total_jobs_analysed, "job")} discovered for you, weighted toward mandatory requirements.`}
      >
        {gap.learn_first.length ? (
          <ol className="space-y-3">
            {gap.learn_first.map((item) => (
              <li key={item.skill} className="surface flex gap-4 px-4 py-3.5">
                <span className="figure shrink-0 text-xl font-semibold text-ink-500">
                  {item.rank}
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-baseline gap-x-3">
                    <span className="text-sm font-semibold text-ink-50">
                      {item.skill}
                    </span>
                    <span className="num text-2xs text-accent-300">
                      est. +{item.estimated_score_lift} points
                    </span>
                  </div>
                  <p className="mt-1 text-xs leading-relaxed text-ink-400">
                    {item.reason}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        ) : (
          <p className="text-sm text-ink-400">No significant gaps found.</p>
        )}
        <p className="mt-3 text-2xs leading-relaxed text-ink-500">
          Estimated lift is an approximation based on how often each skill is
          required and how much headroom those jobs have — not a guarantee.
        </p>
      </Section>

      <Section
        title="Demand across your matched jobs"
        description="How often each missing skill is asked for, as a share of the jobs discovered for you."
      >
        <div className="surface px-4 py-4">
          <DemandBars
            data={gap.gaps.slice(0, 12).map((item) => ({
              label: item.skill,
              value: item.demand_percentage,
              detail: `${item.jobs_requiring} jobs`,
            }))}
          />
        </div>
      </Section>

      <Section title="Full gap list">
        <div className="surface overflow-x-auto">
          <table className="w-full min-w-[36rem] text-sm">
            <thead>
              <tr className="border-b border-ink-700 text-left">
                <th className="px-4 py-2.5 font-medium text-ink-300">Skill</th>
                <th className="px-4 py-2.5 text-right font-medium text-ink-300">Jobs</th>
                <th className="px-4 py-2.5 text-right font-medium text-ink-300">Demand</th>
                <th className="px-4 py-2.5 text-right font-medium text-ink-300">Mandatory</th>
                <th className="px-4 py-2.5 text-right font-medium text-ink-300">Est. lift</th>
              </tr>
            </thead>
            <tbody>
              {gap.gaps.map((item) => (
                <tr key={item.skill} className="border-b border-ink-800">
                  <td className="px-4 py-2.5">
                    <span className="text-ink-100">{item.skill}</span>
                    {item.builds_on.length ? (
                      <span className="mt-0.5 block text-2xs text-ink-500">
                        builds on your {item.builds_on.join(", ")}
                      </span>
                    ) : null}
                  </td>
                  <td className="num px-4 py-2.5 text-right text-ink-300">
                    {item.jobs_requiring}
                  </td>
                  <td className="num px-4 py-2.5 text-right text-ink-300">
                    {item.demand_percentage}%
                  </td>
                  <td className="num px-4 py-2.5 text-right text-ink-300">
                    {item.jobs_requiring_as_mandatory}
                  </td>
                  <td className="num px-4 py-2.5 text-right text-accent-300">
                    +{item.estimated_score_lift}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {gap.strengths.length ? (
        <Section
          title="Your strengths"
          description="Skills you already have that these jobs are asking for."
        >
          <div className="flex flex-wrap gap-1.5">
            {gap.strengths.map((item) => (
              <SkillChip
                key={item.skill}
                skill={`${item.skill} · ${item.jobs_requiring}`}
                tone="matched"
                title={`Requested by ${item.demand_percentage}% of your matched jobs`}
              />
            ))}
          </div>
        </Section>
      ) : null}
    </>
  );
}

function RolesView({ data }: { data: { seniority: string; roles: AlternativeRole[] } }) {
  if (!data.roles.length) {
    return (
      <EmptyState
        title="No role suggestions yet"
        description="Add more skills to your profile so we can identify roles you qualify for."
      />
    );
  }

  return (
    <Section
      title="Roles you could apply for"
      description={`Based on your skills as a ${(SENIORITY_LABEL[data.seniority] ?? data.seniority).toLowerCase()} — not only the job titles on your resume. Fit is computed from how much of each role's defining skill set you already cover.`}
    >
      <div className="grid gap-3 lg:grid-cols-2">
        {data.roles.map((role) => (
          <article key={role.role_key} className="surface px-4 py-4">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-ink-50">{role.title}</h3>
                <p className="mt-1 text-xs leading-relaxed text-ink-400">
                  {role.blurb}
                </p>
              </div>
              <div className="shrink-0 text-right">
                <span className="figure text-2xl font-semibold text-ink-50">
                  {role.fit}%
                </span>
                <p className="text-2xs text-ink-500">skill fit</p>
              </div>
            </div>

            <div className="mt-3">
              <MiniMeter score={role.fit} band={bandOf(role.fit)} />
            </div>

            <p className="mt-3 text-xs leading-relaxed text-ink-300">{role.why}</p>

            {role.matched_skills.length ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {role.matched_skills.slice(0, 8).map((skill) => (
                  <SkillChip key={skill} skill={skill} tone="matched" />
                ))}
              </div>
            ) : null}

            {role.skills_to_add.length ? (
              <div className="mt-2.5">
                <p className="text-2xs text-ink-500">Skills to add</p>
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {role.skills_to_add.map((skill) => (
                    <SkillChip
                      key={skill}
                      skill={skill}
                      tone={role.missing_core_skills.includes(skill) ? "mandatory" : "missing"}
                      title={
                        role.missing_core_skills.includes(skill)
                          ? "Core to this role"
                          : "Supporting skill"
                      }
                    />
                  ))}
                </div>
              </div>
            ) : null}

            <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-ink-800 pt-3">
              <span className="text-2xs text-ink-500">
                {role.open_job_count > 0
                  ? `${pluralise(role.open_job_count, "open role")} indexed`
                  : "No matching listings indexed yet"}
              </span>
              {role.search_terms.length ? (
                <Link
                  href={`/jobs?q=${encodeURIComponent(role.search_terms[0])}`}
                  className="btn-secondary btn-sm"
                >
                  Browse these jobs
                </Link>
              ) : null}
            </div>

            {role.sample_jobs.length ? (
              <ul className="mt-3 space-y-1.5">
                {role.sample_jobs.map((job) => (
                  <li key={job.job_id} className="flex items-center justify-between gap-3 text-2xs">
                    <Link href={`/jobs/${job.job_id}`} className="truncate text-ink-300 hover:text-ink-50">
                      {job.title} · {job.company}
                    </Link>
                    <span className="num shrink-0 text-ink-500">
                      {formatScore(job.score)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}
          </article>
        ))}
      </div>
    </Section>
  );
}

function FeedbackView({ feedback }: { feedback: ResumeFeedback }) {
  const severityTone = {
    high: "danger",
    medium: "warn",
    low: "info",
  } as const;

  return (
    <>
      <Section title="Resume completeness">
        <div className="surface px-4 py-4">
          <div className="flex items-baseline justify-between">
            <span className="figure text-4xl font-semibold text-ink-50">
              {feedback.score}
              <span className="text-lg text-ink-500">/100</span>
            </span>
            <span className="text-2xs text-ink-500">
              Completeness, not a match score
            </span>
          </div>
          <div className="mt-3">
            <MiniMeter score={feedback.score} band={bandOf(feedback.score)} />
          </div>
          <div className="mt-4 flex flex-wrap gap-1.5">
            {Object.entries(feedback.section_coverage).map(([section, present]) => (
              <span
                key={section}
                className={cx(
                  "chip capitalize",
                  present
                    ? "border-signal-ok/30 text-signal-ok"
                    : "border-signal-warn/30 text-signal-warn",
                )}
              >
                {section.replace(/_/g, " ")}
                {present ? "" : " — missing"}
              </span>
            ))}
          </div>
        </div>
      </Section>

      <Section
        title="Suggested improvements"
        description="Ordered by impact on how your resume is read, both by this engine and by recruiters."
      >
        {feedback.suggestions.length ? (
          <div className="space-y-2">
            {feedback.suggestions.map((suggestion, index) => (
              <Callout
                key={index}
                tone={severityTone[suggestion.severity]}
                title={suggestion.title}
              >
                {suggestion.detail}
              </Callout>
            ))}
          </div>
        ) : (
          <p className="text-sm text-signal-ok">
            No structural problems found in your resume.
          </p>
        )}
      </Section>

      {feedback.missing_keywords.length ? (
        <Section
          title="Missing keywords"
          description="Terms that appear in your matched jobs but not in your resume. Add only what you can genuinely evidence."
        >
          <div className="surface overflow-x-auto">
            <table className="w-full min-w-[28rem] text-sm">
              <thead>
                <tr className="border-b border-ink-700 text-left">
                  <th className="px-4 py-2.5 font-medium text-ink-300">Keyword</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">Jobs</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">Frequency</th>
                  <th className="px-4 py-2.5 text-right font-medium text-ink-300">As mandatory</th>
                </tr>
              </thead>
              <tbody>
                {feedback.missing_keywords.map((keyword) => (
                  <tr key={keyword.keyword} className="border-b border-ink-800">
                    <td className="px-4 py-2.5 text-ink-100">{keyword.keyword}</td>
                    <td className="num px-4 py-2.5 text-right text-ink-300">
                      {keyword.job_count}
                    </td>
                    <td className="num px-4 py-2.5 text-right text-ink-300">
                      {keyword.frequency_percentage}%
                    </td>
                    <td className="num px-4 py-2.5 text-right text-ink-300">
                      {keyword.mandatory_count}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      ) : null}
    </>
  );
}
