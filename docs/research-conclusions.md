# Research conclusions and artifact policy

On 2026-10-03, generated research datasets, crops, screenshots, model weights,
feature arrays, raw predictions and telemetry were removed from the working tree
and Git history. Text-only conclusions remain at the existing `evidence/` report
URLs. References inside these historical conclusions to raw files or visual
comparisons are no longer available. These are recorded observations, not a claim
that the removed experiments can still be replayed from this repository.

## Latest decisions

- **Localized heads and limited encoder adaptation:** automatic suppression did
  not qualify. The agreement pilot caught 21/96 contours, including 2/33 on the
  1924 edition, below the respective gates. Forty fresh geographically separated
  targets remained unscored and unreviewed. Production detection was unchanged.
  [Conclusion](../evidence/local-mark-learning/report.html).
- **Alternative noise mechanisms:** better features improved development contour
  removal from 16/96 to 47/96. On 48 unseen targets, the selected method removed
  9/18 contours but also flagged two vegetation targets and one uncertain mark.
  It was rejected for automatic hiding.
  [Conclusion](../evidence/noise-methods-survey/report.html).
- **Off-the-shelf model trials:** none of the five tested candidates demonstrated
  a reliable replacement for the discovery pipeline. CRAFT and YOLOE supplied
  complementary fragment proposals; these observations did not establish broad
  production coverage. [Conclusion](../evidence/model-trials/conclusions.md).

## Future work

Keep source code and concise findings in Git. Generate disposable research
outputs in ignored local storage, and remove them when finished. Preserve only
decisions, limitations, provenance and small aggregate tables. The five small
vegetation regression fixtures are deliberately retained under `tests/fixtures/`.

The repository commit hook rejects generated model/array files, non-text evidence,
embedded media, files above 1 MiB and staged additions above 10 MiB. Fresh clones
must enable it with `git config core.hooksPath .githooks`. The global Codex
instructions apply the same research-storage preference across all projects.

History was rewritten: existing clones must not merge or push old history back.
Save unrelated local work and use a fresh clone, or deliberately realign the local
branch to the rewritten remote before continuing.
