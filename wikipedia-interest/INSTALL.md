# Installing `wikipedia-interest` as an Agent Skill

This folder **is** the skill — it is self-contained (`SKILL.md`, `scripts/`, `references/`,
`examples.md`, `requirements.txt`). To install it into an agent, copy this whole folder into that
agent's skills directory under the name `wikipedia-interest`, then restart the agent so it re-scans.

## Prerequisites
- **Python 3.12+**
- **uv** — https://docs.astral.sh/uv/ (`curl -LsSf https://astral.sh/uv/install.sh | sh`), or plain
  `pip` with `requirements.txt`. No project setup is needed: `scripts/wikipop.py` carries PEP 723
  inline dependencies, so `uv run scripts/wikipop.py …` auto-installs them on first use.
- Internet access to the Wikimedia APIs.

## Claude Code
Personal (available in every project):
```bash
mkdir -p ~/.claude/skills
cp -R wikipedia-interest ~/.claude/skills/wikipedia-interest
```
Project-scoped (checked in with a repo) — from that repo's root:
```bash
mkdir -p .claude/skills
cp -R /path/to/wikipedia-interest .claude/skills/wikipedia-interest
```
Restart Claude Code (or start a new session) so it picks up the new skill. It activates
automatically when a request matches the description in `SKILL.md`, or invoke it with
`/wikipedia-interest`.

## Codex CLI
Codex reads skills from `~/.codex/skills/` (personal) or `.codex/skills/` (project); it also
recognizes the cross-agent `~/.agents/skills/` and `.agents/skills/` locations.
```bash
mkdir -p ~/.codex/skills
cp -R wikipedia-interest ~/.codex/skills/wikipedia-interest
```
Restart Codex. Invoke explicitly with `$wikipedia-interest`, or let Codex select it when a request
matches the skill description.

## Verify the install
From inside the installed skill directory:
```bash
uv run scripts/wikipop.py analyze --topic "astronomy" --langs uk --last 2y
```
You should get a JSON object with `metrics` and `confidence`. See `examples.md` for more.

> Note: paths in `SKILL.md` and `examples.md` are relative to this skill directory. When the agent
> runs the CLI, it should run from here (or prefix `scripts/wikipop.py` with this folder's absolute
> path).
