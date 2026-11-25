import React from 'react';

export const iconPaths: Record<string, string> = {
    dashboard: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
    findjobs: 'M11 4a7 7 0 100 14 7 7 0 000-14z M16 16l5 5',
    writer: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z M19 15l.7 2.3L22 18l-2.3.7L19 21l-.7-2.3L16 18l2.3-.7L19 15z',
    upworkprofile: 'M12 12a4 4 0 100-8 4 4 0 000 8z M4 21c0-4 3-6 8-6s8 2 8 6',
    users: 'M12 12a4 4 0 100-8 4 4 0 000 8z M4 21c0-4 3-6 8-6s8 2 8 6',
    salesplan: 'M12 3a9 9 0 100 18 9 9 0 000-18z M12 7v5l4 2',
    knowledge: 'M4 4h6a3 3 0 013 3v13a3 3 0 00-3-3H4z M20 4h-4a3 3 0 00-3 3v13a3 3 0 013-3h4z',
    proposals: 'M5 3h10l4 4v14H5z M14 3v5h5 M8 12h8 M8 16h8',
    leads: 'M12 21s7-3.5 7-10a7 7 0 10-14 0c0 6.5 7 10 7 10z M12 8a3 3 0 100 6 3 3 0 000-6z',
    followups: 'M12 3a9 9 0 100 18 9 9 0 000-18z M12 7v5l3 2',
    deals: 'M3 8l9-5 9 5v9l-9 4-9-4z M3 8l9 5 9-5 M12 13v8',
    clients: 'M9 12a4 4 0 100-8 4 4 0 000 8z M2.5 20c0-3 2.7-5 6.5-5s6.5 2 6.5 5 M17 5a4 4 0 010 7 M17 15c2.6.4 4.5 2 4.5 5',
    meetings: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M8 14h3 M8 17h3',
    performance: 'M4 20h16 M7 17v-5 M12 17V7 M17 17V4',
    integrations: 'M7 7h3v3H7z M14 7h3v3h-3z M7 14h3v3H7z M14 14h3v3h-3z M10 8.5h4 M8.5 10v4 M15.5 10v4 M10 15.5h4',
    chats: 'M4 5h16v12H8l-4 3z M8 9h8 M8 13h5',
    settings: 'M12 8a4 4 0 100 8 4 4 0 000-8z M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5.6 5.6L7 7 M17 17l1.4 1.4 M18.4 5.6L17 7 M7 17l-1.4 1.4',
    admin: 'M12 3l8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6z M9 12l2 2 4-4',
    roles: 'M12 3l8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6z M9 12l2 2 4-4',
    access: 'M12 3l8 3v5c0 5-3 8-8 10-5-2-8-5-8-10V6z',
    invite: 'M3 5h18v14H3z M3 5l9 7 9-7',
    events: 'M8 6h13 M8 12h13 M8 18h13 M3 6h.01 M3 12h.01 M3 18h.01',
    page: 'M5 3h10l4 4v14H5z M14 3v5h5',
    currency: 'M12 3v18 M17 8c0-2.2-2.2-3.5-5-3.5S7 5.8 7 8s2 3 5 3 5 1.3 5 3.5-2.2 3.5-5 3.5',
    overdue: 'M10.3 4h3.4L21 19H3z M12 9v5 M12 17h.01',
    upcoming: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16',
    nodate: 'M4 5h16v16H4z M8 3v4 M16 3v4 M4 10h16 M9 15l6 6 M15 15l-6 6',
    plus: 'M12 5v14 M5 12h14',
    refresh: 'M21 12a9 9 0 11-3-6.7 M21 3v6h-6',
    download: 'M12 3v12 M8 11l4 4 4-4 M4 21h16',
    inbox: 'M4 6h16v12H4z M4 10l8 5 8-5',
    video: 'M15 9l6-3v12l-6-3z M3 7h12v10H3z',
};

export function AppIcon({name, size}: {name: string; size?: number}) {
    const d = iconPaths[name];
    if (!d) return null;
    return <svg className="app-icon" viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={d} /></svg>;
}