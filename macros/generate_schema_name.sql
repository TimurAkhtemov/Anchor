-- Environment-aware schema routing (the dbt-fundamentals "custom schemas" pattern).
--
-- dev  (target.name != 'prod'): IGNORE custom schemas -> everything lands in the
--      developer's single sandbox dataset (dbt_timurakhtemov). Keeps local
--      iteration in one place; no anchor_* datasets cluttering the sandbox.
-- prod (target.name == 'prod'): use the model's custom +schema AS-IS (no
--      dbt_user_ prefix), so models route to anchor_staging / anchor_intermediate /
--      anchor_marts / anchor_seeds. Models without a custom schema fall to the
--      prod target's default dataset (`anchor`).
--
-- This is what lets the serve layer + scheduled CI build read a stable, named
-- contract (anchor_marts) instead of a personal sandbox.

{% macro generate_schema_name(custom_schema_name, node) -%}

    {%- set default_schema = target.schema -%}

    {%- if target.name == 'prod' and custom_schema_name is not none -%}

        {{ custom_schema_name | trim }}

    {%- else -%}

        {{ default_schema }}

    {%- endif -%}

{%- endmacro %}
