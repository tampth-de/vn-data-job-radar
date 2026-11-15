{#
  Generic test: fails if the combination of the given columns is not unique.
  Usage in YAML:
    data_tests:
      - unique_combination:
          arguments:
            columns: [snapshot_date, job_id]
#}
{% test unique_combination(model, columns) %}
    select {{ columns | join(', ') }}, count(*) as n
    from {{ model }}
    group by {{ columns | join(', ') }}
    having count(*) > 1
{% endtest %}
