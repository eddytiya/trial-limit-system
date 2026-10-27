const fs=require('fs'),vm=require('vm'),assert=require('assert');
class Element{constructor(){this.children=[];this.value='';this.hidden=true;this.files=[];this.events={}}append(...items){this.children.push(...items)}replaceChildren(){this.children=[]}setAttribute(){}addEventListener(event,fn){this.events[event]=fn}checkValidity(){return !!this.value}}
(async()=>{
for(const file of ['inventory.html','frontend.html','automatic_frontend.html','slot_frontend.html','workbook_frontend.html']){
 const el={},requests=[];const get=id=>el[id]??=new Element();get('overPanel').hidden=true;
 const context={document:{getElementById:get,createElement:()=>new Element()},Intl,Date,Map,fetch:async(url,options)=>{if(url==='/api/info')return {ok:true,json:async()=>({date:'2026-10-22'})};const body=JSON.parse(options.body);requests.push(body);const weekday=new Intl.DateTimeFormat('en',{weekday:'long',timeZone:'UTC'}).format(new Date(body.reference_date+'T00:00:00Z'));return {ok:true,json:async()=>({weekday,reference_date:body.reference_date,batches:[]})}}};
 vm.createContext(context);vm.runInContext(fs.readFileSync(require('path').join(__dirname,'..','app',file),'utf8').split('<script>')[1].split('</script>')[0],context);await vm.runInContext('dateReady',context);assert.equal(get('referenceDate').value,'2026-10-22');
 for(const id of ['enrollment','trials','capacity'])get(id).files=[{name:id+'.csv',text:async()=> 'fixture'}];
 get('referenceDate').value='2026-11-01';await vm.runInContext('showSelectedDate();load()',context);assert.equal(requests.at(-1).reference_date,'2026-11-01');assert.match(get('day').textContent,/Sunday/);assert.match(get('overDay').textContent,/Sunday/);assert.match(get('selectedWeekday').textContent,/Sunday/);
 vm.runInContext('tab(true)',context);get('referenceDate').value='2026-10-31';await vm.runInContext('showSelectedDate();load()',context);assert.match(get('day').textContent,/Saturday/);assert.equal(get('overPanel').hidden,false);
 const count=requests.length;get('referenceDate').value='';await vm.runInContext('load()',context);assert.equal(requests.length,count);assert.equal(get('error').hidden,false);assert.equal(get('results').hidden,true);
 console.log(file+': default date, selected-date request, Sunday/Saturday captions, tab preservation, empty-date validation passed');
}
})().catch(error=>{console.error(error);process.exitCode=1});
