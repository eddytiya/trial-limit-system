exec(open('inspect_turnup.py').read().split("print('academy sports'")[0])
# Normalize sport spelling; use academy-wide fallback only where all enrollment evidence agrees.
canon=lambda s: 'Table Tennis' if norm(s)=='tabletennis' else s
pairs={k:{canon(v) for v in vs} for k,vs in pairs.items()};academies={k:{canon(v) for v in vs} for k,vs in academies.items()}
cut='2026-10-23'; seen=set(); data=[]
sessioncounts=collections.Counter(tuple(norm(r[i]) for i in [2,3,4,5,9,10,11]) for r in rows)
for idx,r in enumerate(rows,2):
 duplicate=r in seen;seen.add(r)
 opts=pairs.get((norm(r[4]),norm(r[5])),set());basis='Academy + centre match'
 if len(opts)!=1:opts=academies.get(norm(r[4]),set());basis='Academy mapping (unique sport)'
 sport=next(iter(opts)) if len(opts)==1 else 'Unmapped';basis=basis if sport!='Unmapped' else 'No enrollment mapping'
 date=str(r[9] or '')[:10]; month=date[:7] if date else 'Missing date'
 status=r[15] or 'unmarked';scope='Missing date' if not date else ('Past' if date<cut else 'Today / future')
 eligible=int(scope=='Past' and not duplicate)
 key=tuple(norm(r[i]) for i in [2,3,4,5,9,10,11])
 data.append([idx,r[4] or '(blank academy)',r[5] or '(blank centre)',sport,basis,date,month,r[10],r[11],status,scope,int(duplicate),int(sessioncounts[key]>1),eligible,int(eligible and status=='attended'),int(eligible and status=='not_attended'),int(eligible and status=='rescheduled'),int(eligible and status=='booked'),int(eligible and status=='unmarked'),int(eligible and status not in ['attended','not_attended','rescheduled','booked','unmarked'])])
headers=['Source row','Academy','Coaching centre','Sport','Sport mapping basis','Scheduled date','Scheduled month','Start time','End time','Status','Date scope','Exact duplicate excluded','Possible repeated session','Past booking records','Attended','Not attended','Rescheduled','Booked outcome pending','Unmarked','Other status']
summary=[]
for dim,cols in [('Sport',[3]),('Academy + centre + sport',[1,2,3]),('Month + sport',[6,3])]:
 groups=collections.defaultdict(lambda:[0]*7)
 for r in data:
  if r[13]:
   k=tuple(r[c] for c in cols)
   for j in range(7):groups[k][j]+=r[13+j]
 for key,counts in sorted(groups.items()):summary.append([dim,' / '.join(key),*counts])
notes=[['Historical trial attendance'],['Scheduled before 23-Oct-2026; today/future excluded. All years kept separate in monthly rows.'],['Rate = attended / all past booking records, including unresolved and rescheduled records.'],['Exact identical source rows removed; possible repeated sessions retained and flagged, not assumed duplicates.'],['No booking ID provided. Reschedule chains cannot be reliably linked; rates are record-based estimates.'],['Enrolled/interested remain Other; not automatically treated as attended. No cancelled status supplied.'],['Sport uses academy + centre enrollment match, then unique academy sport; unmatched academies stay Unmapped.'],['Sources: input trial workbook, Original!A:Q; enrollment CSV Academy Name, Coaching Center Location, Sports.'],['Source rows',len(rows)],['Exact duplicate rows excluded',sum(r[11] for r in data)],['Today / future records (after exact dedup)',sum(r[10]=='Today / future' and not r[11] for r in data)],['Missing-date records (after exact dedup)',sum(r[10]=='Missing date' and not r[11] for r in data)],['Possible repeated-session records retained',sum(r[12] and not r[11] for r in data)],['Past records with unmapped sport',sum(r[13] and r[3]=='Unmapped' for r in data)]]
(out/'analysis.json').write_text(json.dumps(dict(headers=headers,data=data,summary=summary,notes=notes)),encoding='utf-8')
with (out/'trial_records_mapped.csv').open('w',newline='',encoding='utf-8-sig') as h:wr=csv.writer(h);wr.writerow(headers);wr.writerows(data)
print('PAST TOTALS', [sum(r[13+j] for r in data) for j in range(7)])
print('SPORT SUMMARY',[r for r in summary if r[0]=='Sport'])
print('NOTES',notes[8:])
