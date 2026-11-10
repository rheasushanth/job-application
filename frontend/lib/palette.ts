/**
 * Chart palette — single source of truth for every data mark.
 *
 * The match-quality scale (excellent → low) is an **ordinal ramp**, so it is a
 * single hue stepped by lightness rather than four separate hues. That is not a
 * stylistic choice: the original green/lime/amber/grey set failed validation
 * badly — "Good" and "Moderate" sat ΔE 2.3 apart under deuteranopia, i.e.
 * indistinguishable for red-green colourblind readers, and "Excellent" vs
 * "Good" was only ΔE 11.6 even with full colour vision. Four hues in the
 * green-amber family cannot be made safe; lightness can.
 *
 * Validated with the dataviz validator against surface #0f1115:
 *   node scripts/validate_palette.js \
 *     "#cfe0fd,#8ab4f8,#4a86ef,#2b60bd" --mode dark --surface "#0f1115" --ordinal
 *   → PASS lightness monotone · PASS adjacent ΔL ≥ 0.06
 *     PASS light-end contrast 3.16:1 · PASS single hue (spread 1°)
 *
 * Re-run the validator if any value here changes.
 */

import type { Band } from "./types";

/** The chart surface these steps were validated against. */
export const SURFACE = "#0f1115";

/** Ordinal match-quality ramp, light → dark. */
export const BAND_HEX: Record<Band, string> = {
  excellent: "#cfe0fd",
  good: "#8ab4f8",
  moderate: "#4a86ef",
  low: "#2b60bd",
};

/**
 * Meter tracks are a lighter step of the *same* ramp, never neutral grey, so
 * the state reads across the whole bar rather than only the filled part.
 */
export const BAND_TRACK: Record<Band, string> = {
  excellent: "rgba(207, 224, 253, 0.16)",
  good: "rgba(138, 180, 248, 0.16)",
  moderate: "rgba(74, 134, 239, 0.18)",
  low: "rgba(43, 96, 189, 0.22)",
};

/** Single hue for magnitude comparisons (category breakdown, demand bars). */
export const SEQUENTIAL = "#4a86ef";
export const SEQUENTIAL_TRACK = "rgba(74, 134, 239, 0.14)";

/**
 * Status palette — reserved for eligibility, which is genuinely categorical
 * state rather than magnitude. Only three values, and each is always rendered
 * with its text label, so identity is never carried by colour alone.
 */
export const STATUS_HEX = {
  ok: "#34d399",
  warn: "#e8b23e",
  danger: "#f2777a",
} as const;

/** Recessive chrome: gridlines and axes, one step off the surface. */
export const GRID = "#272d36";
export const AXIS_TEXT = "#6b7482";
