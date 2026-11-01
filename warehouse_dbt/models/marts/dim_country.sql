select c.country_id, c.country_code, c.country_name,
       c.region_id, r.region_name
from {{ ref('stg_countries') }} c
join {{ ref('stg_regions') }} r on r.region_id = c.region_id
