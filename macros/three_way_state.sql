{#
  Classifies a signed 3-month delta into a three-way directional state using
  a symmetric threshold (a dead-band around zero so small/noisy moves read as
  the neutral middle state). Used by macro_regime to turn each indicator's
  delta into a rising / falling / steady-style label.

  `delta_expr`  — SQL expression for the change (same units as `threshold`)
  `threshold`   — dead-band half-width
  `label_up`    — state when delta >  +threshold
  `label_down`  — state when delta <  -threshold
  `label_mid`   — state within the dead-band
#}
{% macro three_way_state(delta_expr, threshold, label_up, label_down, label_mid) %}
case
    when {{ delta_expr }} >  {{ threshold }} then '{{ label_up }}'
    when {{ delta_expr }} < -{{ threshold }} then '{{ label_down }}'
    else '{{ label_mid }}'
end
{% endmacro %}
