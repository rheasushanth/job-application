# JobMatch — System Architecture

## 1. Overview

JobMatch is a resume-to-job matching platform. A user uploads a resume once; the
system structures it into a candidate profile, discovers real job postings from
multiple external sources, and scores every posting against the profile with a
**hybrid** engine (deterministic weighted algorithm + semantic embeddings +
optional LLM reasoning).

```
                        ┌──────────────────────────────┐
                        │  Next.js 15 (App Router, TS) │
                        │  Tailwind, server components │
                        └──────────────┬───────────────┘
                                       │ JSON / JWT bearer
                        ┌──────────────▼───────────────┐
                        │        FastAPI (Python)      │
                        │  routers/  services/  core/  │
                        └───┬──────────┬───────────┬───┘
                            │          │           │
         ┌──────────────────▼──┐  ┌────▼─────┐  ┌──▼──────────────────┐
         │ Resume pipeline     │  │ Matching │  │ Job discovery       │
         │ pdfplumber / PyMuPDF│  │ engine   │  │ source registry     │
         │ python-docx         │  │ (hybrid) │  │ (pluggable adapters)│
         │ + LLM structuring   │  └────┬─────┘  └──┬──────────────────┘
         └──────────────────┬──┘       │           │
                            │          │           │ httpx
                 ┌──────────▼──────────▼──┐   ┌────▼──────────────────────┐
                 │ PostgreSQL (SQLAlchemy)│   │ Remotive, Arbeitnow,      │
                 │ + SQLite dev fallback  │   │ Jobicy, RemoteOK (live)   │
                 └────────────┬───────────┘   │ Adzuna, JSearch (keyed)   │
                              │               │ LinkedIn/Naukri/… (gated) │
                 ┌────────────▼───────────┐   └───────────────────────────┘
                 │ Task queue             │
                 │ thread worker (default)│
                 │ Celery + Redis (prod)  │
                 └────────────────────────┘
```

## 2. Why hybrid, and where each technique is used

The brief forbids both "LLM guesses a percentage" and "pure keyword match". The
split used here:

| Concern | Technique | Why |
| --- | --- | --- |
| Pull structure out of free-text resume | LLM (JSON schema prompt), heuristic extractor fallback | Resumes have no fixed layout; this is a language task |
| Normalise/expand skills ("JS" → JavaScript, React implies frontend) | Curated skill ontology + fuzzy match (RapidFuzz) | Must be deterministic and auditable |
| "Is a Django project relevant to a Flask job?" | Embedding cosine similarity | Needs meaning, not tokens |
| Final match percentage | Weighted scoring algorithm in Python | Must be explainable, testable, reproducible |
| Hard eligibility (degree, years of experience, mandatory skills) | Rule-based validator | Business rules, not a judgement call |
| "Why does this match / what should I learn" | LLM, with fallback to templated explanation built from score components | Prose generation |
| Alternative role suggestions | Role catalogue + skill-coverage scoring, LLM for rationale | Needs to be grounded in actual skill overlap |

**The LLM never produces the number.** It produces structure and prose. The
number comes from `services/matching/scorer.py`, which is pure and unit-tested.

Embeddings come from `services/matching/embeddings.py`: `sentence-transformers`
(all-MiniLM-L6-v2) when installed, otherwise a hashed TF-IDF vectoriser that
needs no model download and no network, so semantic similarity degrades
gracefully instead of disappearing. `/health` reports which backend is live so
the UI never implies model-grade semantics when running on the fallback.

**Similarity calibration is measured, not assumed.** Raw cosines occupy very
different ranges per backend, so each has its own rescaling band:

| Backend | strong match | adjacent role | unrelated | band used |
| --- | --- | --- | --- | --- |
| MiniLM-L6-v2 | 0.46–0.76 | 0.39–0.44 | 0.11–0.30 | (0.25, 0.78) |
| hashed TF-IDF | 0.24–0.31 | ~0.15 | −0.04–0.01 | (0.03, 0.34) |

Applying one band to both backends was a real bug during development: the
MiniLM band clamped almost every fallback match to 0.0, silently deleting the
whole 20% semantic component from the score. Re-measure if the model changes.

## 3. Match score model

Final score is a weighted sum of six category sub-scores, each normalised 0–1,
then gated by eligibility.

```
raw      = Σ (weight_i × subscore_i) / Σ weight_i
final    = raw × eligibility_multiplier × 100
```

Default weights (configurable per user, table `match_weight_profiles`):

