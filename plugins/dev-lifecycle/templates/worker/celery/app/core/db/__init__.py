"""Async DB session plumbing shared with the backend block, plus this
block's own sync-task wrapper (task_session.py) — Celery's default
execution model is synchronous, SQLAlchemy's async engine is not."""
