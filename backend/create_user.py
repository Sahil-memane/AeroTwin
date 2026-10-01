"""Create or update a login user (there is no self-registration endpoint).

    docker compose --env-file .env.prod -f infra/docker/docker-compose.prod.yml \
        exec backend python create_user.py you@company.com admin

The password is read from the AEROTWIN_USER_PASSWORD env var or prompted for — never passed as an argument.
Roles: operator, maintenance_engineer, program_manager, admin.
"""
import asyncio
import getpass
import os
import sys

from sqlalchemy import select

from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User

ROLES = {"operator", "maintenance_engineer", "program_manager", "admin"}


async def main(email: str, role: str, password: str) -> None:
    async with AsyncSessionLocal() as s:
        user = (await s.execute(select(User).where(User.email == email))).scalars().first()
        if user:
            user.hashed_password = get_password_hash(password)
            user.role = role
            user.is_active = True
            action = "updated"
        else:
            s.add(User(email=email, hashed_password=get_password_hash(password), role=role, is_active=True))
            action = "created"
        await s.commit()
    print(f"User {email} ({role}) {action}.")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[2] not in ROLES:
        sys.exit(f"usage: python create_user.py <email> <{'|'.join(sorted(ROLES))}>")
    pw = os.environ.get("AEROTWIN_USER_PASSWORD") or getpass.getpass("Password (min 12 chars): ")
    if len(pw) < 12:
        sys.exit("Password must be at least 12 characters.")
    asyncio.run(main(sys.argv[1], sys.argv[2], pw))
