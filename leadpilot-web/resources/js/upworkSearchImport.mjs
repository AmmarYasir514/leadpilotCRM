export function parseUpworkSearchUrl(input) {
 let url; try { url=new URL(input.trim()); } catch { throw new Error('Enter a valid Upwork search URL.'); }
 if(url.protocol!=='https:' || !['upwork.com','www.upwork.com'].includes(url.hostname) || !/^\/nx\/search\/jobs\/?$/.test(url.pathname)) throw new Error('Use an Upwork job search URL.');
 const p=url.searchParams; const regions=(p.get('location')||'').split(',').filter(Boolean).map(v=>{try{return decodeURIComponent(v)}catch{return v}});
 const fixed=(p.get('amount')||'').split(',').filter(Boolean);const hours=p.get('hourly_rate')||'';const hourly=/^(\d+(?:\.\d+)?)-$/.exec(hours);
 const warnings=[]; if(hours&&!hourly)warnings.push('Hourly range cannot be applied automatically.');if(fixed.some(x=>!/^\d+-\d+$/.test(x)))warnings.push('Some fixed budget ranges cannot be applied.');
 const unknown=[...new Set([...p.keys()].filter(k=>!['q','amount','hourly_rate','client_hires','contractor_tier','jobs_feed','location','payment_verified','previous_clients','proposals','sort','t'].includes(k)))];if(unknown.length)warnings.push('Additional URL fields need review: '+unknown.join(', '));
 return {query:p.get('q')||'',fixedRanges:fixed.filter(x=>/^\d+-\d+$/.test(x)),hourlyMinimum:hourly?.[1]||'',regions,hires:p.get('client_hires')||'',proposals:p.get('proposals')||'',experience:p.get('contractor_tier')||'',verified:p.get('payment_verified')==='1',sort:p.get('sort')||'',jobTypes:p.get('t')||'',warnings};
}
