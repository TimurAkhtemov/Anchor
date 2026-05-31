# dbt Learning & Troubleshooting Summary

This document summarizes the dbt concepts, workflows, and debugging solutions covered during the development of the Anchor project. It serves as a reference guide for local dbt development and troubleshooting future issues.

---

## 1. Issue Triage & Troubleshooting Reference

### Issue A: The `NoneType` `resolve_source` Error in VS Code
* **Symptom**: Clicking "Generate Model" or other extension buttons raises:
  `AttributeError: 'NoneType' object has no attribute 'resolve_source'`
* **Root Cause**: The dbt Power User extension's internal startup sequence (`init_project()`) failed to compile or parse the dbt project graph. When compilation fails, the extension sets its internal dbt controller reference to `None`, causing all dependent UI features to crash.
* **Common Triggers**:
  1. **Missing staging files**: If a downstream model (like `dim_customers.sql`) uses `{{ ref('stg_jaffle_shop__customers') }}` but the staging file does not exist, the parser fails.
  2. **Duplicate package directories**: Stray or corrupted directories in `dbt_packages/` (e.g., `dbt_packages/dbt_utils 2`).
  3. **Duplicate source definitions**: Defining the same source and table combination in multiple `.yml` files.

### Issue B: Stray Package Folders with Restricted Permissions
* **Symptom**: Compilation fails with error:
  `No dbt_project.yml found at expected path .../dbt_packages/dbt_utils 2/dbt_project.yml`
* **Root Cause**: Unsuccessful package installs or folder movements can leave duplicate packages with restricted permissions (e.g., `drwx------`), preventing standard tools or Git from easily identifying or deleting them, while dbt's dependency parser still scans them.
* **Resolution**:
  1. Update permissions recursively: `chmod -R 777 "dbt_packages/dbt_utils 2"`
  2. Force delete the folder: `rm -rf "dbt_packages/dbt_utils 2"`
  3. Run `dbt clean && dbt deps` to rebuild a clean environment.

### Issue C: Duplicate Source Definition Warnings (`dbt1155`)
* **Symptom**: Warnings about `Duplicate definition for table '...' in source '...'`.
* **Root Cause**: Defining the same schema/table structure in two different YAML files (e.g., trying to test by adding `stripe` to `_src_jaffle_shop.yml` when it already exists in `_src_stripe.yml`).
* **Resolution**: Reorganize your YAML configurations so each source name lives in exactly one file (e.g., jaffle shop tables in `_src_jaffle_shop.yml` and stripe tables in `_src_stripe.yml`).

### Issue D: Source Not Found / JinjaError
* **Symptom**: `JinjaError (dbt1501): Failed to render SQL not a key type: Source not found for source name: stripe, table name: payments`
* **Root Cause**: The name specified in the `{{ source(...) }}` macro must **exactly match** the table name defined in your `_src_*.yml` source configuration.
  * In this project, the BigQuery table name is singular (`payment`), but your model was initially referencing the plural `payments`: `{{ source('stripe', 'payments') }}`.
* **Resolution**: Update the staging model SQL to use the exact singular name:
  ```sql
  select * from {{ source('stripe', 'payment') }}
  ```

---

## 2. Core dbt Concepts

### Defining vs. Referencing Sources
* **Defining (YAML)**: You must define a source, its database, schema, and tables **exactly once** in a `.yml` file in your `models/` directory. This is where you configure metadata, descriptions, testing, and data freshness thresholds.
* **Referencing (SQL)**: You can reference a defined source using the `{{ source('source_name', 'table_name') }}` macro **infinitely many times** across different SQL models in your project.

### BigQuery Database Hierarchy
In the public `dbt-tutorial` BigQuery project, the datasets and tables are structured as follows:
* **Database (GCP Project)**: `dbt-tutorial`
* **Datasets & Tables**:
  * `jaffle_shop`
    * `customers`
    * `orders`
  * `stripe`
    * `payment`
  * `data_prep`
    * `jaffle_shop_customers`
    * `jaffle_shop_orders`
    * `stripe_payments`

---

## 3. Scaffolding & Codegen Workflow

To visually generate source configurations and base models inside VS Code without using terminal commands:

### The Scratchpad Pattern (Repeatable Workflow)
1. **Configure `.gitignore`**: Add `codegen.sql` to your project's `.gitignore` file to keep the workspace clean.
2. **Create `codegen.sql`**: Keep a dedicated file named `codegen.sql` at the root of the project.
3. **Paste the Macro**: Put the `codegen` macro you need to run inside the file:
   ```sql
   {{ codegen.generate_source(schema_name='stripe', database_name='dbt-tutorial') }}
   ```
4. **Compile**: Click the **`< / >` (Compile SQL)** icon in the top-right corner of the editor (or press `Cmd + Enter` / `Ctrl + Enter`).
5. **Copy the Result**: Copy the generated YAML block from the Compiled SQL preview panel and paste it into your target `.yml` configuration file.

### Common Codegen Commands
* **Generate Source YAML**:
  ```sql
  {{ codegen.generate_source(schema_name='schema_name', database_name='database_name') }}
  ```
* **Generate Base Model SQL**:
  ```sql
  {{ codegen.generate_base_model(source_name='source_name', table_name='table_name') }}
  ```
* **Generate Model YAML (for documentation templates)**:
  ```sql
  {{ codegen.generate_model_yaml(model_names=['your_model_name']) }}
  ```

---

## 4. Ongoing Practice Checklist

* [x] Add `codegen.sql` and `temp_codegen.sql` to your `.gitignore`.
* [x] Configure source freshness in `_src_stripe.yml` by adding `loaded_at_field` and the `freshness` block.
* [x] Execute `dbt source freshness` in the terminal to verify the source freshness checks.
