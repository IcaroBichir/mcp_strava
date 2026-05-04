# Blog Series: Building a Strava MCP Server

**Series title:** *"Wiring Claude to My Running Shoes"*
**Platform:** icarobichir.com (Tech pillar)
**Format:** 5 chapters, published as the project evolves
**Tone:** Engineer who codes as a side interest — practical, honest, no hype

---

## Chapter 1 — What is MCP and why I wired it to my running shoes

**Publish:** Before or at launch (introduction chapter)
**Hook:** "I wanted to ask Claude 'how did my training go this month?' and actually get a real answer."

Key beats:
- What the Model Context Protocol is and why it matters (tools vs. context)
- The problem: Claude is great at analysis but blind to your personal data
- Why local-first: your health data shouldn't live on someone's server
- Quick demo of what the finished thing looks like — a real conversation with Claude

Ends with: link to repo, "follow along for the build."

---

## Chapter 2 — Strava OAuth in ~50 lines of Python

**Publish:** Week 2
**Hook:** "OAuth is always the part nobody wants to explain. Here's the whole thing."

Key beats:
- How Strava's OAuth2 flow works (authorization_code grant)
- The local HTTP server trick: spin up `localhost:8765` to catch the redirect
- Token storage and auto-refresh (access tokens expire every 6 hours)
- What scopes you actually need (`activity:read_all`, `profile:read_all`)
- Walk through `auth.py` line by line

Code-heavy chapter. Include the actual file. Demystify it.

---

## Chapter 3 — Designing the tools: what data does Claude actually need?

**Publish:** Week 3
**Hook:** "I started with 12 tools. I shipped 5. Here's what I cut and why."

Key beats:
- What MCP tools are vs. resources vs. prompts (and why tools are the right choice here)
- The question I asked myself for every tool: "what would I want to ask Claude about this?"
- Walking through each of the 5 tools and the design decisions
- The unit problem: meters and seconds vs. km and min/km — and why I left conversion to Claude
- Rate limits: Strava gives you 200 requests per 15 minutes, 2,000 per day

Light on code, heavy on reasoning. Good chapter for non-engineers.

---

## Chapter 4 — Claude as my training coach

**Publish:** Week 4 (after using it for a few weeks)
**Hook:** "I've been using this for 3 weeks. Here's what I actually asked and what I learned."

Key beats:
- Real conversation screenshots with Claude analyzing training data
- The prompt patterns that work well (ask for tables, ask for trends, ask for comparisons)
- Something Claude found that surprised me
- Limitations: Claude can't push data back to Strava, no real-time tracking
- What I'd want next (segments, power data, GPS streams)

Authentic, personal chapter. Include actual Claude responses.

---

## Chapter 5 — Going open source: what the community added

**Publish:** 4–8 weeks after launch (retrospective)
**Hook:** "I shipped it, wrote about it, and then something unexpected happened."

Key beats:
- How many stars / forks (real numbers, no spin)
- First PR: what someone added and whether I merged it
- What I learned about writing a README for contributors
- Features I wouldn't have built myself
- What open source is actually like at the "small project" scale

Written after the fact. Honest retrospective, not a victory lap.

---

## Jekyll front matter template

```yaml
---
layout: post
title: "Wiring Claude to My Running Shoes, Part N: [Chapter Title]"
date: YYYY-MM-DD
category: tech
tags: [mcp, strava, python, claude, ai]
description: "[One sentence for SEO / social preview]"
---
```

Each post lives in `_posts/` in the infocrazy repo.
