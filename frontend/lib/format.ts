import type { Band, Eligibility } from "./types";

export const BAND_LABEL: Record<Band, string> = {
  excellent: "Excellent match",
  good: "Good match",
  moderate: "Moderate match",
  low: "Low match",
};

/**
 * Per-band chip classes. The ramp is ordinal (one hue, stepped by lightness),
 * so the darker steps need light text and the lighter steps need dark text to
 * stay legible — colour alone never carries the band, the label beside it does.
 */
export const BAND_CLASS: Record<Band, string> = {
  excellent: "text-band-excellent border-band-excellent/45 bg-band-excellent/15",
  good: "text-band-good border-band-good/45 bg-band-good/15",
  moderate: "text-accent-300 border-band-moderate/55 bg-band-moderate/20",
  low: "text-accent-300 border-band-low/60 bg-band-low/25",
};

export const BAND_BAR: Record<Band, string> = {
  excellent: "bg-band-excellent",
  good: "bg-band-good",
  moderate: "bg-band-moderate",
  low: "bg-band-low",
};

/** Left border accent for cards, keyed by band. */
export const BAND_EDGE: Record<Band, string> = {
  excellent: "border-l-band-excellent",
  good: "border-l-band-good",
  moderate: "border-l-band-moderate",
  low: "border-l-band-low",
};

/** Top rule for stat tiles, keyed by band. */
export const BAND_TOP: Record<Band, string> = {
  excellent: "border-t-band-excellent",
  good: "border-t-band-good",
  moderate: "border-t-band-moderate",
  low: "border-t-band-low",
};

export const ELIGIBILITY_LABEL: Record<Eligibility, string> = {
  eligible: "Eligible",
  partially_eligible: "Partially eligible",
  not_eligible: "Not eligible",
};

export const ELIGIBILITY_CLASS: Record<Eligibility, string> = {
  eligible: "text-signal-ok",
  partially_eligible: "text-signal-warn",
  not_eligible: "text-signal-danger",
};

export const APPLICATION_LABEL: Record<string, string> = {
  interested: "Interested",
  applied: "Applied",
  assessment: "Assessment",
  interview: "Interview",
  rejected: "Rejected",
  offer: "Offer",
};

export const SENIORITY_LABEL: Record<string, string> = {
  student: "Student",
  fresher: "Fresher",
  intern: "Intern",
  entry_level: "Entry-level professional",
  experienced: "Experienced professional",
};

export const WORK_MODE_LABEL: Record<string, string> = {
  remote: "Remote",
  hybrid: "Hybrid",
  onsite: "On-site",
  unspecified: "Mode not stated",
};

export const JOB_TYPE_LABEL: Record<string, string> = {
  internship: "Internship",
  full_time: "Full-time",
  part_time: "Part-time",
  contract: "Contract",
  freelance: "Freelance",
  unspecified: "Type not stated",
};

export const EXPERIENCE_LEVEL_LABEL: Record<string, string> = {
  internship: "Internship",
  entry: "Entry level",
  mid: "Mid level",
  senior: "Senior",
  lead: "Lead / Principal",
  unspecified: "Level not stated",
};

export const SOURCE_LABEL: Record<string, string> = {
  remotive: "Remotive",
  arbeitnow: "Arbeitnow",
  jobicy: "Jobicy",
  remoteok: "RemoteOK",
  adzuna: "Adzuna",
  google_jobs: "Google Jobs",
  linkedin: "LinkedIn",
  indeed: "Indeed",
  naukri: "Naukri",
  glassdoor: "Glassdoor",
  wellfound: "Wellfound",
  internshala: "Internshala",
};

export const DEGREE_LABEL: Record<number, string> = {
  0: "Not recorded",
  1: "High school",
  2: "Diploma",
  3: "Bachelor's",
  4: "Master's",
  5: "Doctorate",
};

export function sourceName(key: string): string {
  return SOURCE_LABEL[key] ?? key;
}

export function bandOf(score: number): Band {
  if (score >= 85) return "excellent";
  if (score >= 70) return "good";
  if (score >= 50) return "moderate";
  return "low";
}

