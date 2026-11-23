(() => {
    const host = document.createElement('div');
    host.id = 'leadpilot-import-control';
    const shadow = host.attachShadow({ mode: 'closed' });
    const style = document.createElement('style');
    style.textContent = ':host{position:fixed;right:20px;bottom:24px;z-index:2147483647}button{border:0;border-radius:12px;background:#245ddb;color:white;padding:13px 18px;font:600 14px system-ui,sans-serif;box-shadow:0 5px 22px #122d5655;cursor:pointer}button:disabled{opacity:.7;cursor:wait}.status{display:block;color:#9c2230;background:white;border-radius:8px;font:12px system-ui,sans-serif;max-width:260px;margin-top:6px}.status:empty{display:none}';
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Import job in LeadPilot';
    const status = document.createElement('span');
    status.className = 'status';
    status.setAttribute('role', 'status');
    shadow.append(style, button, status);
    const isJob = () => /^\/(jobs|freelance-jobs\/apply|nx\/search\/jobs\/details)\//i.test(location.pathname) && /~0?[0-9]{10,}/.test(location.href);
    const isSubmitted = () => /^\/nx\/proposals\/\d+\/?$/.test(location.pathname) && new URL(location.href).searchParams.has('success');
    const isProfile = () => /^\/(?:freelancers\/[^/]+|nx\/find-work\/profile)\/?$/i.test(location.pathname);
    const isMessages = () => /^\/ab\/messages\/rooms(?:\/[^/]+)?\/?$/i.test(location.pathname);
    const update = () => {
        const active = isJob() || isSubmitted() || isProfile() || isMessages();
        button.textContent = isMessages() ? 'Review chats in LeadPilot' : isProfile() ? 'Import profile to LeadPilot' : isSubmitted() ? 'Add submitted proposal to LeadPilot' : 'Import job in LeadPilot';
        if (active && document.body && !host.isConnected) document.body.append(host);
        if (!active && host.isConnected) host.remove();
    };
    button.addEventListener('click', () => {
        button.disabled = true;
        status.textContent = '';
        chrome.runtime.sendMessage({ type: isMessages() ? 'open-chat-review' : isProfile() ? 'open-current-profile' : isSubmitted() ? 'open-submitted-proposal' : 'open-current-job' }, response => {
            button.disabled = false;
            const error = chrome.runtime.lastError?.message || response?.error;
            if (error) status.textContent = error;
        });
    });
    new MutationObserver(update).observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener('popstate', update);
    update();
})();
