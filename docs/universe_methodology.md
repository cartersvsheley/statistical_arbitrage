# Historical equity universe — December 29, 2023

## Result and evidence standard

The fixed roster contains **904 securities: 503 S&P 500 and 401 S&P MidCap 400**. This is a best-supported public-data reconstruction, **not a certified complete official S&P constituent file**. The S&P 500 is corroborated against a same-date archived fund portfolio. The MidCap list has a complete candidate roster but only partial independent primary-source verification. No constituents were selected using current membership or price availability.

Retrieval date: **October 20, 2026, America/Denver** (some downloads occurred October 21 UTC). Target: US market close December 29, 2023. The project’s earlier fixed-universe plan for 2024–2025 is preserved. The roster is not a rolling point-in-time universe for earlier training periods.

## Prior project work incorporated

Available project conversation context was reviewed: public data only; fixed 2023-12-29 universe; prior pitindex 0.2.1 installation; stale-data warning; update failure caused by the Windows `scripts` namespace collision. The prior update call was never treated as successful. This implementation bypasses package installation and update entirely. Retrieved context is a summary, not an assertion that every historical chat transcript was accessible. No machine learning, price downloads, cointegration tests, or backtests were run.

## Construction

1. Read the pinned `riazarbi/sp500-scraper` Wikipedia snapshot dated 2023-12-29. Assert 503 unique security tickers and the exact observation date. Retain its historical company names, sectors and CIKs.
2. Read that repository’s archived IVV holdings dated 2023-12-29. Keep only the 503 Equity rows for corroboration and identifiers. Exclude four non-equity portfolio rows only from this proxy comparison, not from an index roster. Explicitly map provider spellings BRKB to BRK.B and BFB to BF.B. The resulting ticker sets match exactly. IVV holdings are fund holdings, not official constituent records; the two files share an archive maintainer but have different underlying providers. Verify names manually for punctuation aliases; do not collapse share classes.
3. Read the January 2024 Kiwix mirror of Wikipedia revision **1193645510**. The 401-row table already reflects the January 2 and January 5 changes. The revision timestamp itself was not independently retrieved because the Wikipedia API returned HTTP 403. Do not interpret the archive month as an exact capture date.
4. Reverse the two boundary substitutions: remove PSTG and restore PDCO; remove ALTM and restore VYX. S&P’s January 2 announcement places PSTG/PDCO at the January 5 open. S&P’s December 19 announcement places LTHM/VYX at the January 2 open and describes the later ALTM merger name. The mirror’s ALTM label for the January 2 addition is anachronistic, but neither ALTM nor LTHM is included on December 29. Effective date controls inclusion, not announcement date. PDCO and VYX names and sectors come from those primary releases.
5. Independently execute the pinned pitindex seed-and-event reconstruction through the target date as a diagnostic. The MidCap ticker set matches all 401 records. This is **not fully independent corroboration**, because pitindex also derives from Wikipedia. S&P’s December 18 rebalance release verifies selected additions, deletions and sectors near the target date.
6. The S&P 500 pitindex reconstruction has 504 rows, including BLL, FISV and VMRK absent from the dated 503-row roster, and lacks BALL and FI. Primary Ball and Fiserv releases support BALL and FI. VMRK remains an unsupported upstream extra; it is preserved in the raw source and discrepancy report, not invented as a constituent. Never repair a universe merely to achieve an expected count.
7. Combine security rows. No issuer-name or CIK deduplication. Preserve GOOG/GOOGL, FOX/FOXA, NWS/NWSA and UA/UAA. There are no cross-index ticker overlaps. The count exceeds 900 because these four companies have two included share classes.

## Identifier and sector policy

`universe_security_id` is a locally assigned key for this frozen roster, not a vendor permanent identifier. Historical ticker is never overwritten by a successor. CIK identifies an SEC filer, not a share class or an immutable security. CUSIP, ISIN and SEDOL identify dated securities but can change with corporate actions; none is described as an unconditional permanent identifier. PERMNO/FIGI or another verified permanent security mapping was not obtained. The permanent-security-ID field is therefore blank for every row.

