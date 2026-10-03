# Repository hygiene

- Keep only concise research conclusions in Git. Generate experiments in ignored `data/research/` or `evidence/`; do not commit raw datasets, images, telemetry, models, arrays, or copied dependencies.
- Existing text-only `evidence/**/report.html` pages are archived conclusions kept for application links. Do not replace them with generated visual reports. Use new Markdown conclusions for future research.
- Before committing, run `python tools/check_repo_artifacts.py` and inspect the staged diff. Enable the hook in a fresh clone with `git config core.hooksPath .githooks`.
- Five small crops under `tests/fixtures/vegetation/` are intentional regression inputs. Keep fixtures minimal and explicitly justified; they are not a place to store research corpora.
