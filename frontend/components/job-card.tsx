"use client";

import Link from "next/link";
import { useState } from "react";

import { CompanyMark, MiniMeter } from "@/components/charts";
import { ScoreBadge, SkillChip, SourceTag, cx } from "@/components/ui";
import { api } from "@/lib/api";
import {
  APPLICATION_LABEL,
  BAND_EDGE,
  BAND_LABEL,
  ELIGIBILITY_CLASS,
  ELIGIBILITY_LABEL,
  JOB_TYPE_LABEL,
  WORK_MODE_LABEL,
  formatLocation,
  formatRelativeDate,
  formatSalary,
  sourceName,
} from "@/lib/format";
import type { JobWithMatch } from "@/lib/types";

/**
 * Job card. Shows everything the brief requires on a card: title, company,
 * location, type, mode, source, match percentage, matched and missing skills,
 * posted date, and the three actions.
 */
export function JobCard({
  entry,
  onChanged,
  compact,
}: {
  entry: JobWithMatch;
  onChanged?: () => void;
  compact?: boolean;
}) {
  const { job, match } = entry;
  const [saved, setSaved] = useState(entry.is_saved);
  const [tracked, setTracked] = useState(entry.application_status);
  const [busy, setBusy] = useState(false);

  async function toggleSave() {
    setBusy(true);
    const next = !saved;
    // Optimistic: the button must feel immediate.
    setSaved(next);
    try {
      if (next) await api.saved.add(job.id);
      else await api.saved.remove(job.id);
      onChanged?.();
    } catch {
      setSaved(!next);
    } finally {
      setBusy(false);
    }
  }

  async function track() {
    if (tracked) return;
    setBusy(true);
    setTracked("interested");
    try {
      await api.applications.create(job.id, "interested");
      onChanged?.();
    } catch {
      setTracked(null);
    } finally {
      setBusy(false);
    }
  }

  const matchedSkills = match?.matched_skills ?? [];
  const missingSkills = match?.missing_skills ?? [];
  const mandatoryMissing = new Set(match?.missing_mandatory_skills ?? []);
  const skillLimit = compact ? 4 : 7;

  return (
    <article
      className={cx(
        "surface group border-l-2 px-4 py-4 transition-colors hover:border-ink-500",
        match ? BAND_EDGE[match.band] : "border-l-ink-700",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 flex-1 gap-3">
          <CompanyMark name={job.company} />
          <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-semibold text-ink-50">
            <Link href={`/jobs/${job.id}`} className="hover:underline">
              {job.title}
            </Link>
          </h3>
          <p className="mt-0.5 truncate text-sm text-ink-300">{job.company}</p>

          <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-2xs text-ink-400">
            <span>{formatLocation(job)}</span>
            <span aria-hidden>·</span>
            <span>{WORK_MODE_LABEL[job.work_mode] ?? job.work_mode}</span>
            <span aria-hidden>·</span>
            <span>{JOB_TYPE_LABEL[job.job_type] ?? job.job_type}</span>
            <span aria-hidden>·</span>
            <span>{formatRelativeDate(job.posted_at)}</span>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-2 text-2xs">
            <SourceTag source={sourceName(job.source)} />
            {job.also_seen_on?.length ? (
              <span className="text-ink-500">
                also on {job.also_seen_on.map(sourceName).join(", ")}
              </span>
            ) : null}
            <span className="text-ink-400">
              {formatSalary(job.salary_min, job.salary_max, job.salary_currency)}
            </span>
          </div>
          </div>
        </div>

        <div className="flex shrink-0 flex-col items-end gap-1.5 text-right">
          {match ? (
            <>
              <ScoreBadge score={match.score} band={match.band} />
              <MiniMeter score={match.score} band={match.band} className="w-20" />
              <span className="text-2xs text-ink-500">{BAND_LABEL[match.band]}</span>
              <span
                className={cx("text-2xs", ELIGIBILITY_CLASS[match.eligibility_status])}
              >
                {ELIGIBILITY_LABEL[match.eligibility_status]}
              </span>
            </>
          ) : (
            <span className="text-2xs text-ink-500">Not scored</span>
          )}
        </div>
      </div>

      {match && (matchedSkills.length > 0 || missingSkills.length > 0) ? (
        <div className="mt-3.5 space-y-2">
          {matchedSkills.length ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-2xs text-ink-500">Matched</span>
              {matchedSkills.slice(0, skillLimit).map((skill) => (
                <SkillChip key={skill} skill={skill} tone="matched" />
              ))}
              {matchedSkills.length > skillLimit ? (
                <span className="text-2xs text-ink-500">
                  +{matchedSkills.length - skillLimit}
                </span>
              ) : null}
            </div>
          ) : null}

          {missingSkills.length ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-2xs text-ink-500">Missing</span>
              {missingSkills.slice(0, skillLimit).map((skill) => (
                <SkillChip
                  key={skill}
                  skill={skill}
                  tone={mandatoryMissing.has(skill) ? "mandatory" : "missing"}
                  title={
                    mandatoryMissing.has(skill)
                      ? "Listed as a mandatory requirement"
                      : "Listed as preferred"
                  }
                />
              ))}
              {missingSkills.length > skillLimit ? (
                <span className="text-2xs text-ink-500">
                  +{missingSkills.length - skillLimit}
                </span>
              ) : null}
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <a
          href={job.apply_url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn-primary btn-sm"
        >
          Apply now
        </a>
        <Link href={`/jobs/${job.id}`} className="btn-secondary btn-sm">
          View match analysis
        </Link>
        <button
          type="button"
          onClick={toggleSave}
          disabled={busy}
          className={cx(
            "btn btn-sm",
            saved
              ? "border-accent-line bg-accent-soft text-accent-300"
              : "border-ink-600 bg-ink-850 text-ink-300 hover:border-ink-500 hover:text-ink-100",
          )}
        >
          {saved ? "Saved" : "Save job"}
        </button>
        {tracked ? (
          <span className="chip">{APPLICATION_LABEL[tracked] ?? tracked}</span>
        ) : (
          <button
            type="button"
            onClick={track}
            disabled={busy}
            className="btn-ghost btn-sm"
          >
            Track
          </button>
        )}
      </div>
    </article>
  );
}
