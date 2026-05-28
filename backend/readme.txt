cd axis-ai

# 1. Create virtualenv with your Python 3.11.3
python3.11 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy env and add your keys
cp .env.example .env
# edit .env — minimum required: just leave the defaults for now

# 4. Start Postgres + Redis + Qdrant
docker compose up -d postgres redis qdrant

# 5. Run migrations
alembic upgrade head

# 6. Start the API
uvicorn app.main:app --reload --port 8000

# In another terminal — start Celery worker
celery -A app.tasks.celery_app worker --loglevel=info

# check the application at http://127.0.0.1:8000/docs

# BEFORE we TEST we should start the celery for log loglevel
cd /Users/EDZLEARN/Documents/Claude/Projects/moodle-axis-ai/axis-ai
source .venv/bin/activate
celery -A app.tasks.celery_app worker --loglevel=info -Q default,priority

# check all status - curl http://127.0.0.1:8000/health/ready


# you can run docker
cd ~/Documents/Claude/Projects/moodle-axis-ai/axis-ai
docker compose up -d

# 
docker compose build api
docker compose up -d
docker compose exec api python -m alembic upgrade head

## to get axis api key 
docker compose exec api python scripts/seed_tenant.py --reset

[created] Tenant: Dev School (d3e2a4ba-2a31-455f-9b67-e11e6502aaa0)

============================================================
  DEV TENANT READY
============================================================
  Tenant name : Dev School
  Tenant ID   : d3e2a4ba-2a31-455f-9b67-e11e6502aaa0
  Moodle URL  : http://localhost:8080
  Key name    : dev-key
  Key ID      : 3d888494-98ad-49db-8d37-5533a288bd20

  RAW API KEY (save this — shown only once!):
  axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME

  Add to your .env:
  AXIS_DEV_API_KEY=axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME

  Use in requests:
  Authorization: Bearer axisai_72_05wyTslb46owBbdTcKdQ_1A8_DZMhHzeKzUBPHME
============================================================


# to check docker logs

docker compose logs worker --tail=80

# for any table changes deployment

alembic upgrade head