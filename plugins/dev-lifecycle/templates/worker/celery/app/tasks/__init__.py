"""Task modules. `celery_app.py` autodiscovers every module in this
package via `app.autodiscover_tasks(["app.tasks"])` — a new task module
just needs to live here and decorate its callables with `@shared_task`
(see `base.py` for this block's idempotent/retry/logging task base)."""
