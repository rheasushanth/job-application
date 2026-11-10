import Link from "next/link";

import { SampleMatchCard } from "@/components/sample-match-card";

const STEPS = [
  {
    index: "01",
    title: "Upload your resume",
    body: "PDF or DOCX. Text is extracted, then structured into skills, education, projects and experience. You review and correct everything before it is used.",
  },
  {
    index: "02",
    title: "Discover across platforms",
    body: "A modular engine queries every connected job source in parallel, normalises the results and removes duplicates that appear on more than one portal.",
  },
  {
    index: "03",
    title: "See why each job matches",
    body: "Six weighted categories produce the percentage. Every job shows its own arithmetic, the skills you are missing, and whether you actually meet the hard requirements.",
  },
];

const CATEGORIES = [
  ["Technical skills match", "30%"],
  ["Semantic profile similarity", "20%"],
  ["Project relevance", "15%"],
  ["Internship / work experience", "15%"],
  ["Education match", "10%"],
  ["Experience-level fit", "10%"],
];

export default function LandingPage() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-ink-700">
        <div className="mx-auto flex h-14 max-w-shell items-center justify-between px-5">
          <span className="text-sm font-semibold tracking-tightest text-ink-50">
            JobMatch
          </span>
          <div className="flex items-center gap-2">
            <Link href="/login" className="btn-ghost btn-sm">
              Sign in
            </Link>
            <Link href="/register" className="btn-primary btn-sm">
              Create account
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="glow grid-texture border-b border-ink-700">
          <div className="mx-auto max-w-shell px-5 py-20 text-center sm:py-28">
            <p className="label text-accent-400">Resume-matched job discovery</p>
            <h1 className="mx-auto mt-5 max-w-3xl text-balance text-4xl font-semibold leading-[1.05] tracking-tightest text-ink-50 sm:text-[3.4rem]">
              Upload a resume once. Find every job you are{" "}
              <span className="text-accent-300">actually</span> a fit for.
            </h1>
            <p className="mx-auto mt-6 max-w-xl text-balance text-base leading-relaxed text-ink-300">
              JobMatch reads your resume, searches multiple job platforms, and
              ranks what it finds with an explainable score — so you can see
              exactly why a role fits, and what is missing if it does not.
            </p>
            <div className="mt-9 flex flex-wrap items-center justify-center gap-3">
              <Link href="/register" className="btn-primary">
                Get started
              </Link>
              <Link href="/login" className="btn-secondary">
                I already have an account
              </Link>
            </div>
            <p className="mt-6 text-2xs text-ink-500">
              No fabricated listings. Every job links back to its original
              posting.
            </p>

            {/* An illustrative breakdown built from the app's own chart
                components and tokens, so it cannot drift from what the
                product renders. The card labels itself as an example — these
                are the only figures in the app not computed from real data. */}
            <div className="mx-auto mt-14 max-w-md text-left">
              <SampleMatchCard />
            </div>
          </div>
        </section>

        {/* How it works */}
        <section className="border-b border-ink-700">
          <div className="mx-auto max-w-shell px-5 py-16">
            <div className="grid gap-px border border-ink-700 bg-ink-700 sm:grid-cols-3">
              {STEPS.map((step) => (
                <div key={step.index} className="bg-ink-900 px-6 py-7">
                  <span className="num text-sm font-semibold text-accent-400">
                    {step.index}
                  </span>
                  <h3 className="mt-3 text-sm font-semibold text-ink-50">
                    {step.title}
                  </h3>
                  <p className="mt-2 text-sm leading-relaxed text-ink-400">
                    {step.body}
                  </p>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Scoring transparency */}
        <section className="border-b border-ink-700">
          <div className="mx-auto grid max-w-shell gap-12 px-5 py-16 lg:grid-cols-2">
            <div>
              <h2 className="text-2xl font-semibold tracking-tightest text-ink-50">
                The percentage is arithmetic, not an opinion
              </h2>
              <div className="mt-5 space-y-4 text-sm leading-relaxed text-ink-300">
                <p>
                  A language model reads your resume and each job description,
                  and an embedding model measures how semantically close they
                  are. But the score itself comes from a deterministic weighted
                  formula you can inspect and reproduce.
                </p>
                <p>
                  Mandatory requirements are separated from preferred ones.
                  Strong optional matches can never paper over a requirement you
                  do not meet — those apply a visible penalty and change your
                  eligibility status, not just the number.
                </p>
              </div>
              <div className="mt-6 rounded border border-accent-line bg-accent-soft px-4 py-3">
                <code className="num block text-xs leading-relaxed text-accent-200">
                  score = (Σ weightᵢ × subscoreᵢ ÷ Σ weightᵢ)
                  <br />
                  &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;× eligibility_multiplier × 100
                </code>
              </div>
            </div>

            <div>
              <p className="label">Scoring categories</p>
              <dl className="mt-4 divide-y divide-ink-700 border-y border-ink-700">
                {CATEGORIES.map(([label, weight]) => (
                  <div
                    key={label}
                    className="flex items-center justify-between py-3"
                  >
                    <dt className="text-sm text-ink-200">{label}</dt>
                    <dd className="num rounded-sm border border-ink-700 bg-ink-850 px-2 py-0.5 text-xs text-ink-200">
                      {weight}
                    </dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 text-xs leading-relaxed text-ink-500">
                Weights are configurable per account. Change them and every job
                is rescored immediately.
              </p>
            </div>
          </div>
        </section>

        {/* Honest sourcing */}
        <section>
          <div className="mx-auto max-w-prose px-5 py-16">
            <h2 className="text-lg font-semibold tracking-tightest text-ink-50">
              About job sources
            </h2>
            <div className="mt-4 space-y-4 text-sm leading-relaxed text-ink-300">
              <p>
                Listings come from job platforms that publish an API. Remotive,
                Arbeitnow, Jobicy and RemoteOK work with no setup. Adzuna, and
                Google&nbsp;Jobs, LinkedIn and Indeed via a licensed aggregator,
                activate once you supply the relevant API key.
              </p>
              <p>
                Some platforms — Naukri, Glassdoor, Wellfound and Internshala —
                publish no usable public API, and scraping them would breach
                their terms. They are listed in the app as unavailable, with the
                reason stated, rather than being quietly dropped or filled with
                placeholder jobs.
              </p>
            </div>
            <div className="mt-8">
              <Link href="/register" className="btn-primary">
                Create your account
              </Link>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-ink-700 py-6">
        <div className="mx-auto max-w-shell px-5 text-2xs text-ink-500">
          Match categories are recommendations, not guaranteed eligibility
          decisions.
        </div>
      </footer>
    </div>
  );
}
