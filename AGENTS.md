# Instructions for coding agents (Codex, Claude Code, and others)

## Purpose

This repository is a **project-agnostic, offline 16-bit PNG heightmap processor** for UEFN Landscape. The current implemented operation is `deepen_seabed`. Never claim it can directly import/edit/launch UEFN, modify live Landscape proxies, place actors, or alter Ocean materials.

## Safety and data boundaries

1. **Never overwrite, modify, rename, delete, or commit the source heightmap** or a real island's private JSON configuration. Public examples must remain synthetic.
2. A configuration must have a known `row_zero_world_y`, measured XY/Z transform, a defensible sea-level sample, and explicit protection geometry. Never infer these as verified from an arbitrary PNG.
3. If `orientation_checks` is empty, report that the orientation is **configured but not independently verified**. If control points also fit the opposite direction, label the result **ambiguous**. Do not fabricate error=0 or say "verified".
4. Never reimport into UEFN or change editor content automatically. Ask the human to inspect the generated files before any manual import.
5. Do not remove/disable protection or edge validation just to make a job pass; report the failure and request verified parameters.
6. Respect `LICENSE` and keep any `assets/input/`, `assets/private/`, `private/`, `outputs/`, game files and proprietary data out of public commits.

## Python version and execution context

Use **Python 3.11.x** (reference: 3.11.8). Check `python --version` before executing commands. This tool runs as an **external CLI**, not inside the UEFN Python interpreter. Do not represent compatibility with Python 3.11 as proof of an implemented UEFN Python API integration.

## Preferred workflow

1. Read `README.md`, `docs/CONFIGURATION.md` and the intended JSON config. Confirm its scope and units.
2. Run tests before changing code: `python -m pytest` (install pytest if needed).
3. Run `python src/landscape_tool.py generate --input <INPUT> --config <CONFIG> --dry-run`.
4. Inspect JSON output; if valid, use a **new** output directory for `generate` (never use `--force` as your default).
5. Read `<OUT>/report.json` and `<OUT>/report.md`, then run `validate` with `--candidate <OUT>/heightmap.png`.
6. Explain `changed_samples`, `protected_changed_samples`, `land_changed_samples`, `raised_samples`, `edges_below_sea`, `expected_mismatched_samples` (from `validate`), and `orientation.status`. Refer the UEFN re-import step to the human.

## CLI contracts

- `generate`: `--input`, `--config`, `--output-dir` (or `--dry-run`), optional `--force`
- `validate`: `--input`, `--candidate`, `--config`
- Exit status `0`: passed. Exit status `1`: failed; do not import failed output.
- Public input examples are generated from `scripts/make_demo_heightmap.py`, not real UEFN assets.
- Do not write Markdown describing features that are not implemented.

## Code changes

Core runtime is Python standard library. Do not add dependencies without explaining why. When editing distance mathematics, compare against brute-force Euclidean distances on small grids, including non-square pixels. Add regression tests for any discovered bug. Do not mark an operation verified based solely on self-generated samples.
