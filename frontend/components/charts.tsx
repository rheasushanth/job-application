"use client";

import { useId, useState } from "react";

import { cx } from "@/components/ui";
import {
  AXIS_TEXT,
  BAND_HEX,
  BAND_TRACK,
  GRID,
  SEQUENTIAL,
  SEQUENTIAL_TRACK,
} from "@/lib/palette";
import { BAND_LABEL, bandOf } from "@/lib/format";
import type { Band } from "@/lib/types";

/* Mark specs, held in one place so every chart agrees.
   Bars cap at 24px thick with a 4px rounded data-end and a square baseline;
   touching marks are separated by a 2px gap in the surface colour, never by a
   stroke. */
const BAR_RADIUS = 4;
const SURFACE_GAP = 2;

/* ------------------------------------------------------------------ meter */

/**
 * Radial match meter. A single ratio against a limit, so a meter rather than a
 * pie or a one-bar chart. The track is a lighter step of the same ramp so the
 * band reads across the whole arc.
 *
 * The number inside is the view's hero figure: ≥48px, in the body sans (a
 * display face at this size reads as decoration), and with proportional
 * figures — `tabular-nums` gives every digit a `0`'s width, which looks loose
 * at display sizes.
 */
export function ScoreMeter({
  score,
  band,
  size = 176,
  label,
}: {
  score: number;
  band: Band;
  size?: number;
  label?: string;
}) {
  const stroke = 12;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  // Leave the bottom quarter open so the arc reads as a gauge, not a donut.
  const sweep = 0.75;
  const arc = circumference * sweep;
  const filled = arc * Math.max(0, Math.min(100, score)) / 100;

  return (
    <figure className="flex flex-col items-center gap-3">
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="-rotate-[135deg]"
          role="img"
          aria-label={`Match score ${score.toFixed(1)} percent, ${BAND_LABEL[band]}`}
        >
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={BAND_TRACK[band]}
            strokeWidth={stroke}
            strokeDasharray={`${arc} ${circumference}`}
            strokeLinecap="round"
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={BAND_HEX[band]}
            strokeWidth={stroke}
            strokeDasharray={`${filled} ${circumference}`}
            strokeLinecap="round"
            style={{ transition: "stroke-dasharray 600ms ease-out" }}
          />
        </svg>

        <div className="absolute inset-0 flex flex-col items-center justify-center">
          {/* Hero figure: at least 48px, body sans, proportional figures. */}
          <span
            className="font-sans text-5xl font-semibold leading-none tracking-tightest text-ink-50"
            style={{ fontVariantNumeric: "proportional-nums" }}
          >
            {Math.round(score)}
            <span className="text-xl text-ink-400">%</span>
          </span>
          <span className="mt-1.5 text-2xs text-ink-400">
            {label ?? BAND_LABEL[band]}
          </span>
        </div>
      </div>
    </figure>
  );
}

/* ----------------------------------------------------------- category bars */

export interface CategoryDatum {
  key: string;
  label: string;
  /** 0–1 sub-score. */
  subscore: number;
  /** Effective weight actually applied. */
  weight: number;
  /** Percentage points contributed to the final score. */
  points: number;
  description?: string;
}

/**
 * Horizontal bars comparing each scoring category's contribution. The job is
 * magnitude comparison, so this is a single-hue sequential encoding — length
 * carries the value and colour carries nothing, which keeps six rows calm.
 *
 * Values are direct-labelled at the bar tip (the reader's actual question is
 * "how many points did this add?"), and the full numbers stay in the table
 * below, which is the table view.
 */
