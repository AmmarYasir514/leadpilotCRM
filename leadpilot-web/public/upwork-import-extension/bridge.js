if (location.port === '8137' && window.top === window) {
    window.addEventListener('message', event => {
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-apply-request' && typeof event.data.requestId === 'string') {
            const {requestId, url, draft, amount, paymentType} = event.data;
            chrome.runtime.sendMessage({type:'prepare-application', url, draft, amount, paymentType}, response => {
                const error = chrome.runtime.lastError?.message;
                window.postMessage({type:'leadpilot-apply-result', requestId, ...(error ? {error} : response)}, location.origin);
            });
            return;
        }
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-chats-refresh' && typeof event.data.requestId === 'string') {const {requestId}=event.data;chrome.runtime.sendMessage({type:'refresh-chat-leads'},response=>{const error=chrome.runtime.lastError?.message;window.postMessage({type:'leadpilot-chats-refresh-result',requestId,...(error?{error}:response)},location.origin);});return;}
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-chats-request' && typeof event.data.token === 'string') { const {token}=event.data; chrome.runtime.sendMessage({type:'consume-chat-review',token},response=>{const error=chrome.runtime.lastError?.message;window.postMessage({type:'leadpilot-chats-result',token,...(error?{error}:response)},location.origin);});return; }
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-profile-request' && typeof event.data.token === 'string') {
            const {token}=event.data;
            chrome.runtime.sendMessage({type:'consume-current-profile',token}, response=>{
                const error=chrome.runtime.lastError?.message;
                window.postMessage({type:'leadpilot-profile-result',token,...(error?{error}:response)},location.origin);
            });
            return;
        }
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-refresh-views-request'  && typeof event.data.requestId === 'string') {
            const { requestId } = event.data;
            chrome.runtime.sendMessage({ type: 'refresh-proposal-views' }, response => {
                const error = chrome.runtime.lastError?.message;
                window.postMessage({ type: 'leadpilot-refresh-views-result', requestId, ...(error ? { error } : response) }, location.origin);
            });
            return;
        }
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-proposal-request' && typeof event.data.token === 'string') {
            const { token } = event.data;
            chrome.runtime.sendMessage({ type: 'consume-submitted-proposal', token }, response => {
                const error = chrome.runtime.lastError?.message;
                window.postMessage({ type: 'leadpilot-proposal-result', token, ...(error ? { error } : response) }, location.origin);
            });
            return;
        }
        if (event.source === window && event.origin === location.origin && event.data?.type === 'leadpilot-open-job-request' && typeof event.data.token === 'string') {
            const { token } = event.data;
            chrome.runtime.sendMessage({ type: 'consume-current-job', token }, response => {
                const error = chrome.runtime.lastError?.message;
                window.postMessage({ type: 'leadpilot-open-job-result', token, ...(error ? { error } : response) }, location.origin);
            });
            return;
        }
        if (event.source !== window || event.origin !== location.origin || event.data?.type !== 'leadpilot-job-import-request') return;
        const { requestId, url } = event.data;
        if (typeof requestId !== 'string' || typeof url !== 'string') return;
        chrome.runtime.sendMessage({ type: 'import-job', requestId, url }, response => {
            const error = chrome.runtime.lastError?.message;
            window.postMessage({ type: 'leadpilot-job-import-result', requestId, ...(error ? { error } : response) }, location.origin);
        });
    });
}
