import time
from typing import Optional, Tuple, Dict, Any, List

from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    BigInteger,
    JSON,
    Column,
    Text,
    String,
    func,
    and_,
)

from open_webui.internal.db import Base, get_db
from open_webui.models.users import User


class Usage(Base):
    __tablename__ = "usage_log"

    id = Column(Text, primary_key=True, unique=True)
    user_id = Column(Text, nullable=False)

    provider = Column(String, nullable=False)  # e.g., "openai"
    model = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)  # e.g., "chat.completions", "embeddings"
    request_id = Column(Text, nullable=True)

    # Raw OpenAI-compatible usage object for extensibility
    usage = Column(JSON, nullable=True)

    # Denormalized common counters for easy aggregation
    prompt_tokens = Column(BigInteger, nullable=True)
    completion_tokens = Column(BigInteger, nullable=True)
    total_tokens = Column(BigInteger, nullable=True)

    # Optional metadata (e.g., tenant, ip, extra context)
    extra = Column(JSON, nullable=True)

    created_at = Column(BigInteger, nullable=False)


class UsageModel(BaseModel):
    id: str
    user_id: str
    provider: str
    model: Optional[str] = None
    endpoint: Optional[str] = None
    request_id: Optional[str] = None

    usage: Optional[dict] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    extra: Optional[dict] = None

    created_at: int

    model_config = ConfigDict(from_attributes=True)


class UsageSummaryByUser(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    request_count: int
    total_tokens: int


def _extract_usage_counters(usage: Optional[Dict[str, Any]]) -> Tuple[Optional[int], Optional[int], Optional[int]]:
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    total_tokens = usage.get("total_tokens")
    return prompt_tokens, completion_tokens, total_tokens


class UsagesTable:
    def ensure_table(self):
        with get_db() as db:
            # Create the table if it does not exist
            Usage.__table__.create(bind=db.bind, checkfirst=True)

    def add_usage(
        self,
        *,
        id: str,
        user_id: str,
        provider: str,
        model: Optional[str],
        endpoint: Optional[str],
        request_id: Optional[str],
        usage: Optional[dict],
        extra: Optional[dict] = None,
        created_at: Optional[int] = None,
    ) -> Optional[UsageModel]:
        self.ensure_table()

        created_at = created_at or int(time.time())
        prompt_tokens, completion_tokens, total_tokens = _extract_usage_counters(usage)

        with get_db() as db:
            row = Usage(
                id=id,
                user_id=user_id,
                provider=provider,
                model=model,
                endpoint=endpoint,
                request_id=request_id,
                usage=usage,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                extra=extra,
                created_at=created_at,
            )
            db.add(row)
            db.commit()
            return UsageModel.model_validate(row)

    def get_logs(
        self,
        *,
        user_id: Optional[str] = None,
        user_email: Optional[str] = None,
        provider: Optional[str] = None,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
        skip: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        self.ensure_table()
        with get_db() as db:
            query = db.query(Usage)

            conditions = []
            if user_id:
                conditions.append(Usage.user_id == user_id.strip())
            if user_email:
                query = query.join(User, User.id == Usage.user_id)
                conditions.append(User.email == user_email.strip())
            if provider:
                conditions.append(Usage.provider == provider)
            if start_ts is not None:
                conditions.append(Usage.created_at >= start_ts)
            if end_ts is not None:
                conditions.append(Usage.created_at <= end_ts)

            if conditions:
                query = query.filter(and_(*conditions))

            # Count BEFORE pagination
            total = query.count()

            # Order BEFORE pagination to avoid SQLAlchemy error
            query = query.order_by(Usage.created_at.desc(), Usage.id.desc())

            if skip is not None:
                query = query.offset(skip)
            if limit is not None:
                query = query.limit(limit)

            logs = query.all()
            return {
                "logs": [UsageModel.model_validate(row) for row in logs],
                "total": total,
            }

    def get_summary_by_user(
        self,
        *,
        start_ts: Optional[int] = None,
        end_ts: Optional[int] = None,
    ) -> List[UsageSummaryByUser]:
        self.ensure_table()
        with get_db() as db:
            query = (
                db.query(
                    Usage.user_id.label("user_id"),
                    User.email.label("user_email"),
                    func.count(Usage.id).label("request_count"),
                    func.coalesce(func.sum(Usage.total_tokens), 0).label("total_tokens"),
                )
                .outerjoin(User, User.id == Usage.user_id)
            )

            conditions = []
            if start_ts is not None:
                conditions.append(Usage.created_at >= start_ts)
            if end_ts is not None:
                conditions.append(Usage.created_at <= end_ts)

            if conditions:
                query = query.filter(and_(*conditions))

            query = query.group_by(Usage.user_id, User.email).order_by(
                func.count(Usage.id).desc()
            )
            rows = query.all()

            return [
                UsageSummaryByUser(
                    user_id=row.user_id,
                    user_email=row.user_email,
                    request_count=int(row.request_count or 0),
                    total_tokens=int(row.total_tokens or 0),
                )
                for row in rows
            ]


Usages = UsagesTable()