The S&P 500 has archived CIK values and dated IVV ISIN values. CUSIP and SEDOL are retained where supplied; source '-' placeholders become blanks. Total missing CUSIPs: **419**; total missing SEDOLs: **401**. The CIKs were not individually verified in contemporaneous SEC filings. The MidCap archive lacks numeric CIKs: its SEC links use tickers and are not historical identifiers. Current SEC mappings are accepted only when both the literal ticker and a conservative normalized company name match. These **282 CIK mappings remain flagged as not point-in-time verified**. Name normalization only removes punctuation, common legal suffixes and explicit class labels. No fuzzy match is automatically accepted. Nonmatching current names and third-party candidates are retained in separate candidate fields, not promoted into `sec_cik`.

Physicians Realty Trust’s historical DOC CIK is verified in a 2023 SEC filing as 0001574540. Its current-ticker candidate may describe Healthpeak and is intentionally retained as a visible conflict. Other unresolved matches remain blank. Missing CIKs: **118**. Missing security-level identifiers: **401**, all in MidCap. Missing means unavailable from the verified sources in this build, not nonexistent.

MidCap sectors mostly come from the nearby January archive and are labeled as not independently verified for the exact target date. They are not replaced by current pitindex sectors. These are historical classifications for the frozen universe, not a promise of point-in-time sector histories throughout training. The explicit share-class column covers the known duplicate-issuer pairs and two ticker-format aliases; blank does not assert that a security has no class designation.

## Corporate actions and ambiguity

The report contains **14 targeted primary-source event records** and **155 upstream removal/change candidates**. Announced effective dates are distinguished from verified completion dates. Raw index removal dates are not transaction closing dates or final trading dates. The candidate scan covers original tickers in pitindex files through its 2026-09-07 build; it is not a full corporate-actions database and does not follow every later alias. No event record means no event was captured by this review, not that none occurred. A security can leave an index and subsequently be acquired; the index event log alone cannot audit that later transaction.

Important cases: historical DOC and PEAK are distinct securities before the Healthpeak merger; GPS later becomes GAP; CDAY becomes DAY; FLT becomes CPAY; CHK and SWN combine; PXD, DFS and HES are acquired; WOLF old common equity is cancelled in a reorganization while the ticker persists; LNW announces a US delisting while maintaining an Australian listing. All original rows remain. Selected source date conflicts are documented in event notes. Acquirer or successor tickers are review references, not price-download substitutions. A complete merger consideration, delisting return, bankruptcy and alias-chain audit remains outstanding.

## Reproducibility and validation

Use the ZIP bundle for offline reproducibility. It includes immutable source bytes, a SHA-256 manifest and the standalone Python script. Python 3.9+ standard library only:

```bash
python build_equity_universe.py --offline --output-dir rebuilt
```

If only the script is available, `--download-missing` retrieves pinned sources, but mutable SEC and mirror endpoints can change. A hash mismatch stops the build; use bundled bytes to reproduce this release. A new retrieval must be a separately reviewed source version. The script embeds its source manifest and reviewed factual event annotations. `source_manifest.json` lists exact URLs, hashes, retrieval date and source roles. The external methodology links below are review evidence rather than automated event feeds.

The script generates the universe CSV, row-level quality CSV, event review CSV, discrepancies, JSON audit inputs and this methodology. The XLSX is a formatted rendering of those inputs; it is not needed to construct the universe. The bundle also contains the workbook builder for this ChatGPT runtime. Do not confuse the builder’s runtime dependency with the dependency-free Python construction script.

Assertions verify source hashes, exact observation dates, 503/401 counts, unique keys, disjoint indices, IVV agreement and MidCap reconstruction agreement. These controls detect processing errors; count equality does not prove source completeness. An offline rerun must reproduce the universe CSV byte-for-byte. All 904 rows have price status `not_requested_not_tested`, and price-based exclusions are zero. CIK/CUSIP/SEDOL columns must be imported as text in Excel to preserve leading zeros.

## Known limitations and rejected sources

- No full official S&P historical roster was available in this review. MidCap reconstruction relies materially on Wikipedia; additional independent holdings or regulatory-filing reconciliation remains needed.
- The current iShares download route ignored the historical-date parameter and returned October 2026 data; those responses were rejected. Current membership was never used as a historical substitute.
- An indexkit SEC-derived quarterly Parquet dataset was located but not parsed or reconciled. It supplies no verification credit and is not included as evidence for the finished roster.
- Public snapshots can contain editorial errors, anticipatory edits or stale attributes. The two January boundary changes were checked, but every archived row was not traced to an S&P notice.
- CIKs are partly unverified, MidCap security identifiers are missing, and corporate-action coverage is explicitly partial. There are no invented identifiers or guessed fuzzy matches.
- This is a fixed end-2023 universe. Applying it to earlier periods can create selection/look-ahead bias; that design question is outside this universe-construction deliverable.

