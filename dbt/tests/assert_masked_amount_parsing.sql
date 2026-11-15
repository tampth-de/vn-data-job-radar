-- Singular test: the masked-salary macros must turn TopDev's masked strings into the
-- right ranges. Returns the failing cases (a passing test returns no rows).

with cases (input, expected_low, expected_high) as (
    values
        ('1*******', 10000000::numeric, 19999999::numeric),  -- 8 digits starting with 1
        ('6******',   6000000,           6999999),           -- 7 digits starting with 6
        ('3***',         3000,              3999),           -- USD amounts
        ('25******', 25000000,          25999999),           -- two visible digits
        ('15000000', 15000000,          15000000),           -- fully visible
        ('0',            null,              null),           -- "no lower/upper bound"
        ('*',            null,              null),           -- negotiable
        ('',             null,              null)
),

computed as (
    select
        input,
        expected_low,
        expected_high,
        {{ masked_amount_low('input') }}  as actual_low,
        {{ masked_amount_high('input') }} as actual_high
    from cases
)

select *
from computed
where actual_low is distinct from expected_low
   or actual_high is distinct from expected_high
