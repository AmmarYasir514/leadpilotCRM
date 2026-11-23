import React from 'react';

export function MicIcon({recording=false}:{recording?:boolean}) {
 return <svg aria-hidden="true" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{recording?<rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor" stroke="none"/>:<><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8"/></>}</svg>;
}
export function SendIcon() {
 return <svg aria-hidden="true" width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M22 2 11 13"/><path d="m22 2-7 20-4-9-9-4Z"/></svg>;
}
export function AttachmentIcon() {
 return <svg aria-hidden="true" width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="m21 11.5-8.8 8.8a5.5 5.5 0 0 1-7.8-7.8L13.3 3.6a3.5 3.5 0 0 1 5 5l-8.9 8.8a1.5 1.5 0 0 1-2.1-2.1l8.2-8.1"/></svg>;
}