## Source register

- **arch_wikipedia.csv** — Archived Wikipedia S&P 500 snapshot; 2023-12-29. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/riazarbi/sp500-scraper/3448dba00a0698b6d43eb4fcce57680345ca9823/wikipedia/sp500/csv/20231229.csv). SHA-256: `e15d152ff1adcb5e7832f321efe001431bca8bd7a74c873daaa44ace818a277d`.
- **arch_ishares.csv** — Archived IVV fund holdings; 2023-12-29; proxy, not official index roster. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/riazarbi/sp500-scraper/3448dba00a0698b6d43eb4fcce57680345ca9823/ishares/sp500/csv/20231229.csv). SHA-256: `3519c5c997484298f2f6b1005b5415fc2135de6881c0d29b8ffff9b9cbb56c79`.
- **kiwix400** — Wikipedia revision 1193645510 mirrored in January 2024 Kiwix archive; includes Jan 5 changes. Retrieved 2026-10-20 (America/Denver). [Source](https://offline.goud.so/content/wikipedia_en_all_maxi_2024-01/A/List_of_S%26P_400_companies). SHA-256: `b2b10e8665e27ec7c3bedd4aa0fccd9d959a69ac280a4450c2821bc5cd6d15b3`.
- **sec_tickers.json** — Current SEC ticker-CIK reference; not historical membership. Retrieved 2026-10-20 (America/Denver). [Source](https://www.sec.gov/files/company_tickers.json). SHA-256: `bbffa40adbea620bba590da9a193ea14b21bfc04992f102549a2688d4e7d32df`.
- **sp500_seed.csv** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp500_seed.csv). SHA-256: `1a444b80576333455e6a77d24ac12b5eb1095fbdf2d208e1db07396592e3f8aa`.
- **sp500_changes.csv** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp500_changes.csv). SHA-256: `4d5757c55bb1c113fbd5bb15ae4196000e2a87a34271e680435b3b838e8e1456`.
- **sp400_seed.csv** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_seed.csv). SHA-256: `b16cc5e36c57e4e4b3f731212196d60b04358f97985dad27adc0961716d3dc03`.
- **sp400_changes.csv** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_changes.csv). SHA-256: `ace43903dd31866b223f82455cc6f0ff98bceed608ee32bd1dd87feb0c955ea5`.
- **sp400_current.csv** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_current.csv). SHA-256: `f73de533f7de27176bdcdaacce9ac5eee4257ef7d3cbf5851375c5a808e90416`.
- **build_metadata.json** — Pinned pitindex reconstruction / metadata; built 2026-09-07. Retrieved 2026-10-20 (America/Denver). [Source](https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/build_metadata.json). SHA-256: `1fad2a065f348999f149c7aba986c52d0267e5ff47d750b4d09f038d18be4184`.

### Primary boundary and identity evidence

- https://press.spglobal.com/2023-12-01-Uber-Technologies,-Jabil-and-Builders-FirstSource-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600
- https://press.spglobal.com/2023-12-19-Livent-Set-to-Join-S-P-MidCap-400-NCR-Voyix-and-Rush-Enterprises-to-Join-S-P-SmallCap-600
- https://press.spglobal.com/2024-01-02-Pure-Storage-Set-to-Join-S-P-MidCap-400-Patterson-Companies-to-Join-S-P-SmallCap-600
- https://www.sec.gov/Archives/edgar/data/1574540/000157454023000113/0001574540-23-000113-index.htm

### Reviewed corporate-action evidence

