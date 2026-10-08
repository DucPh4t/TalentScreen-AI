"""Local duplicate hints. Never merge people or send contact data to an LLM."""
from __future__ import annotations

import hashlib
import hmac
import re
import unicodedata
import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Application, Document, Requisition, RequisitionMembership
from app.domain.enums import AccountRole
from app.services.sanitizer import EMAIL_REGEX, PHONE_REGEX


def contact_fingerprints(text: str, organization_id: uuid.UUID) -> list[str]:
    """Keyed digests prevent dictionary lookup of plain phone/email hashes.

    Key rotation requires reingesting documents to restore contact matching.
    File hashes continue to work for legacy documents without these signals.
    """
    identities = set()
    for match in EMAIL_REGEX.finditer(text):
        value = unicodedata.normalize("NFKC", match.group()).casefold()
        if value.split("@", 1)[0] not in {"hr", "info", "careers", "jobs", "recruitment", "noreply", "contact"}:
            identities.add(("email", value))
    for match in PHONE_REGEX.finditer(text):
        value = re.sub(r"\D", "", match.group())
        if value.startswith("84") and len(value) == 11:
            value = "0" + value[2:]
        identities.add(("phone", value))
    key = get_settings().SECRET_KEY.encode()
    return sorted(hmac.new(key, f"duplicate-v1:{organization_id}:{kind}:{value}".encode(), hashlib.sha256).hexdigest()
                  for kind, value in identities)


async def duplicate_signals(db: AsyncSession, requisition: Requisition, ctx) -> dict[uuid.UUID, tuple[int, list[str]]]:
    """Compare current CVs only within the organization and caller-visible requisitions.

    A shared contact or file is a review hint, never proof of identity. Return
    counts/reasons only; do not reveal candidate IDs from other requisitions.
    """
    stmt = (select(Application.id, Application.candidate_id, Document.sha256, Document.duplicate_fingerprints)
        .join(Requisition, Requisition.id == Application.requisition_id)
        .outerjoin(Document, Document.id == Application.current_document_id)
        .where(Requisition.organization_id == requisition.organization_id, Application.status == "active"))
    if not ctx.has_role(AccountRole.ADMIN):
        allowed = select(RequisitionMembership.requisition_id).where(RequisitionMembership.user_id == ctx.user.id,
            RequisitionMembership.active.is_(True))
        stmt = stmt.where(Application.requisition_id.in_(allowed))
    rows = (await db.execute(stmt)).all()
    groups = defaultdict(set)
    keys_by_app = {}
    for app_id, candidate_id, sha, fingerprints in rows:
        keys = [("same_candidate", str(candidate_id))]
        if sha:
            keys.append(("same_file", sha))
        keys.extend(("same_contact", fingerprint) for fingerprint in fingerprints or [])
        keys_by_app[app_id] = keys
        for key in keys:
            groups[key].add(app_id)
    signals = {}
    for app_id, keys in keys_by_app.items():
        matches = {app_id}
        reasons = set()
        for key in keys:
            if len(groups[key]) > 1:
                matches.update(groups[key])
                reasons.add(key[0])
        signals[app_id] = (len(matches), sorted(reasons))
    return signals
