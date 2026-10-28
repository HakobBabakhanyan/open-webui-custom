import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from open_webui.models.usage import Usages, UserModelTotal, UserTokenTotal
from open_webui.utils.auth import get_admin_user


log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

router = APIRouter()


class UsageTotals(BaseModel):
    users: int
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_micros: int
    unpriced_tokens: int


class UsageSummaryResponse(BaseModel):
    users: list[UserTokenTotal]
    models: list[UserModelTotal]
    totals: UsageTotals


@router.get('/admin/usage/summary', response_model=UsageSummaryResponse)
async def get_usage_summary(user=Depends(get_admin_user)):
    try:
        rows = Usages.list_totals()
        models = Usages.list_model_totals()
        return {
            'users': rows,
            'models': models,
            'totals': {
                'users': len(rows),
                'request_count': sum(row.request_count for row in rows),
                'prompt_tokens': sum(row.prompt_tokens for row in rows),
                'completion_tokens': sum(row.completion_tokens for row in rows),
                'total_tokens': sum(row.total_tokens for row in rows),
                'cost_micros': sum(row.cost_micros for row in rows),
                'unpriced_tokens': sum(row.unpriced_tokens for row in rows),
            },
        }
    except Exception as e:
        log.exception(f'Error fetching usage summary: {e}')
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Internal Server Error')
