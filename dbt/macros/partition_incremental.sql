{#-
  En run incrémental : ne lit que les lignes dont la date de partition d’ingestion
  (d_event_received) est strictement après le maximum déjà chargé dans la table.

  À utiliser dans un WHERE après les autres conditions :
    {{ partition_incremental_after_max('d_event_received') }}
-#}

{% macro partition_incremental_after_max(partition_col) -%}
    {%- if is_incremental() -%}
        AND {{ partition_col }} > (
            SELECT COALESCE(MAX({{ partition_col }}), DATE '"2025-11-30')
            FROM {{ this }}
        )
    {%- endif -%}
{%- endmacro %}
