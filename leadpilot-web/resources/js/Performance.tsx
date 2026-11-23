import React, {useEffect, useState} from 'react';
import Targets from './Targets';
import VisualSalesReport from './VisualSalesReport';
type Employee = {id:number; name:string; status:string};
export default function Performance({canManage}: {canManage:boolean}) {
    const [employees, setEmployees] = useState<Employee[]>([]); const [selected, setSelected] = useState<Employee | null>(null); const [page, setPage] = useState(1); const [last, setLast] = useState(1); const [error, setError] = useState('');
    useEffect(() => { const controller = new AbortController(); fetch(`/admin/performance/employees?page=${page}`, {headers:{Accept:'application/json'},signal:controller.signal}).then(async r => {if (!r.ok) throw new Error('Could not load employees.'); return r.json();}).then(data => {setEmployees(data.data);setLast(data.last_page);}).catch(e=>{if (e.name !== 'AbortError') setError(e.message);}); return () => controller.abort(); }, [page]);
    return <><VisualSalesReport/><details><summary>Employee targets and performance</summary><section><h2>Employee performance</h2><p>Select an employee to view their targets.</p>{error && <p role="alert">{error}</p>}{employees.map(employee=><div key={employee.id}><button className="link" onClick={()=>setSelected(employee)}>{employee.name}</button> {employee.status}</div>)}<button className="link" disabled={page<=1} onClick={()=>setPage(page-1)}>Previous employees</button> Page {page} of {last} <button className="link" disabled={page>=last} onClick={()=>setPage(page+1)}>Next employees</button>{selected && <><h3>{selected.name}</h3><Targets key={selected.id} employeeId={selected.id} canManage={canManage} /></>}</section></details></>;
}
