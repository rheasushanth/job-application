"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AppShell } from "@/components/app-shell";
import { JobCard } from "@/components/job-card";
import {
  EmptyState,
  ErrorState,
  Field,
  LoadingBlock,
  PageHeader,
  SkeletonRows,
  cx,
} from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import {
  EXPERIENCE_LEVEL_LABEL,
  JOB_TYPE_LABEL,
  WORK_MODE_LABEL,
  pluralise,
  sourceName,
} from "@/lib/format";
import type { Facet, JobList } from "@/lib/types";

const SORTS = [
  { value: "match_desc", label: "Match: high to low" },
  { value: "match_asc", label: "Match: low to high" },
  { value: "posted_desc", label: "Recently posted" },
  { value: "posted_asc", label: "Oldest posted" },
  { value: "salary_desc", label: "Salary: high to low" },
  { value: "salary_asc", label: "Salary: low to high" },
  { value: "company_asc", label: "Company A–Z" },
];

const PAGE_SIZE = 20;

/** Filter state mirrored into the URL so views are shareable and restorable. */
interface Filters {
  q: string;
  city: string;
  country: string;
  company: string[];
  source: string[];
  work_mode: string[];
  job_type: string[];
  experience_level: string[];
  band: string[];
  eligibility: string[];
  skills: string[];
  min_match: string;
  max_match: string;
  salary_min: string;
  posted_within_days: string;
  saved_only: boolean;
  tracked_only: boolean;
  sort: string;
  page: number;
}

const EMPTY: Filters = {
  q: "",
  city: "",
  country: "",
  company: [],
  source: [],
  work_mode: [],
  job_type: [],
  experience_level: [],
  band: [],
  eligibility: [],
  skills: [],
  min_match: "",
  max_match: "",
  salary_min: "",
  posted_within_days: "",
  saved_only: false,
  tracked_only: false,
  sort: "match_desc",
  page: 1,
};

const MULTI_KEYS = [
  "company",
  "source",
  "work_mode",
  "job_type",
  "experience_level",
  "band",
  "eligibility",
  "skills",
] as const;

function fromParams(params: URLSearchParams): Filters {
  const next: Filters = { ...EMPTY, company: [], source: [], work_mode: [], job_type: [], experience_level: [], band: [], eligibility: [], skills: [] };
  next.q = params.get("q") ?? "";
  next.city = params.get("city") ?? "";
  next.country = params.get("country") ?? "";
  next.min_match = params.get("min_match") ?? "";
  next.max_match = params.get("max_match") ?? "";
  next.salary_min = params.get("salary_min") ?? "";
  next.posted_within_days = params.get("posted_within_days") ?? "";
  next.saved_only = params.get("saved_only") === "true";
  next.tracked_only = params.get("tracked_only") === "true";
  next.sort = params.get("sort") ?? "match_desc";
  next.page = Math.max(1, Number(params.get("page") ?? 1) || 1);
  for (const key of MULTI_KEYS) {
    next[key] = params.getAll(key);
  }
  return next;
}

function toParams(filters: Filters): URLSearchParams {
  const params = new URLSearchParams();
  const simple: (keyof Filters)[] = [
    "q", "city", "country", "min_match", "max_match",
    "salary_min", "posted_within_days",
  ];
  for (const key of simple) {
    const value = filters[key];
    if (typeof value === "string" && value) params.set(key, value);
  }
  for (const key of MULTI_KEYS) {
    filters[key].forEach((value) => params.append(key, value));
  }
  if (filters.saved_only) params.set("saved_only", "true");
  if (filters.tracked_only) params.set("tracked_only", "true");
  if (filters.sort !== "match_desc") params.set("sort", filters.sort);
  if (filters.page > 1) params.set("page", String(filters.page));
  return params;
}

export default function JobsPage() {
  return (
    <AppShell>
      <Suspense fallback={<LoadingBlock />}>
        <JobsBrowser />
      </Suspense>
    </AppShell>
  );
}

