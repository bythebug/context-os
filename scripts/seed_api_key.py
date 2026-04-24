"""
Create an app + API key in the database.
Usage:
    DATABASE_URL=postgresql+asyncpg://... python scripts/seed_api_key.py --app-name "my-app"
"""
import asyncio
import hashlib
import secrets
import sys
import argparse

import asyncpg


async def seed(database_url: str, app_name: str):
    # asyncpg uses postgres:// not postgresql+asyncpg://
    url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)

    app_id = await conn.fetchval(
        "INSERT INTO apps (name) VALUES ($1) RETURNING id", app_name
    )

    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    await conn.execute(
        "INSERT INTO api_keys (app_id, key_hash) VALUES ($1, $2)",
        app_id, key_hash,
    )
    await conn.close()

    print(f"App created:  {app_name} ({app_id})")
    print(f"API key:      {raw_key}")
    print()
    print("Store this key — it cannot be recovered after this point.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-name", required=True)
    parser.add_argument("--database-url", default=None)
    args = parser.parse_args()

    import os
    db_url = args.database_url or os.environ.get("DATABASE_URL", "")
    if not db_url:
        print("Error: provide --database-url or set DATABASE_URL env var")
        sys.exit(1)

    asyncio.run(seed(db_url, args.app_name))
