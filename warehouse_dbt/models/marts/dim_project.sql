select p.project_pk, p.project_id, p.project_name, p.country_id
from {{ ref('stg_projects') }} p
