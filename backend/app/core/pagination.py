from typing import Tuple

from fastapi import Query


def page_params(
    skip: int = Query(0, ge=0),
    limit: int = Query(0, ge=0, le=1000, description="Page size; 0 returns everything. When set, X-Total-Count has the total."),
) -> Tuple[int, int]:
    return skip, limit
