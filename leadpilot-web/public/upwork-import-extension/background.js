function jobId(url) {
    return url.match(/~0?([0-9]{10,})/)?.[1] ?? null;
}

function submittedProposalId(rawUrl) {
    try {
        const url = new URL(rawUrl);
        if (url.protocol !== 'https:' || !['upwork.com', 'www.upwork.com'].includes(url.hostname) || !url.searchParams.has('success')) return null;
        return url.pathname.match(/^\/nx\/proposals\/(\d+)\/?$/)?.[1] ?? null;
    } catch {
        return null;
    }
}

function submittedProposalDetails(text) {
    const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const section = (label, stops) => {
        const start = lines.findIndex(line => label.test(line));
        if (start < 0) return '';
        const end = lines.findIndex((line, index) => index > start && stops.test(line));
        return lines.slice(start + 1, end < 0 ? lines.length : end).join('\n').trim();
    };
    const title = section(/^job details\s*:?$/i, /^(posted\b|job description|summary|view job posting|skills and expertise|cover letter)\b/i).split('\n')[0] || '';
    const coverLetter = section(/^cover letter\s*:?$/i, /^(edit proposal|withdraw proposal|job details|your proposed terms|attachments|questions from the client|about the client|messages|privacy|terms of service|\u00a9)\b/i);
    const posted = lines.findIndex(line => /^posted\b/i.test(line));
    const end = lines.findIndex((line, index) => index > posted && /^(view job posting|skills and expertise|activity on this job|about the client|cover letter|your proposed terms)\b/i.test(line));
    const description = posted < 0 ? '' : lines.slice(posted + 1, end < 0 ? lines.length : end).filter(line => !/^(worldwide|summary|remote)$/i.test(line)).join('\n');
    const skills = section(/^skills and expertise\s*:?$/i, /^(your proposed terms|how do you want|activity on this job|about the client|cover letter|view job posting)\b/i);
    const budget = text.match(/(?:client.s budget|total price of project)[\s\S]{0,100}?([$€£]\s*[\d,.]+(?:\s*(?:-|–|to)\s*[$€£]?\s*[\d,.]+)?)/i)?.[1] ?? '';
    return { title: title.slice(0, 255), coverLetter: coverLetter.slice(0, 30000), description: description.slice(0, 20000), notes: [budget && 'Budget: ' + budget, skills && 'Skills: ' + skills].filter(Boolean).join('\n').slice(0, 10000) };
}

