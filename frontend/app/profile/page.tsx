"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  Callout,
  EmptyState,
  ErrorState,
  Field,
  LoadingBlock,
  PageHeader,
  Section,
  SkillChip,
  Spinner,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  DEGREE_LABEL,
  SENIORITY_LABEL,
  formatMonths,
} from "@/lib/format";
import type { Profile } from "@/lib/types";

export default function ProfilePage() {
  return (
    <AppShell>
      <ProfileView />
    </AppShell>
  );
}

function ProfileView() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [noProfile, setNoProfile] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [draft, setDraft] = useState({ full_name: "", phone: "", location: "" });
  const [skillInput, setSkillInput] = useState("");
  const [skills, setSkills] = useState<string[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.profile.get();
      setProfile(data);
      setSkills(data.skills);
      setDraft({
        full_name: data.full_name ?? "",
        phone: data.phone ?? "",
        location: data.location ?? "",
      });
      setError(null);
      setNoProfile(false);
    } catch (err) {
      if (err instanceof ApiError && err.code === "no_profile") {
        setNoProfile(true);
      } else {
        setError(err instanceof ApiError ? err.message : "Could not load your profile.");
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    setSaving(true);
    setNotice(null);
    try {
      const updated = await api.profile.update({
        full_name: draft.full_name || null,
        phone: draft.phone || null,
        location: draft.location || null,
        skills,
      });
      setProfile(updated);
      setSkills(updated.skills);
      setEditing(false);
      setNotice(
        "Profile saved. Your previous match scores were cleared because the profile changed — rescore from Settings, or run discovery again.",
      );
    } catch (err) {
      setNotice(
        err instanceof ApiError ? err.message : "Could not save your profile.",
      );
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <LoadingBlock label="Loading profile" />;

  if (noProfile) {
    return (
      <>
        <PageHeader title="Profile" />
        <EmptyState
          title="No confirmed profile yet"
          description="Upload a resume and confirm the extracted details to create your candidate profile."
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
        <PageHeader title="Profile" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }
  if (!profile) return null;

  return (
    <>
      <PageHeader
        title="Candidate profile"
        description={`Revision ${profile.revision}. This is what every match score is computed against.`}
        actions={
          <>
            <Link href="/upload" className="btn-secondary btn-sm">
              Upload new resume
            </Link>
            {editing ? (
              <>
                <button
                  type="button"
                  className="btn-ghost btn-sm"
                  onClick={() => {
                    setEditing(false);
                    setSkills(profile.skills);
                    setDraft({
                      full_name: profile.full_name ?? "",
                      phone: profile.phone ?? "",
                      location: profile.location ?? "",
                    });
                  }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn-primary btn-sm"
                  onClick={save}
                  disabled={saving || skills.length === 0}
                >
                  {saving ? <Spinner className="border-ink-900 border-t-ink-950" /> : null}
                  Save changes
                </button>
              </>
            ) : (
              <button
                type="button"
                className="btn-primary btn-sm"
                onClick={() => setEditing(true)}
              >
                Edit
              </button>
            )}
          </>
        }
      />

      {notice ? (
        <div className="mb-6">
          <Callout tone="info">{notice}</Callout>
        </div>
      ) : null}

      <div className="grid gap-8 lg:grid-cols-[1fr_20rem]">
        <div className="min-w-0">
          <Section title="Contact">
            {editing ? (
              <div className="max-w-md space-y-4">
                <Field label="Full name">
                  <input
                    className="field"
                    value={draft.full_name}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, full_name: event.target.value }))
                    }
                  />
                </Field>
                <Field label="Phone">
                  <input
                    className="field"
                    value={draft.phone}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, phone: event.target.value }))
                    }
                  />
                </Field>
                <Field label="Location" hint="Used for location filtering">
                  <input
                    className="field"
                    value={draft.location}
                    onChange={(event) =>
                      setDraft((prev) => ({ ...prev, location: event.target.value }))
                    }
                  />
                </Field>
              </div>
            ) : (
              <dl className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2">
                <Row label="Name" value={profile.full_name ?? "Not set"} />
                <Row label="Email" value={profile.email ?? "Not set"} />
                <Row label="Phone" value={profile.phone ?? "Not set"} />
                <Row label="Location" value={profile.location ?? "Not set"} />
              </dl>
            )}

            {profile.links?.length ? (
              <div className="mt-5">
                <p className="label">Links</p>
                <ul className="mt-2 space-y-1">
                  {profile.links.map((link) => (
                    <li key={link}>
                      <a
                        href={link.startsWith("http") ? link : `https://${link}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="link text-xs"
                      >
                        {link}
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </Section>

          <Section title={`Skills (${skills.length})`}>
            {editing ? (
              <>
                <div className="flex flex-wrap gap-1.5">
                  {skills.map((skill) => (
                    <button
                      key={skill}
                      type="button"
                      onClick={() => setSkills((prev) => prev.filter((s) => s !== skill))}
                      className="group inline-flex items-center gap-1.5 border border-ink-700 bg-ink-850 px-2 py-0.5 text-2xs text-ink-200 hover:border-signal-danger/40 hover:text-signal-danger"
                    >
                      {skill}
                      <span aria-hidden>×</span>
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex max-w-md gap-2">
                  <input
                    className="field"
                    placeholder="Add skills, comma separated"
                    value={skillInput}
                    onChange={(event) => setSkillInput(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        const additions = skillInput
                          .split(",")
                          .map((part) => part.trim())
                          .filter(Boolean);
                        setSkills((prev) => [
                          ...prev,
                          ...additions.filter(
                            (skill) =>
                              !prev.some((s) => s.toLowerCase() === skill.toLowerCase()),
                          ),
                        ]);
                        setSkillInput("");
                      }
                    }}
                  />
                </div>
                <p className="mt-2 text-2xs text-ink-500">
                  Press Enter to add. Unrecognised skills are dropped, since
                  matching uses a fixed vocabulary.
                </p>
              </>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {skills.map((skill) => (
                  <SkillChip key={skill} skill={skill} />
                ))}
              </div>
            )}
          </Section>

          {profile.education?.length ? (
            <Section title="Education">
              <ul className="space-y-4">
                {profile.education.map((entry, index) => (
                  <li key={index} className="border-l border-ink-700 pl-4">
                    <p className="text-sm text-ink-50">
                      {entry.degree ?? entry.level_label ?? "Entry"}
                    </p>
                    <p className="mt-0.5 text-xs text-ink-400">
                      {[
                        entry.institution,
                        entry.field,
                        [entry.start, entry.ongoing ? "present" : entry.end]
                          .filter(Boolean)
                          .join(" – "),
                        entry.score ? `Score ${entry.score}` : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {profile.experience?.length ? (
            <Section title="Internships & work experience">
              <ul className="space-y-4">
                {profile.experience.map((entry, index) => (
                  <li key={index} className="border-l border-ink-700 pl-4">
                    <p className="text-sm text-ink-50">{entry.role}</p>
                    <p className="mt-0.5 text-xs text-ink-400">
                      {[
                        entry.company,
                        entry.kind === "internship" ? "Internship" : "Full-time",
                        entry.months ? formatMonths(entry.months) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    {entry.description ? (
                      <p className="mt-1.5 text-xs leading-relaxed text-ink-400">
                        {entry.description}
                      </p>
                    ) : null}
                    {entry.tech?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {entry.tech.map((tech) => (
                          <SkillChip key={tech} skill={tech} />
                        ))}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {profile.projects?.length ? (
            <Section title="Projects">
              <ul className="space-y-4">
                {profile.projects.map((project, index) => (
                  <li key={index} className="border-l border-ink-700 pl-4">
                    <p className="text-sm text-ink-50">{project.name}</p>
                    {project.description ? (
                      <p className="mt-1 text-xs leading-relaxed text-ink-400">
                        {project.description}
                      </p>
                    ) : null}
                    {project.tech?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {project.tech.map((tech) => (
                          <SkillChip key={tech} skill={tech} />
                        ))}
                      </div>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {profile.certifications?.length ? (
            <Section title="Certifications">
              <ul className="space-y-2">
                {profile.certifications.map((cert, index) => (
                  <li key={index} className="text-sm text-ink-200">
                    {cert.name}
                    {cert.issuer || cert.year ? (
                      <span className="text-ink-500">
                        {" "}
                        — {[cert.issuer, cert.year].filter(Boolean).join(", ")}
                      </span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {profile.achievements?.length ? (
            <Section title="Achievements">
              <ul className="space-y-2 text-sm leading-relaxed text-ink-300">
                {profile.achievements.map((item, index) => (
                  <li key={index}>— {item}</li>
                ))}
              </ul>
            </Section>
          ) : null}
        </div>

        {/* Sidebar */}
        <aside className="space-y-5">
          <div className="surface px-4 py-4">
            <p className="label">Candidate level</p>
            <p className="mt-2 text-sm font-semibold text-ink-50">
              {SENIORITY_LABEL[profile.seniority] ?? profile.seniority}
            </p>
            <dl className="mt-4 space-y-2 text-xs">
              <SideRow
                label="Total experience"
                value={formatMonths(profile.total_experience_months)}
              />
              <SideRow
                label="Internships"
                value={formatMonths(profile.internship_months)}
              />
              <SideRow
                label="Highest degree"
                value={DEGREE_LABEL[profile.highest_degree_level] ?? "—"}
              />
              <SideRow label="Field" value={profile.field_of_study ?? "—"} />
              <SideRow
                label="Graduation"
                value={profile.graduation_year ? String(profile.graduation_year) : "—"}
              />
            </dl>

            {profile.seniority_signals?.length ? (
              <details className="mt-4">
                <summary className="cursor-pointer text-2xs text-ink-400 hover:text-ink-200">
                  How this was determined
                </summary>
                <ul className="mt-2 space-y-1.5 text-2xs leading-relaxed text-ink-500">
                  {profile.seniority_signals.map((signal, index) => (
                    <li key={index}>— {signal.detail}</li>
                  ))}
                </ul>
              </details>
            ) : null}
          </div>

          <div className="surface px-4 py-4">
            <p className="label">Matching setup</p>
            <dl className="mt-3 space-y-2 text-xs">
              <SideRow label="Revision" value={String(profile.revision)} />
              <SideRow
                label="Embedding model"
                value={profile.embedding_model ?? "—"}
              />
            </dl>
            <p className="mt-3 text-2xs leading-relaxed text-ink-500">
              Editing your profile invalidates existing scores so nothing stale
              is shown.
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="label">{label}</dt>
      <dd className="mt-1 text-ink-100">{value}</dd>
    </div>
  );
}

function SideRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-ink-500">{label}</dt>
      <dd className="truncate text-right text-ink-200">{value}</dd>
    </div>
  );
}
