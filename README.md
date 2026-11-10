# JobMatch

Upload a resume once, then discover, rank and track matching jobs from
multiple job platforms — with a match percentage you can audit line by line.

Built as a working application rather than a UI prototype: the job listings are
real, fetched live from job-platform APIs, and the match score is produced by a
deterministic algorithm that is unit-tested and shown to the user as arithmetic.

---

## What it does

| | |
| --- | --- |
| **Resume processing** | PDF/DOCX → text → structured profile (contact, education, skills, projects, internships, certifications, achievements). You review and correct every field before it is used. |
| **Candidate classification** | Student / fresher / intern / entry-level / experienced, with the signals behind the label shown. |
| **Multi-source discovery** | Modular adapters per job platform, queried concurrently, with normalisation and three-tier deduplication. |
| **Hybrid matching** | Six weighted categories + semantic embeddings + rule-based eligibility gating. Configurable weights. |
| **Alternative roles** | Role suggestions derived from skill coverage, not from the job titles on your resume. |
| **Skill gap** | Missing skills ranked by real demand across the jobs discovered for you. |
| **Resume feedback** | Structural suggestions and missing keywords taken from your matched jobs. |
| **Saved jobs & tracker** | Collections, notes, and a six-stage application pipeline with a full audit trail. |
| **Job alerts** | Notifications when newly discovered jobs clear your match threshold. |

---

## Quick start

Requires Python 3.11+ and Node 20+. Nothing else — no Postgres, no Redis, no
API keys needed for a working install.

```bash
python -m venv .venv
```

```bash
.venv/Scripts/python -m pip install -r backend/requirements.txt
```

```bash
cd backend && ../.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

In a second terminal:

```bash
cd frontend && npm install && npm run dev
```

Open <http://localhost:3000>, create an account, upload a resume.

Optional — semantic matching is noticeably sharper with real embeddings:

```bash
.venv/Scripts/python -m pip install sentence-transformers
```

API docs are at <http://127.0.0.1:8000/docs>.

### Configuration

Everything is optional. Copy `.env.example` to `.env` to change defaults.

- **No `.env`** → SQLite, rule-based resume parsing, hashed-TF-IDF embeddings,
  and the four keyless job feeds. Fully functional.
- **`DATABASE_URL`** → Postgres instead of SQLite.
- **`ANTHROPIC_API_KEY`** → LLM resume structuring and written match
  explanations. *Match percentages do not change* — the LLM never produces the
  score.
- **`REDIS_URL`** → dispatch background work through Celery instead of the
  in-process thread pool.
- **`ADZUNA_*` / `JSEARCH_API_KEY`** → enable the credentialed job sources.

---

## Job sources, honestly

The brief asked for LinkedIn, Indeed, Naukri, Glassdoor, Wellfound,
Internshala and Google Jobs. Here is what is actually possible, and what this
build does:

| Source | Status | How |
| --- | --- | --- |
| Remotive, Arbeitnow, Jobicy, RemoteOK | **Live, no setup** | Free public JSON APIs |
| Adzuna | Needs a key | Official free developer API |
| Google Jobs, LinkedIn, Indeed | Needs a key | Via **JSearch** (RapidAPI), a licensed aggregator that indexes those boards. One key enables all three; each is attributed to its originating portal. |
| Naukri, Glassdoor, Wellfound, Internshala | **Unavailable, and the UI says so** | No lawful public job-search API for this use case. Scraping them would breach their terms, so it is not done. |

The unavailable sources are deliberately listed in the UI with the precise
reason and the environment variable that would enable them. They are never
populated with placeholder listings. **No job in this application is
fabricated** — every one links back to its original posting.

---

## How the match score works

The score is a weighted mean of six sub-scores, gated by eligibility:

```
score = (Σ weightᵢ × subscoreᵢ ÷ Σ weightᵢ) × eligibility_multiplier × 100
```

| Category | Default weight |
| --- | --- |
| Technical skills match | 0.30 |
| Semantic profile similarity | 0.20 |
| Project relevance | 0.15 |
| Internship / work experience relevance | 0.15 |
| Education match | 0.10 |
| Experience-level fit | 0.10 |

Bands: **≥85** excellent · **70–84** good · **50–69** moderate · **<50** low.

### What the AI does and does not do

- **The LLM** reads resumes into structured fields, and writes the prose
  explanation of a result. It is never asked for a number.
- **The embedding model** (MiniLM, or a hashed TF-IDF fallback) measures
  semantic similarity between the profile and each job description.
- **The algorithm** produces the percentage. It is a pure function in
  [`scorer.py`](backend/app/services/matching/scorer.py) with no database,
  network or model access, pinned by 31 tests.

### Eligibility cannot be bought with optional skills

This was an explicit requirement. Unmet **mandatory** requirements apply a
multiplier *after* the weighted sum and force the eligibility status away from
"eligible" — so acing every preferred skill can never compensate for a
requirement you do not meet. A candidate missing a required skill always ranks
below an otherwise-identical candidate who has it.

Three judgement calls worth knowing about, each visible in the UI:

- **A posting listing 20+ "required" skills** is almost always a mis-parsed
  page, so it warns instead of hard-failing the candidate.
- **A posting yielding fewer than 4 parseable skills** has its skill-coverage
  *weight* reduced, because "1 of 1 skills matched" is 100% coverage carrying
  no evidence. The other categories absorb the slack.
- **"Or equivalent experience"** next to a degree requirement removes the
  degree gate.

Every job's detail page shows the per-category sub-scores, their weights, their
contribution in percentage points, the gate multipliers and why each applied.
The contributions reconcile to the subtotal — there is a test for that.

---

## Architecture

```
frontend/   Next.js 15 (App Router), TypeScript, Tailwind
backend/    FastAPI, SQLAlchemy 2.0, Postgres (SQLite fallback)
docs/       ARCHITECTURE.md · SCHEMA.md · API.md
```

Design documents, written before the implementation:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system design, the hybrid
  split, source architecture, pipelines, security, scaling
- [docs/SCHEMA.md](docs/SCHEMA.md) — every table and column
- [docs/API.md](docs/API.md) — all 51 endpoints

### Adding a job source

Write one module and decorate it. Nothing else changes — not the matching
engine, not the API, not the frontend, which renders whatever
`GET /api/v1/sources` reports.

```python
@register_source
class MyBoardSource(JobSource):
    key = "myboard"
    display_name = "My Board"
    requires_credentials = False

    async def fetch(self, query: SourceQuery) -> list[RawJob]:
        ...
