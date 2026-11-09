#!/usr/bin/env python3
"""Rebuild the frozen 2023-12-29 universe. Python 3.9+; standard library only.

python build_equity_universe.py --offline
python build_equity_universe.py --download-missing --output-dir rebuilt

The source manifest and reviewed facts are embedded. Exact source bytes are
SHA-256 checked. A changed upstream response fails, never becomes current data.
The script writes CSV, JSON audit inputs and methodology. The supplied XLSX is a
formatted report of these outputs, not a dependency of universe construction.
"""
import argparse, collections, csv, hashlib, io, json, re, urllib.request
from pathlib import Path
from html.parser import HTMLParser

AS_OF = '2023-12-29'
RETRIEVED = '2026-10-20'
MANIFEST = [{'file': 'arch_wikipedia.csv', 'url': 'https://raw.githubusercontent.com/riazarbi/sp500-scraper/3448dba00a0698b6d43eb4fcce57680345ca9823/wikipedia/sp500/csv/20231229.csv', 'sha256': 'e15d152ff1adcb5e7832f321efe001431bca8bd7a74c873daaa44ace818a277d', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Archived Wikipedia S&P 500 snapshot; 2023-12-29'}, {'file': 'arch_ishares.csv', 'url': 'https://raw.githubusercontent.com/riazarbi/sp500-scraper/3448dba00a0698b6d43eb4fcce57680345ca9823/ishares/sp500/csv/20231229.csv', 'sha256': '3519c5c997484298f2f6b1005b5415fc2135de6881c0d29b8ffff9b9cbb56c79', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Archived IVV fund holdings; 2023-12-29; proxy, not official index roster'}, {'file': 'kiwix400', 'url': 'https://offline.goud.so/content/wikipedia_en_all_maxi_2024-01/A/List_of_S%26P_400_companies', 'sha256': 'b2b10e8665e27ec7c3bedd4aa0fccd9d959a69ac280a4450c2821bc5cd6d15b3', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Wikipedia revision 1193645510 mirrored in January 2024 Kiwix archive; includes Jan 5 changes'}, {'file': 'sec_tickers.json', 'url': 'https://www.sec.gov/files/company_tickers.json', 'sha256': 'bbffa40adbea620bba590da9a193ea14b21bfc04992f102549a2688d4e7d32df', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Current SEC ticker-CIK reference; not historical membership'}, {'file': 'sp500_seed.csv', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp500_seed.csv', 'sha256': '1a444b80576333455e6a77d24ac12b5eb1095fbdf2d208e1db07396592e3f8aa', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}, {'file': 'sp500_changes.csv', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp500_changes.csv', 'sha256': '4d5757c55bb1c113fbd5bb15ae4196000e2a87a34271e680435b3b838e8e1456', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}, {'file': 'sp400_seed.csv', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_seed.csv', 'sha256': 'b16cc5e36c57e4e4b3f731212196d60b04358f97985dad27adc0961716d3dc03', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}, {'file': 'sp400_changes.csv', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_changes.csv', 'sha256': 'ace43903dd31866b223f82455cc6f0ff98bceed608ee32bd1dd87feb0c955ea5', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}, {'file': 'sp400_current.csv', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/sp400_current.csv', 'sha256': 'f73de533f7de27176bdcdaacce9ac5eee4257ef7d3cbf5851375c5a808e90416', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}, {'file': 'build_metadata.json', 'url': 'https://raw.githubusercontent.com/arielNacamulli/pitindex/2df030e5c9be7c83cf4b28c3d8597d74d274757e/pitindex/data/build_metadata.json', 'sha256': '1fad2a065f348999f149c7aba986c52d0267e5ff47d750b4d09f038d18be4184', 'retrieved_date': '2026-10-20', 'retrieval_timezone': 'America/Denver', 'description': 'Pinned pitindex reconstruction / metadata; built 2026-09-07'}]
REVIEWED_EVENTS = [{'ticker': 'BALL', 'date': '2022-05-10', 'type': 'historical_ticker_correction', 'related_ticker': 'BLL', 'status': 'primary_source_verified', 'note': "BLL changed to BALL before the universe date. Reject pitindex's 2024 rename date.", 'url': 'https://investors.ball.com/sec-filings/all-sec-filings/content/0000009389-22-000010/bll-20220427x8k.htm'}, {'ticker': 'FI', 'date': '2023-06-07', 'type': 'historical_ticker_correction', 'related_ticker': 'FISV', 'status': 'primary_source_verified', 'note': 'Fiserv began NYSE trading as FI before the universe date.', 'url': 'https://investors.fiserv.com/news-releases/news-release-details/fiserv-completes-listing-transfer-new-york-stock-exchange'}, {'ticker': 'CDAY', 'date': '2024-02-01', 'type': 'ticker_change', 'related_ticker': 'DAY', 'status': 'primary_source_verified', 'note': 'Ceridian became Dayforce. The 2023 ticker remains CDAY.', 'url': 'https://www.dayforce.com/who-we-are/newsroom/ceridian-to-change-ticker-symbol-to-day-on-nyse-and-tsx-effective-february-1'}, {'ticker': 'FLT', 'date': '2024-03-25', 'type': 'ticker_change', 'related_ticker': 'CPAY', 'status': 'primary_source_verified', 'note': "FLEETCOR became Corpay; CUSIP also changed. Do not use pitindex's April 4 rename date.", 'url': 'https://investor.corpay.com/news-releases/news-release-details/fleetcor-announces-rebranding-corpay-0'}, {'ticker': 'DOC', 'date': '2024-03-01', 'type': 'merger_and_ticker_reuse', 'related_ticker': 'PEAK', 'status': 'primary_source_verified', 'note': 'Historical DOC is Physicians Realty Trust, acquired in Healthpeak merger. Subsequent DOC is not this historical issuer. Do not splice ticker histories.', 'url': 'https://ir.healthpeak.com/news/news-details/2024/Healthpeak-Properties-Closes-Merger-with-Physicians-Realty-Trust/default.aspx'}, {'ticker': 'PEAK', 'date': '2024-03-04', 'type': 'ticker_change_after_merger', 'related_ticker': 'DOC', 'status': 'primary_source_announced_effective_date', 'note': 'Healthpeak closed merger March 1; release specifies DOC trading expected March 4. Separate closing from trading-effective date.', 'url': 'https://ir.healthpeak.com/news/news-details/2024/Healthpeak-Properties-Closes-Merger-with-Physicians-Realty-Trust/default.aspx'}, {'ticker': 'PXD', 'date': '2024-05-03', 'type': 'acquisition_completed', 'related_ticker': 'XOM', 'status': 'primary_source_verified', 'note': 'ExxonMobil completed acquisition. Closing date is not the pitindex index-removal date May 8.', 'url': 'https://corporate.exxonmobil.com/news/news-releases/2024/0503_ExxonMobil-completes-acquisition-of-Pioneer-Natural-Resources'}, {'ticker': 'GPS', 'date': '2024-08-22', 'type': 'ticker_change', 'related_ticker': 'GAP', 'status': 'primary_source_announced_effective_date', 'note': 'Gap announced change from GPS to GAP effective August 22.', 'url': 'https://investors.gapinc.com/press-releases/news-details/2024/Gap-Inc.-To-Change-Ticker-Symbol-to-GAP-on-August-22-To-Report-Second-Quarter-Fiscal-2024-Results-on-August-29/default.aspx'}, {'ticker': 'SWN', 'date': '2024-10-01', 'type': 'merger_completed', 'related_ticker': 'EXE', 'status': 'primary_source_verified', 'note': 'Southwestern and Chesapeake merger completed. Keep both original 2023 securities.', 'url': 'https://investors.expandenergy.com/news-releases/news-release-details/chesapeake-energy-and-southwestern-energy-complete-merger-and'}, {'ticker': 'CHK', 'date': '2024-10-02', 'type': 'ticker_change_after_merger', 'related_ticker': 'EXE', 'status': 'primary_source_announced_effective_date', 'note': 'October 1 merger release says CHK trades that day and EXE starts October 2; revision-derived October 15 is not trading-effective date.', 'url': 'https://investors.expandenergy.com/news-releases/news-release-details/chesapeake-energy-and-southwestern-energy-complete-merger-and'}, {'ticker': 'DFS', 'date': '2025-05-18', 'type': 'acquisition_completed', 'related_ticker': 'COF', 'status': 'primary_source_verified', 'note': 'Capital One completed acquisition of Discover; original DFS retained.', 'url': 'https://www.capitalone.com/about/newsroom/capital-one-completes-acquisition-of-discover/'}, {'ticker': 'HES', 'date': '2025-07-18', 'type': 'acquisition_completed', 'related_ticker': 'CVX', 'status': 'primary_source_verified', 'note': 'Chevron completed acquisition; original HES retained.', 'url': 'https://www.chevron.com/newsroom/2025/q3/chevron-completes-acquisition-of-hess-corporation'}, {'ticker': 'WOLF', 'date': '2025-09-29', 'type': 'old_equity_cancelled_reorganization', 'related_ticker': 'WOLF', 'status': 'primary_source_verified', 'note': 'SEC filing states old common shares cancelled and new shares distributed. Same ticker and CIK do not establish security continuity.', 'url': 'https://www.sec.gov/Archives/edgar/data/895419/000119312525223057/d69265d8k.htm'}, {'ticker': 'LNW', 'date': '2025-11-13', 'type': 'US_delisting_announced', 'related_ticker': 'LNW (ASX)', 'status': 'primary_source_announced_effective_date', 'note': 'Issuer announced Nasdaq delisting November 13 and continuation on ASX. Completion not independently verified in this review.', 'url': 'https://explore.lnw.com/newsroom/light-wonder-announces-update-on-nasdaq-delisting-timetable/'}]
SP_DEC = 'https://press.spglobal.com/2023-12-01-Uber-Technologies,-Jabil-and-Builders-FirstSource-Set-to-Join-S-P-500-Others-to-Join-S-P-MidCap-400-and-S-P-SmallCap-600'
SP_JAN2 = 'https://press.spglobal.com/2023-12-19-Livent-Set-to-Join-S-P-MidCap-400-NCR-Voyix-and-Rush-Enterprises-to-Join-S-P-SmallCap-600'
SP_JAN5 = 'https://press.spglobal.com/2024-01-02-Pure-Storage-Set-to-Join-S-P-MidCap-400-Patterson-Companies-to-Join-S-P-SmallCap-600'
DOC_CIK_SOURCE = 'https://www.sec.gov/Archives/edgar/data/1574540/000157454023000113/0001574540-23-000113-index.htm'

class FirstTable(HTMLParser):
    """Extract the archived roster without relying on current Wikipedia APIs."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth=0; self.done=False; self.cell=None; self.row=[]; self.rows=[]; self.sup=0
    def handle_starttag(self,tag,attrs):
        if self.done: return
        if tag=='table': self.depth+=1
        if self.depth==1:
            if tag=='tr': self.row=[]
            elif tag in ('td','th'): self.cell=[]
            elif tag=='sup': self.sup+=1
    def handle_data(self,data):
        if self.depth==1 and self.cell is not None and not self.sup: self.cell.append(data)
    def handle_endtag(self,tag):
        if self.done:return
        if self.depth==1:
            if tag=='sup': self.sup=max(0,self.sup-1)
            elif tag in ('td','th') and self.cell is not None:
                self.row.append(' '.join(''.join(self.cell).split())); self.cell=None
            elif tag=='tr' and self.row:self.rows.append(self.row)
        if tag=='table' and self.depth:
            self.depth-=1
            if self.depth==0:self.done=True

def normal_name(s):
    s=re.sub(r'\(Class [ABC]\)','',s,flags=re.I)
    return re.sub(r'\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|the)\b|[^a-z0-9]','',s.lower())

def write_csv(path,rows,fields=None):
    fields=fields or list(rows[0])
    with path.open('w',newline='',encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def build(source_dir,output_dir,download_missing=False):
    source_dir.mkdir(parents=True,exist_ok=True);output_dir.mkdir(parents=True,exist_ok=True)
    data={}
    for m in MANIFEST:
        path=source_dir/m['file']
        if not path.exists():
            if not download_missing:raise FileNotFoundError(f'{path}: use reproduction bundle or --download-missing')
            req=urllib.request.Request(m['url'],headers={'User-Agent':'PublicHistoricalUniverseResearch/1.0'})
            b=urllib.request.urlopen(req,timeout=60).read()
            if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError(f"Source drift for {m['file']}; obtain archived bytes from bundle")
            path.write_bytes(b)
        b=path.read_bytes()
        if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError(f"Hash mismatch: {path}")
        data[m['file']]=b.decode('utf-8-sig')
    def csvrows(name):return list(csv.DictReader(io.StringIO(data[name])))
    urls={m['file']:m['url'] for m in MANIFEST}
    wiki=csvrows('arch_wikipedia.csv'); holdings=csvrows('arch_ishares.csv')
    assert len(wiki)==503 and {r['date'] for r in wiki}=={AS_OF}
    assert {r['date'] for r in holdings}=={AS_OF}
    # Explicit provider-format aliases; never remove punctuation generically.
    aliases={'BRKB':'BRK.B','BFB':'BF.B'}
    equity=[r for r in holdings if r['asset_class']=='Equity']
    h={aliases.get(r['symbol'],r['symbol']):r for r in equity}
    for row in h.values():
        for field in ['CUSIP','ISIN','SEDOL']:
            if row[field] in ('-', 'NA', 'N/A'): row[field]=''
    assert len(h)==len(equity)==503
    assert set(h)=={r['Symbol'] for r in wiki}
    parser=FirstTable();parser.feed(data['kiwix400'])
    assert parser.rows[0][:3]==['Symbol','Security','GICS Sector']
    mid={r[0]:dict(zip(parser.rows[0],r)) for r in parser.rows[1:]}
    assert len(mid)==401 and '1193645510' in data['kiwix400']
    # Restore pre-effective-date membership. The archived page already uses ALTM
    # for the Jan 2 addition, whereas the official release specifies LTHM first.
    # Neither LTHM nor ALTM belongs in the target-date MidCap roster.
    assert 'PSTG' in mid and 'ALTM' in mid and 'PDCO' not in mid and 'VYX' not in mid
    del mid['PSTG'];del mid['ALTM']
    mid['PDCO']={'Symbol':'PDCO','Security':'Patterson Companies','GICS Sector':'Health Care','GICS Sub-Industry':''}
    mid['VYX']={'Symbol':'VYX','Security':'NCR Voyix','GICS Sector':'Information Technology','GICS Sub-Industry':''}
    def reconstruct(index):
        members={r['ticker'] for r in csvrows(index+'_seed.csv')}
        for r in csvrows(index+'_changes.csv'):
            if r['date']<=AS_OF:
                if r['action']=='added':members.add(r['ticker'])
                elif r['action']=='removed':members.discard(r['ticker'])
                else:raise ValueError('Unknown source action')
        return members
    assert reconstruct('sp400')==set(mid)
    assert not (set(mid)&set(h))
    sec={r['ticker']:r for r in json.loads(data['sec_tickers.json']).values()}
    metadata={r['ticker']:r for r in csvrows('sp400_current.csv')}
    roster=[];quality=[]
    for index,records in [('sp500',wiki),('sp400',list(mid.values()))]:
        for r in records:
            t=r['Symbol'];is500=index=='sp500';hh=h.get(t,{})
            membership='dated_archive_plus_dated_fund_proxy' if is500 else 'reconstructed_archive_with_primary_boundary_checks'
            sector_source=urls['arch_wikipedia.csv'] if is500 else urls['kiwix400']
            sector_status='dated_2023_12_29_archive' if is500 else 'near_date_archive_not_exact_date_verified'
            if t in ('PDCO','VYX'):
                sector_source=SP_JAN5 if t=='PDCO' else SP_JAN2
                sector_status='primary_release_near_date'
            cik='';cik_status='missing';cik_source='';candidate='';candidate_name=''
            flags=[]
            if is500:
                cik=r.get('CIK','').zfill(10) if r.get('CIK') else ''
                cik_status='dated_Wikipedia_not_individually_SEC_verified';cik_source=urls['arch_wikipedia.csv']
            else:
                q=sec.get(t)
                if q:
                    candidate=str(q['cik_str']).zfill(10);candidate_name=q['title']
                    if normal_name(r['Security'])==normal_name(q['title']):
                        cik=candidate;cik_status='current_SEC_exact_name_and_ticker_match_not_PIT_verified';cik_source=urls['sec_tickers.json']
                        flags.append('CIK_HISTORICAL_CONTINUITY_UNVERIFIED')
                    else:flags.append('CIK_NAME_MISMATCH_REVIEW')
                elif metadata.get(t,{}).get('cik'):
                    candidate=metadata[t]['cik'];candidate_name=metadata[t]['name'];flags.append('CIK_THIRD_PARTY_CANDIDATE_ONLY')
                if not cik:flags.append('CIK_MISSING')
                flags.extend(['MIDCAP_MEMBERSHIP_NOT_INDEPENDENTLY_FULLY_VERIFIED','SECTOR_NEAR_DATE'])
            if t=='DOC':
                cik='0001574540';cik_status='historical_SEC_filing_verified';cik_source=DOC_CIK_SOURCE
                flags=[f for f in flags if f not in ('CIK_MISSING','CIK_NAME_MISMATCH_REVIEW')]
                flags.append('TICKER_REUSED_DIFFERENT_ISSUER')
            if t=='WOLF':flags.append('OLD_EQUITY_CANCELLED_SAME_TICKER')
            if not hh.get('ISIN'):flags.append('SECURITY_IDENTIFIER_MISSING')
            if is500 and not hh.get('CUSIP'):flags.append('CUSIP_MISSING')
            if is500 and not hh.get('SEDOL'):flags.append('SEDOL_MISSING')
            share_class={'GOOG':'C','GOOGL':'A','FOX':'B','FOXA':'A','NWS':'B','NWSA':'A','UA':'C','UAA':'A','BRK.B':'B','BF.B':'B'}.get(t,'')
            rev=[e for e in REVIEWED_EVENTS if e['ticker']==t]
            row={'universe_security_id':f'U20231229_{index.upper()}_{t}','as_of_date':AS_OF,'historical_ticker':t,
                 'company_name':r['Security'],'index_membership':'S&P 500' if is500 else 'S&P MidCap 400',
                 'share_class_explicit':share_class,'sector':r['GICS Sector'],'sector_status':sector_status,
                 'sec_cik':cik,'cik_status':cik_status,'candidate_cik':candidate,'candidate_company_name':candidate_name,'candidate_cik_source':(urls['sec_tickers.json'] if candidate and sec.get(t) else urls['sp400_current.csv'] if candidate else ''),
                 'cusip':hh.get('CUSIP',''),'isin':hh.get('ISIN',''),'sedol':hh.get('SEDOL',''),
                 'permanent_security_id':'','permanent_id_status':'not_available_from_verified_public_sources',
                 'membership_status':membership,'membership_source':urls['arch_wikipedia.csv'] if is500 else urls['kiwix400'],
                 'membership_corroboration':urls['arch_ishares.csv'] if is500 else urls['sp400_changes.csv'],
                 'sector_source':sector_source,'cik_source':cik_source,'security_identifier_source':urls['arch_ishares.csv'] if is500 else '',
                 'boundary_source':(SP_JAN5 if t=='PDCO' else SP_JAN2 if t=='VYX' else SP_DEC if t in ['UBER','JBL','BLDR','RMBS','FIX','HLI','EQH'] else ''),
                 'reviewed_event_types':';'.join(e['type'] for e in rev),'event_review_status':'targeted_primary_review_partial' if rev else 'no_primary_event_review_not_evidence_of_no_events',
                 'price_data_status':'not_requested_not_tested','retain_in_historical_universe':'yes','quality_flags':';'.join(flags),'retrieved_date':RETRIEVED}
            roster.append(row)
    roster.sort(key=lambda r:(r['index_membership'],r['historical_ticker']))
    assert len(roster)==904 and len({r['universe_security_id'] for r in roster})==904
    symbols={r['historical_ticker'] for r in roster}
    events=[]
    for idx in ['sp500','sp400']:
        for e in csvrows(idx+'_changes.csv'):
            if e['date']>AS_OF and e['ticker'] in symbols and e['action']=='removed':
                reason=e['reason']
                kind='index_removal_only'
                if 'rename' in reason.lower() or 'ticker' in reason.lower():kind='possible_ticker_change'
                elif 'acquir' in reason.lower() or 'merg' in reason.lower():kind='possible_acquisition_or_merger'
                elif 'delist' in reason.lower():kind='possible_delisting'
                elif 'revision diff' in reason.lower():kind='unresolved_revision_change'
                events.append({'ticker':e['ticker'],'date':e['date'],'type':kind,'related_ticker':'','status':'unverified_upstream_index_event_date_not_corporate_action_date','note':reason,'url':urls[idx+'_changes.csv']})
    events+=REVIEWED_EVENTS
    events.sort(key=lambda r:(r['ticker'],r['date'],r['status']))
    for r in roster:
        ticker=r['historical_ticker'];es=[e for e in events if e['ticker']==ticker]
        quality.append({'ticker':ticker,'index':r['index_membership'],'company':r['company_name'],'membership_evidence':r['membership_status'],
                        'cik_status':r['cik_status'],'sector_status':r['sector_status'],'identifier_status':'dated_ISIN_CUSIP_SEDOL' if r['isin'] else 'missing_security_identifier',
                        'flags':r['quality_flags'],'event_records':len(es),'event_review':r['event_review_status'],
                        'action':'Retain; resolve flagged metadata and security continuity before price mapping'})
    pit500=reconstruct('sp500');w500=set(h)
    discrepancies=[{'source':'pitindex sp500','ticker':t,'issue':'pitindex_only_not_in_dated_roster','resolution':('historical ticker is BALL' if t=='BLL' else 'historical ticker is FI' if t=='FISV' else 'unsupported extra; excluded from final, retained in raw source and this audit')} for t in sorted(pit500-w500)]
    discrepancies += [{'source':'dated Wikipedia and IVV','ticker':t,'issue':'dated_roster_only','resolution':'retain dated historical ticker'} for t in sorted(w500-pit500)]
    summary={'as_of':AS_OF,'total_securities':len(roster),'sp500':503,'sp400':401,'cross_index_overlap':0,
             'missing_cik':sum(not r['sec_cik'] for r in roster),'current_SEC_matched_CIK_not_PIT_verified':sum(r['cik_status'].startswith('current_SEC') for r in roster),
             'missing_security_identifier':sum(not r['isin'] for r in roster),'missing_cusip':sum(not r['cusip'] for r in roster),'missing_sedol':sum(not r['sedol'] for r in roster),'verified_permanent_security_identifiers':0,
             'price_data_exclusions':0,'sp500_vs_IVV_differences_after_explicit_aliases':0,'sp400_vs_pitindex_differences':0,
             'reviewed_events':len(REVIEWED_EVENTS),'upstream_event_candidates':len(events)-len(REVIEWED_EVENTS),
             'full_official_roster_verified':False,'corporate_action_audit_exhaustive':False}
    for filename,rows in [('equity_universe_2023.csv',roster),('quality_records.csv',quality),('corporate_action_review.csv',events),('source_discrepancies.csv',discrepancies)]:write_csv(output_dir/filename,rows)
    audit={'summary':summary,'quality':quality,'events':events,'discrepancies':discrepancies,'sources':MANIFEST,'universe':roster}
    (output_dir/'audit_data.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
    (output_dir/'source_manifest.json').write_text(json.dumps(MANIFEST,indent=2),encoding='utf-8')
    (output_dir/'universe_methodology.md').write_text(methodology(summary),encoding='utf-8')
    print(json.dumps(summary,indent=2))
    return audit

def methodology(s):
    return f'''# Historical equity universe — December 29, 2023

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

The S&P 500 has archived CIK values and dated IVV ISIN values. CUSIP and SEDOL are retained where supplied; source '-' placeholders become blanks. Total missing CUSIPs: **{s['missing_cusip']}**; total missing SEDOLs: **{s['missing_sedol']}**. The CIKs were not individually verified in contemporaneous SEC filings. The MidCap archive lacks numeric CIKs: its SEC links use tickers and are not historical identifiers. Current SEC mappings are accepted only when both the literal ticker and a conservative normalized company name match. These **{s['current_SEC_matched_CIK_not_PIT_verified']} CIK mappings remain flagged as not point-in-time verified**. Name normalization only removes punctuation, common legal suffixes and explicit class labels. No fuzzy match is automatically accepted. Nonmatching current names and third-party candidates are retained in separate candidate fields, not promoted into `sec_cik`.

Physicians Realty Trust’s historical DOC CIK is verified in a 2023 SEC filing as 0001574540. Its current-ticker candidate may describe Healthpeak and is intentionally retained as a visible conflict. Other unresolved matches remain blank. Missing CIKs: **{s['missing_cik']}**. Missing security-level identifiers: **{s['missing_security_identifier']}**, all in MidCap. Missing means unavailable from the verified sources in this build, not nonexistent.

MidCap sectors mostly come from the nearby January archive and are labeled as not independently verified for the exact target date. They are not replaced by current pitindex sectors. These are historical classifications for the frozen universe, not a promise of point-in-time sector histories throughout training. The explicit share-class column covers the known duplicate-issuer pairs and two ticker-format aliases; blank does not assert that a security has no class designation.

## Corporate actions and ambiguity

The report contains **{s['reviewed_events']} targeted primary-source event records** and **{s['upstream_event_candidates']} upstream removal/change candidates**. Announced effective dates are distinguished from verified completion dates. Raw index removal dates are not transaction closing dates or final trading dates. The candidate scan covers original tickers in pitindex files through its 2026-09-07 build; it is not a full corporate-actions database and does not follow every later alias. No event record means no event was captured by this review, not that none occurred. A security can leave an index and subsequently be acquired; the index event log alone cannot audit that later transaction.

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

''' + '\n'.join(f"- **{m['file']}** — {m['description']}. Retrieved {m['retrieved_date']} ({m['retrieval_timezone']}). [Source]({m['url']}). SHA-256: `{m['sha256']}`." for m in MANIFEST) + '\n\n### Primary boundary and identity evidence\n\n' + '\n'.join(f'- {u}' for u in [SP_DEC,SP_JAN2,SP_JAN5,DOC_CIK_SOURCE]) + '\n\n### Reviewed corporate-action evidence\n\n' + '\n'.join(f"- {e['ticker']}: {e['date']}, {e['type']}; {e['status']}. {e['note']} [Source]({e['url']}). Retrieved {RETRIEVED}." for e in REVIEWED_EVENTS) + '''

## Attribution

Wikipedia content is CC BY-SA; attribute the linked original revision and its contributors, and retain applicable share-alike terms for redistributed adapted content. The Kiwix mirror retains the attribution footer. pitindex is MIT and describes its public upstream sources; preserve upstream notices when redistributing its curated files. The scraper archive is an access route to third-party data, not a grant of S&P, iShares or identifier licensing rights. Public accessibility does not imply unrestricted redistribution. SEC government filings are public records; issuer exhibits can retain third-party rights.
'''

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-dir',type=Path,default=Path(__file__).resolve().parent/'sources')
    p.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent)
    g=p.add_mutually_exclusive_group();g.add_argument('--offline',action='store_true');g.add_argument('--download-missing',action='store_true')
    a=p.parse_args();build(a.source_dir,a.output_dir,a.download_missing)
