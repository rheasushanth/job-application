"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { JobCard } from "@/components/job-card";
import {
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  Section,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { pluralise } from "@/lib/format";
import type { SavedJob } from "@/lib/types";

export default function SavedPage() {
  return (
    <AppShell>
      <Saved />
    </AppShell>
  );
}

function Saved() {
  const [items, setItems] = useState<SavedJob[]>([]);
  const [collection, setCollection] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState({ collection: "", notes: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.saved.list());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not load saved jobs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const collections = useMemo(() => {
    const counts = new Map<string, number>();
    items.forEach((item) => {
      counts.set(item.collection, (counts.get(item.collection) ?? 0) + 1);
    });
    return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
  }, [items]);

  const visible = collection
    ? items.filter((item) => item.collection === collection)
    : items;

  async function saveEdits(saved: SavedJob) {
    try {
      await api.saved.update(saved.id, {
        collection: draft.collection.trim() || "Default",
        notes: draft.notes,
      });
      setEditing(null);
      load();
    } catch {
      /* keep the editor open so the user can retry */
    }
  }

  if (loading) return <LoadingBlock label="Loading saved jobs" />;
  if (error) {
    return (
      <>
        <PageHeader title="Saved jobs" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }

  if (!items.length) {
    return (
      <>
        <PageHeader title="Saved jobs" />
        <EmptyState
          title="Nothing saved yet"
          description="Use Save job on any listing to bookmark it here. You can group saved jobs into collections."
          action={
            <Link href="/jobs" className="btn-primary">
              Browse jobs
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Saved jobs"
        description={`${pluralise(items.length, "job")} bookmarked across ${pluralise(collections.length, "collection")}.`}
      />

      {collections.length > 1 ? (
        <div className="mb-6 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => setCollection(null)}
            className={cx(
              "chip",
              collection === null && "border-ink-300 text-ink-50",
            )}
          >
            All ({items.length})
          </button>
          {collections.map(([name, count]) => (
            <button
              key={name}
              type="button"
              onClick={() => setCollection(name)}
              className={cx(
                "chip",
                collection === name && "border-ink-300 text-ink-50",
              )}
            >
              {name} ({count})
            </button>
          ))}
        </div>
      ) : null}

      <Section>
        <div className="space-y-3">
          {visible.map((saved) => (
            <div key={saved.id}>
              <JobCard
                entry={{
                  job: saved.job,
                  match: saved.match,
                  is_saved: true,
                  application_status: null,
                }}
                onChanged={load}
              />

              <div className="surface-raised -mt-px border-t-0 px-4 py-2.5">
                {editing === saved.id ? (
                  <div className="space-y-2">
                    <div className="flex flex-col gap-2 sm:flex-row">
                      <input
                        className="field sm:max-w-[14rem]"
                        placeholder="Collection"
                        value={draft.collection}
                        onChange={(event) =>
                          setDraft((prev) => ({ ...prev, collection: event.target.value }))
                        }
                      />
                      <input
                        className="field"
                        placeholder="Notes"
                        value={draft.notes}
                        onChange={(event) =>
                          setDraft((prev) => ({ ...prev, notes: event.target.value }))
                        }
                      />
                    </div>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        className="btn-primary btn-sm"
                        onClick={() => saveEdits(saved)}
                      >
                        Save
                      </button>
                      <button
                        type="button"
                        className="btn-ghost btn-sm"
                        onClick={() => setEditing(null)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="flex flex-wrap items-center justify-between gap-2 text-2xs">
                    <span className="text-ink-400">
                      <span className="text-ink-200">{saved.collection}</span>
                      {saved.notes ? ` — ${saved.notes}` : ""}
                    </span>
                    <button
                      type="button"
                      className="text-ink-400 hover:text-ink-100"
                      onClick={() => {
                        setEditing(saved.id);
                        setDraft({
                          collection: saved.collection,
                          notes: saved.notes ?? "",
                        });
                      }}
                    >
                      Edit collection & notes
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}
