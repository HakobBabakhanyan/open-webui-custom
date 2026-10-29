import time
from typing import Optional

from pydantic import BaseModel, ConfigDict
from sqlalchemy import BigInteger, Column, String, inspect, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from open_webui.internal.db import Base, get_db
from open_webui.models.users import User


# USD per 1,000,000 tokens: (input, output). Longer names are matched first.
# Unknown models still count tokens, but their spend stays unpriced.
_MODEL_RATES: dict[str, tuple[float, float]] = {
    'gpt-4.1-nano': (0.10, 0.40),
    'gpt-4.1-mini': (0.40, 1.60),
    'gpt-4.1': (2.00, 8.00),
    'gpt-4o-mini': (0.15, 0.60),
    'gpt-4o': (2.50, 10.00),
    'gpt-4-turbo': (10.00, 30.00),
    'gpt-3.5-turbo': (0.50, 1.50),
    'o4-mini': (1.10, 4.40),
    'o3-mini': (1.10, 4.40),
    'o3': (2.00, 8.00),
    'o1-mini': (1.10, 4.40),
    'o1': (15.00, 60.00),
    'text-embedding-3-small': (0.02, 0.0),
    'text-embedding-3-large': (0.13, 0.0),
    'text-embedding-ada-002': (0.10, 0.0),
    'chatgpt-4o-latest': (5.00, 15.00),
    'claude-opus-5-5': (4.00, 20.00),
    'claude-opus-5': (5.00, 25.00),
    'claude-opus-4-8': (5.00, 25.00),
    'claude-opus-4-7': (5.00, 25.00),
    'claude-opus-4-6': (5.00, 25.00),
    'claude-opus-4-5': (5.00, 25.00),
    'claude-opus-4-1': (15.00, 75.00),
    'claude-opus-4': (15.00, 75.00),
    'claude-sonnet-5-5': (2.00, 10.00),
    'claude-sonnet-5': (2.00, 10.00),
    'claude-sonnet-4-6': (3.00, 15.00),
    'claude-sonnet-4-5': (3.00, 15.00),
    'claude-sonnet-4': (3.00, 15.00),
    'claude-haiku-4-5': (1.00, 5.00),
    'claude-3-7-sonnet': (3.00, 15.00),
    'claude-3-5-sonnet': (3.00, 15.00),
    'claude-3-5-haiku': (0.80, 4.00),
    'claude-3-opus': (15.00, 75.00),
    'claude-3-haiku': (0.25, 1.25),
    'claude-3-sonnet': (3.00, 15.00),
    'gemini-3.1-pro': (2.00, 12.00),
    'gemini-2.5-flash-lite': (0.10, 0.40),
    'gemini-2.5-flash': (0.30, 2.50),
    'gemini-2.5-pro': (1.25, 10.00),
    'gemini-2.0-flash-lite': (0.075, 0.30),
    'gemini-2.0-flash': (0.10, 0.40),
    'gemini-1.5-flash-8b': (0.0375, 0.15),
    'gemini-1.5-flash': (0.075, 0.30),
    'gemini-1.5-pro': (1.25, 5.00),
}
_RATE_KEYS = sorted(_MODEL_RATES, key=len, reverse=True)


class UserTokenUsage(Base):
    __tablename__ = 'user_token_usage'

    user_id = Column(String, primary_key=True)
    request_count = Column(BigInteger, nullable=False, default=0)
    prompt_tokens = Column(BigInteger, nullable=False, default=0)
    completion_tokens = Column(BigInteger, nullable=False, default=0)
    total_tokens = Column(BigInteger, nullable=False, default=0)
    cost_micros = Column(BigInteger, nullable=False, default=0)
    unpriced_tokens = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(BigInteger, nullable=False)


