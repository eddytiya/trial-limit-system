// Upload calculations use the same in-memory snapshots as the inventory views.
const workflow=document.createElement('section');
workflow.innerHTML=`<h2>Batch calculation</h2>
<p>Source files are read-only. Calculations and downloads use snapshots. Download blank templates:
<a href="/templates/enrollment.csv" download>Enrollment CSV</a> · <a href="/templates/trials.csv" download>Trial bookings CSV</a> · <a href="/templates/capacity.csv" download>Capacity CSV</a>.</p>
<details><summary>File requirements and counting rules</summary><p>Enrollment: academy ID/name, exact center, sport, age, shared Player DB ID, Start Date, End Date, Course Name and Slots. Enrollment dates accept YYYY-MM-DD or the existing DD-MM-YYYY export format; trial dates use YYYY-MM-DD. Slots use Monday 6:00 PM - 7:00 PM. Enrollment dates are inclusive; Active is ignored.</p><p>Trials: Academy, Coaching Center, Age Category, Course Details, Trial Scheduled Date, Start Time, End Time and Status. Use status booked; cancelled/canceled records are excluded. Add shared Player DB ID and Trial Booking ID for reliable identity and conflict checks. Existing raw CSV and Query result XLSX exports remain supported. Missing IDs remain provisional.</p><p>Capacity: Sport, Centre, Batch Time, Weekday and Total Capacity; include CITY and Proficiency. Use Open for a pool covering every age/course; otherwise explicitly select the exact age/course memberships. Actual Capacity is an optional reported snapshot and is never added to enrollment.</p><p>Each student counts once within the selected session across courses. Trials already enrolled in that pool are excluded using shared IDs. Separate sessions have separate capacities. Remaining places are shown only when the selected calculation is confirmed.</p></details>
<div id="calculationControls" hidden><p><label>Capacity batch <select id="calcBatch"></select></label></p>
<p><label>Enrollment academy / center / sport <select id="calcTarget"></select></label></p>
<p id="mappingStatus" role="status"></p><button id="restoreMapping" type="button" hidden>Restore approved mapping</button><p id="calcScope"></p><div id="calcMemberships"></div>
<p><label><input type="checkbox" id="calcConfirm"> I confirm this exact source link and the whole capacity pool's age/course scope.</label></p>
<button id="calculateBatch">Calculate selected batch</button> <button id="calculationDownload" disabled>Download calculation CSV</button>
<p id="calculationStatus" role="status"></p><div id="calculationResult"></div></div>`;
$('results').before(workflow);
let calculationReport=null, workflowData=null, workflowVersion=0, activeSavedMapping=null;
function csvDownload(name,records){
 const headers=[...new Set(records.flatMap(r=>Object.keys(r)))];
 // Spreadsheet-safe exports; source values are untouched.
 const quote=value=>{let text=value==null?'':typeof value==='object'?JSON.stringify(value):String(value);if(/^[=+@\-\t\r]/.test(text))text="'"+text;return '"'+text.replaceAll('"','""')+'"'};
 const text=[headers,...records.map(r=>headers.map(h=>r[h]))].map(row=>row.map(quote).join(',')).join('\r\n');
 const url=URL.createObjectURL(new Blob(['\ufeff'+text],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function resetCalculation(){++workflowVersion;calculationReport=null;$('calculationDownload').disabled=true;$('calculationResult').replaceChildren();$('calculationStatus').textContent='';$('calcConfirm').checked=false;}
function setupCalculationScope(){
 activeSavedMapping=null;
 resetCalculation();const b=workflowData?.batches.find(b=>b.id===$('calcBatch').value),t=workflowData?.targets.find(t=>t.id===$('calcTarget').value);$('calcMemberships').replaceChildren();
 const open=['Open','Open Age'].includes(b?.division);$('calcScope').textContent=open?'Open pool: all ages and courses are included.':'Select every exact age/course combination covered by this capacity pool ('+(b?.division||'missing proficiency')+').';
 $('mappingStatus').textContent=(b?.mapping_status||'Unmapped')+' · Manual selection; confirm the whole capacity pool before calculating.';
 $('restoreMapping').hidden=!b?.approved_mapping;
 if(!open)for(const pair of t?.proficiency_memberships||[]){const label=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.value=JSON.stringify([pair.age,pair.course]);box.onchange=resetCalculation;label.append(box,document.createTextNode(pair.age+' / '+pair.course));label.style.display='block';$('calcMemberships').append(label);}
}
function selectCalculationBatch(){
 const b=workflowData?.batches.find(b=>b.id===$('calcBatch').value),saved=b?.approved_mapping;
 if(saved)$('calcTarget').value=saved.target_id;
 setupCalculationScope();
 if(!saved)return;
 activeSavedMapping=saved;
 const chosen=new Set(saved.proficiency_pairs.map(pair=>JSON.stringify(pair)));
 for(const box of $('calcMemberships').querySelectorAll('input')){box.checked=chosen.has(box.value);box.onchange=()=>{activeSavedMapping=null;resetCalculation();$('mappingStatus').textContent='Approved scope edited — using a temporary manual link.';};}
 $('mappingStatus').textContent='Approved mapping restored: exact academy, center, sport and age/course scope. '+(saved.age?'Age scope: '+saved.age+'. ':'')+'Review the selection and confirm to calculate. No approval records are changed.';
}
function drawWorkflow(data){
 if(workflowData===data)return;
 workflowData=data;resetCalculation();$('calculationControls').hidden=false;
 for(const [id,items,label] of [['calcBatch',data.batches,b=>[b.center,b.city,b.sport,b.time,b.division,'capacity '+b.capacity].filter(Boolean).join(' · ')],['calcTarget',data.targets,t=>[t.academy,t.center,t.sport].join(' · ')]]){const select=$(id);select.replaceChildren(...items.map(item=>option(item.id,label(item))));}
 if(data.batches.length)$('calcBatch').value=data.batches[0].id;
 if(data.targets.length)$('calcTarget').value=data.targets[0].id;
 selectCalculationBatch();
}
const originalDraw=draw;draw=function(data){originalDraw(data);drawWorkflow(data)};
$('calcBatch').onchange=selectCalculationBatch;$('restoreMapping').onclick=selectCalculationBatch;$('calcTarget').onchange=setupCalculationScope;
$('calculationDownload').onclick=()=>{if(calculationReport)csvDownload('batch_calculation_'+calculationReport.reference_date+'.csv',[calculationReport]);};
// Preserve the confirmation while clearing a previous calculation.
$('calculateBatch').onclick=async()=>{
 const confirmed=$('calcConfirm').checked;resetCalculation();$('calcConfirm').checked=confirmed;
 const requestVersion=workflowVersion,uploadVersion=version;
 try{
 if(!confirmed)throw Error('Confirm the source link and capacity scope.');
 const files=['enrollment','trials','capacity'].map(id=>$(id).files[0]||rememberedFiles[id]);if(files.some(f=>!f))throw Error('Upload all three snapshots.');
 const parts=await Promise.all(files.map((f,i)=>source(['enrollment','trials','capacity'][i],f)));
 const batchId=$('calcBatch').value,targetId=$('calcTarget').value;
 const savedMapping=activeSavedMapping;
 const payload=Object.assign({reference_date:$('referenceDate').value,batch_id:batchId,target_id:targetId,confirmed:true,workbook_hash:workflowData.workbook_hash,proficiency_pairs:[...$('calcMemberships').querySelectorAll('input:checked')].map(box=>JSON.parse(box.value))},...parts);
 if(savedMapping){payload.use_saved_mapping=true;payload.age=savedMapping.age;}
 $('calculationStatus').textContent='Calculating read-only snapshots…';
 const response=await fetch('/api/schedule',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();
 if(requestVersion!==workflowVersion||uploadVersion!==version)return;if(!response.ok)throw Error(data.error||'Calculation failed');
 const r=data.result,b=data.batches.find(b=>b.id===batchId),t=data.targets.find(t=>t.id===targetId);
 calculationReport={reference_date:data.reference_date,center:b.center,city:b.city,sport:b.sport,time:b.time,proficiency:b.division,enrollment_center:t.center,academy:t.academy,scope:payload.proficiency_pairs,...r,enrollment_hash:data.enrollment_hash,trial_hash:data.trial_hash,capacity_hash:data.workbook_hash};
 $('calculationStatus').textContent=r.status+' · '+r.note;
 const table=document.createElement('table');for(const [label,value] of [['Capacity',r.capacity],['Unique enrolled students',r.enrolled],['Booked trial rows',r.booked_rows],['Duplicate trial rows excluded',r.duplicates_excluded],['Trials already enrolled excluded',r.already_enrolled_excluded],['Additional trial students (provisional if unconfirmed)',r.additional_trials],['Occupancy preview',r.preview],['Confirmed occupancy',r.confirmed_total],['Remaining places',r.remaining],['Known excess',r.known_excess]]){const tr=document.createElement('tr');tr.append(cell('th',label),cell('td',value??'Unavailable — needs review'));table.append(tr);} $('calculationResult').append(table);
 for(const issue of r.issues)$('calculationResult').append(cell('p',issue.source+' row '+issue.row+': '+issue.reason));$('calculationDownload').disabled=false;
 }catch(error){if(requestVersion===workflowVersion&&uploadVersion===version)$('calculationStatus').textContent=error.message;}
};
for(const id of ['enrollment','trials','capacity','referenceDate','clearSavedFiles'])$(id).addEventListener(id==='clearSavedFiles'?'click':'change',()=>{resetCalculation();workflowData=null;$('calculationControls').hidden=true;activeSavedMapping=null;});
