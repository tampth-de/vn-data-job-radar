{#
  Text normalization used to match the same job across sources.
  Requires the `unaccent` extension (created in on-run-start, see dbt_project.yml).

  normalize_company("CÔNG TY TRÁCH NHIỆM HỮU HẠN AVEPOINT VIỆT NAM") -> 'avepoint'
    accents removed, legal-form boilerplate removed: without this, any two
    "Công ty TNHH ... Việt Nam" look 60% similar.
  normalize_title("[HN] Data Analyst - Power BI") -> 'data analyst power bi'
    accents and [location tags] removed, punctuation collapsed.
#}

{% macro normalize_company(col) -%}
    trim(regexp_replace(regexp_replace(regexp_replace(
        lower(public.unaccent(coalesce({{ col }}, ''))),
        '\m(tong cong ty|cong ty|co phan|tnhh|trach nhiem huu han|mot thanh vien|mtv|jsc|co|ltd|limited'
        '|corporation|corp|inc|group|tap doan|viet nam|vietnam|vn|chi nhanh)\M', ' ', 'g'),
        '[^a-z0-9 ]', ' ', 'g'),
        '\s+', ' ', 'g'))
{%- endmacro %}

{% macro normalize_title(col) -%}
    trim(regexp_replace(regexp_replace(
        lower(public.unaccent(coalesce({{ col }}, ''))),
        '\[[^]]*\]', ' ', 'g'),
        '[^a-z0-9]+', ' ', 'g'))
{%- endmacro %}
