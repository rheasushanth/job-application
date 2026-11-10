import { CompanyMark, MiniMeter } from "@/components/charts";
import { BAND_HEX, SEQUENTIAL, SEQUENTIAL_TRACK } from "@/lib/palette";

/**
 * A static illustration of the match breakdown for the landing page.
 *
 * Built from the real design tokens and chart components so it cannot drift
 * from what the product actually renders. The numbers are clearly framed as an
 * example — this is the only place in the app with figures not computed from a
 * user's own data, and it is labelled as such.
 */
const EXAMPLE_ROWS: { label: string; points: number }[] = [
  { label: "Technical skills match", points: 24.6 },
  { label: "Semantic similarity", points: 15.1 },
  { label: "Project relevance", points: 11.2 },
  { label: "Experience relevance", points: 10.4 },
  { label: "Education match", points: 9.0 },
  { label: "Experience-level fit", points: 7.0 },
];

export function SampleMatchCard() {
  const max = Math.max(...EXAMPLE_ROWS.map((row) => row.points));
  const total = EXAMPLE_ROWS.reduce((sum, row) => sum + row.points, 0);

  return (
    <div className="surface-raised overflow-hidden">
      <div className="flex items-start gap-3 border-b border-ink-700 px-4 py-3.5">
        <CompanyMark name="Northwind Labs" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink-50">
            Backend Developer Intern
          </p>
          <p className="mt-0.5 truncate text-xs text-ink-400">
            Northwind Labs · Bengaluru · Remote
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="figure text-2xl font-semibold leading-none text-ink-50">
            {Math.round(total)}
            <span className="text-sm text-ink-400">%</span>
          </p>
          <p className="mt-1 text-2xs text-ink-400">Good match</p>
        </div>
      </div>

      <div className="px-4 py-3.5">
        <MiniMeter score={total} band="good" />

        <ul className="mt-4 space-y-2">
          {EXAMPLE_ROWS.map((row) => (
            <li key={row.label} className="grid grid-cols-[1fr_auto] gap-3">
              <div className="min-w-0">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-2xs text-ink-300">
                    {row.label}
                  </span>
                  <span className="num shrink-0 text-2xs text-ink-400">
                    {row.points.toFixed(1)}
                  </span>
                </div>
                <div
                  className="mt-1 h-1.5 overflow-hidden rounded-sm"
                  style={{ background: SEQUENTIAL_TRACK }}
                >
                  <div
                    className="h-full"
                    style={{
                      width: `${(row.points / max) * 100}%`,
                      background: SEQUENTIAL,
                      borderTopRightRadius: 4,
                      borderBottomRightRadius: 4,
                    }}
                  />
                </div>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-4 flex items-center gap-2 border-t border-ink-700 pt-3">
          <span
            aria-hidden
            className="h-2 w-2 shrink-0 rounded-sm"
            style={{ background: BAND_HEX.good }}
          />
          <p className="text-2xs text-ink-500">
            Illustrative example, not real data — every score in the app is
            computed from your own resume.
          </p>
        </div>
      </div>
    </div>
  );
}
