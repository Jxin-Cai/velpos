from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute


async def remove_by_pk(
    session: AsyncSession,
    pk_column: InstrumentedAttribute,
    pk_value: str,
) -> bool:
    stmt = select(pk_column.class_).where(pk_column == pk_value)
    result = await session.execute(stmt)
    model = result.scalar_one_or_none()
    if model is None:
        return False
    await session.delete(model)
    await session.flush()
    return True
