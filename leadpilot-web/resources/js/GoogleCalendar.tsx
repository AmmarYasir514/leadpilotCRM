import React,{useEffect,useMemo,useState} from 'react';
import {AppIcon} from './AppIcon';

type Provider='google_meet'|'zoom';
type Event={id:string;title:string;start:string|null;end:string|null;link:string|null;attendees?:string[];related_job?:string|null;provider?:Provider};
type StoredMeeting={id:number;provider:Provider;title:string;starts_at:string|null;ends_at:string|null;attendees?:string[];meeting_url?:string|null};
type DateRange='all'|'7'|'30'|'90';
type VideoChoice='meet'|'zoom'|'none';

export default function GoogleCalendar({isAdmin}:{isAdmin:boolean}){
 const zoomConnected=false;
 const [clientId,setClientId]=useState('');
 const [clientSecret,setClientSecret]=useState('');
 const [state,setState]=useState<{configured:boolean;connected:boolean}|null>(null);
 const [events,setEvents]=useState<Event[]>([]);
 const [storedMeetings,setStoredMeetings]=useState<StoredMeeting[]>([]);
 const [title,setTitle]=useState('');
 const [start,setStart]=useState('');
 const [end,setEnd]=useState('');
 const [video,setVideo]=useState<VideoChoice>('meet');
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState(false);
 const [historySearch,setHistorySearch]=useState('');
 const [historyRange,setHistoryRange]=useState<DateRange>('all');

 async function loadStored(){
  const r=await fetch('/meetings/history',{headers:{Accept:'application/json'}});
  if(!r.ok)return;
  const data=await r.json();
  setStoredMeetings(Array.isArray(data.meetings)?data.meetings:[]);
 }
 async function load(){
  const r=await fetch('/calendar/status',{headers:{Accept:'application/json'}});
  if(!r.ok){setState(null);return;}
  const d=await r.json();setState(d);
  await loadStored();
  if(d.connected){const e=await fetch('/calendar/events',{headers:{Accept:'application/json'}});const data=await e.json();if(!e.ok)throw new Error(data.message||'Could not load calendar events.');setEvents(data.events);}
  else{setEvents([]);}
 }
 useEffect(()=>{const result=new URLSearchParams(location.search).get('calendar');if(result==='connected')setMessage('Google Calendar connected.');else if(result==='failed')setMessage('Google Calendar connection failed. Check setup and try again.');else if(result==='cancelled')setMessage('Google Calendar connection was cancelled.');load().catch(e=>setMessage(e.message));},[]);
 async function create(e:React.FormEvent){e.preventDefault();setBusy(true);try{const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/events',{method:'POST',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-TOKEN':token},body:JSON.stringify({title,start:new Date(start).toISOString(),end:new Date(end).toISOString(),create_meet:video==='meet'})});const d=await r.json();if(!r.ok)throw new Error(d.message||'Could not create event.');setMessage('Event created in Google Calendar.');setTitle('');await load();}catch(e){setMessage(e instanceof Error?e.message:'Could not create event.');}finally{setBusy(false);}}
 async function configure(e:React.FormEvent){e.preventDefault();setBusy(true);try{const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/configuration',{method:'PUT',headers:{Accept:'application/json','Content-Type':'application/json','X-CSRF-TOKEN':token},body:JSON.stringify({client_id:clientId,client_secret:clientSecret,redirect_uri:`${location.origin}/calendar/callback`})});if(!r.ok)throw new Error('Could not save calendar setup.');setClientId('');setClientSecret('');setMessage('Calendar setup saved. You can now connect.');await load();}catch(e){setMessage(e instanceof Error?e.message:'Could not save calendar setup.');}finally{setBusy(false);}}
 async function disconnect(){if(!confirm('Disconnect your calendar from LeadPilot?'))return;const token=document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content??'';const r=await fetch('/calendar/connection',{method:'DELETE',headers:{Accept:'application/json','X-CSRF-TOKEN':token}});if(!r.ok){setMessage('Could not disconnect.');return;}setEvents([]);setMessage('Disconnected.');await load();}
 const storedEvents=useMemo(()=>storedMeetings.map(meeting=>({id:'stored-'+meeting.id,title:meeting.title,start:meeting.starts_at,end:meeting.ends_at,link:meeting.meeting_url??null,attendees:meeting.attendees,related_job:null,provider:meeting.provider})),[storedMeetings]);
 const upcomingEvents=useMemo(()=>events.filter(event=>event.start&&new Date(event.start).getTime()>=Date.now()).sort((a,b)=>new Date(a.start!).getTime()-new Date(b.start!).getTime()),[events]);
 const pastEvents=useMemo(()=>{
  const fromCalendar=events.filter(event=>event.start&&new Date(event.start).getTime()<Date.now()).map(event=>({...event,provider:event.provider??'google_meet' as const}));
  const calendarIds=new Set(fromCalendar.map(event=>event.id));
  const fromStored=storedEvents.filter(event=>event.start&&new Date(event.start).getTime()<Date.now()&&!calendarIds.has(event.id));
  return [...fromCalendar,...fromStored].sort((a,b)=>new Date(b.start!).getTime()-new Date(a.start!).getTime());
 },[events,storedEvents]);
 const filteredHistory=useMemo(()=>pastEvents.filter(event=>{
  const date=event.start?new Date(event.start):null;
  if(historyRange!=='all'&&date&&Date.now()-date.getTime()>Number(historyRange)*86400000)return false;
  const query=historySearch.trim().toLowerCase();
  return !query||`${event.title} ${event.attendees?.join(' ')||''} ${event.related_job||''} ${event.provider==='zoom'?'zoom':'google meet'}`.toLowerCase().includes(query);
 }),[pastEvents,historyRange,historySearch]);
 const formatDate=(value:string|null)=>value?new Date(value).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'}):'Date unavailable';
 const formatTime=(value:string|null)=>value?new Date(value).toLocaleTimeString(undefined,{hour:'numeric',minute:'2-digit'}):'Time unavailable';
 const duration=(event:Event)=>event.start&&event.end?Math.max(0,Math.round((new Date(event.end).getTime()-new Date(event.start).getTime())/60000)):null;
 const source=(event:Event)=>event.provider==='zoom'
  ? <span className="calendar-source-label"><img src="/images/zoom-icon.svg" alt="" aria-hidden="true"/>Zoom</span>
  : <span className="calendar-source-label"><img src="/images/google-meet-logo.svg" alt="" aria-hidden="true"/>Google Meet</span>;
 const historyEmpty=historySearch||historyRange!=='all'?'No past meetings match your search or date filter.':'No Google Meet or Zoom meetings yet';
 const table=(items:Event[],emptyText:string)=><div className="calendar-table-wrap"><table className="calendar-history-table"><thead><tr><th>Meeting</th><th>Date &amp; time</th><th>Duration</th><th>With</th><th>Source</th><th>Action</th></tr></thead><tbody>{items.length?items.map(event=><tr key={event.id}><td><strong>{event.title||'Untitled meeting'}</strong><small>Related job: {event.related_job||'—'}</small></td><td>{formatDate(event.start)}<small>{formatTime(event.start)}</small></td><td>{duration(event)!==null?`${duration(event)} min`:'—'}</td><td>{event.attendees?.length?event.attendees.join(', '):'—'}</td><td>{source(event)}</td><td>{event.link?<a className="calendar-open-link" href={event.link} target="_blank" rel="noreferrer">{event.provider==='zoom'?<img src="/images/zoom-icon.svg" alt="" aria-hidden="true"/>:<img src="/images/google-meet-logo.svg" alt="" aria-hidden="true"/>}{event.start&&new Date(event.start).getTime()<Date.now()?'Open event':'Join event'} <span aria-hidden="true">↗</span></a>:<span className="calendar-no-link">No link</span>}</td></tr>):<tr><td className="calendar-table-empty" colSpan={6}>{emptyText}</td></tr>}</tbody></table></div>;

 if(!state)return <section className="crm-workspace"><p role="status">Loading calendar...</p>{message&&<p role="alert">{message}</p>}</section>;
 return <section className="crm-workspace calendar-workspace">
  <div className="crm-heading"><div><span className="crm-eyebrow">YOUR SCHEDULE</span><h2 className="heading-with-icon"><AppIcon name="meetings"/>Meetings</h2><p>Upcoming events and your calendar history.</p></div></div>
  <div className="meeting-connect-cards">
   <article className="meeting-connect-card">
    <div className="meeting-connect-head">
     <img src="/images/google-meet-logo.svg" alt="" aria-hidden="true"/>
     <div><h3>Google Meet</h3><p>Uses your Google Calendar connection.</p></div>
     <span className={state.connected?'meeting-status is-connected':'meeting-status'}>{state.connected?'Connected':'Not connected'}</span>
    </div>
    {state.connected?<button type="button" className="button-secondary" onClick={disconnect}>Disconnect</button>:state.configured?<a href="/calendar/connect" className="button">Connect Google Meet</a>:isAdmin?<p>Save the Google Calendar setup below, then connect.</p>:<p>Ask your administrator to configure Google Calendar.</p>}
   </article>
   <article className="meeting-connect-card">
    <div className="meeting-connect-head">
     <img src="/images/zoom-icon.svg" alt="" aria-hidden="true"/>
     <div><h3>Zoom</h3><p>Connect Zoom to add it as a meeting option.</p></div>
     <span className="meeting-status">Not connected</span>
    </div>
    <button type="button" disabled>Connect Zoom</button>
    <small>Zoom connection is not available yet.</small>
   </article>
  </div>
  {!state.configured&&isAdmin&&<form className="profile" onSubmit={configure}><label>Google OAuth client ID<input required value={clientId} onChange={e=>setClientId(e.target.value)}/></label><label>Google OAuth client secret<input type="password" required value={clientSecret} onChange={e=>setClientSecret(e.target.value)}/></label><button disabled={busy}>Save calendar setup</button></form>}
  {state.connected&&<>
   <div className="calendar-toolbar"><button type="button" className="action-with-icon" onClick={()=>load().catch(e=>setMessage(e.message))}><AppIcon name="refresh"/>Refresh calendar</button><button className="button-secondary" type="button" onClick={disconnect}>Disconnect calendar</button></div>
   <form className="profile calendar-create-form" onSubmit={create}><label>Meeting title<input required value={title} onChange={e=>setTitle(e.target.value)}/></label><label>Start (device time)<input type="datetime-local" required value={start} onChange={e=>setStart(e.target.value)}/></label><label>End (device time)<input type="datetime-local" required value={end} onChange={e=>setEnd(e.target.value)}/></label><fieldset className="calendar-video-choice"><legend>Video conference</legend><label><input type="radio" name="video-conference" checked={video==='meet'} onChange={()=>setVideo('meet')}/> Google Meet</label><label className={zoomConnected?'':'is-disabled'}><input type="radio" name="video-conference" checked={video==='zoom'} disabled={!zoomConnected} onChange={()=>setVideo('zoom')}/> Zoom{!zoomConnected&&<small>Connect Zoom first</small>}</label><label><input type="radio" name="video-conference" checked={video==='none'} onChange={()=>setVideo('none')}/> None</label></fieldset><button disabled={busy}>{busy?'Creating...':'Create calendar event'}</button></form>
   <section className="calendar-upcoming-section" aria-labelledby="upcoming-meetings-heading"><div className="calendar-final-heading"><div><span className="crm-eyebrow">YOUR SCHEDULE</span><h3 id="upcoming-meetings-heading" className="heading-with-icon"><AppIcon name="upcoming"/>Upcoming meetings</h3></div><span className="calendar-history-count">{upcomingEvents.length} events</span></div>{table(upcomingEvents,'No upcoming meetings in this calendar range.')}</section>
  </>}
  <section className="calendar-history calendar-final-history" aria-labelledby="past-meetings-heading"><div className="calendar-final-heading"><div><span className="crm-eyebrow">MEETING HISTORY</span><h3 id="past-meetings-heading" className="heading-with-icon"><AppIcon name="events"/>Past meetings</h3><p>Previous Google Meet events from your calendar, plus any saved Zoom meetings.</p></div><span className="calendar-history-count">{filteredHistory.length} events</span></div><div className="calendar-history-filters"><label className="calendar-search"><span className="calendar-search-icon" aria-hidden="true"><AppIcon name="findjobs"/></span><input type="search" value={historySearch} onChange={e=>setHistorySearch(e.target.value)} placeholder="Search meetings..." aria-label="Search past meetings"/></label><label className="calendar-date-filter"><span className="calendar-date-icon" aria-hidden="true"><AppIcon name="meetings"/></span><select value={historyRange} onChange={e=>setHistoryRange(e.target.value as DateRange)} aria-label="Filter past meeting dates"><option value="all">All dates</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select></label></div>{table(filteredHistory,historyEmpty)}</section>
  {state.connected&&<p className="calendar-range-note">Showing up to 100 Google Calendar events from the past week and next 60 days, plus any saved Zoom meetings.</p>}
  {message&&<p role="status">{message}</p>}
 </section>;
}