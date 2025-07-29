# Planned Changes for Make-Only Release Workflow

This document tracks the scope of the *make-only-release* effort on branch `feature/make-only-release`.

## Background
Today vibectl splits its packaging and release logic between:
* `flake.nix` – a `pypi-dist` helper plus a large `shellHook` that runs `pip install …` on entry.
* `Makefile` – a parallel set of `pypi-build / pypi-test / pypi-upload` targets that assume a traditional virtualenv.

This duplication has started to break (e.g. `make pypi-build` fails after the uv switch) and creates cognitive overhead.

## Goals
1. **Single orchestration layer** – All build/lint/test/release verbs should be exposed as GNU Make targets.
2. **Environment agnostic** – Contributors can choose Nix (`nix develop`) *or* uv/virtualenv; Make targets behave identically in both.
3. **No hidden installs** – `flake.nix` must stop mutating `.venv` from its `shellHook`.
4. **CI simplification** – GitHub Actions should call one Make target (`make ci-check`) instead of reproducing each step.
5. **Optional future migration to Poe the Poet** – Keep the Makefile thin so it can wrap `poe` tasks later.

## Deliverables (Phase 1)
- [x] Delete `pypi-dist` helper from `flake.nix` and remove the pip-install section of the `shellHook`.
- [x] Refactor the Makefile:
  - [x] New discrete targets: `lint`, `typecheck`, `test`, `test-coverage`, `wheel`, `release`, `ci-check`.
  - [ ] Pull version/tag logic into `scripts/version.py` (shared by Make & any other tooling). *(next)*
- [x] Update `.github/workflows/tests.yml` to run `make ci-check` instead of the manual steps.
- [ ] Confirm `make release` produces wheel+sdist and tags **in dry-run**. *(pending final validation)*

**Status:** CI passes locally with `make ci-check` (~2200 tests in ≈14 s, dmypy-enabled). Next immediate step is to extract version logic into a reusable `scripts/version.py` and wire `wheel`/`release` targets to use it.

## Deliverables (Phase 2 – nice to have)
- [ ] Introduce Poe the Poet task definitions in `pyproject.toml`.
- [ ] Replace Makefile bodies with `poe <task>` wrappers.
- [ ] Allow CI to call `poe quality` directly once stable.
- [ ] **Investigate faster static type checking alternatives** – explore `dmypy` optimisations or tools like `pyright`/`mypy-protobuf` for improved CI speed.

## Timeline / Ownership
| Task | Owner | Target date |
|------|-------|-------------|
| Phase 1 refactor | core | T + 1–2 days |
| PR review & merge | reviewers | T + 3 days |
| Phase 2 exploration | volunteer | when ready |

---
*Last updated: <2025-07-29>*
