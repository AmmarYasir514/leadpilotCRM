import React,{useEffect,useState} from 'react';
export default function JobCapture({onImport}:{onImport:(data:{title:string;description:string;budget:string;skills:string[];posted:string;proposals:string;lastViewed:string;interviewing:string;invitesSent:string;unansweredInvites:string;url:string})=>void}){
 const [url,setUrl]=useState('');const [text,setText]=useState('');const [error,setError]=useState('');const [loading,setLoading]=useState(false);const [manualOpen,setManualOpen]=useState(false);
 function openJob(){try{const u=new URL(url.trim());if(u.protocol!=='https:'||!['upwork.com','www.upwork.com'].includes(u.hostname)||!/^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(u.pathname))throw new Error('Enter a valid Upwork job link.');window.open(u.toString(),'_blank','noopener,noreferrer');setError('Copy the visible job details, then paste them below.');}catch(e){setError(e instanceof Error?e.message:'Invalid link.');}}
 function parse(input:string, sourceUrl=url){
  const lines=input.split(/\r?\n/).map(s=>s.trim()).filter(Boolean);
  if(!lines.length){setError('Paste the copied job text first.');return;}
  const postedIndex=lines.findIndex(s=>/^posted\b/i.test(s));
  const skip=/^(upwork|find work|job details|save job|flag as inappropriate|search|messages|notifications|back|share job)$/i;
  const candidates=postedIndex>0?lines.slice(0,postedIndex).reverse():lines;
  const title=candidates.find(s=>!skip.test(s)&&!/^https?:\/\//i.test(s))||'';
  let start=postedIndex>=0?postedIndex+1:Math.max(0,lines.indexOf(title)+1);
  const metadata=/^(worldwide|remote|summary|description|job description|show more|show less)$/i;
  while(start<lines.length&&metadata.test(lines[start]))start++;
  const stop=/^(?:worldwide|remote|hourly|fixed[- ]price|intermediate|expert|entry level|project type|skills and expertise|job budget:.*|required skills:.*|activity on this job|about the client|screening questions|you will be asked.*|questions from (?:the )?client|client.s recent history|job details|proposals:.*|(?:less|more) than \d+.*|\d+\s*(?:hrs|hours)\/week.*|[$€£]\s*\d[\d,.]*(?:\s*(?:-|–|to)\s*[$€£]?\s*\d[\d,.]*)?)$/i;
  const end=lines.findIndex((line,index)=>index>=start&&stop.test(line));
  const description=lines.slice(start,end<0?lines.length:end).join('\n').slice(0,20000);
  if(!description.trim()){setError('Could not find the job description. Open the job and use the manual paste option, then check the details.');return;}
  const activity=lines.findIndex(s=>/^activity on this job/i.test(s));
  const skillsIndex=lines.findIndex(s=>/^(skills and expertise|required skills)\s*:?$/i.test(s));
  const skills:string[]=[];
  if(skillsIndex>=0){for(const line of lines.slice(skillsIndex+1)){if(/^(activity on this job|about the client|client.s recent history|screening questions|you will be asked|preferred qualifications|job activity|proposals:)\b/i.test(line))break;if(!/^(mandatory skills|preferred skills|skills|tools|other|show more|show less)$/i.test(line)&&line.length<=100&&skills.length<30)skills.push(line);}}
  const explicitBudget=lines.find(s=>/^job budget:\s*/i.test(s));
  const metadataEnd=skillsIndex>=0?skillsIndex:activity>=0?activity:lines.length;
  const metadataLines=end<0?[]:lines.slice(end,metadataEnd);
  const currency=/(?:[$€£]\s*\d[\d,.]*(?:\s*(?:-|–|to)\s*[$€£]?\s*\d[\d,.]*)?)/i;
  const amountIndex=metadataLines.findIndex(line=>currency.test(line));
  let budget=explicitBudget?.replace(/^job budget:\s*/i,'').trim()||'';
  if(!budget&&amountIndex>=0){budget=metadataLines[amountIndex].match(currency)?.[0]||'';if(metadataLines[amountIndex+1]==='-'&&currency.test(metadataLines[amountIndex+2]||''))budget+=' - '+metadataLines[amountIndex+2].match(currency)?.[0];const type=metadataLines.find(line=>/^(hourly|fixed[- ]price)$/i.test(line));if(type)budget+=' ('+type+')';}
  const activityLines=activity>=0?lines.slice(activity+1):[];
  const value=(label:RegExp)=>{const i=activityLines.findIndex(line=>label.test(line));if(i<0)return '';const inline=activityLines[i].replace(label,'').replace(/^\s*[:\-]\s*/,'').trim();return (inline||activityLines[i+1]||'').slice(0,120);};
  onImport({title:title.slice(0,255),description,budget,skills,posted:postedIndex<0?'':lines[postedIndex].replace(/^posted\s*/i,'').slice(0,120),proposals:value(/^proposals\s*:?/i),lastViewed:value(/^last viewed by client\s*:?/i),interviewing:value(/^interviewing\s*:?/i),invitesSent:value(/^invites sent\s*:?/i),unansweredInvites:value(/^unanswered invites\s*:?/i),url:sourceUrl});
  setError('Job details imported. Please review them before writing.');
 }
 async function pasteAndExtract(){try{const copied=await navigator.clipboard.readText();if(!copied.trim()){setError('Clipboard is empty. Copy the job details first.');return;}if(copied.length>40000){setError('Copied text is longer than 40,000 characters. Copy a shorter selection.');return;}setText(copied);parse(copied);}catch{setError('Clipboard access was unavailable. Paste the copied job text below and select Extract job details.');}}
 function automaticImport(jobUrl=url){if(loading)return;let parsed:URL;try{parsed=new URL(jobUrl.trim());if(parsed.protocol!=='https:'||!['upwork.com','www.upwork.com'].includes(parsed.hostname)||!/^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(parsed.pathname)||!/~0?[0-9]{10,}/.test(parsed.href))throw new Error('Enter a valid Upwork job link.');}catch{setError('Enter a valid Upwork job link.');return;}const requestId=crypto.randomUUID();setLoading(true);setError('Opening the job and reading its visible details. This requires the LeadPilot browser extension.');let timer:number;const receive=(event:MessageEvent)=>{if(event.source!==window||event.origin!==location.origin||event.data?.type!=='leadpilot-job-import-result'||event.data.requestId!==requestId)return;window.clearTimeout(timer);window.removeEventListener('message',receive);setLoading(false);if(typeof event.data.text==='string'&&event.data.text.trim()){parse(event.data.text,parsed.toString());}else setError(event.data.error||'Could not read the job.');};window.addEventListener('message',receive);timer=window.setTimeout(()=>{window.removeEventListener('message',receive);setLoading(false);setError('No response from the browser extension. Check that it is installed and enabled in this browser, then try again.');},35000);window.postMessage({type:'leadpilot-job-import-request',requestId,url:parsed.toString()},location.origin);}
 useEffect(()=>{
  const token=new URLSearchParams(location.hash.slice(1)).get('leadpilot-import');
  if(!token||!/^[0-9a-f-]{36}$/i.test(token))return;
  const receive=(event:MessageEvent)=>{if(event.source!==window||event.origin!==location.origin||event.data?.type!=='leadpilot-open-job-result'||event.data.token!==token)return;window.removeEventListener('message',receive);window.clearTimeout(timer);history.replaceState(null,'',location.pathname+location.search);if(typeof event.data.url==='string'){setUrl(event.data.url);automaticImport(event.data.url);}else setError(event.data.error||'Could not receive the job from the extension.');};
  window.addEventListener('message',receive);
  const timer=window.setTimeout(()=>{window.removeEventListener('message',receive);setError('Could not connect to the extension. Reload the extension, then import the job again.');},5000);
  window.postMessage({type:'leadpilot-open-job-request',token},location.origin);
  return ()=>{window.removeEventListener('message',receive);window.clearTimeout(timer);};
 },[]);
 return <div className="job-capture">
  <div className="job-capture-heading"><div><span className="writer-step">OPTIONAL / IMPORT</span><h3>Bring in a job</h3><p>Paste an Upwork job link to import its details into your workspace.</p></div><span className="job-source">UPWORK</span></div>
  <label>Upwork job URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://www.upwork.com/jobs/..."/></label>
  <div className="writer-actions"><button type="button" disabled={loading} onClick={()=>automaticImport()}>{loading?<><span className="import-spinner" aria-hidden="true"/> Importing job...</>:"Import job"}</button><button className="writer-secondary" type="button" onClick={openJob}>Open job only</button></div>
  <p className="writer-hint">Keep your Upwork account signed in in this browser while the job is imported.</p>
  {error&&<p className="writer-notice" role="status">{error}</p>}
  <details className="writer-manual" open={manualOpen} onToggle={event=>setManualOpen(event.currentTarget.open)}><summary><span>Having trouble? Paste job details manually</span><span className="writer-summary-toggle" aria-label={manualOpen?'Collapse manual paste':'Expand manual paste'}><b>+</b></span></summary><p>Copy the job text from Upwork, then paste and extract it here.</p><button className="writer-secondary" type="button" onClick={pasteAndExtract}>Paste and extract job details</button><label>Copied job page<textarea rows={5} maxLength={40000} value={text} onChange={e=>setText(e.target.value)}/></label><button className="writer-secondary" type="button" onClick={()=>parse(text)}>Extract job details</button></details>
 </div>;
}
