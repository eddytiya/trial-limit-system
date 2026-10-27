const fs=require('fs'),vm=require('vm'),assert=require('assert');
class E{constructor(){this.children=[];this.value='';this.hidden=true;this.events={}}append(...v){this.children.push(...v)}replaceChildren(...v){this.children=[...v]}setAttribute(){}addEventListener(k,f){this.events[k]=f}}
(async()=>{for(const file of ['inventory.html','frontend.html','automatic_frontend.html','slot_frontend.html','workbook_frontend.html']){
const el={},get=id=>el[id]??=new E();const ctx={document:{getElementById:get,createElement:()=>new E()},Intl,Date,Map,fetch:async()=>({ok:true,json:async()=>({date:'2026-10-22'})})};vm.createContext(ctx);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'..','app',file),'utf8').split('<script>')[1].split('</script>')[0],ctx);await vm.runInContext('dateReady',ctx);

const labels=['Nahar International School','Nahar International School Basic Batch (Powai)','Nahar International School Elite Batch (Powai)','Nahar International School, Powai'];
const sports=[['Table Tennis'],['Football'],['Football'],['Badminton','Basketball']];
const centers=labels.map((center,i)=>({center,city:'Mumbai',sports:sports[i]}));
const batches=centers.flatMap(c=>c.sports.map(sport=>({...c,sport,time:'6pm to 7pm',start:1080,end:1140,division:'Open',capacity:8,workbook_reported_count:2,reference_remaining:6,issues:[],reference_status:'Available'})));
ctx.week={week_start:'2026-10-19',week_end:'2026-10-25',centers,days:[{weekday:'Monday',date:'2026-10-19',batches}]};
vm.runInContext('setupWeekly(week)',ctx);assert.equal(get('weeklyCenter').children.length,1);assert.match(get('weeklyCenter').children[0].textContent,/Badminton, Basketball, Football, Table Tennis/);assert.match(get('weeklySummary').textContent,/5 batch sessions/);
get('sportFilter').value='Football';get('sportFilter').events.change();assert.equal(get('sportCenters').children.length,1);assert.match(get('sportSummary').textContent,/1 centers · 2 batch sessions/);
ctx.basic=batches[1];ctx.elite=batches[2];assert.match(vm.runInContext('batchDetails(basic)',ctx),/Basic batch/);assert.match(vm.runInContext('batchDetails(elite)',ctx),/Elite batch/);
assert.equal(ctx.week.centers.length,4);assert.equal(ctx.week.days[0].batches.length,5);assert.equal(ctx.week.days[0].batches[1].center,labels[1]);ctx.other={center:labels[0],city:'Pune'};assert.equal(vm.runInContext('centerName(other)',ctx),labels[0]);console.log(file+': one Nahar center, four sports, five original batches, Basic/Elite retained and source labels unchanged');
}})().catch(e=>{console.error(e);process.exitCode=1});
