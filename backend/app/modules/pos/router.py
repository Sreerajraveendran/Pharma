from fastapi import APIRouter, Depends, Query
from typing import List
from app.modules.auth.dependencies import get_current_user
from app.modules.pos import schemas, service

router = APIRouter()

@router.post("/checkout", response_model=schemas.CheckoutResponse)
async def checkout(checkout_req: schemas.CheckoutRequest, user: dict = Depends(get_current_user)):
    return await service.execute_checkout(checkout_req.model_dump(), user)

@router.get("/audit-logs", response_model=List[schemas.AuditLogRead])
async def read_audit_logs(limit: int = Query(50, ge=1, le=200)):
    return await service.get_recent_audit_logs(limit)
