{#
  Classifies a holding's relative position vs a benchmark into
  ahead / behind / in_line, using a symmetric in-line band measured
  in percentage points (pp). The band width is configurable via the
  `inline_band_pp` dbt var (default 2).

  `relative_expr` is a SQL expression for (holding% - benchmark%),
  already in percentage-point units.
#}
{% macro ahead_behind(relative_expr) %}
case
    when {{ relative_expr }} >  {{ var('inline_band_pp', 2) }} then 'ahead'
    when {{ relative_expr }} < -{{ var('inline_band_pp', 2) }} then 'behind'
    else 'in_line'
end
{% endmacro %}
