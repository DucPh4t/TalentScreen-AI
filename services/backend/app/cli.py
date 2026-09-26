"""Administrative CLI commands for TalentScreen AI.
Usage:
    python -m app.cli create-admin --login admin --password <secret> --display-name "Administrator"
    python -m app.cli list-users
    python -m app.cli disable-user --login <user_login>
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.db.models import Organization, User, UserAccountRole
from app.db.session import get_session_factory
from app.domain.enums import AccountRole, EnvironmentMode, UserStatus
from app.domain.security import hash_password


async def ensure_default_organization() -> Organization:
    """Ensure a default organization exists in the database."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(Organization).limit(1)
        result = await session.execute(stmt)
        org = result.scalar_one_or_none()
        if not org:
            org = Organization(
                id=uuid.uuid4(),
                name="Trường Đại học (Mặc định)",
                environment=EnvironmentMode.SANDBOX,
            )
            session.add(org)
            await session.commit()
            print(f"[OK] Created default organization: {org.name} ({org.id})")
        return org


async def create_admin(login: str, password: str, display_name: str) -> None:
    """Bootstrap or update an admin user."""
    await ensure_default_organization()
    factory = get_session_factory()
    normalized_login = login.strip().lower()

    async with factory() as session:
        stmt = (
            select(User)
            .where(User.login_name == normalized_login)
            .options(selectinload(User.account_roles))
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        pw_hash = hash_password(password)

        if user:
            user.display_name = display_name
            user.password_hash = pw_hash
            user.status = UserStatus.ACTIVE

            # Ensure admin role exists
            has_admin = any(r.role == AccountRole.ADMIN for r in user.account_roles)
            if not has_admin:
                session.add(UserAccountRole(user_id=user.id, role=AccountRole.ADMIN))
            await session.commit()
            print(f"[OK] Updated existing user '{normalized_login}' with ADMIN role.")
        else:
            user_id = uuid.uuid4()
            user = User(
                id=user_id,
                login_name=normalized_login,
                display_name=display_name,
                password_hash=pw_hash,
                status=UserStatus.ACTIVE,
            )
            session.add(user)
            await session.flush()

            admin_role = UserAccountRole(user_id=user.id, role=AccountRole.ADMIN)
            session.add(admin_role)
            await session.commit()
            print(f"[OK] Created new ADMIN user '{normalized_login}' ({user.id}).")


async def disable_user(login: str) -> None:
    """Disable a user account, enforcing the last-admin guard."""
    factory = get_session_factory()
    normalized_login = login.strip().lower()

    async with factory() as session:
        stmt = (
            select(User)
            .where(User.login_name == normalized_login)
            .options(selectinload(User.account_roles))
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print(f"[ERROR] User '{normalized_login}' not found.", file=sys.stderr)
            sys.exit(1)

        is_admin = any(r.role == AccountRole.ADMIN for r in user.account_roles)
        if is_admin:
            # Check how many active admins remain
            count_stmt = (
                select(func.count(User.id))
                .join(UserAccountRole, User.id == UserAccountRole.user_id)
                .where(
                    UserAccountRole.role == AccountRole.ADMIN,
                    User.status == UserStatus.ACTIVE,
                    User.id != user.id,
                )
            )
            remaining_active_admins = (await session.execute(count_stmt)).scalar() or 0
            if remaining_active_admins == 0:
                print(
                    "[ERROR] Last-admin guard: Cannot disable the only remaining active admin account.",
                    file=sys.stderr,
                )
                sys.exit(1)

        user.status = UserStatus.DISABLED
        await session.commit()
        print(f"[OK] Disabled user account '{normalized_login}'.")


async def list_users() -> None:
    """List all accounts and their roles."""
    factory = get_session_factory()
    async with factory() as session:
        stmt = select(User).options(selectinload(User.account_roles)).order_by(User.login_name)
        result = await session.execute(stmt)
        users = result.scalars().all()

        print("-" * 75)
        print(f"{'Login':<20} {'Display Name':<25} {'Status':<10} {'Roles'}")
        print("-" * 75)
        for u in users:
            roles_str = ", ".join(r.role.value for r in u.account_roles)
            print(f"{u.login_name:<20} {u.display_name:<25} {u.status.value:<10} {roles_str}")
        print("-" * 75)


async def run_worker_command(once: bool = False) -> None:
    """Run background worker loop."""
    from app.services.worker import run_worker_once
    factory = get_session_factory()
    w_id = f"cli_worker_{uuid.uuid4().hex[:8]}"
    print(f"[OK] Starting background worker '{w_id}' (once={once})...")

    while True:
        async with factory() as session:
            processed = await run_worker_once(session, worker_id=w_id)
        if once:
            print(f"[OK] Worker finished single pass. Processed job: {processed}")
            break
        if not processed:
            await asyncio.sleep(2.0)


async def apply_deletion_ledger_command() -> None:
    """Re-apply deletion ledger sweep (SEC-11 invariant)."""
    from app.services.deletion import apply_deletion_ledger
    factory = get_session_factory()
    async with factory() as session:
        print("[INFO] Scanning deletion ledger for zombie records...")
        report = await apply_deletion_ledger(session)
        await session.commit()
        print(f"[OK] Deletion ledger applied. Re-purged applications: {report.get('re_purged_applications_count', 0)}")


def main():
    parser = argparse.ArgumentParser(description="TalentScreen AI Admin CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create-admin
    admin_parser = subparsers.add_parser("create-admin", help="Bootstrap admin account")
    admin_parser.add_argument("--login", required=True, help="Login username")
    admin_parser.add_argument("--password", required=True, help="Account password")
    admin_parser.add_argument("--display-name", default="Administrator", help="Display name")

    # disable-user
    disable_parser = subparsers.add_parser("disable-user", help="Disable a user account")
    disable_parser.add_argument("--login", required=True, help="Login username to disable")

    # list-users
    subparsers.add_parser("list-users", help="List all users")

    # run-worker
    worker_parser = subparsers.add_parser("run-worker", help="Run background worker process")
    worker_parser.add_argument("--once", action="store_true", help="Process one job and exit")

    # apply-deletion-ledger
    subparsers.add_parser("apply-deletion-ledger", help="Re-apply deletion ledger sweep (SEC-11 invariant)")

    args = parser.parse_args()

    if args.command == "create-admin":
        asyncio.run(create_admin(args.login, args.password, args.display_name))
    elif args.command == "disable-user":
        asyncio.run(disable_user(args.login))
    elif args.command == "list-users":
        asyncio.run(list_users())
    elif args.command == "run-worker":
        asyncio.run(run_worker_command(args.once))
    elif args.command == "apply-deletion-ledger":
        asyncio.run(apply_deletion_ledger_command())


if __name__ == "__main__":
    main()
