"use client";

import type {
  AlternativeRole,
  Application,
  ApplicationBoard,
  ApplicationStatus,
  DashboardSummary,
  DiscoveryRun,
  Health,
  JobList,
  JobWithMatch,
  MatchAnalysis,
  Notification,
  ParsedPayload,
  ParsedResume,
  Profile,
  ResumeFeedback,
  SavedJob,
  SeniorityInfo,
  SkillGap,
  SourceInfo,
  TokenPair,
  User,
  Weights,
} from "./types";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000/api/v1";

const ACCESS_KEY = "jobmatch.access";
const REFRESH_KEY = "jobmatch.refresh";
const USER_KEY = "jobmatch.user";

export class ApiError extends Error {
  code: string;
  status: number;
  fields: Record<string, string>;

  constructor(
    message: string,
    status: number,
    code = "error",
    fields: Record<string, string> = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
  }
}

/* ------------------------------------------------------------------ tokens */

export const tokens = {
  access: () =>
    typeof window === "undefined" ? null : localStorage.getItem(ACCESS_KEY),
  refresh: () =>
    typeof window === "undefined" ? null : localStorage.getItem(REFRESH_KEY),
  user: (): User | null => {
    if (typeof window === "undefined") return null;
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    try {
      return JSON.parse(raw) as User;
    } catch {
      return null;
    }
  },
  save: (pair: TokenPair) => {
    localStorage.setItem(ACCESS_KEY, pair.access_token);
    localStorage.setItem(REFRESH_KEY, pair.refresh_token);
    localStorage.setItem(USER_KEY, JSON.stringify(pair.user));
  },
  saveUser: (user: User) => {
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear: () => {
    localStorage.removeItem(ACCESS_KEY);
    localStorage.removeItem(REFRESH_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

/* ------------------------------------------------------------- core fetch */

// A single in-flight refresh shared by all callers, so a burst of parallel
// 401s triggers one rotation rather than racing and invalidating each other
// (the backend treats a reused refresh token as a leak and revokes the family).
let refreshInFlight: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  const refresh = tokens.refresh();
  if (!refresh) return false;

  if (!refreshInFlight) {
    refreshInFlight = (async () => {
      try {
        const response = await fetch(`${API_BASE}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: refresh }),
        });
        if (!response.ok) {
          tokens.clear();
          return false;
        }
        tokens.save((await response.json()) as TokenPair);
        return true;
      } catch {
        return false;
      } finally {
        refreshInFlight = null;
      }
    })();
  }
  return refreshInFlight;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  form?: FormData;
  retry?: boolean;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, retry = true, signal } = options;

  const headers: Record<string, string> = {};
  const access = tokens.access();
  if (access) headers.Authorization = `Bearer ${access}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
    });
  } catch (error) {
    if ((error as Error)?.name === "AbortError") throw error;
    throw new ApiError(
      "Could not reach the server. Check that the API is running.",
      0,
      "network_error",
    );
  }

  if (response.status === 401 && retry && tokens.refresh()) {
    if (await refreshAccessToken()) {
      return request<T>(path, { ...options, retry: false });
    }
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const payload = text ? safeParse(text) : null;

  if (!response.ok) {
    const detail = (payload as { detail?: unknown })?.detail;
    if (detail && typeof detail === "object") {
      const d = detail as {
        message?: string;
        code?: string;
        fields?: Record<string, string>;
      };
      throw new ApiError(
        d.message ?? "Request failed",
        response.status,
        d.code ?? "error",
        d.fields ?? {},
      );
    }
    throw new ApiError(
      typeof detail === "string" ? detail : `Request failed (${response.status})`,
      response.status,
    );
  }

  return payload as T;
}

function safeParse(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

/** Build a query string, dropping empties and expanding arrays. */
export function qs(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== "") {
          search.append(key, String(item));
        }
      });
    } else if (typeof value === "boolean") {
      if (value) search.set(key, "true");
    } else {
      search.set(key, String(value));
    }
  }
  const out = search.toString();
  return out ? `?${out}` : "";
}

/* ----------------------------------------------------------------- client */

export const api = {
  health: () => request<Health>("/health"),

  auth: {
    register: (email: string, password: string, fullName?: string) =>
      request<TokenPair>("/auth/register", {
        method: "POST",
        body: { email, password, full_name: fullName || null },
      }),
    login: (email: string, password: string) =>
      request<TokenPair>("/auth/login", {
        method: "POST",
        body: { email, password },
      }),
    logout: async () => {
      const refresh = tokens.refresh();
      if (refresh) {
        try {
          await request<void>("/auth/logout", {
            method: "POST",
            body: { refresh_token: refresh },
          });
        } catch {
          // Signing out locally must succeed even if the call fails.
        }
      }
      tokens.clear();
    },
    me: () => request<User>("/auth/me"),
    updateMe: (patch: Partial<Pick<User, "full_name" | "alert_enabled" | "alert_min_match">>) =>
      request<User>("/auth/me", { method: "PATCH", body: patch }),
  },

  resumes: {
    upload: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<ParsedResume>("/resumes", { method: "POST", form });
    },
    list: () => request<unknown[]>("/resumes"),
    parsed: (id: string) => request<ParsedResume>(`/resumes/${id}/parsed`),
    saveParsed: (id: string, payload: ParsedPayload) =>
      request<ParsedResume>(`/resumes/${id}/parsed`, {
        method: "PUT",
        body: { payload },
      }),
    confirm: (id: string) =>
      request<Profile>(`/resumes/${id}/confirm`, { method: "POST" }),
    remove: (id: string) => request<void>(`/resumes/${id}`, { method: "DELETE" }),
  },

  profile: {
    get: () => request<Profile>("/profile"),
    update: (patch: Record<string, unknown>) =>
      request<Profile>("/profile", { method: "PATCH", body: patch }),
    seniority: () => request<SeniorityInfo>("/profile/seniority"),
  },

  sources: {
    list: () => request<SourceInfo[]>("/sources"),
    setEnabled: (key: string, isEnabled: boolean) =>
      request<SourceInfo>(`/sources/${key}`, {
        method: "PATCH",
        body: { is_enabled: isEnabled },
      }),
  },

  discovery: {
    run: (payload: { sources?: string[]; queries?: string[]; location?: string }) =>
      request<DiscoveryRun>("/discovery/run", { method: "POST", body: payload }),
    runs: () => request<DiscoveryRun[]>("/discovery/runs"),
    run_detail: (id: string) =>
      request<{ run: DiscoveryRun; source_logs: unknown[] }>(
        `/discovery/runs/${id}`,
      ),
    rescore: () =>
      request<{ matches_computed: number }>("/discovery/rescore", {
        method: "POST",
      }),
  },

  jobs: {
    search: (params: Record<string, unknown>, signal?: AbortSignal) =>
      request<JobList>(`/jobs${qs(params)}`, { signal }),
    get: (id: string) => request<JobWithMatch>(`/jobs/${id}`),
    analysis: (id: string) => request<MatchAnalysis>(`/jobs/${id}/analysis`),
    summary: () => request<DashboardSummary>("/matches/summary"),
  },

  saved: {
    list: (collection?: string) =>
      request<SavedJob[]>(`/saved${qs({ collection })}`),
    collections: () =>
      request<{ name: string; count: number }[]>("/saved/collections"),
    add: (jobId: string, collection = "Default", notes?: string) =>
      request<SavedJob>("/saved", {
        method: "POST",
        body: { job_id: jobId, collection, notes: notes ?? null },
      }),
    update: (savedId: string, patch: { collection?: string; notes?: string }) =>
      request<SavedJob>(`/saved/${savedId}`, { method: "PATCH", body: patch }),
    remove: (jobId: string) =>
      request<void>(`/saved/${jobId}`, { method: "DELETE" }),
  },

  applications: {
    list: (status?: ApplicationStatus[]) =>
      request<Application[]>(`/applications${qs({ status })}`),
    board: () => request<ApplicationBoard>("/applications/board"),
    create: (jobId: string, status: ApplicationStatus = "interested", notes?: string) =>
      request<Application>("/applications", {
        method: "POST",
        body: { job_id: jobId, status, notes: notes ?? null },
      }),
    update: (id: string, patch: { status?: ApplicationStatus; notes?: string }) =>
      request<Application>(`/applications/${id}`, {
        method: "PATCH",
        body: patch,
      }),
    remove: (id: string) =>
      request<void>(`/applications/${id}`, { method: "DELETE" }),
  },

  insights: {
    skillGap: () => request<SkillGap>("/insights/skill-gap"),
    alternativeRoles: (includeAll = false) =>
      request<{ seniority: string; roles: AlternativeRole[] }>(
        `/insights/alternative-roles${qs({ include_all: includeAll })}`,
      ),
    resumeFeedback: (includeRewrites = false, targetRole?: string) =>
      request<ResumeFeedback>(
        `/insights/resume-feedback${qs({
          include_rewrites: includeRewrites,
          target_role: targetRole,
        })}`,
      ),
  },

  notifications: {
    list: (unreadOnly = false) =>
      request<Notification[]>(`/notifications${qs({ unread_only: unreadOnly })}`),
    markRead: (id: string) =>
      request<Notification>(`/notifications/${id}/read`, { method: "POST" }),
    markAllRead: () =>
      request<void>("/notifications/read-all", { method: "POST" }),
  },

  alerts: {
    get: () =>
      request<{ alert_enabled: boolean; alert_min_match: number }>(
        "/alerts/config",
      ),
    set: (alertEnabled: boolean, alertMinMatch: number) =>
      request<{ alert_enabled: boolean; alert_min_match: number }>(
        "/alerts/config",
        {
          method: "PUT",
          body: { alert_enabled: alertEnabled, alert_min_match: alertMinMatch },
        },
      ),
  },

  weights: {
    get: () => request<Weights>("/settings/weights"),
    set: (weights: Record<string, number>) =>
      request<Weights>("/settings/weights", { method: "PUT", body: { weights } }),
    reset: () => request<Weights>("/settings/weights/reset", { method: "POST" }),
  },
};