| Category | Weight | Computation |
| --- | --- | --- |
| `technical_skills` | 0.30 | Coverage of job's required skills by candidate skills, mandatory weighted 2× preferred; fuzzy + ontology-aware |
| `semantic_similarity` | 0.20 | Cosine(profile embedding, job embedding) rescaled from the [0.15, 0.85] useful band |
| `project_relevance` | 0.15 | Best-of per-project cosine vs job description, plus skill overlap bonus |
| `experience_relevance` | 0.15 | Same as projects over internships/jobs, weighted by duration |
| `education_match` | 0.10 | Degree level vs requirement, field-of-study adjacency |
| `experience_level_fit` | 0.10 | Candidate years vs required band; penalises over- and under-shoot asymmetrically |

**Eligibility multiplier** — this is what stops optional skills from papering
over a hard miss:

- Unmet **mandatory** skill: multiplier × 0.55 for the first, × 0.75 for each
  subsequent one (floor 0.25).
- Degree requirement not met: × 0.6.
- Candidate years below the hard minimum: scaled by `years / required`, floored
  at 0.5.
- Any hard failure forces `eligibility_status` to `not_eligible` or
  `partially_eligible`; it can never read `eligible`.

Every job's stored breakdown includes each sub-score, its weight, its
contribution in percentage points, the multiplier and the reasons it was
applied — so the UI can show the arithmetic rather than asserting a number.

**Evidence-weighted skill coverage.** A posting's skill coverage is only as
trustworthy as the number of skills parsed from it. "Covers 1 of 1 skills" is
100% coverage carrying almost no evidence, and unchecked it floated
thinly-described senior postings to the top of a junior candidate's results.
Below `MIN_TRUSTED_JOB_SKILLS` (4), the `technical_skills` *weight* is scaled by
`parsed / 4`; because the score normalises by the weight total, the other
categories absorb the slack automatically. The adjustment and its reason are
reported in the breakdown rather than applied silently.

**Ontology precision.** Skills are extracted from job prose by scanning a
curated vocabulary, which makes bare common words dangerous: `go` matched the
verb, `r` and `c` matched stray letters, and `operations`/`sales`/`communication`
matched boilerplate. Those tokens produced a backend posting that "required"
Operations and Human Resources, and skill-gap advice telling a CS student to
learn Sales. `PROSE_AMBIGUOUS_TERMS` excludes them from *text scanning* only —
they still match when a candidate lists them explicitly, and unambiguous
aliases (`golang`, `r language`, `ansi c`) still scan. Language names that
essentially always mean the technology in a software posting (Rust, Swift,
Scala, Spring) are deliberately **not** excluded.

Bands: ≥85 Excellent · 70–84 Good · 50–69 Moderate · <50 Low.

## 4. Job source architecture

A source is a class implementing `JobSource`:

```python
class JobSource(Protocol):
    key: str                  # "remotive"
    display_name: str         # "Remotive"
    requires_credentials: bool
    credential_env_vars: list[str]
    def availability(self) -> SourceAvailability: ...
    async def fetch(self, query: SourceQuery) -> list[RawJob]: ...
```

Adapters live in `services/sources/` and self-register via `@register_source`.
Adding a portal means adding one file — no change to the matching engine, the
API, or the frontend. The frontend reads `/api/v1/sources` and renders whatever
it finds, including per-source status.

Each adapter normalises its payload into `RawJob`, then the ingestion service
enriches it (skill extraction, requirement parsing, salary parsing, work-mode
inference), deduplicates it, and persists it.

Status is surfaced honestly in the UI:

| Source | Status | Mechanism |
| --- | --- | --- |
| Remotive, Arbeitnow, Jobicy, RemoteOK | **live** | Public JSON APIs, no key |
| Adzuna | needs key | Free API; `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` |
| Google Jobs, LinkedIn, Indeed, Glassdoor, Naukri, Wellfound, Internshala | **requires integration** | No lawful public API. Adapters are implemented against JSearch/RapidAPI (`JSEARCH_API_KEY`), which is a licensed aggregator covering Google Jobs, LinkedIn and Indeed. Without a key the adapter reports `unavailable` with the reason and the env var needed. Nothing is scraped and no placeholder jobs are invented. |

### Deduplication

Three-tier, cheapest first:

