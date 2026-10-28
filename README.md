# UEFN Landscape Automation

Reusable Python tools for generating and validating Fortnite/UEFN landscape
heightmaps. The repository is intentionally project-agnostic; project-specific
UEFN wiring remains in the target project.

## Layout

- `src/` — reusable generators and UEFN API probes
- `assets/input/` — required source heightmaps
- `docs/` — generated layout and tuning notes

The current generator is `src/generate_landscape_v5.py`. It accepts an input
16-bit grayscale PNG and an output directory, preserving its protected regions
according to the generator's built-in rules.

