import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from open_webui.models.usage import Usages, UsageModel, UsageSummaryByUser
from open_webui.utils.auth import get_admin_user
from open_webui.env import SRC_LOG_LEVELS


log = logging.getLogger(__name__)
log.setLevel(SRC_LOG_LEVELS["MODELS"])

router = APIRouter()


class UsageLogsResponse(BaseModel):
    logs: list[UsageModel]
    total: int


@router.get("/admin/usage/logs", response_model=UsageLogsResponse)
async def get_usage_logs(
    request: Request,
    user=Depends(get_admin_user),
    user_id: Optional[str] = Query(None),
    user_email: Optional[str] = Query(None),
    provider: Optional[str] = Query(None),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
    skip: Optional[int] = Query(None, ge=0),
    limit: Optional[int] = Query(50, ge=1, le=500),
):
    try:
        return Usages.get_logs(
            user_id=user_id,
            user_email=user_email,
            provider=provider,
            start_ts=start_ts,
            end_ts=end_ts,
            skip=skip,
            limit=limit,
        )
    except Exception as e:
        log.error(f"Error fetching usage logs: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")


@router.get("/admin/usage/summary", response_model=list[UsageSummaryByUser])
async def get_usage_summary(
    request: Request,
    user=Depends(get_admin_user),
    start_ts: Optional[int] = Query(None),
    end_ts: Optional[int] = Query(None),
):
    try:
        return Usages.get_summary_by_user(start_ts=start_ts, end_ts=end_ts)
    except Exception as e:
        log.error(f"Error fetching usage summary: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Internal Server Error")


