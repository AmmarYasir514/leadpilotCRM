import React, {useEffect, useState} from 'react';

export default function ActivitySettings({timezone, isAdmin, onTimezone}: {timezone: string; isAdmin: boolean; onTimezone: (value: string) => void}) {
    const [zone, setZone] = useState(timezone || 'UTC');
    const detectedZone=Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const zoneOptions=Array.from(new Set(['UTC','Asia/Karachi',zone,detectedZone,...(typeof (Intl as any).supportedValuesOf==='function'?(Intl as any).supportedValuesOf('timeZone'):['Europe/London','America/New_York','Asia/Dubai'])])).sort() as string[];
    const [days, setDays] = useState('');
    const [message, setMessage] = useState('');
    const token = document.querySelector<HTMLMetaElement>('meta[name="csrf-token"]')?.content ?? '';
    useEffect(() => { if (isAdmin) fetch('/admin/activity-retention', {headers: {Accept: 'application/json'}}).then(r => r.ok ? r.json() : Promise.reject()).then(data => setDays(data.days == null ? '' : String(data.days))).catch(() => setMessage('Could not load retention settings.')); }, [isAdmin]);
    async function save(path: string, payload: object) {
        setMessage('');
        const response = await fetch(path, {method: 'PUT', headers: {'Content-Type': 'application/json', Accept: 'application/json', 'X-CSRF-TOKEN': token}, body: JSON.stringify(payload)});
        const result = await response.json();
        if (!response.ok) throw new Error(Object.values(result.errors ?? {}).flat().join(' ') || result.message || 'Could not save settings.');
        return result;
    }
    return <section><h2>Workspace preferences</h2><form className="create" onSubmit={async e => {e.preventDefault(); try {await save('/account/timezone', {timezone: zone}); onTimezone(zone); setMessage('Timezone saved.');} catch (error) {setMessage(error instanceof Error ? error.message : 'Could not save timezone.');}}}><label>Timezone<select value={zone} onChange={e=>setZone(e.target.value)}>{zoneOptions.map(value=><option key={value} value={value}>{value}</option>)}</select></label><button type="button" className="timezone-detect" onClick={()=>{setZone(detectedZone);setMessage(`System timezone selected: ${detectedZone}. Save to apply.`)}}>Use system timezone</button><button>Save changes</button></form><p>Use a timezone name such as Asia/Karachi. Activity filters and the security activity table use your selected timezone.</p>
    {isAdmin && <form className="create" onSubmit={async e => {e.preventDefault(); if (days && !window.confirm(`Automatically remove routine login and logout records older than ${days} days?`)) return; try {await save('/admin/activity-retention', {days: days ? Number(days) : null}); setMessage('Retention saved.');} catch (error) {setMessage(error instanceof Error ? error.message : 'Could not save retention.');}}}><label>Keep routine login/logout events for days<input type="number" min="30" max="3650" value={days} onChange={e => setDays(e.target.value)} placeholder="Keep indefinitely" /></label><button>Save retention</button></form>}{isAdmin && <p>Blank keeps all records. A value removes only old routine login and logout events when scheduled maintenance is running; security and administrative events remain.</p>}{message && <p role="status">{message}</p>}</section>;
}
