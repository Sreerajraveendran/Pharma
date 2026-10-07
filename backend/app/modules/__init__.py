"""Feature modules. Each one holds everything for its feature:

  router.py      HTTP endpoints (FastAPI APIRouter)
  schemas.py     request/response models (Pydantic)
  service.py     business rules
  repository.py  database queries; the only code that touches the tables

Repository conventions: functions take and return plain dicts with string ids; batch
lookups (`*_by_ids`) return {id: row} and cost one query regardless of size; list
functions take skip/limit (limit=0 means no limit) and never silently truncate.
"""