- BALL: 2022-05-10, historical_ticker_correction; primary_source_verified. BLL changed to BALL before the universe date. Reject pitindex's 2024 rename date. [Source](https://investors.ball.com/sec-filings/all-sec-filings/content/0000009389-22-000010/bll-20220427x8k.htm). Retrieved 2026-10-20.
- FI: 2023-06-07, historical_ticker_correction; primary_source_verified. Fiserv began NYSE trading as FI before the universe date. [Source](https://investors.fiserv.com/news-releases/news-release-details/fiserv-completes-listing-transfer-new-york-stock-exchange). Retrieved 2026-10-20.
- CDAY: 2024-02-01, ticker_change; primary_source_verified. Ceridian became Dayforce. The 2023 ticker remains CDAY. [Source](https://www.dayforce.com/who-we-are/newsroom/ceridian-to-change-ticker-symbol-to-day-on-nyse-and-tsx-effective-february-1). Retrieved 2026-10-20.
- FLT: 2024-03-25, ticker_change; primary_source_verified. FLEETCOR became Corpay; CUSIP also changed. Do not use pitindex's April 4 rename date. [Source](https://investor.corpay.com/news-releases/news-release-details/fleetcor-announces-rebranding-corpay-0). Retrieved 2026-10-20.
- DOC: 2024-03-01, merger_and_ticker_reuse; primary_source_verified. Historical DOC is Physicians Realty Trust, acquired in Healthpeak merger. Subsequent DOC is not this historical issuer. Do not splice ticker histories. [Source](https://ir.healthpeak.com/news/news-details/2024/Healthpeak-Properties-Closes-Merger-with-Physicians-Realty-Trust/default.aspx). Retrieved 2026-10-20.
- PEAK: 2024-03-04, ticker_change_after_merger; primary_source_announced_effective_date. Healthpeak closed merger March 1; release specifies DOC trading expected March 4. Separate closing from trading-effective date. [Source](https://ir.healthpeak.com/news/news-details/2024/Healthpeak-Properties-Closes-Merger-with-Physicians-Realty-Trust/default.aspx). Retrieved 2026-10-20.
- PXD: 2024-05-03, acquisition_completed; primary_source_verified. ExxonMobil completed acquisition. Closing date is not the pitindex index-removal date May 8. [Source](https://corporate.exxonmobil.com/news/news-releases/2024/0503_ExxonMobil-completes-acquisition-of-Pioneer-Natural-Resources). Retrieved 2026-10-20.
- GPS: 2024-08-22, ticker_change; primary_source_announced_effective_date. Gap announced change from GPS to GAP effective August 22. [Source](https://investors.gapinc.com/press-releases/news-details/2024/Gap-Inc.-To-Change-Ticker-Symbol-to-GAP-on-August-22-To-Report-Second-Quarter-Fiscal-2024-Results-on-August-29/default.aspx). Retrieved 2026-10-20.
- SWN: 2024-10-01, merger_completed; primary_source_verified. Southwestern and Chesapeake merger completed. Keep both original 2023 securities. [Source](https://investors.expandenergy.com/news-releases/news-release-details/chesapeake-energy-and-southwestern-energy-complete-merger-and). Retrieved 2026-10-20.
- CHK: 2024-10-02, ticker_change_after_merger; primary_source_announced_effective_date. October 1 merger release says CHK trades that day and EXE starts October 2; revision-derived October 15 is not trading-effective date. [Source](https://investors.expandenergy.com/news-releases/news-release-details/chesapeake-energy-and-southwestern-energy-complete-merger-and). Retrieved 2026-10-20.
- DFS: 2025-05-18, acquisition_completed; primary_source_verified. Capital One completed acquisition of Discover; original DFS retained. [Source](https://www.capitalone.com/about/newsroom/capital-one-completes-acquisition-of-discover/). Retrieved 2026-10-20.
- HES: 2025-07-18, acquisition_completed; primary_source_verified. Chevron completed acquisition; original HES retained. [Source](https://www.chevron.com/newsroom/2025/q3/chevron-completes-acquisition-of-hess-corporation). Retrieved 2026-10-20.
- WOLF: 2025-09-29, old_equity_cancelled_reorganization; primary_source_verified. SEC filing states old common shares cancelled and new shares distributed. Same ticker and CIK do not establish security continuity. [Source](https://www.sec.gov/Archives/edgar/data/895419/000119312525223057/d69265d8k.htm). Retrieved 2026-10-20.
- LNW: 2025-11-13, US_delisting_announced; primary_source_announced_effective_date. Issuer announced Nasdaq delisting November 13 and continuation on ASX. Completion not independently verified in this review. [Source](https://explore.lnw.com/newsroom/light-wonder-announces-update-on-nasdaq-delisting-timetable/). Retrieved 2026-10-20.

## Attribution

Wikipedia content is CC BY-SA; attribute the linked original revision and its contributors, and retain applicable share-alike terms for redistributed adapted content. The Kiwix mirror retains the attribution footer. pitindex is MIT and describes its public upstream sources; preserve upstream notices when redistributing its curated files. The scraper archive is an access route to third-party data, not a grant of S&P, iShares or identifier licensing rights. Public accessibility does not imply unrestricted redistribution. SEC government filings are public records; issuer exhibits can retain third-party rights.
