# PCA factor exposures, Ward clusters, and pair screen

## Run results

- 821 eligible equities keyed by `universe_security_id`.
- Formation window: 2021-01-04 through 2023-12-29.
- 753 input dates; one shared initial return date was incomplete because no prior formation price existed. It was omitted, leaving 752 complete observations.
- Standardized each security’s returns over the formation window using its sample mean and sample standard deviation. No return was imputed.
- Parallel analysis retained 16 PCs, explaining 57.5% of standardized-return variance.
- Ward clustering used Euclidean distances between the 16-dimensional stock exposure vectors, producing 40 clusters.
- The nearest 10 within-cluster stock pairs were screened in each cluster, yielding 396 unique tests.
- 27 pairs had direction-adjusted Engle–Granger p-values below 0.05 before across-pair adjustment. None passed Benjamini–Hochberg FDR at 5%; zero pairs pass the initial exploratory screen.

## Leading nominal screens

| Ticker pair | Direction-adjusted p | BH q | AR(1) phi | Half-life (sessions) |
|---|---:|---:|---:|---:|
| EG / ACGL | 0.0008954 | 0.3546 | 0.9429 | 11.8 |
| NVT / WAB | 0.002321 | 0.4596 | 0.9526 | 14.3 |
| CDW / APH | 0.004512 | 0.5175 | 0.9671 | 20.7 |
| BRX / REG | 0.005335 | 0.5175 | 0.9529 | 14.4 |
| SON / ATR | 0.007916 | 0.5175 | 0.9563 | 15.5 |

These are exploratory formation-period rankings, not validated trading pairs. The leading nominal pair still has q = 0.355. Candidate pairs were selected using the same formation sample, so standard p-values do not account for all selection steps. The residual ADF p-value column is descriptive only; Engle–Granger p-values carry the cointegration test.

## Modeling choices and limits

- Factor count: 100 independently circular-shifted return panels, 95th-percentile eigenvalue threshold, seed 20231021. Circular shifts preserve each stock’s observed sequence up to wraparound while disrupting cross-stock alignment. This is an initial parallel-analysis screen; factor-count sensitivity is still needed.
- Exposure: correlation of each standardized stock return with a unit-variance PC score, calculated as the PCA loading times the square root of its eigenvalue.
- Ward candidates: Ward’s method is defined for Euclidean geometry. Candidate restriction to the nearest 10 pairs in each of 40 clusters is a configurable discovery rule, not a universal optimum.
- Cointegration: Engle–Granger log adjusted price levels with a constant, tested in both regression directions; the smaller p-value was multiplied by two and capped at one, then BH-adjusted across 396 screened pairs.
- Mean-reversion summary: AR(1) coefficient and implied half-life of the Engle–Granger residual in NYSE sessions. Positive stable AR(1) alone does not establish an economically tradable spread.
- Fundamentals have not been included. When added, their cross-sectional scaling parameters must be fit on formation data only and kept separate from return standardization.
- The universe was selected by December 2023 membership. Formation results inherit earlier selection bias; 2024–2025 is conditional evaluation of this end-2023 roster, not a survivorship-free historical universe.
- No costs, borrow availability, hedge rebalancing, execution, or profitability are tested.

## Files

- `standardized_formation_returns.parquet`: 752 x 821 z-scored return matrix.
- `pca_factor_returns.parquet`: 752 x 16 standardized PC factor time series.
- `pca_factor_exposures.csv`: 821 x 16 stock exposures, keyed by historical security ID.
- `pca_explained_variance.csv`: retained factor eigenvalues and variance shares.
- `ward_cluster_assignments.csv`: one cluster per eligible security.
- `candidate_pairs_and_tests.csv`: 396 pair tests, p/q-values, AR(1) and half-life statistics.
- `excluded_incomplete_dates.csv`: dates omitted before PCA.
- `model_manifest.json`: parameters, input checksums, package versions, dimensions and limitations.

To reproduce, install `pandas numpy pyarrow scikit-learn scipy statsmodels`, then run `pca_ward_pairs.py` with the three input paths. Defaults select 80% variance only when `--factor-selection variance` is passed; default uses parallel analysis.

## Correction in version 1.0.1

The ADF call now detects support for the newer result-object argument and handles legacy tuple returns. The log-price regression now correctly assigns the intercept before the hedge ratio in the [constant, predictor] design. This replaces the previous erroneous hedge-ratio, residual ADF, AR(1), and half-life statistics. PCA outputs, Ward clusters, candidate selection, and Engle–Granger p/q-values were verified byte-for-byte or numerically unchanged. The 396-pair screen still has zero BH-significant pairs.
