# AI collaboration

This project was developed through an iterative conversation with ChatGPT. AI assistance was substantial and is part of what this portfolio project demonstrates.

## Project-owner direction

The owner requested a public-data research workflow, a historical security universe, PCA exposures followed by Ward clustering, explicit development/test periods, configurable longer histories, and separate strict and exploratory outcomes. The owner ran code locally and supplied installation errors and tracebacks to guide troubleshooting.

## AI assistance

ChatGPT generated and revised acquisition, preparation, modeling, accounting, tests, notebooks, and documentation. It helped diagnose command-line requirements, the statsmodels ADF API mismatch, an intercept/hedge-ratio assignment error, output-directory collisions, and Python environment/kernel mismatches.

## Validation actually performed

Seven synthetic tests passed, and the assembled notebook completed an end-to-end run on the embedded historical data. The run selected zero strict and ten exploratory pairs, with incomplete exploratory valuations. Packaging checks are recorded in `docs/VALIDATION.md`.

These checks are not a claim of independent financial validation. No claim is made that the owner manually verified every generated line, that all data identities are resolved, or that the strategy is profitable. Known gaps remain visible in `docs/KNOWN_LIMITATIONS.md`.

## Learning demonstrated

The work connects reproducible data preparation, dimension reduction, clustering, multiple-testing awareness, chronological evaluation, and software debugging. It also illustrates why generated code and plausible outputs require inspection: execution success alone does not make a backtest economically valid.
