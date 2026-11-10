"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { useAuth } from "@/components/auth-provider";
import { LoadingBlock, cx } from "@/components/ui";
import { api } from "@/lib/api";

const NAV = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/jobs", label: "Jobs" },
  { href: "/insights", label: "Insights" },
  { href: "/saved", label: "Saved" },
  { href: "/tracker", label: "Tracker" },
  { href: "/profile", label: "Profile" },
  { href: "/settings", label: "Settings" },
];

/**
 * Authenticated layout. Redirects to /login when there is no session, and
 * keeps the unread-notification count in the header.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const { user, ready, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [unread, setUnread] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (ready && !user) router.replace("/login");
  }, [ready, user, router]);

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    api.notifications
      .list(true)
      .then((items) => {
        if (!cancelled) setUnread(items.length);
      })
      .catch(() => {
        /* the badge is non-essential */
      });
    return () => {
      cancelled = true;
    };
  }, [user, pathname]);

  useEffect(() => {
    setMenuOpen(false);
  }, [pathname]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <LoadingBlock label="Restoring session" />
      </div>
    );
  }
  if (!user) return null;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-ink-700 bg-ink-950/90 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-shell items-center gap-6 px-5">
          <Link
            href="/dashboard"
            className="shrink-0 text-sm font-semibold tracking-tightest text-ink-50"
          >
            JobMatch
          </Link>

          <nav className="hidden flex-1 items-center gap-1 md:flex">
            {NAV.map((item) => {
              const active =
                pathname === item.href || pathname.startsWith(`${item.href}/`);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cx(
                    "rounded px-2.5 py-1.5 text-sm transition-colors",
                    active
                      ? "bg-accent-soft text-accent-300"
                      : "text-ink-400 hover:bg-ink-850 hover:text-ink-100",
                  )}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-3">
            <Link
              href="/notifications"
              className="relative text-sm text-ink-400 transition-colors hover:text-ink-100"
            >
              Alerts
              {unread > 0 ? (
                <span className="num absolute -right-3 -top-1.5 rounded-sm border border-accent-line bg-accent-600 px-1 text-[10px] font-semibold text-white">
                  {unread > 99 ? "99+" : unread}
                </span>
              ) : null}
            </Link>
            <span className="hidden text-xs text-ink-500 lg:inline">
              {user.email}
            </span>
            <button
              type="button"
              onClick={() => logout()}
              className="btn-ghost btn-sm"
            >
              Sign out
            </button>
            <button
              type="button"
              className="btn-ghost btn-sm md:hidden"
              aria-expanded={menuOpen}
              aria-label="Toggle navigation"
              onClick={() => setMenuOpen((open) => !open)}
            >
              Menu
            </button>
          </div>
        </div>

        {menuOpen ? (
          <nav className="divider grid grid-cols-2 gap-1 px-5 py-3 md:hidden">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="px-2 py-2 text-sm text-ink-300"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        ) : null}
      </header>

      <main className="mx-auto w-full max-w-shell flex-1 px-5 py-9">
        {children}
      </main>

      <footer className="border-t border-ink-700 py-5">
        <div className="mx-auto max-w-shell px-5 text-2xs text-ink-500">
          Match percentages are guidance, not eligibility decisions. Always read
          the original posting before applying.
        </div>
      </footer>
    </div>
  );
}
