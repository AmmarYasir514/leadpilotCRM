import Targets from './Targets';
import React, { useEffect, useState } from 'react';

type Employee = {id: number; name: string; status: string; team_id: number | null; last_activity_at: string | null};
type Profile = {employee: Employee & {email: string; job_title: string | null; department: string | null; joining_date: string | null; last_login_at: string | null}; recent_activity: {action: string; created_at: string}[]};
type Data = {total_users: number; active_users: number; suspended_users: number; active_today: number; signed_in_today: number; recorded_events_in_range: number | null; total_leads: number; leads_added_today: number; total_proposals: number; proposals_submitted_today: number; deals_won:number; deals_lost:number; closed_value_by_currency:{currency:string;cents:string}[]; teams: {id: number; name: string}[]; employees: {data: Employee[]; current_page: number; last_page: number}};
const unavailable = ['Follow-ups due', 'Overdue follow-ups', 'Meetings scheduled', 'Interviews booked', 'Monthly sales target', 'Team conversion rate'];

export default function Dashboard({timezone}: {timezone: string}) {
    const formatTime = (value: string) => new Date(value.includes('T') ? value : value.replace(' ', 'T') + 'Z').toLocaleString(undefined, {timeZone: timezone});
    const [data, setData] = useState<Data | null>(null);
    const [team, setTeam] = useState('');
    const [employeeId, setEmployeeId] = useState('');
    const [page, setPage] = useState(1);
    const [selected, setSelected] = useState<Employee | null>(null);
    const [profile, setProfile] = useState<Profile | null>(null);
    const [from, setFrom] = useState(''); const [to, setTo] = useState('');
    const [range, setRange] = useState<{from: string; to: string} | null>(null);
    const [error, setError] = useState('');
    useEffect(() => {
        const params = new URLSearchParams({page: String(page)});
        if (team) params.set('team_id', team);
        if (employeeId) params.set('user_id', employeeId);
        if (range) { params.set('from', range.from); params.set('to', range.to); }
        const controller = new AbortController();
        setError('');
        fetch(`/admin/dashboard?${params}`, {headers: {Accept: 'application/json'}, signal: controller.signal})
            .then(async response => { if (!response.ok) throw new Error('Dashboard could not be loaded.'); return response.json(); })
            .then(setData).catch(reason => { if (reason.name !== 'AbortError') setError(reason.message); });
        return () => controller.abort();
    }, [team, employeeId, page, range, timezone]);
    useEffect(() => {
        setProfile(null);
        if (!selected) return;
        const controller = new AbortController();
        fetch(`/admin/dashboard/employees/${selected.id}`, {headers: {Accept: 'application/json'}, signal: controller.signal})
            .then(async response => { if (!response.ok) throw new Error('Employee profile could not be loaded.'); return response.json(); })
            .then(setProfile).catch(reason => { if (reason.name !== 'AbortError') setError(reason.message); });
        return () => controller.abort();
    }, [selected]);
    return <section><h2>Super Admin dashboard</h2><p>User counts are current. Activity today means a recorded request today, not time worked.</p>
        {error && <p role="alert">{error}</p>}
        {data ? <><label>Team<select value={team} onChange={e => {setTeam(e.target.value); setEmployeeId(''); setPage(1); setSelected(null);}}><option value="">All teams</option>{data.teams.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>{employeeId && <p>Showing one employee. <button type="button" className="link" onClick={() => {setEmployeeId(''); setPage(1); setSelected(null);}}>Show all employees</button></p>}
        <div className="table"><table><thead><tr><th>Total users</th><th>Active accounts</th><th>Suspended accounts</th><th>Active today</th><th>Signed in today</th></tr></thead><tbody><tr><td>{data.total_users}</td><td>{data.active_users}</td><td>{data.suspended_users}</td><td>{data.active_today}</td><td>{data.signed_in_today}</td></tr></tbody></table></div>
        <form className="create" onSubmit={e => {e.preventDefault(); setRange({from, to});}}><label>Activity from (my timezone)<input type="date" value={from} onChange={e => setFrom(e.target.value)} required /></label><label>Activity to (my timezone)<input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} required /></label><button>Apply date range</button><button type="button" className="link" onClick={() => {setFrom(''); setTo(''); setRange(null);}}>Clear</button></form>{data.recorded_events_in_range !== null && <p>Recorded audit events in selected range: {data.recorded_events_in_range}. User counts above are current; this count includes recorded security and administration events only.</p>}
        <h3>Leads across the workspace</h3><p>Total leads: {data.total_leads}. Leads added today: {data.leads_added_today}. These totals cover the whole workspace and do not use the team or employee filter.</p><h3>Proposals across the workspace</h3><p>Total proposals: {data.total_proposals}. Manually marked submitted today: {data.proposals_submitted_today}. These totals cover the whole workspace.</p><h3>Deals across the workspace</h3><p>Won: {data.deals_won}; lost: {data.deals_lost}. Agreed closed project value by currency:</p>{data.closed_value_by_currency.length?<ul>{data.closed_value_by_currency.map(row=><li key={row.currency}>{row.currency} {String(BigInt(row.cents)/100n)}.{String(BigInt(row.cents)%100n).padStart(2,"0")}</li>)}</ul>:<p>No closed project value recorded.</p>}<p>Workspace totals do not use the team or employee filter.</p><h3>Employees</h3><div className="table"><table><thead><tr><th>Employee</th><th>Status</th><th>Last recorded activity</th><th>Performance</th></tr></thead><tbody>{data.employees.data.map(employee => <tr key={employee.id}><td><button className="link" onClick={() => setSelected(employee)}>{employee.name}</button></td><td>{employee.status}</td><td>{employee.last_activity_at ? formatTime(employee.last_activity_at) : 'Not recorded'}</td><td>Open profile for available metrics</td></tr>)}</tbody></table></div>
        <button className="link" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button> Page {data.employees.current_page} of {data.employees.last_page} <button className="link" disabled={page >= data.employees.last_page} onClick={() => setPage(page + 1)}>Next</button>
        {selected && <div><h3>{selected.name}</h3><Targets key={selected.id} employeeId={selected.id} />{profile ? <><p>{profile.employee.email} · {profile.employee.job_title || 'Job title not set'} · {profile.employee.department || 'Department not set'}</p><p>Status: {profile.employee.status}. Available sales summary appears below; additional metrics need their source modules.</p><h4>Recent recorded activity</h4>{profile.recent_activity.length ? <ul>{profile.recent_activity.map((item, index) => <li key={index}>{item.action} — {formatTime(item.created_at)}</li>)}</ul> : <p>No recorded activity.</p>}</> : <p>Loading profile...</p>}<button className="link" onClick={() => {setEmployeeId(String(selected.id)); setPage(1);}}>Filter to this employee</button><button className="link" onClick={() => setSelected(null)}>Close</button></div>}</> : !error && <p>Loading dashboard...</p>}
        <h3>Sales and performance metrics</h3><p>These figures will become available when their respective modules are implemented.</p><div className="table"><table><tbody>{unavailable.map(metric => <tr key={metric}><th>{metric}</th><td>Not available yet</td></tr>)}</tbody></table></div>
    </section>;
}
