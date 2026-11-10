# Database Schema

PostgreSQL is the target. SQLAlchemy 2.0 declarative models; `JSONB` on Postgres
degrades to `JSON` on SQLite (dev), and array-ish fields are stored as JSON lists
so both backends work from one model definition.

## users
| column | type | notes |
| --- | --- | --- |
| id | uuid pk | |
| email | citext unique not null | login identity |
| password_hash | text not null | bcrypt |
| full_name | text | |
| created_at / updated_at | timestamptz | |
| is_active | bool default true | |
| alert_min_match | int default 70 | job-alert threshold |
| alert_enabled | bool default true | |

## refresh_tokens
`id`, `user_id → users`, `token_hash` (sha256, unique), `expires_at`,
`revoked_at`, `replaced_by_id`. Rotation + reuse detection.

## resumes
Uploaded file record.
`id`, `user_id`, `original_filename`, `stored_path`, `content_type`,
`size_bytes`, `file_sha256`, `uploaded_at`,
`status` ∈ `uploaded | extracting | parsed | awaiting_review | confirmed | failed`,
`extraction_engine` (`pdfplumber|pymupdf|python-docx`), `raw_text`,
`error_message`.

## parsed_resumes
Machine output before the user confirms it. One per resume (latest wins).
`id`, `resume_id` unique, `structuring_mode` (`llm|heuristic|merged`),
`payload` jsonb — the structured document:

```jsonc
{
  "contact":    { "name", "email", "phone", "location", "links": [] },
  "education":  [ { "degree","field","institution","start","end","score","level" } ],
  "skills":     { "technical": [], "soft": [], "tools": [] },
  "languages":  [ "Python", ... ],          // programming languages
  "frameworks": [ "React", ... ],
  "projects":   [ { "name","description","tech": [],"highlights": [] } ],
  "experience": [ { "role","company","kind":"internship|job","start","end",
                    "months","description","tech": [] } ],
  "certifications": [ { "name","issuer","year" } ],
  "achievements": [ "..." ]
}
```

`field_confidence` jsonb — per-field 0–1, drives the "please check this" hints in
the review UI. `warnings` jsonb — list of missing/ambiguous sections.

## candidate_profiles
The confirmed, user-owned profile the matcher reads. One active per user.
`id`, `user_id`, `resume_id`, `revision` int, `is_active` bool,
`full_name`, `email`, `phone`, `location`, `links` json,
`education` json, `skills` json (normalised), `raw_skills` json (as written),
`programming_languages` json, `frameworks` json, `tools` json,
`projects` json, `experience` json, `certifications` json, `achievements` json,
`total_experience_months` int, `internship_months` int,
`highest_degree_level` int (0 none → 5 doctorate), `field_of_study`,
`graduation_year` int,
`seniority` ∈ `student | fresher | intern | entry_level | experienced`,
`seniority_signals` json (why that label),
`embedding` json (float vector), `embedding_model`, `profile_text` text,
`created_at`, `updated_at`.

Index: `(user_id, is_active)`.

## job_sources
Registry mirror, so status is queryable and the UI is data-driven.
`key` pk, `display_name`, `kind` (`public_api|licensed_api|gated`),
`requires_credentials` bool, `credential_env_vars` json,
`is_enabled` bool, `last_run_at`, `last_status`, `last_error`,
`jobs_last_run` int, `notes` text.

## source_run_log
Per-fetch audit: `id`, `source_key`, `started_at`, `finished_at`,
`status` (`ok|partial|error|skipped`), `fetched`, `inserted`, `duplicates`,
`error`, `query` json.

## jobs
Global, shared across users.
| column | type | notes |
| --- | --- | --- |
| id | uuid pk | |
| source | text not null | fk → job_sources.key |
| source_job_id | text | unique with `source` |
| title / company | text not null | |
| company_normalised | text | dedupe key |
| description | text | plain text, HTML stripped |
| description_html | text | original |
| required_skills | json | mandatory |
| preferred_skills | json | nice-to-have |
| all_skills | json | union, normalised — filter target |
| education_requirement | json | `{min_level, fields[], raw}` |
| experience_min_years / experience_max_years | numeric | |
| experience_level | text | `internship\|entry\|mid\|senior\|lead` |
| location_raw / city / state / country | text | |
| is_remote | bool | |
| work_mode | text | `remote\|hybrid\|onsite\|unspecified` |
| job_type | text | `internship\|full_time\|part_time\|contract\|freelance` |
| salary_min / salary_max | numeric | normalised to annual |
| salary_currency | text | |
| salary_period | text | original period |
| stipend_min / stipend_max | numeric | for internships |
| posted_at | timestamptz | |
| deadline_at | timestamptz | nullable |
| apply_url | text not null | |
| content_hash | text | dedupe tier 2 |
| duplicate_of_id | uuid → jobs.id | tier 3 |
| also_seen_on | json | `["linkedin","indeed"]` |
| embedding | json | |
| embedding_model | text | |
| first_seen_at / last_seen_at | timestamptz | |
| is_active | bool | |

Indices: `(source, source_job_id)` unique · `content_hash` ·
`posted_at desc` · `job_type` · `work_mode` · `experience_level` ·
`country, state, city` · `salary_max` · GIN on `all_skills` (Postgres).

## job_matches
Per user × job score. The explainable record.
`id`, `user_id`, `job_id`, `profile_id`, `profile_revision`,
`job_content_hash`, `weight_profile_hash`,
`score` numeric(5,2), `band` (`excellent|good|moderate|low`),
`eligibility_status` (`eligible|partially_eligible|not_eligible`),
`eligibility_multiplier` numeric,
`category_scores` jsonb — `{category: {raw, weight, contribution}}`,
`matched_skills` json, `missing_skills` json, `missing_mandatory_skills` json,
`extra_skills` json,
`relevant_projects` json, `relevant_experience` json,
`reasons` json, `blockers` json, `recommendations` json,
`explanation` text, `explanation_source` (`llm|template`),
`computed_at`.

Unique `(user_id, job_id)`. Indices on `(user_id, score desc)`,
`(user_id, band)`.

## match_weight_profiles
`id`, `user_id` (null = system default), `name`, `weights` jsonb,
`is_active`, `hash` text. Changing weights invalidates matches by hash.

## saved_jobs
`id`, `user_id`, `job_id`, `collection` text default 'Default',
`notes` text, `created_at`. Unique `(user_id, job_id)`.

## applications
`id`, `user_id`, `job_id`, `status` ∈
`interested | applied | assessment | interview | rejected | offer`,
`applied_at`, `notes`, `created_at`, `updated_at`.
Unique `(user_id, job_id)`.

## application_events
Status-change audit: `id`, `application_id`, `from_status`, `to_status`,
`note`, `created_at`.

## notifications
`id`, `user_id`, `kind` (`new_matches|discovery_complete|discovery_failed`),
`title`, `body`, `payload` json, `is_read`, `created_at`.

## discovery_runs
`id`, `user_id`, `status` (`queued|running|completed|failed|partial`),
`started_at`, `finished_at`, `sources_attempted` json,
`sources_succeeded` json, `sources_failed` json,
`jobs_fetched`, `jobs_new`, `jobs_duplicate`, `matches_computed`,
`error`, `progress` int.

## skill_ontology_overrides
Lets an operator extend the shipped ontology without a deploy:
`id`, `canonical`, `aliases` json, `category`, `related` json, `weight`.
