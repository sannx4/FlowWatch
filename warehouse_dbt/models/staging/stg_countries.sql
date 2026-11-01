select country_id, country_code, country_name, region_id
from {{ source('operational', 'countries') }}