export function formatScore(score: number | null | undefined): string {
  if (score === null || score === undefined) return "—";
  return `${score.toFixed(score % 1 === 0 ? 0 : 1)}%`;
}

export function formatRelativeDate(iso: string | null): string {
  if (!iso) return "Date not given";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "Date not given";

  const diffMs = Date.now() - then;
  if (diffMs < 0) return "Just posted";

  const minutes = Math.floor(diffMs / 60000);
  if (minutes < 60) return minutes <= 1 ? "Just posted" : `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months}mo ago`;
  return `${Math.floor(months / 12)}y ago`;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const CURRENCY_PREFIX: Record<string, string> = {
  USD: "$",
  INR: "₹",
  EUR: "€",
  GBP: "£",
  CAD: "C$",
  AUD: "A$",
  SGD: "S$",
};

function compactMoney(value: number, currency: string): string {
  // Indian figures read naturally in lakh/crore; everything else in k/M.
  if (currency === "INR") {
    if (value >= 10_000_000) return `${(value / 10_000_000).toFixed(1)}Cr`;
    if (value >= 100_000) return `${(value / 100_000).toFixed(1)}L`;
    if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
    return String(Math.round(value));
  }
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`;
  return String(Math.round(value));
}

/**
 * Salary is stored annualised. Shows a range when both bounds exist, and
 * explicitly says nothing was published rather than implying zero.
 */
export function formatSalary(
  min: number | null,
  max: number | null,
  currency: string | null,
): string {
  if (min === null && max === null) return "Salary not published";
  const code = currency ?? "USD";
  const prefix = CURRENCY_PREFIX[code] ?? `${code} `;

  if (min !== null && max !== null) {
    if (Math.round(min) === Math.round(max)) {
      return `${prefix}${compactMoney(min, code)}/yr`;
    }
    return `${prefix}${compactMoney(min, code)} – ${prefix}${compactMoney(max, code)}/yr`;
  }
  const value = (min ?? max) as number;
  return `${min !== null ? "From " : "Up to "}${prefix}${compactMoney(value, code)}/yr`;
}

export function formatLocation(job: {
  city: string | null;
  state: string | null;
  country: string | null;
  location_raw: string | null;
  is_remote: boolean;
}): string {
  const parts = [job.city, job.state, job.country].filter(Boolean) as string[];
  // De-duplicate "Delhi, Delhi".
  const unique = parts.filter((part, index) => parts.indexOf(part) === index);
  if (unique.length) return unique.join(", ");
  if (job.location_raw) return job.location_raw;
  return job.is_remote ? "Remote" : "Location not stated";
}

export function formatMonths(months: number | null | undefined): string {
  if (!months) return "None recorded";
  if (months < 12) return `${months} month${months === 1 ? "" : "s"}`;
  const years = Math.floor(months / 12);
  const rest = months % 12;
  const yearPart = `${years} year${years === 1 ? "" : "s"}`;
  return rest ? `${yearPart} ${rest}mo` : yearPart;
}

export function formatExperienceRequirement(
  min: number | null,
  max: number | null,
): string {
  if (min === null && max === null) return "Not stated";
  if (min !== null && max !== null) return `${min}–${max} years`;
  if (min !== null) return min === 0 ? "No minimum" : `${min}+ years`;
  return `Up to ${max} years`;
}

export function pluralise(count: number, singular: string, plural?: string): string {
  return `${count} ${count === 1 ? singular : (plural ?? `${singular}s`)}`;
}

export function titleCase(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

export function truncate(text: string, limit: number): string {
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1).trimEnd()}…`;
}

/** Collapse a job description into a readable one-paragraph preview. */
export function descriptionPreview(description: string, limit = 240): string {
  const cleaned = description
    .split("\n")
    .map((line) => line.replace(/^-\s*/, "").trim())
    .filter((line) => line.length > 0)
    .join(" ")
    .replace(/\s+/g, " ");
  return truncate(cleaned, limit);
}
