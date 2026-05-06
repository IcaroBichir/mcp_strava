from __future__ import annotations

import click


@click.group()
def cli() -> None:
    """Strava MCP server — connect Claude to your Strava training data."""


@cli.command()
def auth() -> None:
    """Authenticate with Strava and store OAuth tokens locally."""
    from .auth import TOKENS_FILE, get_client_credentials, run_oauth_flow

    try:
        client_id, client_secret = get_client_credentials()
        click.echo(f"Using Client ID from environment: {client_id}")
    except RuntimeError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1)

    try:
        token_data = run_oauth_flow(client_id, client_secret)
        athlete = token_data.get("athlete", {})
        name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
        click.echo(f"\nAuthenticated as: {name or 'athlete'}")
        click.echo(f"Tokens saved to: {TOKENS_FILE}")
    except Exception as exc:
        click.echo(f"\nAuthentication failed: {exc}", err=True)
        raise SystemExit(1)


@cli.command()
def serve() -> None:
    """Start the MCP server (stdio transport for Claude)."""
    from .server import mcp
    mcp.run()


@cli.group()
def cache() -> None:
    """Inspect or manage the local response cache."""


@cache.command("stats")
def cache_stats() -> None:
    """Show cache entry count and file size."""
    from .cache import CacheStore

    s = CacheStore().stats()
    click.echo(f"Entries:  {s['total_entries']} total, {s['expired_entries']} expired")
    click.echo(f"Size:     {s['cache_size_bytes'] / 1024:.1f} KB")


@cache.command("clear")
def cache_clear() -> None:
    """Delete all cached responses."""
    from .cache import CacheStore

    count = CacheStore().clear()
    click.echo(f"Cleared {count} cache entries.")


if __name__ == "__main__":
    cli()
