\# FlowWatch Local Development



\## Prerequisites



The local FlowWatch development environment requires:



\- Python 3.12

\- Docker Desktop

\- Docker Compose

\- Git



\## Python Environment



Create and activate the project virtual environment:



```bat

python -m venv .venv

.venv\\Scripts\\activate

```



Install project dependencies:



```bat

python -m pip install -r requirements.txt

```



\## Environment Configuration



Copy the example environment configuration:



```bat

copy .env.example .env

```



Replace all placeholder passwords in `.env` with local development secrets.



The real `.env` file must never be committed to Git.



\## Core Services



Start PostgreSQL and MongoDB:



```bat

docker compose up -d

```



Check service status:



```bat

docker compose ps

```



Both `flowwatch-postgres` and `flowwatch-mongo` should report a healthy status.



\## PostgreSQL



PostgreSQL is exposed only on the local interface using the port configured by `POSTGRES\_PORT`.



Check connectivity:



```bat

docker compose exec postgres psql -U flowwatch\_owner -d flowwatch -c "SELECT current\_database(), current\_user;"

```



Apply all migrations:



```bat

alembic upgrade head

```



\## MongoDB



MongoDB is exposed only on the local interface using the port configured by `MONGO\_PORT`.



Check connectivity from inside the container:



```bat

docker compose exec mongo mongosh

```



MongoDB is introduced on Day 6 as infrastructure only.



Raw collection definitions, indexes, lineage envelopes, and persistence semantics are introduced later in the project.



\## Tests



Run:



```bat

pytest -q

```



\## Linting



Run:



```bat

ruff check src tests

```



\## Structured Logging



FlowWatch uses JSON logs with common correlation metadata.



Relevant fields include:



\- `run\_id`

\- `request\_id`

\- `component`

\- `duration\_ms`

\- `status`



The common implementation lives in:



`src/observability/logging.py`



These identifiers allow events produced by later ingestion, API, orchestration, and ML components to be correlated across one logical execution.



\## Stopping Services



Stop containers while preserving database volumes:



```bat

docker compose down

```



Removing volumes destroys local PostgreSQL and MongoDB data:



```bat

docker compose down -v

```



Use the volume-removal command only when intentionally performing a clean-environment test.

