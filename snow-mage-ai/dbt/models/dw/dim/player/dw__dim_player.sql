{{ config(
    alias = 'player',
    materialized = 'table',
    transient = false,
    tags = ["dw", "dim"]
) }}

SELECT
    {{ dbt_utils.star(ref('stg__dim_player')) }}
FROM {{ ref('stg__dim_player') }}