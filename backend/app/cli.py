"""Admin CLI.

    python -m app.cli seed-brands
    python -m app.cli create-machine RVM-SIM-001 --name "Simulator" --location "Dev laptop"
    python -m app.cli rotate-key RVM-SIM-001
    python -m app.cli create-admin admin --name "Administrator" --role ADMIN   (prompts for password)
"""

import argparse
import asyncio
import getpass

from sqlalchemy.dialects.postgresql import insert as pg_insert

from .db import SessionLocal
from .models import AdminUser, EligibleBrand, Machine, Role
from .security import hash_api_key, hash_password, new_api_key, password_problem

TEST_BRANDS = {"KF": "Test Brand KF", "MC": "Test Brand MC", "OC": "Test Brand OC",
               "RC": "Test Brand RC", "BP": "Test Brand BP"}


async def seed_brands() -> None:
    async with SessionLocal() as db:
        for code, name in TEST_BRANDS.items():
            await db.execute(pg_insert(EligibleBrand).values(code=code, name=name, active=True)
                             .on_conflict_do_nothing())
        await db.commit()
    print(f"Seeded {len(TEST_BRANDS)} test brands")


async def create_machine(machine_id: str, name: str, location: str | None, api_key: str | None) -> None:
    key = api_key or new_api_key()
    async with SessionLocal() as db:
        if await db.get(Machine, machine_id):
            raise SystemExit(f"Machine {machine_id} already exists (use rotate-key)")
        db.add(Machine(id=machine_id, name=name, location=location, api_key_hash=hash_api_key(key)))
        await db.commit()
    print(f"Machine {machine_id} created.\nAPI key (shown once, put it in the machine config): {key}")


async def rotate_key(machine_id: str) -> None:
    key = new_api_key()
    async with SessionLocal() as db:
        m = await db.get(Machine, machine_id)
        if m is None:
            raise SystemExit(f"Machine {machine_id} not found")
        m.api_key_hash = hash_api_key(key)
        await db.commit()
    print(f"New API key for {machine_id}: {key}")


async def create_admin(username: str, name: str, role: str, password: str | None) -> None:
    if password is None:
        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Repeat password: "):
            raise SystemExit("Passwords do not match")
    if problem := password_problem(password):
        raise SystemExit(problem)
    async with SessionLocal() as db:
        db.add(AdminUser(username=username, full_name=name, role=Role(role), password_hash=hash_password(password)))
        await db.commit()
    print(f"Admin user {username} ({role}) created")


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("seed-brands")
    c = sub.add_parser("create-machine")
    c.add_argument("machine_id")
    c.add_argument("--name", default="RVM")
    c.add_argument("--location")
    c.add_argument("--api-key", help="use a fixed key (dev only)")
    r = sub.add_parser("rotate-key")
    r.add_argument("machine_id")
    u = sub.add_parser("create-admin")
    u.add_argument("username")
    u.add_argument("--name", default="Administrator")
    u.add_argument("--role", default="ADMIN", choices=[r.value for r in Role])
    u.add_argument("--password", help="dev only; omit to be prompted")
    a = p.parse_args()
    if a.cmd == "seed-brands":
        asyncio.run(seed_brands())
    elif a.cmd == "create-machine":
        asyncio.run(create_machine(a.machine_id, a.name, a.location, a.api_key))
    elif a.cmd == "create-admin":
        asyncio.run(create_admin(a.username, a.name, a.role, a.password))
    else:
        asyncio.run(rotate_key(a.machine_id))


if __name__ == "__main__":
    main()
