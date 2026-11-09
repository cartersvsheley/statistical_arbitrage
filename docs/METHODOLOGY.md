# Methodology

Development defaults to 2021–2022; validation is 2023; refit ends December 29, 2023; test is 2024–2025. Development eligibility is recomputed from development data rather than imported from the later formation roster.

Daily stock returns are centered and scaled over training observations. PCA uses complete shared return dates. Factor selection uses circular-shift parallel analysis with 100 replicates; stock features are eigenvectors scaled by square roots of eigenvalues. Ward clustering uses Euclidean distances between these exposures, not raw daily returns as clustering features. Forty clusters and up to ten nearest candidate pairs per cluster are considered.

Two-direction Engle–Granger tests use log adjusted prices, with a Bonferroni correction for orientation and BH correction across screened candidates. Residual ADF results are descriptive; candidate selection complicates nominal inferential guarantees. Rolling hedge stability and mean-reversion diagnostics supplement these tests.

Validation compares entry thresholds 1.5, 2.0, and 2.5. Ranking combines statistical (15%), stability (15%), reversion(15%), economic(25%) and validation scores (30%). Execution feasibility is unobserved and has zero ranking weight. Candidates need positive validation net return, at least two trades and positive hedge elasticity. Only validated pairs rediscovered in the refit may be selected. Strict selection additionally requires refit q <= .05. Both modes select at most ten pairs.

Signals formed at close t execute at the next session's adjusted close. Entry gross notional is one; dollar weights are proportional to [direction, -direction * beta]. Commission, slippage, and calendar-day borrow are charged. Fixed equal sleeves use additive P&L on initial capital. No cash interest or long financing is modeled. Adjusted units are synthetic total-return proxies, not executable share fills.

Missing prices invalidate valuation under the current implementation; the portfolio remains unavailable after the first missing sleeve valuation. Current code also invalidates a pair when missing prices occur while flat. Diagnosing and revising that policy is future work, not part of this packaging release.

Fundamental features are an intended extension and are absent from the current pipeline. The fixed end-2023 roster introduces earlier selection bias. Repeatedly comparing histories using the same test period would make it an exploratory test, not an untouched holdout.
