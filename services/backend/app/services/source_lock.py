"""Consistent lock ordering for mutations of an application's source documents."""
from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.candidate import Application
from app.db.models.document import Document, SanitizedVersion


async def lock_source_application(
    db: AsyncSession,
    source_model: type[Document] | type[SanitizedVersion],
    source_id: uuid.UUID,
) -> Application | None:
    """Lock Application before Document/SanitizedVersion to match reassessment FK writes.

    The first source lookup is deliberately unlocked. Callers acquire the source row
    lock afterwards and recheck existence, within the same transaction.
    """
    application_id = (await db.execute(select(source_model.application_id).where(
        source_model.id == source_id
    ))).scalar_one_or_none()
    if application_id is None:
        return None
    return (await db.execute(select(Application).where(
        Application.id == application_id
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
