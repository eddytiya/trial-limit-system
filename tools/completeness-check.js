const fs=require('fs'),vm=require('vm'),assert=require('assert');
class E{constructor(){this.children=[];this.value='';this.hidden=true;this.events={}}append(...v){this.children.push(...v)}replaceChildren(){this.children=[]}setAttribute(){}addEventListener(k,f){this.events[k]=f}}
(async()=>{for(const file of ['inventory.html','frontend.html','automatic_frontend.html','slot_frontend.html','workbook_frontend.html']){
 const elements={};const get=id=>elements[id]??=new E();const ctx={document:{getElementById:get,createElement:()=>new E()},Intl,Date,Map,fetch:async()=>({ok:true,json:async()=>({date:'2026-10-22'})})};vm.createContext(ctx);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'..','app',file),'utf8').split('<script>')[1].split('</script>')[0],ctx);await vm.runInContext('dateReady',ctx);
 const complete={center:'Complete',city:'Mumbai',sport:'Football',time:'5pm to 6pm',division:'Open',capacity:10,workbook_reported_count:0,reference_remaining:10,issues:[]};
 const missing={...complete,center:'Missing',division:null,capacity:null,workbook_reported_count:null,reference_remaining:null};
 const partial={...complete,center:'Partial',workbook_reported_count:null,reference_remaining:null};
 ctx.data={weekday:'Thursday',reference_date:'2026-10-22',batches:[missing,partial,{...complete,center:'On hold',reference_remaining:null,issues:['Source marks center unavailable; review before use']},{...missing,center:'Mixed'},complete,{...complete,center:'Mixed'}]};
 vm.runInContext('draw(data)',ctx);
 const rows=get('rows').children,centers=rows.filter(r=>r.className==='center-heading').map(r=>r.children[0].textContent);
 assert.deepEqual(centers,['Complete','Mixed','On hold','Partial','Missing']);
 assert.deepEqual(rows.filter(r=>String(r.className).startsWith('completeness-heading')).map(r=>r.children[0].textContent),['Complete data · 1 center','Partial data · 3 centers','Missing data · 1 center']);
 assert.equal(vm.runInContext('batchCompleteness(data.batches[4])',ctx),0); // zero reported count is complete
 assert.equal(vm.runInContext('batchCompleteness(data.batches[2])',ctx),1); // hold cannot be complete
 assert.equal(data=ctx.data.batches.length,6);assert.equal(rows.filter(r=>r.className==='batch-row').length,6);
 assert.equal(ctx.data.batches[0].center,'Missing'); // original order unchanged
 const mixedStart=rows.findIndex(r=>r.className==='center-heading'&&r.children[0].textContent==='Mixed');assert.match(rows[mixedStart+2].children[0].children[1].textContent,/Complete data/);
 ctx.data.batches=[];vm.runInContext('draw(data)',ctx);assert.equal(get('rows').children.length,1);
 console.log(file+': completeness ordering, mixed centers, hold status, zero counts, batch preservation and empty state passed');
}})().catch(e=>{console.error(e);process.exitCode=1});
