# auditsmart-engine

Python 3.11 · FastAPI · Pydantic v2 · SQLAlchemy 2 + Alembic · Decimal for all money. AI is never used for calculations.

```bash
uv venv --python 3.11 .venv && uv pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env            # fill AUTH_* values; never commit .env
.venv/bin/alembic upgrade head  # empty DATABASE_URL = local SQLite file
.venv/bin/uvicorn app.main:app --reload   # http://127.0.0.1:8000/docs
.venv/bin/pytest --cov          # coverage gate 90%
.venv/bin/ruff check . && .venv/bin/mypy
```

Empty `DATABASE_URL` uses SQLite; empty `REDIS_URL` uses the in-process job runner (Workbook Stage 3 caution).
