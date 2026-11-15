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

## Rules we follow

- Read each site's Terms of Service before scheduling daily runs.
- 2–3 seconds between requests, descriptive User-Agent.
- Never log in to scrape, never store personal contact data.
