# Contributing

[#contributing](#contributing)

Thanks for considering a contribution to this template. Contributions here should improve the **shared scaffold** — the parts every fork inherits — not add domain-specific logic for one vertical.

## Before you start

Ask: *"Would this help every fork of this template, or just mine?"*

- **Every fork** (fix a bug in the auth middleware, improve the retrieve/generate flow, add a missing error code, improve a folder README) → belongs here.
- **Just mine** (a new router for contract-specific fields, a vertical's custom system prompt) → belongs in your fork, not this template.

## Setup

```bash
make setup   # uv sync --locked + pre-commit install
```

Pre-commit will now run automatically on every commit. Don't skip it with `--no-verify` — if a hook is genuinely wrong for a legitimate change, fix the hook, don't bypass it.

## Making a change

1. Branch from `main`.
2. Make your change, keeping to the conventions in `CLAUDE.md` §4 (error handling pattern, router/schema structure, config-via-`args`, index naming).
3. Add or update the relevant folder `README.md` if you changed what that folder does.
4. Run `make test` and `make pre_commit` before opening a PR.
5. Write commit messages in Conventional Commits + gitmoji format (enforced by commitizen) — e.g. `✨ feat: add retry to Bedrock retrieve call`.

## Pull requests

- Keep PRs scoped to one change. A PR that both fixes a bug and adds a feature is harder to review and revert.
- Describe *why*, not just *what* — especially for anything touching the auth middleware or the Bedrock system prompt, since those are load-bearing for correctness/security.
- If your change affects the checklist in `CLAUDE.md` §6 (how to fork this template for a new vertical), update that checklist in the same PR.

## Reporting bugs

Open an issue with:

- What you expected vs. what happened
- Whether it's specific to one auth mode (local JWT vs. Azure AD SSO) or reproducible in both
- Relevant `error_code` from the response, if applicable

## Code of conduct

Be direct, be kind, assume good faith. Disagreements about architecture are fine and expected — keep them about the code.
