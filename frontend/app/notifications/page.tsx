"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/app-shell";
import {
  EmptyState,
  ErrorState,
  LoadingBlock,
  PageHeader,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Notification } from "@/lib/types";

export default function NotificationsPage() {
  return (
    <AppShell>
      <Notifications />
    </AppShell>
  );
}

function Notifications() {
  const [items, setItems] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.notifications.list());
      setError(null);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not load notifications.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function markAll() {
    await api.notifications.markAllRead();
    load();
  }

  async function markOne(id: string) {
    await api.notifications.markRead(id);
    setItems((prev) =>
      prev.map((item) => (item.id === id ? { ...item, is_read: true } : item)),
    );
  }

  if (loading) return <LoadingBlock label="Loading alerts" />;
  if (error) {
    return (
      <>
        <PageHeader title="Alerts" />
        <ErrorState message={error} onRetry={load} />
      </>
    );
  }

  const unread = items.filter((item) => !item.is_read).length;

  if (!items.length) {
    return (
      <>
        <PageHeader title="Alerts" />
        <EmptyState
          title="No alerts yet"
          description="When a discovery run finds jobs above your match threshold, they appear here. Adjust the threshold in Settings."
          action={
            <Link href="/settings" className="btn-secondary">
              Alert settings
            </Link>
          }
        />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Alerts"
        description={
          unread
            ? `${unread} unread of ${items.length}.`
            : `${items.length} alerts, all read.`
        }
        actions={
          unread ? (
            <button type="button" className="btn-secondary btn-sm" onClick={markAll}>
              Mark all read
            </button>
          ) : undefined
        }
      />

      <ul className="space-y-2">
        {items.map((item) => (
          <li
            key={item.id}
            className={cx(
              "surface px-4 py-3.5",
              !item.is_read && "border-l-2 border-l-ink-100",
            )}
          >
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <p
                  className={cx(
                    "text-sm",
                    item.is_read ? "text-ink-300" : "font-medium text-ink-50",
                  )}
                >
                  {item.title}
                </p>
                {item.body ? (
                  <p className="mt-1 text-xs leading-relaxed text-ink-400">
                    {item.body}
                  </p>
                ) : null}
                <p className="mt-1.5 text-2xs text-ink-500">
                  {formatDateTime(item.created_at)}
                </p>
              </div>

              <div className="flex shrink-0 flex-col items-end gap-2">
                {!item.is_read ? (
                  <button
                    type="button"
                    className="text-2xs text-ink-400 hover:text-ink-100"
                    onClick={() => markOne(item.id)}
                  >
                    Mark read
                  </button>
                ) : null}
                {Number(item.payload?.threshold) ? (
                  <Link
                    href={`/jobs?min_match=${item.payload.threshold}`}
                    className="btn-secondary btn-sm"
                  >
                    View matches
                  </Link>
                ) : null}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
