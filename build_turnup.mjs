import fs from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire('C:/Users/biswajit.das/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/package.json');
const {Workbook,SpreadsheetFile}=await import((await import('node:url')).pathToFileURL(require.resolve('@oai/artifact-tool')).href);
const dir='outputs/turnup_20261023';const d=JSON.parse(await fs.readFile(dir+'/analysis.json','utf8'));const w=Workbook.create();
const s=w.worksheets.add('Turn-up summary'), g=w.worksheets.add('Centre and month detail'),r=w.worksheets.add('Mapped trial records');
function put(sh,row,values){sh.getRangeByIndexes(row-1,0,values.length,values[0].length).values=values;}
function style(sh,header,last,cols){sh.showGridLines=false;sh.getRangeByIndexes(0,0,last,cols).format.font={name:'Arial',size:10};sh.getRangeByIndexes(header-1,0,1,cols).format={fill:'#203864',font:{color:'#FFFFFF',bold:true},wrapText:true,rowHeight:36};sh.getRangeByIndexes(0,0,last,cols).format.columnWidth=17;sh.freezePanes.freezeRows(header);}
put(s,2,[['Trial turn-up by sport']]);put(s,3,[['Scheduled before 23-Oct-2026; record-based rates; unresolved outcomes included.']]);
const h=['Sport','Past booked records','Attended','Not attended','Rescheduled','Booked / pending','Unmarked','Other','Turn-up %'];put(s,5,[h]);
const sports=d.summary.filter(a=>a[0]==='Sport');put(s,6,sports.map(a=>[a[1],...a.slice(2),null]));for(let i=0;i<sports.length;i++)s.getRange(`I${6+i}`).formulas=[[`=IF(B${6+i}=0,"n.a.",C${6+i}/B${6+i})`]];
let total=6+sports.length;put(s,total,[['Total',...Array(8).fill(null)]]);for(let c=1;c<8;c++){let l=String.fromCharCode(65+c);s.getRange(`${l}${total}`).formulas=[[`=SUM(${l}6:${l}${total-1})`]];}s.getRange(`I${total}`).formulas=[[`=C${total}/B${total}`]];
let n=total+3;for(const a of d.notes.slice(2)){put(s,n,[a.length===1?[a[0],null]:a]);n++;}style(s,5,n,9);s.getRange('A:A').format.columnWidth=24;s.getRange('I6:I14').setNumberFormat('0.0%');s.getRange(`A${total}:I${total}`).format.fill='#E4EBF5';s.getRange(`A${total+3}:I${n}`).format.rowHeight=25;
// Long methodology lines occupy otherwise empty cells.
const groups=d.summary.filter(a=>a[0]!=='Sport');const gh=['Grouping','Academy / centre / sport or month / sport',...h.slice(1)];put(g,1,[gh]);put(g,2,groups.map(a=>[...a,null]));for(let i=0;i<groups.length;i++)g.getRange(`J${i+2}`).formulas=[[`=IF(C${i+2}=0,"n.a.",D${i+2}/C${i+2})`]];style(g,1,groups.length+1,10);g.getRange('B:B').format.columnWidth=100;g.getRange(`J2:J${groups.length+1}`).setNumberFormat('0.0%');g.tables.add(`A1:J${groups.length+1}`,true,'GroupedTurnup');
put(r,1,[d.headers]);put(r,2,d.data);style(r,1,d.data.length+1,20);r.getRange('B:E').format.columnWidth=34;r.tables.add(`A1:T${d.data.length+1}`,true,'MappedTrials');
w.recalculate();console.log((await w.inspect({kind:'table',range:'Turn-up summary!A5:I14',tableMaxRows:10,tableMaxCols:9,maxChars:3000})).ndjson);
await fs.writeFile(dir+'/preview.png',new Uint8Array(await (await w.render({sheetName:s.name,range:'A1:I15',scale:1.5,format:'png'})).arrayBuffer()));
await (await SpreadsheetFile.exportXlsx(w)).save(dir+'/trial_turnup_report.xlsx');console.log('Export complete');

