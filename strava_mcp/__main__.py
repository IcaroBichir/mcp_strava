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


if __name__ == "__main__":
    cli()