function JobsBrowser() {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [filters, setFilters] = useState<Filters>(() =>
    fromParams(new URLSearchParams(searchParams.toString())),
  );
  const [searchText, setSearchText] = useState(filters.q);
  const [data, setData] = useState<JobList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [panelOpen, setPanelOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Debounce the free-text box so typing doesn't fire a request per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((prev) =>
        prev.q === searchText ? prev : { ...prev, q: searchText, page: 1 },
      );
    }, 350);
    return () => clearTimeout(timer);
  }, [searchText]);

  // Keep the URL in step with the filter state.
  useEffect(() => {
    const query = toParams(filters).toString();
    router.replace(query ? `/jobs?${query}` : "/jobs", { scroll: false });
  }, [filters, router]);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setLoading(true);
    try {
      const result = await api.jobs.search(
        { ...filters, page_size: PAGE_SIZE },
        controller.signal,
      );
      setData(result);
      setError(null);
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      setError(err instanceof ApiError ? err.message : "Could not load jobs.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  function update<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value, page: 1 }));
  }

  function toggleMulti(key: (typeof MULTI_KEYS)[number], value: string) {
    setFilters((prev) => {
      const current = prev[key];
      const next = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      return { ...prev, [key]: next, page: 1 };
    });
  }

  function reset() {
    setSearchText("");
    setFilters({ ...EMPTY, company: [], source: [], work_mode: [], job_type: [], experience_level: [], band: [], eligibility: [], skills: [] });
  }

  const activeCount = useMemo(() => {
    let count = 0;
    if (filters.q) count += 1;
    if (filters.city) count += 1;
    if (filters.country) count += 1;
    if (filters.min_match) count += 1;
    if (filters.max_match) count += 1;
    if (filters.salary_min) count += 1;
    if (filters.posted_within_days) count += 1;
    if (filters.saved_only) count += 1;
    if (filters.tracked_only) count += 1;
    for (const key of MULTI_KEYS) count += filters[key].length;
    return count;
  }, [filters]);

  const facets = data?.facets;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <>
      <PageHeader
        title="Job discovery"
        description="Filtering and sorting run as database queries, so results stay accurate across every page."
      />

      {/* Search + sort bar */}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center">
        <input
          className="field flex-1"
          placeholder="Search titles, companies and descriptions"
          value={searchText}
          onChange={(event) => setSearchText(event.target.value)}
          aria-label="Search jobs"
        />
        <select
          className="field sm:w-56"
          value={filters.sort}
          onChange={(event) => update("sort", event.target.value)}
          aria-label="Sort results"
        >
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="btn-secondary lg:hidden"
          onClick={() => setPanelOpen((open) => !open)}
        >
          Filters{activeCount ? ` (${activeCount})` : ""}
        </button>
      </div>

      <div className="grid gap-6 lg:grid-cols-[17rem_1fr]">
        {/* Filter panel */}
        <aside className={cx("lg:block", panelOpen ? "block" : "hidden")}>
          <div className="surface sticky top-20 max-h-[calc(100vh-6rem)] overflow-y-auto px-4 py-4">
            <div className="flex items-center justify-between">
              <h2 className="label">Filters</h2>
              {activeCount ? (
                <button type="button" onClick={reset} className="text-2xs text-ink-400 hover:text-ink-100">
                  Clear all ({activeCount})
                </button>
              ) : null}
            </div>

            <div className="mt-4 space-y-5">
              <div className="space-y-2">
                <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-200">
                  <input
                    type="checkbox"
                    className="accent-ink-50"
                    checked={filters.saved_only}
                    onChange={(event) => update("saved_only", event.target.checked)}
                  />
                  Saved jobs only
                </label>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-ink-200">
                  <input
                    type="checkbox"
                    className="accent-ink-50"
                    checked={filters.tracked_only}
                    onChange={(event) => update("tracked_only", event.target.checked)}
                  />
                  In my tracker only
                </label>
              </div>

              <FilterGroup label="Match percentage">
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    max={100}
                    placeholder="Min"
                    className="field"
                    value={filters.min_match}
                    onChange={(event) => update("min_match", event.target.value)}
                  />
                  <span className="text-ink-500">–</span>
                  <input
                    type="number"
                    min={0}
                    max={100}
                    placeholder="Max"
                    className="field"
                    value={filters.max_match}
                    onChange={(event) => update("max_match", event.target.value)}
                  />
                </div>
              </FilterGroup>

              <CheckGroup
                label="Match band"
                options={[
                  { value: "excellent", label: "Excellent 85%+" },
                  { value: "good", label: "Good 70–84%" },
                  { value: "moderate", label: "Moderate 50–69%" },
                  { value: "low", label: "Low below 50%" },
                ]}
                selected={filters.band}
                onToggle={(value) => toggleMulti("band", value)}
              />

              <CheckGroup
                label="Eligibility"
                options={[
                  { value: "eligible", label: "Eligible" },
                  { value: "partially_eligible", label: "Partially eligible" },
                  { value: "not_eligible", label: "Not eligible" },
                ]}
                selected={filters.eligibility}
                onToggle={(value) => toggleMulti("eligibility", value)}
              />

              <FacetGroup
                label="Work mode"
                facets={facets?.work_modes}
                selected={filters.work_mode}
                onToggle={(value) => toggleMulti("work_mode", value)}
                labels={WORK_MODE_LABEL}
              />

              <FacetGroup
                label="Job type"
                facets={facets?.job_types}
                selected={filters.job_type}
                onToggle={(value) => toggleMulti("job_type", value)}
                labels={JOB_TYPE_LABEL}
              />

              <FacetGroup
                label="Experience level"
                facets={facets?.experience_levels}
                selected={filters.experience_level}
                onToggle={(value) => toggleMulti("experience_level", value)}
                labels={EXPERIENCE_LEVEL_LABEL}
              />

              <FacetGroup
                label="Job portal"
                facets={facets?.sources}
                selected={filters.source}
                onToggle={(value) => toggleMulti("source", value)}
                labelFn={sourceName}
              />

              <FilterGroup label="Location">
                <div className="space-y-2">
                  <input
                    className="field"
                    placeholder="City"
                    value={filters.city}
                    onChange={(event) => update("city", event.target.value)}
                  />
                  <input
                    className="field"
                    placeholder="Country"
                    value={filters.country}
                    onChange={(event) => update("country", event.target.value)}
                  />
                </div>
              </FilterGroup>

              <FilterGroup label="Minimum salary (annual)">
                <input
                  type="number"
                  min={0}
                  step={10000}
                  className="field"
                  placeholder="Any"
                  value={filters.salary_min}
                  onChange={(event) => update("salary_min", event.target.value)}
                />
                <p className="mt-1.5 text-2xs text-ink-500">
                  Jobs that publish no salary are still shown.
                </p>
              </FilterGroup>

              <FilterGroup label="Date posted">
                <select
                  className="field"
                  value={filters.posted_within_days}
                  onChange={(event) => update("posted_within_days", event.target.value)}
                >
                  <option value="">Any time</option>
                  <option value="1">Last 24 hours</option>
                  <option value="3">Last 3 days</option>
                  <option value="7">Last week</option>
                  <option value="14">Last 2 weeks</option>
                  <option value="30">Last month</option>
                </select>
              </FilterGroup>

              <FacetGroup
                label="Required skills"
                facets={facets?.skills?.slice(0, 24)}
                selected={filters.skills}
                onToggle={(value) => toggleMulti("skills", value)}
                hint="All selected skills must be present"
              />

              <FacetGroup
                label="Company"
                facets={facets?.companies?.slice(0, 20)}
                selected={filters.company}
                onToggle={(value) => toggleMulti("company", value)}
              />
            </div>
          </div>
        </aside>

        {/* Results */}
        <div className="min-w-0">
          <div className="mb-4 flex items-center justify-between text-xs text-ink-400">
            <span>
              {loading && !data
                ? "Loading…"
                : data
                  ? `${pluralise(data.total, "job")} found`
                  : ""}
            </span>
            {data && data.total > 0 ? (
              <span className="num">
                Page {data.page} of {totalPages}
              </span>
            ) : null}
          </div>

          {error ? (
            <ErrorState message={error} onRetry={load} />
          ) : loading && !data ? (
            <SkeletonRows rows={5} />
          ) : !data || data.items.length === 0 ? (
            <EmptyState
              title={activeCount ? "No jobs match these filters" : "No jobs yet"}
              description={
                activeCount
                  ? "Try removing a filter — the match-percentage and skill filters are the most restrictive."
                  : "Run a discovery pass from the dashboard to search the connected job platforms."
              }
              action={
                activeCount ? (
                  <button type="button" className="btn-secondary" onClick={reset}>
                    Clear all filters
                  </button>
                ) : undefined
              }
            />
          ) : (
            <>
              <div className={cx("space-y-3", loading && "opacity-60 transition-opacity")}>
                {data.items.map((entry) => (
                  <JobCard key={entry.job.id} entry={entry} onChanged={load} />
                ))}
              </div>

              {totalPages > 1 ? (
                <nav className="mt-6 flex items-center justify-between">
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={data.page <= 1}
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, page: prev.page - 1 }))
                    }
                  >
                    Previous
                  </button>
                  <span className="num text-xs text-ink-400">
                    {data.page} / {totalPages}
                  </span>
                  <button
                    type="button"
                    className="btn-secondary btn-sm"
                    disabled={data.page >= totalPages}
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, page: prev.page + 1 }))
                    }
                  >
                    Next
                  </button>
                </nav>
              ) : null}
            </>
          )}
        </div>
      </div>
    </>
  );
}