function jobTextOnly(text) {
    const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean);
    const posted = lines.findIndex(line => /^posted\b/i.test(line));
    if (posted < 1) return '';
    const skip = /^(upwork|find work|job details|save job|flag as inappropriate|search|messages|notifications|back|share job)$/i;
    const title = lines.slice(0, posted).reverse().find(line => !skip.test(line) && !/^https?:\/\//i.test(line));
    let start = posted + 1;
    const metadata = /^(worldwide|remote|summary|description|job description|show more|show less)$/i;
    while (start < lines.length && metadata.test(lines[start])) start++;
    const boundary = /^(?:worldwide|remote|hourly|fixed[- ]price|intermediate|expert|entry level|project type|skills and expertise|activity on this job|about the client|screening questions|you will be asked.*|questions from (?:the )?client|client.s recent history|job details|proposals:.*|(?:less|more) than \d+.*|\d+\s*(?:hrs|hours)\/week.*|[$€£]\s*\d[\d,.]*(?:\s*(?:-|–|to)\s*[$€£]?\s*\d[\d,.]*)?)$/i;
    const end = lines.findIndex((line, index) => index >= start && boundary.test(line));
    const description = lines.slice(start, end < 0 ? lines.length : end);
    const skillsIndex = lines.findIndex(line => /^skills and expertise\s*:?$/i.test(line));
    const budgetEnd = skillsIndex >= 0 ? skillsIndex : lines.findIndex((line, index) => index >= start && /^(activity on this job|about the client|screening questions)$/i.test(line));
    const metadataLines = end < 0 ? [] : lines.slice(end, budgetEnd < 0 ? lines.length : budgetEnd);
    const currency = /(?:[$€£]\s*\d[\d,.]*(?:\s*(?:-|–|to)\s*[$€£]?\s*\d[\d,.]*)?)/i;
    const amountIndex = metadataLines.findIndex(line => currency.test(line));
    let budget = '';
    if (amountIndex >= 0) {
        budget = metadataLines[amountIndex].match(currency)[0];
        if (metadataLines[amountIndex + 1] === '-' && currency.test(metadataLines[amountIndex + 2] || '')) budget += ' - ' + metadataLines[amountIndex + 2].match(currency)[0];
        const type = metadataLines.find(line => /^(hourly|fixed[- ]price)$/i.test(line));
        if (type) budget += ' (' + type + ')';
    }
    const skills = [];
    if (skillsIndex >= 0) {
        for (const line of lines.slice(skillsIndex + 1)) {
            if (/^(activity on this job|about the client|client.s recent history|screening questions|you will be asked|preferred qualifications|job activity|proposals:)\b/i.test(line)) break;
            if (!/^(mandatory skills|preferred skills|skills|tools|other|show more|show less)$/i.test(line) && line.length <= 100 && skills.length < 30) skills.push(line);
        }
    }
    const activityIndex = lines.findIndex(line => /^activity on this job/i.test(line));
    const activity = activityIndex < 0 ? [] : lines.slice(activityIndex + 1);
    const labels = [/^proposals\s*:?/i, /^last viewed by client\s*:?/i, /^interviewing\s*:?/i, /^invites sent\s*:?/i, /^unanswered invites\s*:?/i];
    const values = labels.flatMap(label => {
        const i = activity.findIndex(line => label.test(line));
        if (i < 0) return [];
        const inline = activity[i].replace(label, '').replace(/^\s*[:\-]\s*/, '').trim();
        const next = activity[i + 1] || '';
        const value = inline || (!labels.some(other => other.test(next)) ? next : '');
        return value ? [activity[i].match(label)[0].replace(/\s*:?$/, '') + ': ' + value.slice(0, 120)] : [];
    });
    if (!title || !description.length) return '';
    return [title, lines[posted], ...description, ...(budget ? ['Job budget: ' + budget] : []), ...(skills.length ? ['Required skills:', ...skills] : []), 'Activity on this job', ...values].join('\n').slice(0, 40000);
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (message?.type === 'prepare-application') {
        (async () => {
            const source = new URL(sender.url);
            const target = new URL(message.url);
            const id = target.pathname.match(/~(0?\d{10,})/)?.[1];
            if (source.origin !== 'http://127.0.0.1:8137' || target.protocol !== 'https:' || !['upwork.com','www.upwork.com'].includes(target.hostname) || !id || !/^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(target.pathname)) throw new Error('Choose a valid Upwork job first.');
            if (typeof message.draft !== 'string' || !message.draft.trim() || message.draft.length > 5000 || !['fixed','hourly'].includes(message.paymentType) || !Number.isFinite(Number(message.amount)) || Number(message.amount) <= 0) throw new Error('Enter a valid draft, payment type and amount.');
            const tab = await chrome.tabs.create({url:`https://www.upwork.com/nx/proposals/job/~${id}/apply/`, active:true});
            for (let attempt = 0; attempt < 30; attempt++) {
                await new Promise(resolve => setTimeout(resolve, 1000));
                const current = await chrome.tabs.get(tab.id);
                if (!current.url?.startsWith(`https://www.upwork.com/nx/proposals/job/~${id}/apply`)) continue;
                try {
                    const [{result}] = await chrome.scripting.executeScript({target:{tabId:tab.id}, args:[message.draft, Number(message.amount), message.paymentType], func:(draft, amount, paymentType) => {
                        const visible = el => !!el.getClientRects().length;
                        const fields = [...document.querySelectorAll('input,textarea')].filter(visible);
                        const label = el => (el.labels?.[0]?.innerText || el.getAttribute('aria-label') || (el.getAttribute('aria-labelledby') || '').split(/\s+/).map(id => document.getElementById(id)?.innerText || '').join(' ') || '').trim();
                        const letter = fields.find(el => el.tagName === 'TEXTAREA' && /cover letter/i.test(label(el)));
                        if (!letter) return null;
                        const text = document.body.innerText;
                        const fixed = /how do you want to be paid/i.test(text);
                        const hourly = /hourly rate/i.test(text) && !fixed;
                        const set = (el,value) => { const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto,'value').set.call(el,value); el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true})); el.blur(); };
                        set(letter,draft);
                        const typeMatches = paymentType === 'fixed' ? fixed : hourly;
                        const amountField = typeMatches && fields.find(el => paymentType === 'fixed' ? /^bid$/i.test(label(el)) : /hourly rate/i.test(label(el)));
                        if (amountField) set(amountField,String(amount));
                        const actual = amountField ? Number(amountField.value.replace(/[^\d.]/g,'')) : NaN;
                        return {letter:letter.value === draft, amount:!!amountField && actual === amount, typeMatches};
                    }});
                    if (!result) continue;
                    respond({ok:true, ...result}); return;
                } catch { /* Upwork may still be loading. */ }
            }
            throw new Error('Could not fill the application. Check sign-in and complete the form on the opened Upwork tab.');
        })().catch(error => respond({error:error.message || 'Could not open the application.'}));
        return true;
    }
    if (message?.type === 'open-current-profile') {
        (async () => {
            const url = new URL(sender.url);
            if (url.protocol !== 'https:' || !['upwork.com', 'www.upwork.com'].includes(url.hostname) || !/^\/(?:freelancers\/[^/]+|nx\/find-work\/profile)\/?$/i.test(url.pathname) || !sender.tab?.id) throw new Error('Open the freelancer profile first.');
            const [{result}] = await chrome.scripting.executeScript({target:{tabId:sender.tab.id},func:()=>{
                const visible=el=>!!(el.getClientRects().length && getComputedStyle(el).visibility!=='hidden');
                const headings=[...document.querySelectorAll('h2,h3')].filter(visible).map(e=>e.innerText.trim()).filter(Boolean).slice(0,40);
                const titleHeading=[...document.querySelectorAll('h2,h3')].find(e=>visible(e)&&/\$\s*[\d,.]+\s*\/\s*hr/i.test(e.parentElement?.innerText||'')&&e.innerText.trim().length>5&&!/^\$\s*[\d,.]+\s*\/\s*hr\s*$/i.test(e.innerText.trim()));
                const title=titleHeading?.innerText.trim()||'';
                const container=titleHeading?.closest('section, article, [data-test]')||titleHeading?.parentElement?.parentElement;
                const paragraphs=container?[...container.querySelectorAll('p,[data-test*="overview"], [data-test*="description"]')].filter(visible).map(e=>e.innerText.trim()).filter(t=>t.length>80):[];
                return {text:(document.body?.innerText||'').slice(0,40000),title:document.querySelector('h1')?.innerText||'',headings,profileTitle:title,profileDescription:paragraphs.sort((a,b)=>b.length-a.length)[0]||''};
            }});
            if (!result.text || /log in to your upwork account|verify you are human/i.test(result.text)) throw new Error('Sign in to Upwork and open the profile before importing.');
            const token=crypto.randomUUID();
            await chrome.storage.session.set({['profile-'+token]:{data:{url:url.origin+url.pathname,...result},expires:Date.now()+120000}});
            await chrome.tabs.create({url:'http://127.0.0.1:8137/#leadpilot-profile='+token,active:true});
            respond({ok:true});
        })().catch(error=>respond({error:error.message || 'Could not read the profile.'}));
        return true;
    }
    if (message?.type === 'consume-current-profile') {
        (async()=>{
            if (new URL(sender.url).origin !== 'http://127.0.0.1:8137' || typeof message.token !== 'string' || !/^[0-9a-f-]{36}$/i.test(message.token)) throw new Error('Invalid profile request.');
            const key='profile-'+message.token;const stored=(await chrome.storage.session.get(key))[key];await chrome.storage.session.remove(key);
            if (!stored || stored.expires<Date.now()) throw new Error('Import expired. Import the profile again.');
            respond({data:stored.data});
        })().catch(error=>respond({error:error.message}));
        return true;
    }
    if (message?.type === 'refresh-chat-leads') {
        (async()=>{
            if (new URL(sender.url).origin !== 'http://127.0.0.1:8137') throw new Error('Invalid LeadPilot origin.');
            const tabs=await chrome.tabs.query({url:['https://www.upwork.com/ab/messages/rooms*','https://upwork.com/ab/messages/rooms*']});
            for (const tab of tabs) {
                if (!tab.id) continue;
                const [{result}]=await chrome.scripting.executeScript({target:{tabId:tab.id},func:()=>[...document.querySelectorAll('[data-test="room-list-item"]')].slice(0,200).map(item=>({url:item.href||'',name:item.querySelector('[data-test="room-name"]')?.textContent?.trim()||'',timestamp:item.querySelector('.timestamp, time, [data-test*="timestamp"]')?.textContent?.trim()||'',text:(item.innerText||'').trim().slice(0,2000)}))});
                if(result.length){respond({rows:result});return;}
            }
            throw new Error('Open your signed-in Upwork Messages list in this browser, then try again.');
        })().catch(error=>respond({error:error.message||'Could not read conversations.'}));return true;
    }
    if (message?.type === 'open-chat-review') {
        (async () => {
            const source = new URL(sender.url);
            if (source.protocol !== 'https:' || !['www.upwork.com','upwork.com'].includes(source.hostname) || !/^\/ab\/messages\/rooms(?:\/[^/]+)?\/?$/i.test(source.pathname) || !sender.tab?.id) throw new Error('Open Upwork Messages first.');
            const [{result}] = await chrome.scripting.executeScript({target:{tabId:sender.tab.id},func:()=>[...document.querySelectorAll('[data-test="room-list-item"]')].slice(0,200).map(item=>({url:item.href||'',name:item.querySelector('[data-test="room-name"]')?.textContent?.trim()||'',timestamp:item.querySelector('.timestamp, time, [data-test*="timestamp"]')?.textContent?.trim()||'',text:(item.innerText||'').trim().slice(0,2000)}))});
            if (!result.length) throw new Error('No visible conversations found. Open the messages list and try again.');
            const token=crypto.randomUUID(); await chrome.storage.session.set({['chats-'+token]:{rows:result,expires:Date.now()+120000}});
            await chrome.tabs.create({url:'http://127.0.0.1:8137/#leadpilot-chats='+token,active:true}); respond({ok:true});
        })().catch(error=>respond({error:error.message||'Could not read conversations.'}));return true;
    }
    if (message?.type === 'consume-chat-review') {
        (async()=>{if(new URL(sender.url).origin!=='http://127.0.0.1:8137'||typeof message.token!=='string'||!/^[0-9a-f-]{36}$/i.test(message.token))throw new Error('Invalid request.');const key='chats-'+message.token;const data=(await chrome.storage.session.get(key))[key];await chrome.storage.session.remove(key);if(!data||data.expires<Date.now())throw new Error('Request expired. Please try again.');respond({rows:data.rows});})().catch(error=>respond({error:error.message}));return true;
    }
    if (message?.type === 'refresh-proposal-views') {
        (async () => {
            if (new URL(sender.url).origin !== 'http://127.0.0.1:8137') throw new Error('Invalid LeadPilot origin.');
            const tab = await chrome.tabs.create({ url: 'https://www.upwork.com/nx/proposals/', active: false });
            const visited = new Set();
            const ids = new Set();
            const matches = new Map();
            let pages = 0;
            let unresolved = 0;
            let partial = false;
            let expectedUrl = null;
            try {
                for (let page = 0; page < 15; page++) {
                    let snapshot = null;
                    for (let attempt = 0; attempt < 10; attempt++) {
                        await new Promise(resolve => setTimeout(resolve, 1200));
                        const current = await chrome.tabs.get(tab.id);
                        if (!current.url) continue;
                        const currentUrl = new URL(current.url);
                        if (!['upwork.com', 'www.upwork.com'].includes(currentUrl.hostname) || !currentUrl.pathname.startsWith('/nx/proposals')) continue;
                        if (expectedUrl && currentUrl.href !== expectedUrl) continue;
                        if (current.status !== 'complete') continue;
                        try {
                            const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => {
                                const anchors = [...document.querySelectorAll('a[href]')].filter(a => /^\/nx\/proposals\/\d+\/?$/.test(new URL(a.href).pathname));
                                const seen = new Set();
                                const viewed = [];
                                let unresolved = 0;
                                for (const anchor of anchors) {
                                    const id = new URL(anchor.href).pathname.match(/\/(\d+)\/?$/)?.[1];
                                    if (!id || seen.has(id)) continue;
                                    seen.add(id);
                                    const card = anchor.closest('article, li, [data-test*="proposal-card"], [data-test*="proposal-item"]');
                                    if (!card) { unresolved++; continue; }
                                    const related = new Set([...card.querySelectorAll('a[href]')].map(a => new URL(a.href).pathname.match(/^\/nx\/proposals\/(\d+)\/?$/)?.[1]).filter(Boolean));
                                    if (related.size !== 1) { unresolved++; continue; }
                                    const text = card.innerText || '';
                                    if (/(?:not\s+(?:yet\s+)?|never\s+|un)viewed\s+by\s+client\b|client\s+viewed\s*:\s*(?:no|false|not yet)\b/i.test(text)) continue;
                                    if (/(?:viewed\s+by\s+client|client\s+viewed)\b/i.test(text)) {
                                        const title = (anchor.innerText || '').trim().replace(/\s+/g, ' ');
                                        const dates = [...text.matchAll(/\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s+(\d{1,2}),\s+(\d{4})\b/gi)];
                                        const uniqueDates = [...new Set(dates.map(date => {
                                            const month = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec'].indexOf(date[1].slice(0,3).toLowerCase()) + 1;
                                            const year = Number(date[3]), day = Number(date[2]);
                                            const parsed = new Date(Date.UTC(year, month - 1, day));
                                            return parsed.getUTCFullYear() === year && parsed.getUTCMonth() + 1 === month && parsed.getUTCDate() === day ? `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}` : '';
                                        }).filter(Boolean))];
                                        const safeTitle = title.length > 8 && title.length <= 250 && !/^(view|open|proposal|details)\b/i.test(title) ? title : '';
                                        viewed.push({ id, title: safeTitle, date: uniqueDates.length === 1 ? uniqueDates[0] : '' });
                                    }
                                }
                                const controls = [...document.querySelectorAll('button, a')];
                                const isNext = element => /^(next|next page|›|→)$/i.test((element.getAttribute('aria-label') || element.textContent || '').trim()) || element.getAttribute('rel') === 'next';
                                const nextControl = controls.find(element => isNext(element) && !element.disabled && element.getAttribute('aria-disabled') !== 'true');
                                const next = nextControl?.tagName === 'A' ? nextControl.href : null;
                                const pagination = document.querySelector('[aria-label*="pagination" i], [data-test*="pagination" i]');
                                const hasKnownNextControl = controls.some(isNext);
                                return { found: seen.size, viewed, unresolved, next, unsupportedNext: (!!nextControl && !next) || (!!pagination && !hasKnownNextControl), text: (document.body?.innerText || '').slice(0, 3000) };
                            } });
                            if (/log in to your upwork|sign in to upwork|verify you are human/i.test(result.text)) throw new Error('Please sign in to Upwork in this browser and try again.');
                            if (result.found > 0) { snapshot = result; break; }
                        } catch (error) { if (/sign in to Upwork/.test(error.message)) throw error; }
                    }
                    if (!snapshot) throw new Error('Could not read the proposals list. Check that Upwork is signed in and the page is accessible.');
                    pages++;
                    snapshot.viewed.forEach(row => {
                        ids.add(row.id);
                        if (!row.title || !row.date) return;
                        const candidate = { id: row.id, title: row.title, proposal_date: row.date };
                        const previous = matches.get(row.id);
                        if (!matches.has(row.id)) matches.set(row.id, candidate);
                        else if (previous && (previous.title !== candidate.title || previous.proposal_date !== candidate.proposal_date)) matches.set(row.id, null);
                    });
                    unresolved += snapshot.unresolved;
                    if (snapshot.unsupportedNext) { partial = true; break; }
                    if (!snapshot.next) break;
                    let next;
                    try { next = new URL(snapshot.next); } catch { partial = true; break; }
                    if (next.protocol !== 'https:' || !['upwork.com', 'www.upwork.com'].includes(next.hostname) || !next.pathname.startsWith('/nx/proposals') || visited.has(next.href)) { partial = true; break; }
                    visited.add(next.href);
                    if (page === 14) { partial = true; break; }
                    expectedUrl = next.href;
                    await chrome.tabs.update(tab.id, { url: next.href });
                }
                const selected = [...ids].slice(0, 500);
                respond({ ids: selected, matches: selected.map(id => matches.get(id)).filter(Boolean), pages, unresolved, partial: partial || ids.size > 500 });
            } finally {
                await chrome.tabs.remove(tab.id).catch(() => {});
            }
        })().catch(error => respond({ error: error.message || 'Could not refresh proposal views.' }));
        return true;
    }
    if (message?.type === 'open-submitted-proposal') {
        (async () => {
            const id = submittedProposalId(sender.url);
            if (!id || !sender.tab?.id) throw new Error('Open the submitted proposal success page first.');
            const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: sender.tab.id }, func: () => ({ text: document.body?.innerText || '', links: [...document.querySelectorAll('a[href]')].map(a => a.href) }) });
            const data = submittedProposalDetails(result.text);
            if (!data.title || !data.coverLetter) throw new Error('Could not find the job title and submitted proposal on this page. Nothing was saved.');
            const jobUrl = result.links.find(link => { try { const u = new URL(link); return u.protocol === 'https:' && ['upwork.com', 'www.upwork.com'].includes(u.hostname) && /^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(u.pathname) && jobId(u.href); } catch { return false; } }) || null;
            const token = crypto.randomUUID();
            await chrome.storage.session.set({ ['proposal-' + token]: { data: { upwork_proposal_id: id, title: data.title, cover_letter: data.coverLetter, job_description: data.description || null, notes: data.notes || null, job_url: jobUrl }, expires: Date.now() + 120000 } });
            await chrome.tabs.create({ url: 'http://127.0.0.1:8137/#leadpilot-proposal=' + token, active: true });
            respond({ ok: true });
        })().catch(error => respond({ error: error.message || 'Could not read this proposal.' }));
        return true;
    }
    if (message?.type === 'consume-submitted-proposal') {
        (async () => {
            if (new URL(sender.url).origin !== 'http://127.0.0.1:8137' || typeof message.token !== 'string' || !/^[0-9a-f-]{36}$/i.test(message.token)) throw new Error('Invalid import request.');
            const key = 'proposal-' + message.token;
            const stored = (await chrome.storage.session.get(key))[key];
            await chrome.storage.session.remove(key);
            if (!stored || stored.expires < Date.now()) throw new Error('Import expired. Please select the proposal again.');
            respond({ data: stored.data });
        })().catch(error => respond({ error: error.message }));
        return true;
    }
    if (message?.type === 'open-current-job') {
        (async () => {
            const url = new URL(sender.url);
            if (url.protocol !== 'https:' || !['upwork.com', 'www.upwork.com'].includes(url.hostname) || !/^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(url.pathname) || !jobId(url.href)) throw new Error('Open an Upwork job first.');
            const token = crypto.randomUUID();
            await chrome.storage.session.set({ ['job-' + token]: { url: url.href, expires: Date.now() + 120000 } });
            await chrome.tabs.create({ url: 'http://127.0.0.1:8137/#leadpilot-import=' + token, active: true });
            respond({ ok: true });
        })().catch(error => respond({ error: error.message }));
        return true;
    }
    if (message?.type === 'consume-current-job') {
        (async () => {
            if (new URL(sender.url).origin !== 'http://127.0.0.1:8137' || typeof message.token !== 'string' || !/^[0-9a-f-]{36}$/i.test(message.token)) throw new Error('Invalid import request.');
            const key = 'job-' + message.token;
            const stored = (await chrome.storage.session.get(key))[key];
            await chrome.storage.session.remove(key);
            if (!stored || stored.expires < Date.now()) throw new Error('Import request expired. Please select the job again.');
            respond({ url: stored.url });
        })().catch(error => respond({ error: error.message }));
        return true;
    }
    if (message?.type !== 'import-job') return;
    (async () => {
        const source = new URL(sender.url);
        const target = new URL(message.url);
        if (source.origin !== 'http://127.0.0.1:8137' || target.protocol !== 'https:' || !['upwork.com', 'www.upwork.com'].includes(target.hostname) || !/^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(target.pathname) || !jobId(target.href)) throw new Error('Invalid LeadPilot or Upwork job URL.');
        const expectedId = jobId(target.href);
        const tab = await chrome.tabs.create({ url: target.href, active: false });
        try {
        for (let attempt = 0; attempt < 20; attempt++) {
            await new Promise(resolve => setTimeout(resolve, 1500));
            const current = await chrome.tabs.get(tab.id);
            if (!current.url || !['upwork.com', 'www.upwork.com'].includes(new URL(current.url).hostname)) continue;
            if (jobId(current.url) !== expectedId) continue;
            try {
                const [{ result }] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => document.body?.innerText || '' });
                if (result && result.length >= 100 && /\bposted\b/i.test(result) && !/verify you are human|log in to your upwork account/i.test(result)) {
                    const text = jobTextOnly(result);
                    if (text) {
                        respond({ text });
                        return;
                    }
                }
            } catch { /* Page may still be loading. */ }
        }
        throw new Error('Could not read the job description. Check that you are signed in to Upwork and the job is accessible, then try again.');
        } finally {
            await chrome.tabs.remove(tab.id).catch(() => {});
        }
    })().catch(error => respond({ error: error.message || 'Job import failed.' }));
    return true;
});
