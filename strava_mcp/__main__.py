from __future__ import annotations

import click


@click.group()
def cli() -> None:
    """Strava MCP server — connect Claude to your Strava training data."""


@cli.command()
def auth() -> None:
    """Authenticate with Strava and store credentials locally."""
    from .auth import TOKENS_FILE, run_oauth_flow

    click.echo("You'll need a Strava API application.")
    click.echo("Create one at: https://www.strava.com/settings/api")
    click.echo('Set the "Authorization Callback Domain" to: localhost\n')

    client_id = click.prompt("Client ID")
    client_secret = click.prompt("Client Secret", hide_input=True)

    try:
        token_data = run_oauth_flow(client_id, client_secret)
        athlete = token_data.get("athlete", {})
        name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
        click.echo(f"\nAuthenticated as: {name or 'athlete'}")
        click.echo(f"Credentials saved to: {TOKENS_FILE}")
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
