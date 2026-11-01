select project_pk, project_id, project_name, country_id
from {{ source('operational', 'projects') }}
