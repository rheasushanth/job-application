"use client";

import { useMemo, useState } from "react";

import { Callout, Field, PageHeader, SkillChip, Spinner, cx } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { DEGREE_LABEL, SENIORITY_LABEL, formatMonths } from "@/lib/format";
import type { ParsedPayload, ParsedResume } from "@/lib/types";

/** Fields below this confidence get a visible "please check" marker. */
const LOW_CONFIDENCE = 0.75;

export function ResumeReview({
  parsed,
  onConfirmed,
  onReplace,
}: {
  parsed: ParsedResume;
  onConfirmed: () => void;
  onReplace?: () => void;
}) {
  const [payload, setPayload] = useState<ParsedPayload>(parsed.payload);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [skillInput, setSkillInput] = useState("");

  const confidence = parsed.field_confidence ?? {};
  const derived = parsed.derived;

  const skills = payload.skills?.technical ?? [];
  const unrecognised = payload.skills?.unrecognised ?? [];

  const summary = useMemo(
    () => ({
      skills: skills.length,
      education: payload.education?.length ?? 0,
      projects: payload.projects?.length ?? 0,
      experience: payload.experience?.length ?? 0,
      certifications: payload.certifications?.length ?? 0,
    }),
    [payload, skills.length],
  );

  function patchContact(key: keyof ParsedPayload["contact"], value: string) {
    setPayload((prev) => ({
      ...prev,
      contact: { ...prev.contact, [key]: value || null },
    }));
  }

  function removeSkill(skill: string) {
    setPayload((prev) => ({
      ...prev,
      skills: {
        ...prev.skills,
        technical: (prev.skills.technical ?? []).filter((s) => s !== skill),
      },
    }));
  }

  function addSkills(raw: string) {
    const additions = raw
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
    if (!additions.length) return;
    setPayload((prev) => {
      const existing = prev.skills.technical ?? [];
      const merged = [...existing];
      for (const skill of additions) {
        if (!merged.some((s) => s.toLowerCase() === skill.toLowerCase())) {
          merged.push(skill);
        }
      }
      return { ...prev, skills: { ...prev.skills, technical: merged } };
    });
    setSkillInput("");
  }

  async function confirm() {
    setError(null);
    setSaving(true);
    try {
      // Persist the edits, then promote to the active profile.
      await api.resumes.saveParsed(parsed.resume_id, payload);
      await api.resumes.confirm(parsed.resume_id);
      onConfirmed();
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not save your profile. Try again.",
      );
      setSaving(false);
    }
  }

  const modeNote =
    parsed.structuring_mode === "heuristic"
      ? "Extracted with rule-based parsing (no AI key configured). Please check each field carefully."
      : "Extracted with AI structuring, cross-checked against rule-based parsing.";

  return (
    <>
      <PageHeader
        title="Review what we found"
        description="Correct anything that is wrong before continuing — these fields drive every match score."
        actions={
          onReplace ? (
            <button type="button" className="btn-secondary btn-sm" onClick={onReplace}>
              Upload a different file
            </button>
          ) : undefined
        }
      />

      <div className="mx-auto max-w-prose space-y-8">
        <p className="text-xs text-ink-500">{modeNote}</p>

        {parsed.warnings?.length ? (
          <Callout tone="warn" title="Worth checking">
            <ul className="space-y-1.5">
              {parsed.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </Callout>
        ) : null}

        {/* Derived classification */}
        <section className="surface px-4 py-4">
          <p className="label">Detected candidate level</p>
          <p className="mt-2 text-sm font-medium text-ink-50">
            {SENIORITY_LABEL[derived.seniority] ?? derived.seniority}
          </p>
          <dl className="mt-4 grid gap-x-6 gap-y-2 text-xs sm:grid-cols-2">
            <Pair
              label="Total experience"
              value={formatMonths(derived.total_experience_months)}
            />
            <Pair
              label="Of which internships"
              value={formatMonths(derived.internship_months)}
            />
            <Pair
              label="Highest degree"
              value={DEGREE_LABEL[derived.highest_degree_level] ?? "Not recorded"}
            />
            <Pair label="Field of study" value={derived.field_of_study ?? "Not detected"} />
            <Pair
              label="Graduation year"
              value={derived.graduation_year ? String(derived.graduation_year) : "Not detected"}
            />
          </dl>
          {derived.seniority_signals?.length ? (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-ink-400 hover:text-ink-200">
                Why this level?
              </summary>
              <ul className="mt-2 space-y-1.5 text-xs leading-relaxed text-ink-400">
                {derived.seniority_signals.map((signal, index) => (
                  <li key={index}>— {signal.detail}</li>
                ))}
              </ul>
            </details>
          ) : null}
        </section>

        {/* Contact */}
        <section>
          <h2 className="label mb-4">Contact details</h2>
          <div className="space-y-4">
            <Field
              label="Name"
              hint={needsCheck(confidence["contact.name"]) ? "Low confidence — please verify" : undefined}
            >
              <input
                className={cx("field", needsCheck(confidence["contact.name"]) && "border-signal-warn/50")}
                value={payload.contact?.name ?? ""}
                onChange={(event) => patchContact("name", event.target.value)}
                placeholder="Your full name"
              />
            </Field>

            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Email">
                <input
                  type="email"
                  className="field"
                  value={payload.contact?.email ?? ""}
                  onChange={(event) => patchContact("email", event.target.value)}
                />
              </Field>
              <Field label="Phone">
                <input
                  className="field"
                  value={payload.contact?.phone ?? ""}
                  onChange={(event) => patchContact("phone", event.target.value)}
                />
              </Field>
            </div>

            <Field
              label="Location"
              hint="City and region. Used for location filtering."
            >
              <input
                className={cx("field", needsCheck(confidence["contact.location"]) && "border-signal-warn/50")}
                value={payload.contact?.location ?? ""}
                onChange={(event) => patchContact("location", event.target.value)}
                placeholder="e.g. Bengaluru, Karnataka"
              />
            </Field>

            {payload.contact?.links?.length ? (
              <div>
                <p className="label">Links found</p>
                <ul className="mt-2 space-y-1">
                  {payload.contact.links.map((link) => (
                    <li key={link} className="truncate text-xs text-ink-300">
                      {link}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </section>

        {/* Skills */}
        <section>
          <div className="mb-3 flex items-end justify-between">
            <h2 className="label">Skills ({skills.length})</h2>
          </div>

          {skills.length ? (
            <div className="flex flex-wrap gap-1.5">
              {skills.map((skill) => (
                <button
                  key={skill}
                  type="button"
                  onClick={() => removeSkill(skill)}
                  title={`Remove ${skill}`}
                  className="group inline-flex items-center gap-1.5 border border-ink-700 bg-ink-850 px-2 py-0.5 text-2xs text-ink-200 transition-colors hover:border-signal-danger/40 hover:text-signal-danger"
                >
                  {skill}
                  <span aria-hidden className="text-ink-500 group-hover:text-signal-danger">
                    ×
                  </span>
                </button>
              ))}
            </div>
          ) : (
            <Callout tone="danger" title="No skills detected">
              Matching needs at least one skill. Add them below.
            </Callout>
          )}

          <div className="mt-4 flex gap-2">
            <input
              className="field"
              placeholder="Add skills, comma separated"
              value={skillInput}
              onChange={(event) => setSkillInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  event.preventDefault();
                  addSkills(skillInput);
                }
              }}
            />
            <button
              type="button"
              className="btn-secondary shrink-0"
              onClick={() => addSkills(skillInput)}
              disabled={!skillInput.trim()}
            >
              Add
            </button>
          </div>
          <p className="mt-2 text-2xs text-ink-500">
            Skills are matched against a known vocabulary, so &ldquo;ReactJS&rdquo; and
            &ldquo;React&rdquo; count as the same thing.
          </p>

          {unrecognised.length ? (
            <div className="mt-4">
              <p className="label">Not recognised</p>
              <p className="mt-1.5 text-xs leading-relaxed text-ink-400">
                These were found in your resume but are not in the skill
                vocabulary, so they will not contribute to skill matching:
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {unrecognised.map((item) => (
                  <SkillChip key={item} skill={item} tone="missing" />
                ))}
              </div>
            </div>
          ) : null}
        </section>

        {/* Parsed sections at a glance */}
        <section>
          <h2 className="label mb-3">Extracted sections</h2>
          <div className="divide-y divide-ink-700 border-y border-ink-700">
            <SummaryRow label="Education entries" count={summary.education} />
            <SummaryRow label="Projects" count={summary.projects} />
            <SummaryRow label="Internships & roles" count={summary.experience} />
            <SummaryRow label="Certifications" count={summary.certifications} />
          </div>

          {payload.education?.length ? (
            <details className="mt-4">
              <summary className="cursor-pointer text-xs text-ink-400 hover:text-ink-200">
                View education, projects and experience
              </summary>
              <div className="mt-4 space-y-5">
                <DetailList
                  title="Education"
                  items={payload.education.map((entry) => ({
                    heading: entry.degree ?? entry.level_label ?? "Entry",
                    meta: [
                      entry.institution,
                      entry.field,
                      [entry.start, entry.end].filter(Boolean).join(" – "),
                      entry.score ? `Score ${entry.score}` : null,
                    ]
                      .filter(Boolean)
                      .join(" · "),
                  }))}
                />
                <DetailList
                  title="Projects"
                  items={(payload.projects ?? []).map((project) => ({
                    heading: project.name ?? "Untitled",
                    meta: (project.tech ?? []).join(", "),
                    body: project.description,
                  }))}
                />
                <DetailList
                  title="Internships & roles"
                  items={(payload.experience ?? []).map((entry) => ({
                    heading: entry.role ?? "Role",
                    meta: [
                      entry.company,
                      entry.kind === "internship" ? "Internship" : "Full-time",
                      entry.months ? formatMonths(entry.months) : null,
                    ]
                      .filter(Boolean)
                      .join(" · "),
                    body: entry.description,
                  }))}
                />
              </div>
            </details>
          ) : null}
        </section>

        {error ? (
          <Callout tone="danger" title="Could not continue">
            {error}
          </Callout>
        ) : null}

        <div className="divider flex flex-col gap-3 pt-6 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-ink-500">
            You can edit all of this later from your profile.
          </p>
          <button
            type="button"
            className="btn-primary"
            onClick={confirm}
            disabled={saving || skills.length === 0}
          >
            {saving ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
            {saving ? "Saving profile" : "Confirm and find jobs"}
          </button>
        </div>
      </div>
    </>
  );
}

function needsCheck(value: number | undefined): boolean {
  return value !== undefined && value > 0 && value < LOW_CONFIDENCE;
}

function Pair({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-4 sm:block">
      <dt className="text-ink-500">{label}</dt>
      <dd className="text-ink-200 sm:mt-0.5">{value}</dd>
    </div>
  );
}

function SummaryRow({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between py-2.5">
      <span className="text-sm text-ink-200">{label}</span>
      <span
        className={cx(
          "num text-sm",
          count === 0 ? "text-signal-warn" : "text-ink-400",
        )}
      >
        {count === 0 ? "None found" : count}
      </span>
    </div>
  );
}

function DetailList({
  title,
  items,
}: {
  title: string;
  items: { heading: string; meta?: string; body?: string }[];
}) {
  if (!items.length) return null;
  return (
    <div>
      <p className="label">{title}</p>
      <ul className="mt-2 space-y-3">
        {items.map((item, index) => (
          <li key={index} className="border-l border-ink-700 pl-3">
            <p className="text-sm text-ink-100">{item.heading}</p>
            {item.meta ? (
              <p className="mt-0.5 text-2xs text-ink-500">{item.meta}</p>
            ) : null}
            {item.body ? (
              <p className="mt-1 line-clamp-2 text-xs leading-relaxed text-ink-400">
                {item.body}
              </p>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