```

### Deduplication

Three tiers, cheapest first: `(source, source_job_id)`, then a content hash of
normalised title + company + location, then fuzzy title/company matching within
a company bucket. Cross-portal duplicates are linked to a canonical row, and
the UI shows "also on LinkedIn, Indeed".

---

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest tests/ -q
```

**153 tests**, covering the parts where being wrong is expensive:

| File | What it pins |
| --- | --- |
| `test_scorer.py` | Score bounds, determinism, that contributions reconcile, mandatory gating, weight behaviour, skill ontology precision |
| `test_resume_pipeline.py` | Extraction against real generated PDF and DOCX files, seniority rules, graceful degradation |
| `test_normalize_ingest.py` | Salary/location/experience/education parsing, dedup tiers, enrichment |
| `test_api.py` | The full journey over HTTP, auth, ownership isolation, filtering, tracker transitions |

Several are explicit regression tests for bugs found against live feed data —
`"intern"` substring-matching `"international"`, a salary range truncating
`40000` to `400`, the same posting arriving twice in one batch.

An end-to-end script additionally exercises **133 assertions** against the
running API and the live job feeds, covering registration through to token
rotation.

---

## Security

- bcrypt password hashing with SHA-256 pre-hashing for long passphrases
- JWT access tokens (30 min) + refresh rotation with **reuse detection** — a
  replayed refresh token revokes the whole family
- Every user-owned row is ownership-checked; a mismatch returns 404, not 403,
  so IDs cannot be probed for existence
- Uploads validated by **magic bytes**, not extension; 10 MB cap enforced while
  streaming; stored under a UUID filename outside any served directory
- Rate limiting on auth and upload endpoints; CORS pinned to the frontend origin

---

## Known limitations

Stated plainly rather than papered over:

- **Four job sources work out of the box.** The rest need credentials, and four
  named platforms have no lawful API at all. The UI reports this per source.
- **The keyless feeds skew remote and senior.** They carry few internships, so
  a student's results are dominated by low-band matches. That is the available
  supply, not a scoring defect — the engine scores a genuinely well-matched
  pair above 70% (there is a test).
- **Remotive's `search` parameter is ignored** by its API, verified against the
  live endpoint, so relevance filtering for that source happens client-side.
- **No OCR.** A scanned or photographed resume yields no text; the app detects
  this and says so rather than silently producing an empty profile.
- **Skill matching uses a closed vocabulary.** A skill outside the ontology is
  surfaced to the user as unrecognised instead of being silently dropped.
- **The in-process rate limiter is per-instance.** Behind multiple replicas it
  needs the Redis-backed equivalent.
