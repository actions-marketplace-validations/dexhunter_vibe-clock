# Contributing to vibe-clock

Thanks for looking. Issues and pull requests are welcome.

## Getting set up

```bash
git clone https://github.com/dexhunter/vibe-clock
cd vibe-clock
uv run pytest -q          # uv resolves the environment for you; no venv step needed
```

Before opening a PR:

```bash
uvx ruff check --fix .
uv run pytest -q
```

CI runs exactly these on Python 3.10 through 3.13.

To try your working copy against your own data without installing it:

```bash
uv run vibe-clock summary
uv run vibe-clock push --dry-run     # never sends anything
```

## Adding an agent collector

This is the most useful contribution and the smallest. A collector reads whatever an agent writes to disk and returns `Session` objects; everything downstream — aggregation, sanitizing, charts — already works.

1. Add the agent's data directory to `PathsConfig` in `vibe_clock/config.py`.
2. Write `vibe_clock/collectors/<agent>.py`. Return a `list[Session]`; build each session's `active_stretches` from the timestamps you read, rather than from its first and last timestamp. `vibe_clock/intervals.py` explains why: a session is often a process left open for days, so its span is not time spent.
3. Register it in `vibe_clock/collectors/__init__.py` and add the name to `_KNOWN_AGENTS` in `vibe_clock/sanitizer.py` — an agent not in that set is stripped from the public payload.
4. Add a test in `tests/test_collectors.py` using a synthetic log file in `tmp_path`.

## Things to know before you change something

**The public payload is a versioned wire format.** `vibe_clock/payload.py` is the contract between the machine that runs `push` and the Action that renders. Any change to the emitted key set must bump `SCHEMA_VERSION`. Required fields have no defaults on purpose: a payload from an older producer must fail loudly rather than render a plausible wrong number.

**Never let anything into the payload that isn't in the allowlist.** `sanitizer.py` builds the public view field by field, and `_validate_no_pii` re-checks the finished JSON. If you add a field, decide whether it is unconditional or belongs behind a `share_*` flag, and add a test either way.

**The workflow YAML lives in `vibe_clock/workflow.py`, not in the READMEs.** `tests/test_docs.py` asserts every doc embeds the generated output verbatim. Edit the template, then re-run the substitution — do not hand-edit a YAML block in a README.

**Use synthetic data in tests.** No real usage data, gist IDs, or personal paths in fixtures.

## Translations

`README.md` is the source. `README.zh-CN.md`, `README.ja.md`, and `README.es.md` follow the same section order with identical code blocks, so a structural change has to be made in all four. `tests/test_docs.py` enforces the parts that can be checked mechanically. Corrections to any translation are very welcome.

## Releases

Releases are cut by the maintainer through the **Create Release** workflow, which runs `scripts/bump_version.py` and tags. Tagging triggers publication to PyPI and the Homebrew tap.

Two parts of this are maintainer-only by construction and cannot run from a fork: PyPI trusted publishing, and the push to `dexhunter/homebrew-tap`, which needs a secret. The macOS binary is built on `macos-latest` and is therefore **arm64 only** — there is no Intel or Linux binary, which is why the READMEs point everyone at PyPI first. If you want to change the release process, open an issue first; a PR cannot test it.

`scripts/bump_version.py` is owner-agnostic, so it works in a fork: it rewrites `ACTION_REF` in `vibe_clock/workflow.py` and any action reference in the docs, whatever the owner is.
