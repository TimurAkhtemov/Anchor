{#
  Classifies a signed 3-month delta into a three-way directional state using
  a symmetric threshold (a dead-band around zero so small/noisy moves read as
  the neutral middle state). Used by macro_regime to turn each indicator's
  delta into a rising / falling / steady-style label.

  `delta_expr`  — SQL expression for the change (same units as `threshold`)
  `threshold`   — dead-band half-width
  `label_up`    — state when delta >  +threshold (>= when inclusive)
  `label_down`  — state when delta <  -threshold (<= when inclusive)
  `label_mid`   — state within the dead-band
  `inclusive`   — default false: a move of exactly the threshold stays in the
                  dead-band. true: a move of exactly the threshold counts as a
                  change ("at least X pp"), matching the regime guide.
#}
{% macro three_way_state(delta_expr, threshold, label_up, label_down, label_mid, inclusive=false) %}
{%- set gt = '>=' if inclusive else '>' -%}
{%- set lt = '<=' if inclusive else '<' -%}
case
    when {{ delta_expr }} {{ gt }}  {{ threshold }} then '{{ label_up }}'
    when {{ delta_expr }} {{ lt }} -{{ threshold }} then '{{ label_down }}'
    else '{{ label_mid }}'
end
{% endmacro %}
