# API Reference

Base path `/api/v1`. All routes except auth and `/health` need
`Authorization: Bearer <access_token>`. Errors are
`{"detail": {"code": "...", "message": "...", "fields": {...}}}`.

## Auth
| Method | Path | Body / Query | Returns |
| --- | --- | --- | --- |
| POST | `/auth/register` | `email, password, full_name` | `access_token, refresh_token, user` |
| POST | `/auth/login` | `email, password` | same |
| POST | `/auth/refresh` | `refresh_token` | rotated pair |
| POST | `/auth/logout` | `refresh_token` | 204 |
| GET | `/auth/me` | — | `user` |
| PATCH | `/auth/me` | `full_name?, alert_min_match?, alert_enabled?` | `user` |

## Resumes
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/resumes` | multipart `file`; PDF/DOCX ≤ 10 MB. Extracts + structures synchronously for small files, else queues. Returns `resume` with `status`. |
| GET | `/resumes` | list user's resumes |
| GET | `/resumes/{id}` | detail incl. `status`, `warnings` |
| GET | `/resumes/{id}/parsed` | structured payload + `field_confidence` for the review screen |
| PUT | `/resumes/{id}/parsed` | user's edited payload (validated) |
| POST | `/resumes/{id}/confirm` | promotes parsed payload → `candidate_profile` (new revision), computes embedding, returns `profile` |
| GET | `/resumes/{id}/file` | streams original to owner only |
| DELETE | `/resumes/{id}` | removes row + file |

## Profile
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/profile` | active profile; 404 if none confirmed yet |
| PATCH | `/profile` | edit confirmed profile → bumps `revision`, invalidates matches |
| GET | `/profile/seniority` | label + the signals behind it |

## Sources
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/sources` | every registered source with `kind`, `available`, `reason`, `credential_env_vars`, `last_run_at`, `jobs_last_run`. Drives the honest "requires integration" UI. |
| PATCH | `/sources/{key}` | `{is_enabled}` |

## Discovery
| Method | Path | Notes |
| --- | --- | --- |
| POST | `/discovery/run` | `{sources?: [], queries?: [], location?}` → `discovery_run` (queued). Uses profile-derived role queries when `queries` omitted. |
| GET | `/discovery/runs` | history |
| GET | `/discovery/runs/{id}` | progress, per-source outcome |
| POST | `/discovery/rescore` | recompute matches for active profile without re-fetching |

## Jobs & matches
`GET /jobs` is the main search endpoint — all filtering, sorting and pagination
happen in SQL.

Query parameters:

```
q                 free text over title/company/description
city, state, country
work_mode         remote|hybrid|onsite        (repeatable)
job_type          internship|full_time|part_time|contract|freelance (repeatable)
experience_level  internship|entry|mid|senior|lead (repeatable)
min_match, max_match     0–100
company           (repeatable)
source            (repeatable)
skills            (repeatable, AND semantics)
salary_min, salary_max
posted_within_days
eligibility       eligible|partially_eligible|not_eligible (repeatable)
band              excellent|good|moderate|low (repeatable)
saved_only, tracked_only   bool
sort              match_desc | match_asc | posted_desc | posted_asc
                  | salary_desc | salary_asc | company_asc
page, page_size   (≤100)
```

Response: `{items: [JobWithMatch], total, page, page_size, facets}` where
`facets` carries available companies/sources/skill counts for the filter panel.

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/jobs/{id}` | job + full match analysis for the caller |
| GET | `/jobs/{id}/analysis` | score breakdown, arithmetic, reasons, blockers, recommendations, per-category contributions |
| GET | `/matches/summary` | dashboard counters: total / excellent / good / moderate / low / saved / tracked |

## Saved jobs
`GET /saved` · `POST /saved` `{job_id, collection?, notes?}` ·
`PATCH /saved/{id}` · `DELETE /saved/{job_id}` · `GET /saved/collections`

## Application tracker
`GET /applications` (filter `status`) · `POST /applications`
`{job_id, status?, notes?}` · `PATCH /applications/{id}`
`{status?, notes?}` (writes an `application_event`) ·
`DELETE /applications/{id}` · `GET /applications/{id}/events` ·
`GET /applications/board` (grouped by status, for the kanban view)

## Insights
| Method | Path | Notes |
| --- | --- | --- |
| GET | `/insights/skill-gap` | missing skills ranked by demand frequency across the user's matched jobs, with `learn_first` ordering and score-lift estimate |
| GET | `/insights/alternative-roles` | suggested roles with fit %, why, missing skills, sample matching jobs |
| GET | `/insights/resume-feedback` | resume improvements, missing keywords, per-section suggestions |

## Alerts & notifications
`GET /notifications` · `POST /notifications/{id}/read` ·
`POST /notifications/read-all` · `GET /alerts/config` ·
`PUT /alerts/config` `{alert_enabled, alert_min_match}`

## Settings
`GET /settings/weights` · `PUT /settings/weights` `{weights}` (validated to sum
> 0, normalised internally; triggers rescore) · `POST /settings/weights/reset`

## Health
`GET /health` → `{status, db, embedding_model, llm_provider, sources_live}`
