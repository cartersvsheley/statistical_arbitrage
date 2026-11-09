# Validation record

Packaging checks performed November 9, 2026:

- Seven existing synthetic accounting/timing tests passed through the new root launcher.
- Every code cell in the lightweight demo notebook executed against included reference results; saved output contains no execution errors.
- Notebook schema, Python syntax, and relative Markdown links validated.
- Source/results were checked for original machine paths; manifests use portable input labels.
- ZIP excludes raw/processed prices, encoded data archives, caches, environments, and private local experiment folders.

The real-data model was not rerun during packaging. The reference outputs are from the earlier completed default run: zero strict selections, ten exploratory selections, incomplete aggregate exploratory valuations. Packaging does not resolve that limitation or imply economic validity.

Package versions used for the packaging checks are in `packaging_environment.json`; these are not a reconstruction of the original model execution environment. The test run emitted a third-party pytest-plugin deprecation warning and passed all seven tests.
