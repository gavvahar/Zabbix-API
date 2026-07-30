# Contributing

## Getting started

Follow the [Setup](README.md#setup) and [Development](README.md#development) sections in the README to install dependencies and get `tox` working locally.

## Code style

- No classes — this codebase is functions-only. `tox -e no-classes-check` fails the build if one is added.
- Combine all top-level bare `import x` statements in a file onto a single line (`import x, y`). `tox -e combined-imports-check` enforces this; run it with `--fix` via `tox -e format` to auto-combine.
- Add a one-line docstring to every function.
- Formatting (Ruff for Python, Prettier for JSON/YAML/Markdown, Taplo for TOML) is enforced, not a matter of preference — don't hand-format around it.

## Before opening a PR

Run the full local suite, which formats in place and then runs the same checks CI does:

```bash
tox -e all
```

If you only want to check without modifying files (what CI runs):

```bash
tox -e github
```

Fix anything it reports, then commit the results.

## Commit messages

Keep them short and imperative, describing the "what": e.g. `Add hostgroup_id function for looking up host group ids by name`.

## Secrets

Never commit `.env` or a real API token. `.env` is gitignored — use `.env.example` as the template for any new environment variables you add.

## Review

This repo has a single `CODEOWNERS` entry, so all PRs are automatically routed for review.
