import React, {useEffect, useRef} from 'react';
export default function AdminDialog({children, onClose, label, drawer = false}: {children: React.ReactNode; onClose: () => void; label: string; drawer?: boolean}) {
    const ref = useRef<HTMLDialogElement>(null);
    useEffect(() => { const dialog = ref.current; if (dialog && !dialog.open) dialog.showModal(); return () => { if (dialog?.open) dialog.close(); }; }, []);
    return <dialog ref={ref} className={`admin-dialog ${drawer ? 'admin-drawer' : ''}`} aria-label={label} onKeyDown={event => {if(event.key==='Escape'){event.preventDefault(); onClose();}}} onCancel={event => {event.preventDefault(); onClose();}}><button type="button" className="admin-dialog-close" onClick={onClose} aria-label={`Close ${label}`}>&times;</button>{children}</dialog>;
}
