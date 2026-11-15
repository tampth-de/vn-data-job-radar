{#
  TopDev masks salaries for anonymous visitors: "1*******" means an 8-digit number
  starting with 1, i.e. somewhere in [10,000,000 ; 19,999,999].

  masked_amount_low("1*******")  -> 10000000
  masked_amount_high("1*******") -> 19999999
  Fully visible numbers ("15000000") return themselves; "0", "*", "" return null.
#}

{% macro masked_amount_low(col) -%}
    {%- set v = "(" ~ col ~ ")" -%}
    case
        when {{ v }} ~ '^[0-9]+\*+$'
            then (substring({{ v }} from '^([0-9]+)'))::numeric
                 * power(10::numeric, length({{ v }}) - length(substring({{ v }} from '^([0-9]+)')))
        when {{ v }} ~ '^[0-9]+$' and ({{ v }})::numeric > 0
            then ({{ v }})::numeric
    end
{%- endmacro %}

{% macro masked_amount_high(col) -%}
    {%- set v = "(" ~ col ~ ")" -%}
    case
        when {{ v }} ~ '^[0-9]+\*+$'
            then ((substring({{ v }} from '^([0-9]+)'))::numeric + 1)
                 * power(10::numeric, length({{ v }}) - length(substring({{ v }} from '^([0-9]+)'))) - 1
        when {{ v }} ~ '^[0-9]+$' and ({{ v }})::numeric > 0
            then ({{ v }})::numeric
    end
{%- endmacro %}
