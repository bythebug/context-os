"""
contextos CLI — server management and key management for ContextOS.

Usage:
    contextos start              # start the ContextOS server (Docker required)
    contextos stop               # stop the server
    contextos logs               # tail server logs
    contextos health             # check a running server
    contextos keys create ...    # create an app and API key
    contextos keys list          # list apps and keys
    contextos keys delete <id>   # delete a key
"""
import hashlib
import os
import secrets
import subprocess
import sys
from pathlib import Path

try:
    import click
except ImportError:
    print("CLI dependencies missing. Install with: pip install contextos[cli]")
    sys.exit(1)


# Path to the compose file bundled inside the package
_SERVER_DIR = Path(__file__).parent / "server"
_COMPOSE_FILE = _SERVER_DIR / "docker-compose.yml"
_PROJECT_NAME = "contextos"


def _compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    """Run docker compose with the bundled compose file."""
    cmd = [
        "docker", "compose",
        "-f", str(_COMPOSE_FILE),
        "-p", _PROJECT_NAME,
        *args,
    ]
    if capture:
        return subprocess.run(cmd, capture_output=True, text=True)
    return subprocess.run(cmd)


@click.group()
def cli():
    """ContextOS — cross-app personal memory for AI tools."""


# ── Server commands ────────────────────────────────────────────────────────

@cli.command()
@click.option("--extraction", default=None, envvar="EXTRACTION_PROVIDER",
              help="Extraction provider: mock (default, no key), anthropic, openai.")
@click.option("--anthropic-key", default=None, envvar="ANTHROPIC_API_KEY")
@click.option("--openai-key", default=None, envvar="OPENAI_API_KEY")
def start(extraction, anthropic_key, openai_key):
    """Start the ContextOS server. Requires Docker."""
    _check_docker()

    # Pass env vars through to docker compose
    env = os.environ.copy()
    if extraction:
        env["EXTRACTION_PROVIDER"] = extraction
    if anthropic_key:
        env["ANTHROPIC_API_KEY"] = anthropic_key
    if openai_key:
        env["OPENAI_API_KEY"] = openai_key

    click.echo("Starting ContextOS server...")
    result = subprocess.run(
        [
            "docker", "compose",
            "-f", str(_COMPOSE_FILE),
            "-p", _PROJECT_NAME,
            "up", "-d", "--pull", "always",
        ],
        env=env,
    )
    if result.returncode != 0:
        click.echo("Failed to start server. Is Docker running?", err=True)
        sys.exit(1)

    click.echo("")
    click.echo(click.style("ContextOS is running.", fg="green", bold=True))
    click.echo("  API:    http://localhost:8000")
    click.echo("  Health: http://localhost:8000/health")
    click.echo("")
    click.echo("Next: create an API key:")
    click.echo(click.style(
        "  contextos keys create --app-name myapp "
        "--database-url postgresql://contextos:contextos@localhost:5433/contextos",
        fg="cyan",
    ))


@cli.command()
def stop():
    """Stop the ContextOS server."""
    _check_docker()
    click.echo("Stopping ContextOS server...")
    _compose("down")


@cli.command()
@click.option("-f", "--follow", is_flag=True, default=False, help="Follow log output.")
@click.option("-n", "--tail", default="50", help="Number of lines to show (default 50).")
def logs(follow, tail):
    """Show server logs."""
    _check_docker()
    args = ["logs", "--tail", tail]
    if follow:
        args.append("-f")
    _compose(*args)


@cli.command()
@click.option("--url", default="http://localhost:8000", show_default=True,
              help="ContextOS base URL.")
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


# ── Key management ─────────────────────────────────────────────────────────

@cli.group()
def keys():
    """Manage API keys."""


@keys.command("create")
@click.option("--app-name", required=True, help="App name (created if it doesn't exist).")
@click.option("--database-url", required=True, envvar="DATABASE_URL",
              help="Postgres URL. Default: postgresql://contextos:contextos@localhost:5433/contextos")
def keys_create(app_name: str, database_url: str):
    """Create a new app and API key."""
    _require_sqlalchemy()
    import sqlalchemy
    from sqlalchemy import text

    engine = sqlalchemy.create_engine(database_url)
    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT id FROM apps WHERE name = :name"), {"name": app_name}
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

    click.echo(f"API key: {click.style(raw_key, fg='cyan', bold=True)}")
    click.echo("\nStore this key — it cannot be recovered.")


@keys.command("list")
@click.option("--database-url", required=True, envvar="DATABASE_URL")
def keys_list(database_url: str):
    """List all apps and their key counts."""
    _require_sqlalchemy()
    import sqlalchemy
    from sqlalchemy import text

    engine = sqlalchemy.create_engine(database_url)
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
@click.option("--database-url", required=True, envvar="DATABASE_URL")
@click.confirmation_option(prompt="Delete this API key?")
def keys_delete(key_id: str, database_url: str):
    """Delete an API key by ID."""
    _require_sqlalchemy()
    import sqlalchemy
    from sqlalchemy import text

    engine = sqlalchemy.create_engine(database_url)
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM api_keys WHERE id = :id RETURNING id"), {"id": key_id}
        )
        if result.rowcount == 0:
            click.echo(f"Key {key_id} not found.", err=True)
            sys.exit(1)
    click.echo(f"Deleted key {key_id}.")


# ── Helpers ────────────────────────────────────────────────────────────────

def _check_docker():
    result = subprocess.run(
        ["docker", "info"], capture_output=True
    )
    if result.returncode != 0:
        click.echo(
            "Docker is not running. Start Docker Desktop and try again.", err=True
        )
        sys.exit(1)


def _require_sqlalchemy():
    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        click.echo("Database dependencies missing. Install with: pip install contextos[cli]", err=True)
        sys.exit(1)


def main():
    cli()


if __name__ == "__main__":
    main()