export function CategoryBars({ data }: { data: CategoryDatum[] }) {
  const [hovered, setHovered] = useState<string | null>(null);
  const max = Math.max(...data.map((d) => d.points), 1);

  return (
    <div className="surface px-4 py-4">
      <ul className="space-y-3.5">
        {data.map((item) => {
          const pct = (item.points / max) * 100;
          const active = hovered === item.key;
          return (
            <li
              key={item.key}
              tabIndex={0}
              onPointerEnter={() => setHovered(item.key)}
              onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(item.key)}
              onBlur={() => setHovered(null)}
              className="group relative cursor-default rounded outline-none"
            >
              <div className="flex items-baseline justify-between gap-3">
                <span className="truncate text-xs text-ink-200">{item.label}</span>
                <span className="num shrink-0 text-xs font-medium text-ink-100">
                  {item.points.toFixed(2)}
                  <span className="ml-1 text-ink-500">pts</span>
                </span>
              </div>

              {/* Track is a lighter step of the bar's own hue. */}
              <div
                className="mt-1.5 h-2 w-full overflow-hidden rounded-sm"
                style={{ background: SEQUENTIAL_TRACK }}
              >
                <div
                  className="h-full transition-all duration-500"
                  style={{
                    width: `${Math.max(pct, item.points > 0 ? 1.5 : 0)}%`,
                    background: SEQUENTIAL,
                    borderTopRightRadius: BAR_RADIUS,
                    borderBottomRightRadius: BAR_RADIUS,
                    opacity: active ? 1 : 0.88,
                  }}
                />
              </div>

              {/* Tooltip enhances; every number here is also in the table. */}
              {active ? (
                <div
                  role="tooltip"
                  className="pointer-events-none absolute left-0 top-full z-20 mt-1 w-full max-w-sm rounded border border-ink-600 bg-ink-800 px-3 py-2 shadow-lg"
                >
                  <p className="num text-sm font-semibold text-ink-50">
                    {item.points.toFixed(2)} points
                  </p>
                  <p className="mt-0.5 text-2xs text-ink-300">
                    sub-score {item.subscore.toFixed(3)} × weight{" "}
                    {item.weight.toFixed(2)}
                  </p>
                  {item.description ? (
                    <p className="mt-1.5 text-2xs leading-relaxed text-ink-400">
                      {item.description}
                    </p>
                  ) : null}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------ distribution bar */

export interface DistributionDatum {
  band: Band;
  count: number;
}

/**
 * Part-to-whole across the four match bands. Horizontal stacked bar, with a
 * 2px surface-coloured gap separating touching segments (never a stroke) and a
 * legend always present, since there is more than one series.
 */
export function BandDistribution({
  data,
  total,
}: {
  data: DistributionDatum[];
  total: number;
}) {
  const [hovered, setHovered] = useState<Band | null>(null);
  const present = data.filter((d) => d.count > 0);

  if (!total || !present.length) {
    return (
      <p className="text-sm text-ink-400">
        No scored jobs yet, so there is no distribution to show.
      </p>
    );
  }

  return (
    <div className="surface px-4 py-4">
      <div className="flex items-baseline justify-between">
        <p className="label">Match distribution</p>
        <p className="num text-xs text-ink-400">{total} scored</p>
      </div>

      <div className="mt-3 flex h-7 w-full items-stretch overflow-hidden rounded-sm">
        {present.map((item, index) => {
          const pct = (item.count / total) * 100;
          const active = hovered === item.band;
          return (
            <div
              key={item.band}
              tabIndex={0}
              onPointerEnter={() => setHovered(item.band)}
              onPointerLeave={() => setHovered(null)}
              onFocus={() => setHovered(item.band)}
              onBlur={() => setHovered(null)}
              title={`${BAND_LABEL[item.band]}: ${item.count} of ${total}`}
              className="relative cursor-default outline-none transition-opacity"
              style={{
                width: `${pct}%`,
                background: BAND_HEX[item.band],
                opacity: hovered && !active ? 0.6 : 1,
                // The 2px separator is surface-coloured negative space.
                marginLeft: index === 0 ? 0 : SURFACE_GAP,
                borderRadius: 2,
              }}
            >
              {/* Only label a segment when the text comfortably fits. */}
              {pct > 14 ? (
                <span
                  className="num absolute inset-0 flex items-center justify-center text-2xs font-semibold"
                  style={{ color: item.band === "low" ? "#f5f7fa" : "#0a0b0e" }}
                >
                  {Math.round(pct)}%
                </span>
              ) : null}
            </div>
          );
        })}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
        {data.map((item) => (
          <li key={item.band} className="flex items-center gap-1.5 text-2xs">
            <span
              aria-hidden
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ background: BAND_HEX[item.band] }}
            />
            <span className="text-ink-300">{BAND_LABEL[item.band]}</span>
            <span className="num text-ink-500">{item.count}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ---------------------------------------------------------- demand bars */

export interface DemandDatum {
  label: string;
  value: number;
  /** Secondary count rendered after the value, e.g. mandatory-of-total. */
  detail?: string;
  hint?: string;
}

/**
 * Horizontal magnitude bars for skill demand. Single hue; the axis is implied
 * by a hairline baseline and the direct label at each tip.
 */
export function DemandBars({
  data,
  unit = "%",
  max,
}: {
  data: DemandDatum[];
  unit?: string;
  max?: number;
}) {
  const [hovered, setHovered] = useState<string | null>(null);
  const ceiling = max ?? Math.max(...data.map((d) => d.value), 1);

  return (
    <ul className="space-y-2.5">
      {data.map((item) => {
        const pct = (item.value / ceiling) * 100;
        const active = hovered === item.label;
        return (
          <li
            key={item.label}
            tabIndex={0}
            onPointerEnter={() => setHovered(item.label)}
            onPointerLeave={() => setHovered(null)}
            onFocus={() => setHovered(item.label)}
            onBlur={() => setHovered(null)}
            className="grid cursor-default grid-cols-[9rem_1fr_auto] items-center gap-3 outline-none sm:grid-cols-[11rem_1fr_auto]"
          >
            <span className="truncate text-xs text-ink-200" title={item.label}>
              {item.label}
            </span>
            <div
              className="h-2.5 w-full overflow-hidden rounded-sm"
              style={{ background: SEQUENTIAL_TRACK }}
            >
              <div
                className="h-full transition-all duration-500"
                style={{
                  width: `${Math.max(pct, 2)}%`,
                  background: SEQUENTIAL,
                  borderTopRightRadius: BAR_RADIUS,
                  borderBottomRightRadius: BAR_RADIUS,
                  opacity: active ? 1 : 0.88,
                }}
              />
            </div>
            <span className="num whitespace-nowrap text-xs text-ink-300">
              {item.value}
              {unit}
              {item.detail ? (
                <span className="ml-1.5 text-ink-500">{item.detail}</span>
              ) : null}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

/* -------------------------------------------------------- sparkline-ish */

/**
 * Compact linear meter, for use inside cards where a radial gauge is too big.
 * Same contract as ScoreMeter: fill is the band step, track a lighter step of
 * the same hue.
 */
export function MiniMeter({
  score,
  band,
  className,
}: {
  score: number;
  band?: Band;
  className?: string;
}) {
  const resolved = band ?? bandOf(score);
  return (
    <div
      className={cx("h-1.5 w-full overflow-hidden rounded-sm", className)}
      style={{ background: BAND_TRACK[resolved] }}
      role="meter"
      aria-valuenow={Math.round(score)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={`Match score ${Math.round(score)} percent`}
    >
      <div
        className="h-full transition-all duration-500"
        style={{
          width: `${Math.max(2, Math.min(100, score))}%`,
          background: BAND_HEX[resolved],
          borderTopRightRadius: BAR_RADIUS,
          borderBottomRightRadius: BAR_RADIUS,
        }}
      />
    </div>
  );
}

/* --------------------------------------------------------- company mark */

const MONOGRAM_TINTS = [
  "rgba(74,134,239,0.16)",
  "rgba(138,180,248,0.16)",
  "rgba(52,211,153,0.14)",
  "rgba(232,178,62,0.14)",
  "rgba(147,187,250,0.16)",
];

/**
 * Company monogram. Purely typographic identity — gives each card an anchor
 * without fetching third-party logos (which would leak the user's browsing to
 * every employer's CDN).
 */
export function CompanyMark({ name, size = 34 }: { name: string; size?: number }) {
  const id = useId();
  const initials = name
    .replace(/[^\p{L}\p{N} ]/gu, " ")
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");

  // Stable tint from the name, so a company looks the same everywhere.
  let hash = 0;
  for (let i = 0; i < name.length; i += 1) {
    hash = (hash * 31 + name.charCodeAt(i)) % 9973;
  }
  const tint = MONOGRAM_TINTS[hash % MONOGRAM_TINTS.length];

  return (
    <span
      key={id}
      aria-hidden
      className="flex shrink-0 items-center justify-center rounded border border-ink-700 font-semibold text-ink-100"
      style={{
        width: size,
        height: size,
        background: tint,
        fontSize: size * 0.38,
      }}
    >
      {initials || "—"}
    </span>
  );
}

export { GRID, AXIS_TEXT };
