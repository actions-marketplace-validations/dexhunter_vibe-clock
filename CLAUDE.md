# vibe-clock

A CLI tool that tracks AI coding agent usage across Claude Code, Codex, Gemini CLI, and OpenCode.

## Project Structure

- `vibe_clock/` — main package
  - `cli.py` — Click CLI entry point (setup, init, summary, render, workflow, share, push)
  - `config.py` — TOML + env var config loading (`~/.config/vibe-clock/config.toml`)
  - `models.py` — Pydantic v2 models (Session, TokenUsage, AgentStats, etc.)
  - `intervals.py` — The one definition of "active time": union of stretches, never a session span
  - `aggregator.py` — Pure function merging sessions into AgentStats
  - `sanitizer.py` — Strips PII/paths/project names before any remote push
  - `payload.py` — Versioned public wire format; required fields have no defaults on purpose
  - `workflow.py` — The Actions workflow template; the READMEs embed its output verbatim
  - `gh.py` — Optional `gh` CLI integration; never required, never raises
  - `scheduler.py` — launchd / systemd user timer / crontab backends
  - `collectors/` — Agent-specific parsers (claude_code, codex, gemini_cli, opencode)
  - `svg/` — Pure Python SVG renderers (card, heatmap, donut, bars, token_bars, hourly, weekly)
- `action.yml` — GitHub composite action for profile repo integration
- `tests/` — pytest tests for collectors, aggregator, payload, docs, SVG output

## Key Commands

```bash
vibe-clock setup           # Full onboarding: agents, Gist, secret, workflow, schedule
vibe-clock summary         # Terminal stats
vibe-clock render          # Generate SVG files
vibe-clock workflow        # Print the Actions workflow to install
vibe-clock push --dry-run  # Preview exactly what would be pushed
vibe-clock push            # Push sanitized stats to GitHub Gist
```

## Development

```bash
uv run pytest -q
uvx ruff check --fix .
```

See CONTRIBUTING.md. CI runs both on 3.10-3.13.

## Privacy Rules

- NEVER push file paths, project names, message content, or PII
- `sanitizer.py` must always run before any network I/O
- Use `--dry-run` to inspect output before pushing
- The `_validate_no_pii` function checks for username leaks using word-boundary regex

## Style

- Python 3.10+, Pydantic v2, Click for CLI, Rich for terminal output
- SVGs use `Arial, Helvetica, sans-serif` (GitHub-compatible)
- `httpx` respects the system proxy (`trust_env` was removed in 311952d)

## Failure Rules

- Never render a plausible wrong number. Missing data must fail with a message
  naming the fix — an unknown theme, an unknown chart type, a payload from an
  older producer, and a chart whose data was never shared all exit non-zero.
- Never guess remote state. `profile_repo` is confirmed, not inferred; the
  workflow filename is configurable; `trigger_workflow` is opt-in because
  dispatching needs the far broader `repo` scope.
- Docs that describe behaviour must be generated from it, or tested against it.