class UserModelUsage(Base):
    __tablename__ = 'user_model_usage'

    user_id = Column(String, primary_key=True)
    model = Column(String, primary_key=True)
    request_count = Column(BigInteger, nullable=False, default=0)
    prompt_tokens = Column(BigInteger, nullable=False, default=0)
    completion_tokens = Column(BigInteger, nullable=False, default=0)
    total_tokens = Column(BigInteger, nullable=False, default=0)
    cost_micros = Column(BigInteger, nullable=False, default=0)
    unpriced_tokens = Column(BigInteger, nullable=False, default=0)
    updated_at = Column(BigInteger, nullable=False)


class UserTokenTotal(BaseModel):
    user_id: str
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_micros: int
    unpriced_tokens: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


class UserModelTotal(BaseModel):
    user_id: str
    model: str
    request_count: int
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_micros: int
    unpriced_tokens: int
    updated_at: int

    model_config = ConfigDict(from_attributes=True)


def _int_or_zero(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _token_counts(usage: Optional[dict]) -> Optional[tuple[int, int, int]]:
    if not isinstance(usage, dict):
        return None

    prompt = usage.get('prompt_tokens')
    if prompt is None:
        prompt = usage.get('input_tokens')
    completion = usage.get('completion_tokens')
    if completion is None:
        completion = usage.get('output_tokens')

    prompt = _int_or_zero(prompt)
    completion = _int_or_zero(completion)
    total = usage.get('total_tokens')
    total = _int_or_zero(total) if total is not None else prompt + completion
    if prompt == 0 and completion == 0 and total == 0:
        return None
    if total < prompt + completion:
        total = prompt + completion
    return prompt, completion, total


def _model_key(model: Optional[str]) -> str:
    name = (model or '').strip().lower()
    if '/' in name:
        name = name.rsplit('/', 1)[-1]
    if name.startswith('ft:'):
        parts = name.split(':')
        if len(parts) >= 2:
            name = parts[1]
    return name or 'unknown'


def estimate_cost_micros(model: Optional[str], prompt_tokens: int, completion_tokens: int) -> tuple[int, int]:
    """Return (cost in micro-USD, tokens that had no price)."""
    name = _model_key(model)
    for key in _RATE_KEYS:
        if name == key or name.startswith(f'{key}-'):
            input_rate, output_rate = _MODEL_RATES[key]
            cost = int(round(prompt_tokens * input_rate + completion_tokens * output_rate))
            return cost, 0
    return 0, prompt_tokens + completion_tokens


class UserTokenUsages:
    def __init__(self):
        self._ready = False

    def ensure_table(self):
        if self._ready:
            return
        with get_db() as db:
            UserTokenUsage.__table__.create(bind=db.bind, checkfirst=True)
            UserModelUsage.__table__.create(bind=db.bind, checkfirst=True)
            need_users = db.query(UserTokenUsage.user_id).first() is None
            need_models = db.query(UserModelUsage.user_id).first() is None
            changed = False
            if need_users or need_models:
                self._rollup_legacy_logs(db, users=need_users, models=need_models)
                changed = True
            if self._reprice_stored_totals(db):
                changed = True
            if changed:
                db.commit()
        self._ready = True

    def _reprice_stored_totals(self, db) -> bool:
        """Recompute stored estimates from token counts and the current rate table."""
        changed = False
        cost_by_user: dict[str, int] = {}
        unpriced_by_user: dict[str, int] = {}
        for row in db.query(UserModelUsage).all():
            cost, unpriced = estimate_cost_micros(
                row.model, _int_or_zero(row.prompt_tokens), _int_or_zero(row.completion_tokens)
            )
            cost_by_user[row.user_id] = cost_by_user.get(row.user_id, 0) + cost
            unpriced_by_user[row.user_id] = unpriced_by_user.get(row.user_id, 0) + unpriced
            if _int_or_zero(row.cost_micros) != cost or _int_or_zero(row.unpriced_tokens) != unpriced:
                row.cost_micros = cost
                row.unpriced_tokens = unpriced
                changed = True

        for row in db.query(UserTokenUsage).all():
            if row.user_id not in cost_by_user:
                continue
            cost = cost_by_user[row.user_id]
            unpriced = unpriced_by_user.get(row.user_id, 0)
            if _int_or_zero(row.cost_micros) != cost or _int_or_zero(row.unpriced_tokens) != unpriced:
                row.cost_micros = cost
                row.unpriced_tokens = unpriced
                changed = True
        return changed

    def _rollup_legacy_logs(self, db, *, users: bool, models: bool):
        if not inspect(db.bind).has_table('usage_log'):
            return

        rows = db.execute(
            text(
                """
                SELECT user_id,
                       model,
                       COUNT(*) AS request_count,
                       COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                       COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                       COALESCE(SUM(total_tokens), 0) AS total_tokens,
                       MAX(created_at) AS updated_at
                FROM usage_log
                WHERE prompt_tokens IS NOT NULL
                   OR completion_tokens IS NOT NULL
                   OR total_tokens IS NOT NULL
                GROUP BY user_id, model
                """
            )
        ).mappings()

        folded: dict[str, dict] = {}
        by_model: dict[tuple[str, str], dict] = {}
        for row in rows:
            user_id = row['user_id']
            if not user_id:
                continue
            prompt = _int_or_zero(row['prompt_tokens'])
            completion = _int_or_zero(row['completion_tokens'])
            total = _int_or_zero(row['total_tokens']) or (prompt + completion)
            if prompt == 0 and completion == 0 and total == 0:
                continue
            cost, unpriced = estimate_cost_micros(row['model'], prompt, completion)
            if models:
                key = (user_id, _model_key(row['model']))
                current_model = by_model.setdefault(
                    key,
                    {
                        'request_count': 0,
                        'prompt_tokens': 0,
                        'completion_tokens': 0,
                        'total_tokens': 0,
                        'cost_micros': 0,
                        'unpriced_tokens': 0,
                        'updated_at': 0,
                    },
                )
                current_model['request_count'] += _int_or_zero(row['request_count'])
                current_model['prompt_tokens'] += prompt
                current_model['completion_tokens'] += completion
                current_model['total_tokens'] += total
                current_model['cost_micros'] += cost
                current_model['unpriced_tokens'] += unpriced
                current_model['updated_at'] = max(current_model['updated_at'], _int_or_zero(row['updated_at']))
            if not users:
                continue
            current = folded.setdefault(
                user_id,
                {
                    'request_count': 0,
                    'prompt_tokens': 0,
                    'completion_tokens': 0,
                    'total_tokens': 0,
                    'cost_micros': 0,
                    'unpriced_tokens': 0,
                    'updated_at': 0,
                },
            )
            current['request_count'] += _int_or_zero(row['request_count'])
            current['prompt_tokens'] += prompt
            current['completion_tokens'] += completion
            current['total_tokens'] += total
            current['cost_micros'] += cost
            current['unpriced_tokens'] += unpriced
            current['updated_at'] = max(current['updated_at'], _int_or_zero(row['updated_at']))

        for user_id, totals in folded.items():
            db.add(UserTokenUsage(user_id=user_id, **totals))
        for (user_id, model_name), totals in by_model.items():
            db.add(UserModelUsage(user_id=user_id, model=model_name, **totals))

    def add_tokens(self, *, user_id: str, model: Optional[str], usage: Optional[dict]) -> bool:
        counts = _token_counts(usage)
        if not user_id or counts is None:
            return False
        prompt, completion, total = counts
        cost, unpriced = estimate_cost_micros(model, prompt, completion)
        now = int(time.time())

        self.ensure_table()
        model_name = _model_key(model)
        with get_db() as db:
            self._increment(
                db, UserTokenUsage, {'user_id': user_id}, ['user_id'], prompt, completion, total, cost, unpriced, now
            )
            self._increment(
                db,
                UserModelUsage,
                {'user_id': user_id, 'model': model_name},
                ['user_id', 'model'],
                prompt,
                completion,
                total,
                cost,
                unpriced,
                now,
            )
            db.commit()
        return True

    def _increment(self, db, table, identity, conflict_cols, prompt, completion, total, cost, unpriced, now):
        dialect = db.bind.dialect.name
        if dialect in ('postgresql', 'sqlite'):
            insert = pg_insert if dialect == 'postgresql' else sqlite_insert
            stmt = insert(table).values(
                **identity,
                request_count=1,
                prompt_tokens=prompt,
                completion_tokens=completion,
                total_tokens=total,
                cost_micros=cost,
                unpriced_tokens=unpriced,
                updated_at=now,
            )
            excluded = stmt.excluded
            stmt = stmt.on_conflict_do_update(
                index_elements=conflict_cols,
                set_={
                    'request_count': table.request_count + excluded.request_count,
                    'prompt_tokens': table.prompt_tokens + excluded.prompt_tokens,
                    'completion_tokens': table.completion_tokens + excluded.completion_tokens,
                    'total_tokens': table.total_tokens + excluded.total_tokens,
                    'cost_micros': table.cost_micros + excluded.cost_micros,
                    'unpriced_tokens': table.unpriced_tokens + excluded.unpriced_tokens,
                    'updated_at': excluded.updated_at,
                },
            )
            db.execute(stmt)
            return

        filters = [getattr(table, key) == value for key, value in identity.items()]
        row = db.query(table).filter(*filters).one_or_none()
        if row is None:
            db.add(
                table(
                    **identity,
                    request_count=1,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    total_tokens=total,
                    cost_micros=cost,
                    unpriced_tokens=unpriced,
                    updated_at=now,
                )
            )
            return
        row.request_count = _int_or_zero(row.request_count) + 1
        row.prompt_tokens = _int_or_zero(row.prompt_tokens) + prompt
        row.completion_tokens = _int_or_zero(row.completion_tokens) + completion
        row.total_tokens = _int_or_zero(row.total_tokens) + total
        row.cost_micros = _int_or_zero(row.cost_micros) + cost
        row.unpriced_tokens = _int_or_zero(row.unpriced_tokens) + unpriced
        row.updated_at = now

    def list_totals(self) -> list[UserTokenTotal]:
        self.ensure_table()
        with get_db() as db:
            rows = (
                db.query(
                    UserTokenUsage,
                    User.email.label('user_email'),
                    User.name.label('user_name'),
                )
                .outerjoin(User, User.id == UserTokenUsage.user_id)
                .order_by(UserTokenUsage.total_tokens.desc(), UserTokenUsage.user_id.asc())
                .all()
            )
            return [
                UserTokenTotal(
                    user_id=usage.user_id,
                    user_email=email,
                    user_name=name,
                    request_count=_int_or_zero(usage.request_count),
                    prompt_tokens=_int_or_zero(usage.prompt_tokens),
                    completion_tokens=_int_or_zero(usage.completion_tokens),
                    total_tokens=_int_or_zero(usage.total_tokens),
                    cost_micros=_int_or_zero(usage.cost_micros),
                    unpriced_tokens=_int_or_zero(usage.unpriced_tokens),
                    updated_at=_int_or_zero(usage.updated_at),
                )
                for usage, email, name in rows
            ]

    def list_model_totals(self) -> list[UserModelTotal]:
        self.ensure_table()
        with get_db() as db:
            rows = db.query(UserModelUsage).order_by(UserModelUsage.total_tokens.desc(), UserModelUsage.model.asc()).all()
            return [
                UserModelTotal(
                    user_id=row.user_id,
                    model=row.model,
                    request_count=_int_or_zero(row.request_count),
                    prompt_tokens=_int_or_zero(row.prompt_tokens),
                    completion_tokens=_int_or_zero(row.completion_tokens),
                    total_tokens=_int_or_zero(row.total_tokens),
                    cost_micros=_int_or_zero(row.cost_micros),
                    unpriced_tokens=_int_or_zero(row.unpriced_tokens),
                    updated_at=_int_or_zero(row.updated_at),
                )
                for row in rows
            ]


Usages = UserTokenUsages()