1. `source_job_id` + `source` unique constraint (same posting re-fetched).
2. `content_hash` = sha1 of `normalise(title) | normalise(company) | normalise(location)`.
3. Near-duplicate across portals: candidates sharing a company token bucket are
   compared with token-set ratio on title (≥ 92) and company (≥ 90); the loser
   is linked to the winner via `duplicate_of_id` and the winner accumulates
   `also_seen_on`, so the UI can say "also on LinkedIn".

## 5. Pipelines

### Resume → profile

```
upload ─► store (uuid name, outside web root, size/MIME/magic-byte checked)
       ─► text extraction  pdfplumber → PyMuPDF fallback → python-docx
       ─► section segmentation (heading regex)
       ─► LLM structuring (JSON schema, temp 0) ──┐
          heuristic extractor ────────────────────┴─► merge, confidence per field
       ─► skill normalisation against ontology
       ─► seniority classification (student/fresher/intern/entry/experienced)
       ─► ParsedResume row, status = awaiting_review
       ─► user edits & confirms ─► CandidateProfile (+ profile embedding)
```

Seniority is decided by rules over total months of experience, graduation date
vs today, and internship-vs-full-time ratio — listed in `seniority.py` with the
triggering signal recorded so the UI can explain the label.

### Profile → ranked jobs

```
confirm profile ─► enqueue discovery
   ─► fetch every (source × query) pair concurrently under a semaphore
      (settings.source_concurrency), per-pair timeout, failures isolated and
      recorded in source_run_log
   ─► normalise ─► enrich ─► dedupe ─► upsert jobs
   ─► embed new jobs (batched, cached by content hash)
   ─► score every job × profile ─► JobMatch rows with full breakdown
   ─► derive skill-gap aggregate + alternative-role set
   ─► alerts: new matches ≥ user threshold ─► notifications
```

Scoring is incremental: a `JobMatch` is recomputed only when the job's
`content_hash`, the profile's `revision`, or the weight profile changes.

Fetching concurrently matters more than it looks. Six role queries across four
sources is 24 HTTP calls; sequentially, with a 30 s per-call timeout, a slow
portal pushes a run past 10 minutes. Running them under a semaphore brought a
measured full run (693 listings fetched, 263 new, 263 scored) from a 300 s
timeout to **63 seconds end to end**. Ingestion stays single-threaded
afterwards because it shares one DB session.

## 6. Security

- Argon2-style bcrypt password hashing, JWT access (30 min) + refresh (14 day)
  tokens, refresh rotation with reuse detection.
- Every resume/profile/match/saved/application row is scoped by `user_id`;
  reads go through `require_owned(...)` so an ID guess returns 404, not 403.
- Uploads: extension + MIME + magic bytes checked, 10 MB cap, stored under a
  UUID filename in a non-served directory, streamed back only to the owner.
- Rate limits on auth and upload endpoints; CORS pinned to the frontend origin.
- Secrets only from env; `.env.example` documents every variable.

## 7. Scalability

- Stateless API — horizontally scalable behind a load balancer.
- Postgres indices on every filter/sort column, plus GIN on skill arrays.
- Job rows are global and shared across users; only `JobMatch` is per-user, so
  discovery cost amortises as users grow.
- Embedding cache keyed by content hash avoids recomputation.
- Discovery and scoring run off-request in the task queue; the thread-pool
  worker is swapped for Celery + Redis by setting `REDIS_URL`, with no code
  change at call sites (`tasks.enqueue(...)`).

## 8. Repository layout

```
backend/
  app/
    main.py              FastAPI app, middleware, router mounting
    core/                config, security, db session, deps, errors
    models/              SQLAlchemy ORM
    schemas/             Pydantic request/response
    routers/             auth, resumes, profiles, jobs, matches, saved,
                         applications, alerts, insights, sources, settings
    services/
      resume/            extract, segment, llm_structure, heuristics, seniority
      sources/           base, registry, remotive, arbeitnow, jobicy, remoteok,
                         adzuna, jsearch_family, gated
      matching/          scorer, eligibility, skills, embeddings, explain
      insights/          skill_gap, alt_roles, resume_feedback
      ingest.py          normalise → enrich → dedupe → persist
      llm.py             provider abstraction + offline fallback
      tasks.py           queue abstraction
    data/                skill ontology, role catalogue
  tests/                 scorer, eligibility, dedupe, parsing, api
frontend/
  app/                   landing, auth, upload, profile, dashboard, jobs,
                         job/[id], saved, tracker, settings
  components/            ui primitives + feature components
  lib/                   api client, types, formatting
docs/                    ARCHITECTURE.md, SCHEMA.md, API.md
```
