<!-- fragment: block:components/backend/pagination -->

## Setup
Copy `schema.py` into `app/core/db/pagination/schema.py`. On the
SQLAlchemy side, also copy `query.py` into the same directory (it imports
`schema.py` as a flat sibling module). A Django project (Stage 4) copies
`schema.py` alone and reimplements the `{items, total, page, size, pages}`
shape against its own DRF paginator.

## Maintenance
`query.py` is SQLAlchemy-specific; `schema.py` is the framework-neutral
contract both Stage 3 (FastAPI) and Stage 4 (Django) conform to.
