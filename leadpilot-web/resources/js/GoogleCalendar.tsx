import React,{useEffect,useMemo,useState} from 'react';

type Event={id:string;title:string;start:string|null;end:string|null;link:string|null;attendees?:string[];related_job?:string|null};
type DateRange='all'|'7'|'30'|'90';

export default function GoogleCalendar({isAdmin}:{isAdmin:boolean}){
 const [clientId,setClientId]=useState('');
 const [clientSecret,setClientSecret]=useState('');
 const [state,setState]=useState<{configured:boolean;connected:boolean}|null>(null);
 const [events,setEvents]=useState<Event[]>([]);
 const [title,setTitle]=useState('');
 const [start,setStart]=useState('');
 const [end,setEnd]=useState('');
 const [meet,setMeet]=useState(true);
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState(false);
 const [historySearch,setHistorySearch]=useState('');
 const [historyRange,setHistoryRange]=useState<DateRange>('all');

 async function load(){
  const r=await fetch('/calendar/status',{headers:{Accept:'application/json'}});
  if(!r.ok){setState(null);return;}
  const d=await r.json();setState(d);
  if(d.connected){const e=await fetch('/calendar/events',{headers:{Accept:'application/json'}});const data=await e.json();if(!e.ok)throw new Error(data.message||'Could not load calendar events.');setEvents(data.events);}
 }
 useEffect(()=>{const result=new URLSearchParams(location.search).get('calendar');if(result==='connected')setMessage('Google Calendar connected.');else if(result==='failed')setMessage('Google Calendar connection failed. Check setup and try again.');else if(result==='cancelled')setMessage('Google Calendar connection was cancelled.');load().catch(e=>setMessage(e.message));},[]);
 async function create(e:React.FormEvent){e.preventDefault();setBusy(true);try{const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/events',{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-TOKEN':token},body:JSON.stringify({title,start:new Date(start).toISOString(),end:new Date(end).toISOString(),create_meet:meet})});const d=await r.json();if(!r.ok)throw new Error(d.message||'Could not create event.');setMessage('Event created in Google Calendar.');setTitle('');await load();}catch(e){setMessage(e instanceof Error?e.message:'Could not create event.');}finally{setBusy(false);}}
 async function configure(e:React.FormEvent){e.preventDefault();setBusy(true);try{const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/configuration',{method:'PUT',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-TOKEN':token},body:JSON.stringify({client_id:clientId,client_secret:clientSecret,redirect_uri:`${location.origin}/calendar/callback`})});if(!r.ok)throw new Error('Could not save calendar setup.');setClientId('');setClientSecret('');setMessage('Calendar setup saved. You can now connect.');await load();}catch(e){setMessage(e instanceof Error?e.message:'Could not save calendar setup.');}finally{setBusy(false);}}
 async function disconnect(){if(!confirm('Disconnect your calendar from LeadPilot?'))return;const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/connection',{method:'DELETE',headers:{Accept:'application/json','X-CSRF-TOKEN':token}});if(!r.ok){setMessage('Could not disconnect.');return;}setEvents([]);setMessage('Disconnected.');await load();}
 const now=Date.now();
 const pastEvents=useMemo(()=>events.filter(event=>event.start&&new Date(event.start).getTime()<Date.now()).sort((a,b)=>new Date(b.start!).getTime()-new Date(a.start!).getTime()),[events]);
 const upcomingEvents=useMemo(()=>events.filter(event=>event.start&&new Date(event.start).getTime()>=Date.now()).sort((a,b)=>new Date(a.start!).getTime()-new Date(b.start!).getTime()),[events]);
 const filteredHistory=useMemo(()=>pastEvents.filter(event=>{
  const date=event.start?new Date(event.start):null;
  if(historyRange!=='all'&&date&&Date.now()-date.getTime()>Number(historyRange)*86400000)return false;
  const query=historySearch.trim().toLowerCase();
  return !query||`${event.title} ${event.attendees?.join(' ')||''} ${event.related_job||''}`.toLowerCase().includes(query);
 }),[pastEvents,historyRange,historySearch]);
 const formatDate=(value:string|null)=>value?new Date(value).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}):'Date unavailable';
 const formatTime=(value:string|null)=>value?new Date(value).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}):'Time unavailable';
 const duration=(event:Event)=>event.start&&event.end?Math.max(0,Math.round((new Date(event.end).getTime()-new Date(event.start).getTime())/60000)):null;
 const table=(items:Event[],emptyText:string)=><div className="calendar-table-wrap"><table className="calendar-history-table"><thead><tr><th>Meeting</th><th>Date &amp; time</th><th>Duration</th><th>With</th><th>Source</th><th>Action</th></tr></thead><tbody>{items.length?items.map(event=><tr key={event.id}><td><strong>{event.title||'Untitled meeting'}</strong><small>Related job: {event.related_job||'—'}</small></td><td>{formatDate(event.start)}<small>{formatTime(event.start)}</small></td><td>{duration(event)!==null?`${duration(event)} min`:'—'}</td><td>{event.attendees?.length?event.attendees.join(', '):'—'}</td><td><span className="calendar-source-label"><img src="/images/google-meet-logo.svg" alt="" aria-hidden="true"/>Google Calendar</span></td><td>{event.link?<a className="calendar-open-link" href={event.link} target="_blank" rel="noreferrer"><img src="/images/google-meet-logo.svg" alt="" aria-hidden="true"/>{event.start&&new Date(event.start).getTime()<Date.now()?'Open event':'Join event'} <span aria-hidden="true">↗</span></a>:<span className="calendar-no-link">No link</span>}</td></tr>):<tr><td className="calendar-table-empty" colSpan={6}>{emptyText}</td></tr>}</tbody></table></div>;

 if(!state)return <section className="crm-workspace"><p role="status">Loading calendar...</p>{message&&<p role="alert">{message}</p>}</section>;
 return <section className="crm-workspace calendar-workspace">
  <div className="crm-heading"><div><span className="crm-eyebrow">YOUR SCHEDULE</span><h2>Meetings</h2><p>Upcoming events and your calendar history.</p></div></div>
  {!state.configured?<>{isAdmin?<form className="profile" onSubmit={configure}><label>Google OAuth client ID<input required value={clientId} onChange={e=>setClientId(e.target.value)}/></label><label>Google OAuth client secret<input type="password" required value={clientSecret} onChange={e=>setClientSecret(e.target.value)}/></label><button disabled={busy}>Save calendar setup</button></form>:<p>Ask your administrator to configure Google Calendar.</p>}</>:!state.connected?<a href="/calendar/connect">Connect your Google Calendar</a>:<>
   <div className="calendar-toolbar"><button type="button" onClick={()=>load().catch(e=>setMessage(e.message))}>Refresh calendar</button><button className="button-secondary" type="button" onClick={disconnect}>Disconnect calendar</button></div>
   <form className="profile calendar-create-form" onSubmit={create}><label>Meeting title<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Start (device time)<input type="datetime-local" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>End (device time)<input type="datetime-local" required value={end} onChange={e=>setEnd(e.target.value)}/></label><label className="calendar-meet-toggle"><input type="checkbox" checked={meet} onChange={e=>setMeet(e.target.checked)}/> Request a Google Meet link</label><button disabled={busy}>{busy?'Creating...':'Create calendar event'}</button></form>
   <section className="calendar-upcoming-section" aria-labelledby="upcoming-meetings-heading"><div className="calendar-final-heading"><div><span className="crm-eyebrow">YOUR SCHEDULE</span><h3 id="upcoming-meetings-heading">Upcoming meetings</h3></div><span className="calendar-history-count">{upcomingEvents.length} events</span></div>{table(upcomingEvents,'No upcoming meetings in this calendar range.')}</section>
   <section className="calendar-history calendar-final-history" aria-labelledby="past-meetings-heading"><div className="calendar-final-heading"><div><span className="crm-eyebrow">MEETING HISTORY</span><h3 id="past-meetings-heading">Past meetings</h3><p>Previous events from your connected calendar.</p></div><span className="calendar-history-count">{filteredHistory.length} events</span></div><div className="calendar-history-filters"><label className="calendar-search"><span className="calendar-search-icon" aria-hidden="true">⌕</span><input type="search" value={historySearch} onChange={e=>setHistorySearch(e.target.value)} placeholder="Search meetings..." aria-label="Search past meetings"/></label><label className="calendar-date-filter"><span className="calendar-date-icon" aria-hidden="true">▦</span><select value={historyRange} onChange={e=>setHistoryRange(e.target.value as DateRange)} aria-label="Filter past meeting dates"><option value="all">All dates</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label></div>{table(filteredHistory,'No past meetings match your search or date filter.')}</section>
   <p className="calendar-range-note">Showing up to 100 events from the past week and next 60 days.</p>
  </>}{message&&<p role="status">{message}</p>}</section>;
}
