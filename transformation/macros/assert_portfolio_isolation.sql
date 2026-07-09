{#
  PRIVACY INTERLOCK. The public contract (prod -> anchor_marts -> committed
  snapshot -> public deploy) and CI must never be built from real holdings.
  This is the structural guarantee from docs/make_it_real_design.md: a leak
  is not a mistake you can make — it's a build the system refuses to run.
  Runs from on-run-start (dbt_project.yml).
#}
{% macro assert_portfolio_isolation() %}
    {% if var('holdings_source', 'demo') == 'real' and target.name in ('prod', 'ci') %}
        {{ exceptions.raise_compiler_error(
            "PRIVACY INTERLOCK: holdings_source=real cannot build into the public '"
            ~ target.name ~ "' target. Use --target prod-private (make build-private)."
        ) }}
    {% endif %}
{% endmacro %}
