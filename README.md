# strava-mcp

MCP server for Strava. Gives Claude access to your training data — activities, stats, and gear — so you can ask questions, build reports, and track progress directly in conversation.

**Runs locally. Your data never leaves your machine.**

---

## Setup

### 1. Create a Strava API application

Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api) and fill in the form:

| Field | What to enter |
|---|---|
| **Application Name** | Anything you like, e.g. `local_mcp` |
| **Category** | Pick any — `Visualizer` works fine |
| **Club** | Leave empty |
| **Website** | Any valid URL, e.g. `http://localhost` |
| **Application Description** | Anything, e.g. `Local MCP server for Claude` |
| **Authorization Callback Domain** | `localhost` — **this one matters** |

Check the API agreement box and click **Create**.

Strava will immediately prompt you to **Upload an app icon** — this is required before the app can be used. Any image works (even a placeholder). Upload one and continue.

You'll land on your app's **Details** page at [https://www.strava.com/settings/api](https://www.strava.com/settings/api). It shows:

- **Client ID** — visible in plain text (e.g. `235398`)
- **Client Secret** — hidden by default; click **Show** to reveal it
- **Your Access Token / Refresh Token** — ignore these, `strava-mcp auth` handles tokens for you
- **Rate limits** — 100 read requests per 15 minutes, 1,000 daily (plenty for personal use)
- **Number of athletes allowed to connect: 1** — this is fine, the server is for your account only

Copy the **Client ID** and the revealed **Client Secret** — you'll need both in step 3.

### 2. Install

```bash
pip install strava-mcp
```

> Requires Python 3.11+

If you're running from source (for development or to test changes):

```bash
git clone https://github.com/icarobichir/strava-mcp
cd strava-mcp
pip install -e .
```

### 3. Authenticate

```bash
strava-mcp auth
```

Before running, make sure your credentials are available — either exported as environment variables:

```bash
export STRAVA_CLIENT_ID=your_client_id
export STRAVA_CLIENT_SECRET=your_client_secret
```

Or saved in a `.env` file in the project root:

```
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
```

Then run:

```bash
strava-mcp auth
```

This opens your browser, completes the Strava OAuth flow, and stores tokens at `~/.config/strava-mcp/tokens.json`. Tokens are refreshed automatically — you only need to run this once.

### 4. Add to Claude

**Claude Desktop** — edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "strava": {
      "command": "strava-mcp",
      "args": ["serve"]
    }
  }
}
```

**Claude Code** — edit `.claude/settings.json` in your project (or global `~/.claude/settings.json`):

```json
{
  "mcpServers": {
    "strava": {
      "command": "strava-mcp",
      "args": ["serve"]
    }
  }
}
```

Restart Claude after editing the config.

---

## Available tools

| Tool | Description |
|---|---|
| `list_activities` | List activities with optional filters (sport type, date range, limit) |
| `get_activity` | Full detail for a single activity: splits, segments, laps, best efforts |
| `get_athlete_stats` | Aggregate totals per sport — recent (4 weeks) / YTD / all-time |
| `get_athlete` | Profile info: name, location, weight, FTP, measurement preference |
| `get_gear` | Bike or shoe details with total distance logged |

---

## Example prompts

Once connected, try asking Claude:

- *"Show me my last 10 runs with pace and distance"*
- *"How many kilometers did I ride this year vs last year?"*
- *"Build a weekly training summary for the past month"*
- *"What's my longest run ever? What about my fastest 5K effort?"*
- *"Compare my running volume this month vs last month"*
- *"Which shoes have the most mileage on them?"*
- *"Show me my heart rate trends across the last 20 workouts"*

---

## Contributing

PRs are welcome. Some ideas for v0.2:

- **Segments** — `get_starred_segments`, `get_segment_efforts`
- **Streams** — raw GPS, power, cadence time-series data for a given activity
- **Clubs** — club feed and leaderboards
- **Webhook support** — real-time activity sync
- **Cached responses** — avoid hitting rate limits (100 req/15min) during analysis sessions

Please open an issue before starting significant work so we can align on approach.

---

## License

MIT