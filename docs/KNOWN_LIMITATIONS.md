# Known limitations

- **Incomplete exploratory valuation:** the reference run selects ten pairs but cannot report aggregate test return or drawdown. The cause has not been isolated in this packaging task. Missing observations must be diagnosed by security and date; neither deleting troublesome pairs after selection nor replacing missing prices with zeros is an acceptable silent repair.
- **Strict abstention:** zero FDR-qualified selections is a valid negative result; no threshold is relaxed to force trades.
- **Universe selection:** end-2023 membership is used for earlier development history. The test is conditional on that roster.
- **Identity review:** project IDs do not establish an authoritative permanent-ID database. Corporate-action review records are not automatically enforced as verified event restrictions.
- **Execution assumptions:** adjusted prices, scenario costs and borrowing rates are not observed fills or actual borrow availability. Volume screens and portfolio exposure caps are absent.
- **Inference:** data-driven candidate selection and validation tuning limit interpretation of p-values and profitability.
- **Scope:** no financial fundamentals, rolling walk-forward discovery, benchmark attribution, or complete audit has been implemented.
- **Reproduction:** historical downloads can change, and dependencies are not a fully locked cross-platform environment. Recorded checksums describe the original inputs; full price snapshots are not redistributed.

Packaging does not change model selection, trading logic, or the recorded findings.
