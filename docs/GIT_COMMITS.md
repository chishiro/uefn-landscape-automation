# Recommended Git commit sequence

Recommended when applying these files to your current (private) repository. The ZIP delivered by this task does not contain a `.git` folder or committed history. **Run these commands in your own repository after reviewing the diff.** They do not publish to GitHub.

## Recommended commit messages

1. `fix: add validated PNG handling and exact shoreline distances`
2. `feat: add config-driven seabed generation and validation CLI`
3. `test: cover distance, protection, and CLI regressions`
4. `docs: document UEFN workflow and AI agent usage`
5. `chore: add BSD-2-Clause license and CI`

## How to apply (commands to paste into Terminal)

First check the branch and compare your current code. **Do not blindly delete your existing repository or its `.git` directory.** Move the files from the supplied `uefn-landscape-automation-public.zip` into the existing repository, preserving its `.git` folder. Keep original island-specific assets and legacy source files in private storage only.

```bash
git switch -c feat/generic-uefn-landscape-tool
git status --short
git diff --stat
```

The public release omits old project-bound source/asset paths. If those old files are still tracked in your existing repository, `git add -u` would stage deletions **along with any unrelated work**, so use only explicit paths after checking them; see the migration section below.

**Commit 1: PNG and Euclidean distance primitives**

```bash
git add src/heightmap_png.py src/shore_distance.py
git diff --cached --stat
git commit -m "fix: add validated PNG handling and exact shoreline distances"
```

**Commit 2: new generic CLI, demo data generation, and JSON example**

```bash
git add src/landscape_tool.py src/landscape_api_probe.py examples/demo_config.json scripts/make_demo_heightmap.py pyproject.toml
git diff --cached --stat
git commit -m "feat: add config-driven seabed generation and validation CLI"
```

**Commit 3: automated tests**

```bash
git add tests/
git diff --cached --stat
git commit -m "test: cover distance, protection, and CLI regressions"
```

**Commit 4: README + AI-agent documentation**

```bash
git add README.md AGENTS.md CLAUDE.md docs/CONFIGURATION.md docs/GIT_COMMITS.md docs/images/
git diff --cached --stat
git commit -m "docs: document UEFN workflow and AI agent usage"
```

**Commit 5: license and CI**

Before this commit, update `<COPYRIGHT HOLDER>` in `LICENSE` with the actual owner name and confirm redistribution rights:

```bash
git add LICENSE .gitignore .github/workflows/tests.yml .python-version
git diff --cached --stat
git commit -m "chore: add BSD-2-Clause license and CI"
```

**If migrating an existing Git repository**, the old project-specific tracked files need a separate, carefully reviewed cleanup commit after you have archived any private data. Example *only if those exact old paths are tracked and backed up*:

```bash
# Inspect exact tracked paths first.
git ls-files assets/input docs src/generate_landscape_v5.py

# Do not run until you have a safe, private copy of the removed data.
# git rm --cached assets/input/base_heightmap_505.png
# git rm src/generate_landscape_v5.py docs/SF_Island_Layout_V5.md docs/SF_Ocean_Tuning_V5.md
# git commit -m "refactor: remove project-specific legacy generator and assets from public tree"
```

`git rm --cached` removes a file **from Git tracking**, while keeping the local file. `git rm` removes it from both tracking and the working tree: back up the files first or use `git rm --cached` if the local copy must remain. To avoid accidental publishing, run `git ls-files` and audit the staged diff before pushing.

Finish by running the tests, checking the exact staged/tracked files and reviewing the commit list:

```bash
python -m pytest
git status --short
git ls-files | grep -E 'assets/input|assets/private|private/|SF_|\.umap|\.uasset' || true
git log --oneline -6
```

On Windows PowerShell, the last `grep` pipeline can be replaced with:

```powershell
git ls-files | Select-String 'assets/input|assets/private|private/|SF_|\.umap|\.uasset'
```

Only when you approve the changes, push with your normal GitHub workflow, for example `git push -u origin feat/generic-uefn-landscape-tool`. **A Git push is never performed by this tool or this document.**

### Note on commit splitting

The suggested grouping avoids `git add -p` because the implementation is separated into different files. When you modify a single file for several unrelated reasons, use `git add -p <file>` to stage changes hunk by hunk, checking `git diff --cached` before committing.
