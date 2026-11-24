# Source survey

Surveyed on 2026-11-15. Search keyword: "data engineer".

| Source | robots.txt | Access method | Notes | Decision |
|---|---|---|---|---|
| TopDev | Allows job pages | Public JSON API `api.topdev.vn/td/v2/jobs` | Structured fields: `skills_arr`, `salary`, `job_levels_str`, `experiences_str`, `published`. Requires `fields[job]=...` param, otherwise returns almost empty objects. | **Primary source** |
| ITviec | Allows all | Server-rendered HTML, ~20 jobs/page | Salary hidden behind login. We do not log in, so salary will be missing for this source. | Secondary source |
| TopCV | Allows job pages | Server-rendered HTML | Cloudflare challenge script present; many non-IT jobs. | Later |
| VietnamWorks | No robots.txt (404) | Next.js, data loaded client-side | Needs internal API investigation. | Optional |
| CareerViet | Allows job pages | HTML | No Data jobs found with the tested URL. | Skipped |

## Sample TopDev record (trimmed)

```json
{
  "id": 2144836,
  "title": "Data Engineer (Big Data / Lakehouse)",
  "salary": {"is_negotiable": "1", "min": "*", "max": "*", "currency": "VND", "unit": "MONTH"},
  "skills_arr": ["SQL", "Python", "PySpark"],
  "job_levels_str": "Nhân viên",
  "experiences_str": "2 năm, 4 năm",
  "published": {"date": "06-11-2026"}
}
```

Observed data quality issues to handle later:
- Negotiable salary encoded as `min: "*"`, `max: "*"`.
- Dates in `DD-MM-YYYY` format.
- Experience as free text (`"2 năm, 4 năm"`).
- Keyword search on the API looks strict (only a handful of results for "data engineer"); need to test broader keywords or category filters.

## ITviec details (2026-11-15)

- Category pages: `https://itviec.com/it-jobs/<slug>`, 20 jobs per page, `?page=N`.
  The `<h1>` holds the total (e.g. "25 data engineer jobs in Vietnam").
- Categories used: data-engineer (25), data-analyst (17), data-science (13), ai (131),
  machine-learning (41), big-data (2), business-intelligence (8) → 237 rows, 181 unique jobs.
- Each job card has: slug, title, company, "Posted N days ago", work mode, location, skill tags.
  Salary shows "Sign in to view salary" for anonymous visitors.
- Observed issues for staging: multi-city locations in both orders
  ("Ho Chi Minh - Ha Noi" / "Ha Noi - Ho Chi Minh"); relative posting dates;
  the `ai` category includes general software jobs (Java, Microservices), so a
  relevance filter is needed.

## Terms of Service review (2026-11-15)

Not legal advice, just how we read the terms and what we decided.

| Source | What the terms say | Technical signal | Decision |
|---|---|---|---|
| TopDev (`/term-of-services`) | Content may not be modified, copied for distribution, published, turned into derivative works or exploited commercially. Digital copies for viewing and reasonable copies for internal use are allowed, keeping the source (topdev.vn + URL). | Open JSON API, no blocking. | **Scheduled daily.** Raw data stays in a private repo; only aggregated statistics are published, credited to topdev.vn; no commercial use. |
| ITviec (`/blog/terms-and-conditions/`) | §2.2: other than reasonable personal use, content "may not be retrieved, displayed, modified, copied, printed, sold, downloaded … without our prior written consent". | Returns 403 to cloud (GitHub Actions) IPs. | **Not scheduled.** Parser kept for reference; would require written permission from ITviec. |

## Second survey: more Vietnamese job boards (2026-11-24)

Goal: more volume than TopDev's ~20 Data/AI jobs a day, without breaking any site's rules.
Each board went through robots.txt → Terms of Service → technical access.

| Source | robots.txt | Terms of Service | Technical | Decision |
|---|---|---|---|---|
| TopCV | Job pages allowed | No copying, adapting, publishing, distributing or exploiting "TopCV Content"; no personal-use exception | Cloudflare challenge | ❌ No |
| VietnamWorks | 404 | Same content clause as TopDev, **and** reserves the right to refuse anyone who "exploits information provided by the service not for their own recruitment" | Data loaded client-side | ❌ No (intent is clear) |
| CareerViet | Job pages allowed | **Explicitly forbids** "crawlers, robots … to index or find any CareerViet page" | – | ❌ No |
| 123job | Allowed | Forbids "unauthorised collection, exploitation or use of data from the system" | – | ❌ No |
| Glints | Allowed | – | **403** to our client (Cloudflare) | ❌ No (blocked, not evaded) |
| JobsGo | Allowed | – | **403** (Cloudflare) | ❌ No (blocked, not evaded) |
| Vieclam24h | Search URLs with `?q` **disallowed** | No clause against copying or automated access found | Jobs loaded client-side via an internal API | ⏸ Possible later (category pages only) |
| **CareerLink** | Job and search pages allowed (`_rsc` disallowed) | Claims rights over interface, code, editorial content and brand; **job ads belong to the employers**. Forbids overloading the system and collecting users' *personal* data | Server-rendered; job pages carry **schema.org `JobPosting` JSON-LD** | ✅ **Scheduled** |

### CareerLink details

- Search: `/vieclam/list?keyword=<kw>&page=N`, 50 jobs per page; the page says "N việc làm".
  Search is full-text, so broad words explode ("data" → 2,231, "power bi" → 92 mostly
  unrelated): only precise phrases are used.
- Job pages embed a `JobPosting` JSON-LD: title, company, `datePosted`, `validThrough`,
  **exact salary** (`minValue`/`maxValue`, or "Thương lượng"/"Cạnh tranh"),
  `monthsOfExperience`, location, CareerLink's own `occupationalCategory`
  ("Kỹ sư dữ liệu", "AI developer", "Phân tích dữ liệu"…), description. No skill tags:
  skills are extracted from the description in dbt.
- During the first test run, after ~40 job pages in a row the site started returning an
  empty shell page. We treat that as a "slow down" signal: job pages are now fetched
  **once per job**, only when the search-result title looks Data/AI related, 5 s apart,
  at most 40 per run, and the run stops after 3 empty pages in a row (circuit breaker).
  Daily cost: ~10 search pages + a few new job pages.

## Rules we follow

- Read each site's robots.txt and Terms of Service before scheduling daily runs.
- Respect blocks and throttling signals: never rotate IPs, fake browsers or log in.
- 2–5 seconds between requests, honest User-Agent, fetch each job page only once.
- Never store personal contact data; raw data stays private; publish aggregates only,
  credited to the sources; no commercial use.
