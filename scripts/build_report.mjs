import fs from 'node:fs/promises';
import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';
const out=process.argv[2];
const d=JSON.parse(await fs.readFile(`${out}/audit_data.json`,'utf8'));
const wb=Workbook.create();
const summary=wb.worksheets.add('Summary');
const quality=wb.worksheets.add('Security review');
const events=wb.worksheets.add('Event review');
const diffs=wb.worksheets.add('Source discrepancies');
const sources=wb.worksheets.add('Sources');
function style(sh,rows,cols){
 sh.showGridLines=false;
 const r=sh.getRangeByIndexes(0,0,rows,cols);
 r.format.font={name:'Arial',size:10,color:'#172B4D'};
 r.format.rowHeight=29;r.format.verticalAlignment='center';
}
function table(sh,headers,rows,widths,name){
 sh.getRangeByIndexes(0,0,rows.length+1,headers.length).values=[headers,...rows];
 style(sh,rows.length+1,headers.length);
 sh.getRangeByIndexes(0,0,1,headers.length).format={fill:'#20395B',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},rowHeight:34,wrapText:true};
 widths.forEach((w,i)=>sh.getRangeByIndexes(0,i,rows.length+1,1).format.columnWidth=w);
 const tb=sh.tables.add(sh.getRangeByIndexes(0,0,rows.length+1,headers.length).address,true,name);tb.style='TableStyleMedium2';
 sh.freezePanes.freezeRows(1);
}
// Raw audit inputs stay typed; statuses use plain labels for spreadsheet readers.
const human=s=>s.replaceAll('_',' ');
table(quality,['Ticker','Index','Historical company','Membership evidence','CIK status','Sector status','Identifier status','Quality flags','Event records','Event review','Next action'],d.quality.map(r=>[r.ticker,r.index,r.company,human(r.membership_evidence),human(r.cik_status),human(r.sector_status),human(r.identifier_status),human(r.flags),r.event_records,human(r.event_review),r.action]),[12,20,33,48,57,48,29,78,14,55,78],'SecurityReview');
quality.getRange('D2:H905').format.wrapText=true;quality.getRange('J2:K905').format.wrapText=true;
quality.getRange('A2:K905').format.rowHeight=48;
quality.getRange('E2:E905').conditionalFormats.add('containsText',{text:'missing',format:{fill:'#FFF1CD',font:{color:'#854A00'}}});
quality.getRange('H2:H905').conditionalFormats.add('containsText',{text:'TICKER REUSED',format:{fill:'#FCE4E4',font:{bold:true,color:'#9C2424'}}});
table(events,['Ticker','Event date','Event type','Related ticker','Evidence status','Notes','Source URL'],d.events.map(r=>[r.ticker,new Date(r.date+'T12:00:00Z'),human(r.type),r.related_ticker,human(r.status),r.note,r.url]),[12,14,36,18,61,100,100],'EventReview');
events.getRange(`B2:B${d.events.length+1}`).setNumberFormat('yyyy-mm-dd');
events.getRange(`C2:G${d.events.length+1}`).format.wrapText=true;
events.getRange(`A2:G${d.events.length+1}`).format.rowHeight=50;
events.getRange(`E2:E${d.events.length+1}`).conditionalFormats.add('containsText',{text:'unverified',format:{fill:'#FFF1CD',font:{color:'#854A00'}}});
table(diffs,['Source','Ticker','Discrepancy','Resolution'],d.discrepancies.map(r=>[r.source,r.ticker,human(r.issue),r.resolution]),[34,12,43,90],'SourceDiscrepancies');
diffs.getRange('A2:D6').format.wrapText=true;diffs.getRange('A2:D6').format.rowHeight=52;
table(sources,['Source file','Role and limitations','Retrieved','Source URL','SHA-256'],d.sources.map(r=>[r.file,r.description,new Date(r.retrieved_date+'T12:00:00Z'),r.url,r.sha256]),[28,80,14,115,75],'SourceRegister');
sources.getRange('C2:C11').setNumberFormat('yyyy-mm-dd');sources.getRange('B2:E11').format.wrapText=true;sources.getRange('A2:E11').format.rowHeight=70;
style(summary,32,6);summary.tabColor='#20395B';
summary.getRange('A1:F32').format.columnWidth=15;
summary.getRange('A2').values=[['Historical equity universe quality review']];summary.getRange('A2').format.font={name:'Arial',size:16,bold:true,color:'#20395B'};
summary.getRange('A3').values=[['December 29, 2023 close | retrieved October 20, 2026 (Denver)']];
summary.getRange('A5:B5').values=[['Measure','Count']];summary.getRange('A5:B5').format={fill:'#20395B',font:{name:'Arial',color:'#FFFFFF',bold:true}};
summary.getRange('A6:A19').values=[['S&P 500 securities'],['S&P MidCap 400 securities'],['Combined securities'],['Missing CIK'],['Current SEC CIK matches; not PIT verified'],['Missing security-level identifier'],['Missing CUSIP'],['Missing SEDOL'],['Verified permanent security IDs'],['Primary-source event records'],['Unverified upstream event candidates'],['Price-based exclusions'],['Cross-index overlaps'],['S&P 500 vs dated IVV differences']];
summary.getRange('B6:B11').formulas=[['=COUNTIF(\'Security review\'!B2:B905,"S&P 500")'],['=COUNTIF(\'Security review\'!B2:B905,"S&P MidCap 400")'],['=COUNTA(\'Security review\'!A2:A905)'],['=COUNTIF(\'Security review\'!E2:E905,"missing")'],['=COUNTIF(\'Security review\'!E2:E905,"current SEC exact name and ticker match not PIT verified")'],['=COUNTIF(\'Security review\'!G2:G905,"missing security identifier")']];
summary.getRange('B12:B19').values=[[d.summary.missing_cusip],[d.summary.missing_sedol],[0],[d.summary.reviewed_events],[d.summary.upstream_event_candidates],[0],[0],[0]];
summary.getRange('A5:A19').format.columnWidth=51;summary.getRange('B5:B19').format.columnWidth=16;summary.getRange('B6:B19').setNumberFormat('#,##0');
summary.getRange('D5').values=[['Verification limits']];summary.getRange('D5').format.font={bold:true,color:'#854A00',name:'Arial',size:12};
const notes=[
 'Best-supported reconstruction; no full official S&P roster verified.',
 '503 S&P 500 rows match dated IVV equity holdings after two explicit ticker-format aliases.',
 '401 MidCap rows match pitindex, but both share Wikipedia ancestry. Primary checks cover boundary changes only.',
 'Keep all 904 historical rows, including acquired, delisted and unresolved securities.',
 'CIK identifies a filer, not a security. Current SEC matches remain historically unverified.',
 'DOC in 2023 is Physicians Realty Trust. Later DOC is Healthpeak; do not join by ticker alone.',
 'WOLF old common shares were cancelled in 2025. The continuing ticker does not prove security continuity.',
 'Event review is partial. Index removal dates are not transaction close or final trading dates.',
 'Zero price-based exclusions means no price screening was performed, not that all prices are available.'
];
notes.forEach((n,i)=>{summary.getRange(`D${6+i}`).values=[[n]];});
summary.getRange('D6:D14').format.columnWidth=93;summary.getRange('D6:D14').format.wrapText=true;
summary.getRange('A6:F14').format.rowHeight=48;
summary.getRange('A22').values=[['Use the filters on Security review and Event review to inspect unresolved records.']];
summary.getRange('A24').values=[['Reproduction: Python 3.9+ standard library; immutable raw sources and SHA-256 manifest in the ZIP.']];
summary.getRange('A26').values=[['No price retrieval, machine learning, cointegration testing or backtesting performed.']];
wb.recalculate();
console.log((await wb.inspect({kind:'table',range:'Summary!A5:B19',include:'values,formulas',tableMaxRows:15,tableMaxCols:2,maxChars:2500})).ndjson);
console.log((await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#NUM!',options:{useRegex:true,maxResults:20},maxChars:500})).ndjson);
if(summary.getRange('B10').values[0][0]!==282)throw new Error('CIK summary mismatch');
for(const [name,range,file] of [['Summary','A1:D26','summary'],['Security review','A1:F7','quality'],['Event review','A1:F7','events'],['Source discrepancies','A1:D6','discrepancies'],['Sources','A1:D5','sources']]){
 const b=await wb.render({sheetName:name,range,scale:1,format:'png'});
 await fs.writeFile(`/tmp/universe_workbook/${file}.png`,new Uint8Array(await b.arrayBuffer()));
}
await (await SpreadsheetFile.exportXlsx(wb)).save(`${out}/universe_data_quality_report.xlsx`);
