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

## Rules we follow

- Read each site's Terms of Service before scheduling daily runs. (TODO)
- 2–3 seconds between requests, descriptive User-Agent.
- Never log in to scrape, never store personal contact data.
