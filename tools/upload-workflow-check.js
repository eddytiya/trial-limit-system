const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element {
 constructor(){this.children=[];this.value='';this.files=[];this.style={};this.checked=false;this.events={};}
 append(...items){this.children.push(...items)} replaceChildren(...items){this.children=items}
 before(){} setAttribute(){} addEventListener(name,fn){this.events[name]=fn}
 querySelectorAll(selector){return this.children.flatMap(label=>label.children).filter(box=>typeof box==='object'&&(selector==='input'||box.checked))}
 click(){this.clicked=true}
}
const elements={},get=id=>elements[id]??=new Element();
const data={reference_date:'2026-10-19',workbook_hash:'capacity-hash',validation:{enrollment_rows:2,trial_rows:3,issues:[],scope:'All rows'},batches:[{id:'2',center:'Club',sport:'Sport',time:'6pm to 7pm',division:'Open',capacity:2}],targets:[{id:'0',academy:'Academy',center:'Center',sport:'Sport',proficiency_memberships:[]}]};
const response={...data,enrollment_hash:'e',trial_hash:'t',result:{capacity:2,enrolled:1,booked_rows:3,duplicates_excluded:1,already_enrolled_excluded:1,additional_trials:1,preview:2,confirmed_total:2,remaining:0,known_excess:0,status:'Full',note:'Shared IDs',issues:[]}};
let calls=0,blob,lastPayload;
const context=vm.createContext({document:{createElement:()=>new Element(),createTextNode:text=>text},$:get,cell:(tag,text)=>({tag,text}),option:(value,text)=>({value,text}),draw:()=>{},version:1,rememberedFiles:{},source:async(kind,file)=>({[kind]:file.name}),URL:{createObjectURL:b=>{blob=b;return 'blob:test'},revokeObjectURL:()=>{}},Blob,setTimeout,fetch:async(url,options)=>{calls++;lastPayload=JSON.parse(options.body);return {ok:true,json:async()=>response}}});
(async()=>{
 vm.runInContext(fs.readFileSync('app/upload_workflow.js','utf8'),context);context.fixture=data;vm.runInContext('draw(fixture)',context);
 get('calcBatch').value='2';get('calcTarget').value='0';get('referenceDate').value=data.reference_date;
 for(const kind of ['enrollment','trials','capacity'])get(kind).files=[{name:kind+'.csv'}];
 await get('calculateBatch').onclick();assert.equal(calls,0);assert.match(get('calculationStatus').textContent,/Confirm/);
 get('calcConfirm').checked=true;await get('calculateBatch').onclick();assert.equal(calls,1);assert.equal(get('calculationDownload').disabled,false);assert.match(get('calculationStatus').textContent,/Full/);assert.equal(get('calculationResult').children[0].children.length,10);
 get('calculationDownload').onclick();assert.match(await blob.text(),/capacity_hash/);
 get('enrollment').events.change();assert.equal(get('calculationDownload').disabled,true);assert.equal(get('calculationControls').hidden,true);
 vm.runInContext(`csvDownload('safe.csv',[{value:'=1+1'}])`,context);assert.match(await blob.text(),/'=1\+1/);
 const saved={target_id:'0',age:'U8',proficiency_pairs:[['U8','Beginner']]};
 const mapped={...data,batches:[{...data.batches[0],division:'Beginner',approved_mapping:saved,mapping_status:'Approved batch mapping'}],targets:[{...data.targets[0],proficiency_memberships:[{age:'U8',course:'Beginner'},{age:'U10',course:'Advanced'}]}]};
 context.mapped=mapped;vm.runInContext('draw(mapped)',context);assert.equal(get('calcTarget').value,'0');assert.match(get('mappingStatus').textContent,/Approved mapping restored/);assert.equal(get('calcConfirm').checked,false);
 let boxes=get('calcMemberships').querySelectorAll('input');assert.equal(boxes[0].checked,true);assert.equal(boxes[1].checked,false);
 get('calcConfirm').checked=true;await get('calculateBatch').onclick();assert.equal(lastPayload.use_saved_mapping,true);assert.equal(lastPayload.age,'U8');
 boxes[1].checked=true;boxes[1].onchange();get('calcConfirm').checked=true;await get('calculateBatch').onclick();assert.equal(lastPayload.use_saved_mapping,undefined);assert.equal(lastPayload.proficiency_pairs.length,2);
 get('restoreMapping').onclick();assert.equal(get('calcMemberships').querySelectorAll('input')[1].checked,false);
 const changed={...mapped,batches:[{...mapped.batches[0],approved_mapping:null,mapping_status:'Needs review — capacity definition changed'}]};context.changed=changed;vm.runInContext('draw(changed)',context);assert.match(get('mappingStatus').textContent,/Needs review/);assert.equal(get('restoreMapping').hidden,true);assert.equal(get('calcConfirm').checked,false);
 console.log('Saved mappings: prefill, scope reuse, edited scope and invalidation passed');
 console.log('Upload workflow: confirmation, calculation, CSV export, formula safety and stale-result clearing passed');
})().catch(error=>{console.error(error);process.exitCode=1});