function FilterGroup({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <p className="label mb-2">{label}</p>
      {children}
    </div>
  );
}

function CheckGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: { value: string; label: string }[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  return (
    <FilterGroup label={label}>
      <div className="space-y-1.5">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex cursor-pointer items-center gap-2 text-xs text-ink-200"
          >
            <input
              type="checkbox"
              className="accent-ink-50"
              checked={selected.includes(option.value)}
              onChange={() => onToggle(option.value)}
            />
            {option.label}
          </label>
        ))}
      </div>
    </FilterGroup>
  );
}

function FacetGroup({
  label,
  facets,
  selected,
  onToggle,
  labels,
  labelFn,
  hint,
}: {
  label: string;
  facets: Facet[] | undefined;
  selected: string[];
  onToggle: (value: string) => void;
  labels?: Record<string, string>;
  labelFn?: (value: string) => string;
  hint?: string;
}) {
  // Always render anything already selected, even if it fell out of the facet
  // list, so a filter can never become impossible to switch off.
  const values = new Map<string, number | null>();
  (facets ?? []).forEach((facet) => values.set(facet.value, facet.count));
  selected.forEach((value) => {
    if (!values.has(value)) values.set(value, null);
  });

  if (values.size === 0) return null;

  return (
    <FilterGroup label={label}>
      <div className="space-y-1.5">
        {Array.from(values.entries()).map(([value, count]) => (
          <label
            key={value}
            className="flex cursor-pointer items-center justify-between gap-2 text-xs text-ink-200"
          >
            <span className="flex min-w-0 items-center gap-2">
              <input
                type="checkbox"
                className="accent-ink-50"
                checked={selected.includes(value)}
                onChange={() => onToggle(value)}
              />
              <span className="truncate">
                {labelFn ? labelFn(value) : (labels?.[value] ?? value)}
              </span>
            </span>
            {count !== null ? (
              <span className="num shrink-0 text-ink-500">{count}</span>
            ) : null}
          </label>
        ))}
      </div>
      {hint ? <p className="mt-1.5 text-2xs text-ink-500">{hint}</p> : null}
    </FilterGroup>
  );
}
