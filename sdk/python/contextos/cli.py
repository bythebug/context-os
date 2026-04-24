"""
contextos CLI — key management for ContextOS.

Usage:
    contextos keys create --app-name my-app --database-url postgresql://...
    contextos keys list   --database-url postgresql://...
    contextos keys delete <key-id> --database-url postgresql://...
    contextos health      --url https://your-app.fly.dev
"""
import hashlib
import secrets
import sys

try:
    import click
    import sqlalchemy
    from sqlalchemy import text
except ImportError:
    print("CLI dependencies missing. Install with: pip install contextos[cli]")
    sys.exit(1)


def _engine(database_url: str):
    return sqlalchemy.create_engine(database_url)


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@click.group()
def cli():
    """ContextOS key management CLI."""


@cli.group()
def keys():
    """Manage API keys."""


@keys.command("create")
@click.option("--app-name", required=True, help="Name for the app (creates one if it doesn't exist).")
@click.option("--database-url", required=True, envvar="DATABASE_URL", help="Postgres connection URL.")
def keys_create(app_name: str, database_url: str):
    """Create a new app and API key."""
    engine = _engine(database_url)
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = _hash(raw_key)

    with engine.begin() as conn:
        # Upsert app
        row = conn.execute(
            text("SELECT id FROM apps WHERE name = :name"),
            {"name": app_name},
        ).fetchone()

        if row:
            app_id = row[0]
            click.echo(f"App:     {app_name} (existing, id={app_id})")
        else:
            app_id = conn.execute(
                text("INSERT INTO apps (name) VALUES (:name) RETURNING id"),
                {"name": app_name},
            ).scalar()
            click.echo(f"App:     {app_name} (created, id={app_id})")

        conn.execute(
            text("INSERT INTO api_keys (app_id, key_hash) VALUES (:app_id, :key_hash)"),
            {"app_id": app_id, "key_hash": key_hash},
        )

    click.echo(f"API key: {raw_key}")
    click.echo("\nStore this key — it cannot be recovered.")


@keys.command("list")
@click.option("--database-url", required=True, envvar="DATABASE_URL", help="Postgres connection URL.")
def keys_list(database_url: str):
    """List all apps and their key counts."""
    engine = _engine(database_url)
    with engine.connect() as conn:
        rows = conn.execute(
            text("""
                SELECT a.name, a.id, COUNT(k.id) AS key_count, a.created_at
                FROM apps a
                LEFT JOIN api_keys k ON k.app_id = a.id
                GROUP BY a.id
                ORDER BY a.created_at DESC
            """)
        ).fetchall()

    if not rows:
        click.echo("No apps found.")
        return

    click.echo(f"{'App':<30} {'ID':<38} {'Keys':>4}  {'Created'}")
    click.echo("-" * 85)
    for row in rows:
        click.echo(f"{row[0]:<30} {str(row[1]):<38} {row[2]:>4}  {row[3].strftime('%Y-%m-%d')}")


@keys.command("delete")
@click.argument("key_id")
@click.option("--database-url", required=True, envvar="DATABASE_URL", help="Postgres connection URL.")
@click.confirmation_option(prompt="Delete this API key?")
def keys_delete(key_id: str, database_url: str):
    """Delete an API key by ID."""
    engine = _engine(database_url)
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM api_keys WHERE id = :id RETURNING id"),
            {"id": key_id},
        )
        if result.rowcount == 0:
            click.echo(f"Key {key_id} not found.", err=True)
            sys.exit(1)
    click.echo(f"Deleted key {key_id}.")


@cli.command()
@click.option("--url", default="http://localhost:8000", show_default=True, help="ContextOS base URL.")
def health(url: str):
    """Check the health of a running ContextOS instance."""
    try:
        import httpx
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=10.0)
        data = resp.json()
        status = data.get("status", "unknown")
        postgres = data.get("postgres", "unknown")
        redis = data.get("redis", "unknown")
        color = "green" if status == "ok" else "red"
        click.echo(f"Status:   {click.style(status, fg=color, bold=True)}")
        click.echo(f"Postgres: {postgres}")
        click.echo(f"Redis:    {redis}")
        click.echo(f"URL:      {url}")
    except Exception as exc:
        click.echo(f"Could not reach {url}: {exc}", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
