# Data and reproduction

`universe/` contains the project's constructed 904-security roster and review records. These are research outputs with uncertainty flags, not an official index constituent feed. Source URLs and original retrieval metadata are listed in `../docs/source_manifest.json`; reconstruction decisions appear in `../docs/universe_methodology.md`.

Raw/processed market prices, original third-party snapshots and the encoded all-in-one data archive are excluded from this public package. No blanket redistribution permission for provider data is asserted. Follow source terms when acquiring or sharing data.

## Use previously prepared data

Copy your local `adjusted_prices.parquet` into `data/processed/`. The matrix must have a unique daily DatetimeIndex and columns matching `universe_security_id`. Preserve missing values. Then run `python run.py model` from the repository root.

## Download and prepare again

```bat
python run.py download
python run.py prepare --formation-start 2021-01-01 --formation-end 2023-12-29 --test-start 2024-01-01 --test-end 2025-12-31
```

Acquisition may have held or failed securities requiring review. Preparation should not silently bypass incomplete-run checks. V2 recalculates its own development eligibility from the full price matrix; preparation's later formation roster does not choose the earlier training universe.

The downloader's default history is 2000–2025. Network access and provider availability are required. New downloads need not exactly match the original recorded run.

To rebuild the roster, supply the original snapshots named by the source manifest under `data/sources/`, then use `python run.py universe --offline`. The frozen constructed roster is already supplied; rebuilding it is optional. `scripts/build_report.mjs` is an archived optional workbook/report helper with the original environment’s `@oai/artifact-tool` JavaScript dependency (not supplied here), not part of the Python quick start.
