import React from 'react';
import {AppIcon} from './AppIcon';
import AdminDialog from './AdminDialog';

type Role = {id: number; name: string};
type Team = {id: number; name: string; team_lead_id?: number | null; team_lead_name?: string | null; member_count?: number};
type Permission = {id: number; module: string; action: string};
type User = {
    id: number;
    name: string;
    email: string;
    timezone?: string;
    status: string;
    is_super_admin: boolean;
    phone?: string | null;
    job_title?: string | null;
    department?: string | null;
    joining_date?: string | null;
    team_id?: number | null;
    roles?: Role[];
};
type AuditEntry = {id: number; actor_id: number | null; actor_name?: string | null; action: string; subject_type: string | null; subject_id: number | null; subject_name?: string | null; subject_email?: string | null; created_at: string};
type AuditTarget = {id: number; name: string; email?: string};
type TeamHistoryEntry = {id: number; team_name: string; started_at: string; ended_at: string | null; changed_by: number | null};

type Props = {
    user: User;
    canManageUserAccess: boolean;
    canEditUserProfile: boolean;
    userAccessLoading: boolean;
    visible: boolean;
    section: string;
    setSection: (section: string) => void;
    dark: boolean;
    toggleDark: () => void;
    users: User[];
    roles: Role[];
    teams: Team[];
    catalog: Permission[];
    permissionRole: number | null;
    matrix: Record<number, string>;
    setMatrix: (matrix: Record<number, string>) => void;
    roleName: string;
    setRoleName: (name: string) => void;
    teamName: string;
    setTeamName: (name: string) => void;
    name: string;
    setName: (name: string) => void;
    email: string;
    timezone?: string;
    setEmail: (email: string) => void;
    creatingUser: boolean;
    setCreatingUser: (creating: boolean) => void;
    newUserTeamId: string;
    setNewUserTeamId: (id: string) => void;
    newUserRoleId: string;
    setNewUserRoleId: (id: string) => void;
    editing: User | null;
    setEditing: (user: User | null) => void;
    selectedRoles: number[];
    setSelectedRoles: (roles: number[]) => void;
    overrides: Record<number, string>;
    setOverrides: (overrides: Record<number, string>) => void;
    search: string;
    setSearch: (search: string) => void;
    statusFilter: string;
    setStatusFilter: (status: string) => void;
    teamFilter: string;
    setTeamFilter: (team: string) => void;
    roleFilter: string;
    setRoleFilter: (role: string) => void;
    page: number;
    lastPage: number;
    userTotal: number;
    message: string;
    audit: AuditEntry[];
    auditTotal: number;
    auditAccessChanges: number;
    auditPeople: AuditTarget[];
    auditActions: string[];
    auditTitle: string;
    auditTarget?: AuditTarget;
    setAuditTarget: (target?: AuditTarget) => void;
    auditPage: number;
    auditLastPage: number;
    auditFrom: string;
    setAuditFrom: (date: string) => void;
    auditTo: string;
    setAuditTo: (date: string) => void;
    auditAction: string;
    setAuditAction: (action: string) => void;
    teamHistoryUser: User | null;
    setTeamHistoryUser: (user: User | null) => void;
    teamHistory: TeamHistoryEntry[];
    onCreateUser: (event: React.FormEvent<HTMLFormElement>) => void;
    onSaveProfile: (event: React.FormEvent<HTMLFormElement>) => void;
    onSearch: (event: React.FormEvent<HTMLFormElement>) => void;
    onRefresh: (search: string, page: number) => void;
    onCreateRole: (event: React.FormEvent<HTMLFormElement>) => void;
    onEditPermissions: (roleId: number) => void;
    onSavePermissions: (event: React.FormEvent<HTMLFormElement>) => void;
    onRenameRole: (role: Role) => void;
    onDeleteRole: (role: Role) => void;
    onCreateTeam: (event: React.FormEvent<HTMLFormElement>) => void;
    onRenameTeam: (team: Team) => void;
    onDeleteTeam: (team: Team) => void;
    onSetTeamMembership: (person: User, teamId: number | null) => Promise<void>;
    onSetTeamLead: (team: Team, userId: number | null) => Promise<void>;
    onManageUser: (user: User) => void;
    onUploadPhoto: (user: User, file?: File) => void;
    onShowAudit: (user?: AuditTarget, page?: number) => void;
    onShowTeamHistory: (user: User) => void;
    onOpenOverrides: (user: User) => void;
    onChangeAdmin: (user: User) => void;
    onSendLink: (user: User) => void;
    onRevoke: (user: User) => void;
    onArchive: (user: User) => void;
    onStatusChange: (user: User, status: string) => void;
    onFilterAudit: (user?: AuditTarget) => void;
    onClearAuditFilters: () => void;
};

const sections = [
    ['overview', 'Overview', 'dashboard'],
    ['people', 'Users', 'users'],
    ['roles', 'Roles & permissions', 'roles'],
    ['teams', 'Teams', 'clients'],
    ['audit', 'Activity & audit', 'events'],
] as const;

function initials(name: string): string {
    return name.split(/\s+/).slice(0, 2).map(part => part[0]  ??  '').join('').toUpperCase();
}

function titleCase(value: string): string {
    return value.replaceAll('_', ' ').replace(/\b\w/g, character => character.toUpperCase());
}

function scopes(): React.ReactNode {
    return <><option value="">No access</option><option value="own">Own</option><option value="assigned">Assigned</option><option value="team">Team</option><option value="organization">Organization</option></>;
}

export default function AdminWorkspace(props: Props) {
    const [creatingTeam, setCreatingTeam] = React.useState(false);
    const [managedTeam, setManagedTeam] = React.useState<Team | null>(null);
    const [addingMembers, setAddingMembers] = React.useState(false);
    const [selectedNewMembers, setSelectedNewMembers] = React.useState<number[]>([]);
    const [teamSearch, setTeamSearch] = React.useState('');
    const [teamFilter, setLocalTeamFilter] = React.useState('');
    const moduleNames = [...new Set(props.catalog.map(permission => permission.module))];
    const selectedRole = props.roles.find(role => role.id === props.permissionRole);
    const activeUsers = props.users.filter(person => person.status === 'active').length;
    const invitedUsers = props.users.filter(person => person.status === 'invited').length;
    const selectedTeam = props.teams.find(team => team.id === props.editing?.team_id)?.name  ??  'Unassigned';
    const canEditCurrentProfile = Boolean(props.editing && (props.canManageUserAccess || (props.canEditUserProfile && !props.editing.is_super_admin && props.editing.id !== props.user.id)));
    const auditExportParams = new URLSearchParams();
    if (props.auditTarget) auditExportParams.set('user_id', String(props.auditTarget.id));
    if (props.auditFrom && props.auditTo) { auditExportParams.set('from', props.auditFrom); auditExportParams.set('to', props.auditTo); }
    if (props.auditAction) auditExportParams.set('action', props.auditAction);
    const auditExportUrl = `/admin/audit/export${auditExportParams.size ? `?${auditExportParams}` : ''}`;

    React.useEffect(() => {
        if (props.visible && props.section === 'roles' && props.permissionRole === null && props.roles.length > 0) {
            props.onEditPermissions(props.roles[0].id);
        }
    }, [props.visible, props.section, props.permissionRole, props.roles]);

    const filteredTeams = props.teams.filter(team => {
        const matchesSearch = `${team.name} ${team.team_lead_name ?? ''}`.toLowerCase().includes(teamSearch.trim().toLowerCase());
        const members = Number(team.member_count ?? props.users.filter(person => person.team_id === team.id).length);
        return matchesSearch && (teamFilter === '' || (teamFilter === 'members' ? members > 0 : !team.team_lead_id));
    });

    return <div className={`workspace-panel admin-workspace admin-screen ${props.dark ? 'admin-dark' : ''}`} data-admin-section={props.section} hidden={!props.visible}>
        <div className="admin-toolbar"><button type="button" className="admin-theme-toggle" onClick={props.toggleDark}>{props.dark ? 'Light appearance' : 'Dark appearance'}</button></div>
        <nav className="admin-subnav" aria-label="Administration sections">{sections.map(([id, label, icon]) => <button key={id} type="button" className={props.section === id ? 'active' : ''} aria-current={props.section === id ? 'page' : undefined} onClick={() => props.setSection(id)}><AppIcon name={icon} />{label}</button>)}</nav>
        {props.message && <p className="admin-feedback" role="status">{props.message}</p>}

        {props.section === 'overview' && <section className="admin-screen-panel admin-overview-screen">
            <div className="admin-screen-heading"><div><span className="writer-eyebrow">ADMINISTRATION</span><h2 className="heading-with-icon"><AppIcon name="dashboard"/>Workspace overview</h2><p>See your people, access and recent activity in one place.</p></div><button type="button" onClick={() => props.setSection('people')}>Manage users</button></div>
            <div className="admin-kpis"><article><span><AppIcon name="users"/>Total users</span><strong>{props.userTotal}</strong><small>{activeUsers} active</small></article><article><span><AppIcon name="invite"/>Invitations</span><strong>{invitedUsers}</strong><small>Waiting to join</small></article><article><span><AppIcon name="clients"/>Teams</span><strong>{props.teams.length}</strong><small>Across your workspace</small></article><article><span><AppIcon name="roles"/>Roles</span><strong>{props.roles.length}</strong><small>Access is role based</small></article></div>
            <div className="admin-overview-grid admin-overview-live"><section><h3>Recent activity</h3><p>Latest changes to people, roles and teams appear in Activity &amp; audit.</p><button type="button" onClick={() => props.setSection('audit')}>View recent activity</button></section><section><h3>People status</h3><p><strong>{activeUsers}</strong> active · <strong>{invitedUsers}</strong> invited</p><p>{props.userTotal} people across {props.teams.length} teams</p></section></div>
        </section>}

        {props.section === 'people' && <section className="admin-screen-panel admin-users admin-people">
            <div className="admin-screen-heading"><div><span className="writer-eyebrow">TEAM ACCESS</span><h2 className="heading-with-icon"><AppIcon name="users"/>Users</h2><p>Manage people and their workspace access.</p></div><button type="button" onClick={() => {props.setName(''); props.setEmail(''); props.setCreatingUser(true);}} className="action-with-icon"><AppIcon name="plus"/>Add user</button></div>
            <form className="admin-users-filters" onSubmit={props.onSearch}><label className="admin-users-search"><span className="sr-only">Search name or email</span><input aria-label="Search name or email" placeholder="Search name or email" value={props.search} onChange={event => props.setSearch(event.target.value)} /></label><label><span className="sr-only">Filter by status</span><select aria-label="Filter by status" value={props.statusFilter} onChange={event => props.setStatusFilter(event.target.value)}><option value="">All statuses</option><option value="active">Active</option><option value="invited">Invited</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option></select></label><label><span className="sr-only">Filter by team</span><select aria-label="Filter by team" value={props.teamFilter} onChange={event => props.setTeamFilter(event.target.value)}><option value="">All teams</option>{props.teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label><details className="admin-users-more-filters"><summary>More filters</summary><label><span className="sr-only">Filter by role</span><select aria-label="Filter by role" value={props.roleFilter} onChange={event => props.setRoleFilter(event.target.value)}><option value="">All roles</option>{props.roles.map(role => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label></details><button className="admin-users-apply" type="submit">Apply filters</button></form>
            <div className="table admin-people-table"><table><thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Team</th><th><span className="sr-only">Manage user</span></th></tr></thead><tbody>{props.users.map(person => <tr key={person.id}><td><span className="admin-user-name"><span className="admin-user-avatar">{initials(person.name)}</span><span><strong>{person.name}</strong>{person.is_super_admin && <small>Super Admin</small>}</span></span></td><td className="admin-user-email">{person.email}</td><td><span className="admin-user-role-list">{person.roles?.length ? person.roles.map(role => <span className="admin-user-role" key={role.id}>{role.name}</span>) : <span className="admin-user-muted">No role assigned</span>}</span></td><td><span className={`badge admin-status admin-status-${person.status}`}>{person.status}</span></td><td>{props.teams.find(team => team.id === person.team_id)?.name  ??  <span className="admin-user-muted">Unassigned</span>}</td><td><button type="button" className="admin-user-manage" onClick={() => props.onManageUser(person)}>Manage</button></td></tr>)}</tbody></table>{props.users.length === 0 && <p className="admin-users-empty empty-with-icon"><AppIcon name="inbox"/>No users match these filters.</p>}</div>
            <div className="admin-users-pagination"><span>Showing {props.userTotal === 0 ? 0 : (props.page - 1) * 25 + 1}-{Math.min(props.page * 25, props.userTotal)} of {props.userTotal} users</span><div><button type="button" className="admin-user-secondary" disabled={props.page <= 1} onClick={() => props.onRefresh(props.search, props.page - 1)}>Previous</button><span>Page {props.page} of {props.lastPage}</span><button type="button" className="admin-user-secondary" disabled={props.page >= props.lastPage} onClick={() => props.onRefresh(props.search, props.page + 1)}>Next</button></div></div>
            <div className="admin-users-flow"><strong>Simple user flow</strong><span>Search or filter <b>&gt;</b> Add or invite <b>&gt;</b> Assign role and team <b>&gt;</b> Manage access</span></div>
        </section>}

        {props.section === 'roles' && <section className="admin-screen-panel admin-role-screen">
            <div className="admin-screen-heading"><div><span className="writer-eyebrow">ACCESS CONTROL</span><h2 className="heading-with-icon"><AppIcon name="roles"/>Roles & permissions</h2><p>Choose a role, then set access for each action and its data scope.</p></div></div>
            <form className="admin-role-create" onSubmit={props.onCreateRole}><label>New role name<input value={props.roleName} onChange={event => props.setRoleName(event.target.value)} placeholder="For example, Sales manager" required /></label><button type="submit" className="action-with-icon"><AppIcon name="plus"/>Create role</button></form>
            <div className="admin-role-layout"><div className="admin-role-list">{props.roles.map(role => <article className={`admin-role-card ${role.id === props.permissionRole ? 'selected' : ''}`} key={role.id}><div><strong>{role.name}</strong><small>{props.users.filter(person => person.roles?.some(assigned => assigned.id === role.id)).length} assigned</small></div><button type="button" onClick={() => props.onEditPermissions(role.id)}>{role.id === props.permissionRole ? 'Selected' : 'Edit access'}</button><div className="admin-role-actions"><button type="button" className="link" onClick={() => props.onRenameRole(role)}>Rename</button><button type="button" className="link" onClick={() => props.onDeleteRole(role)}>Delete</button></div></article>)}</div>
                <div className="admin-role-permissions">{selectedRole ? <><div className="admin-role-permissions-head"><div><h3>{selectedRole.name}</h3><p>Set access and data scope for each action. These permissions apply to everyone with this role.</p></div><button type="button" className="admin-user-secondary" onClick={() => props.onRenameRole(selectedRole)}>Edit role name</button></div><form onSubmit={props.onSavePermissions}>{moduleNames.map(module => <section className="admin-role-module" key={module}><h4>{titleCase(module)}</h4>{props.catalog.filter(item => item.module === module).map(permission => <label className="admin-role-permission-row" key={permission.id}><span><strong>{titleCase(module)}</strong><small>{titleCase(permission.action)}</small></span><select aria-label={`${module} ${permission.action} scope`} value={props.matrix[permission.id] ?? ''} onChange={event => props.setMatrix({...props.matrix, [permission.id]: event.target.value})}><option value="">No access</option><option value="own">Own</option><option value="assigned">Assigned</option><option value="team">Team</option><option value="organization">Organization</option></select></label>)}</section>)}<p className="admin-user-help">These rules apply to all users assigned the {selectedRole.name} role.</p><button type="submit">Save permissions</button></form></> : <div className="admin-role-empty"><strong>No roles yet</strong><p>Create a role to set access for your workspace users.</p></div>}</div>
            </div>
        </section>}

        {props.section === 'teams' && <section className="admin-screen-panel admin-team-screen">
            <div className="admin-screen-heading"><div><span className="writer-eyebrow">WORKSPACE ORGANIZATION</span><h2 className="heading-with-icon"><AppIcon name="clients"/>Teams</h2><p>Group users to make ownership and access easy to manage.</p></div><button type="button" onClick={() => {props.setTeamName(''); setCreatingTeam(true);}} className="action-with-icon"><AppIcon name="plus"/>Create team</button></div>
            <form className="admin-team-filters" onSubmit={event => event.preventDefault()}><input aria-label="Search team name or lead" placeholder="Search team name or lead" value={teamSearch} onChange={event => setTeamSearch(event.target.value)} /><select aria-label="Filter teams" value={teamFilter} onChange={event => setLocalTeamFilter(event.target.value)}><option value="">All teams</option><option value="members">With members</option><option value="no-lead">Without a lead</option></select><button type="submit" className="admin-user-secondary">Apply</button></form>
            <div className="table admin-team-table"><table><thead><tr><th>Team name</th><th>Team lead</th><th>Members</th><th>People</th><th><span className="sr-only">Team actions</span></th></tr></thead><tbody>{filteredTeams.map(team => {const members = props.users.filter(person => person.team_id === team.id); const count = Number(team.member_count ?? members.length); return <tr key={team.id}><td><span className="admin-team-table-name"><span className="admin-team-table-icon">{initials(team.name).slice(0, 1)}</span><span><strong>{team.name}</strong><small>Workspace team</small></span></span></td><td>{team.team_lead_name ?? <span className="admin-user-muted">No team lead</span>}</td><td>{count} {count === 1 ? 'person' : 'people'}</td><td><span className="admin-team-avatars">{members.slice(0, 4).map(person => <span className="admin-user-avatar" title={person.name} key={person.id}>{initials(person.name)}</span>)}{count > members.length && <span className="admin-team-more">+{count - members.length}</span>}</span></td><td><div className="admin-team-row-actions"><button type="button" className="admin-user-secondary" onClick={() => setManagedTeam(team)}>Manage</button><button type="button" className="link" onClick={() => props.onRenameTeam(team)}>Rename</button><button type="button" className="link" onClick={() => props.onDeleteTeam(team)}>Delete</button></div></td></tr>;})}</tbody></table>{filteredTeams.length === 0 && <p className="admin-users-empty empty-with-icon"><AppIcon name="inbox"/>No teams match these filters.</p>}</div>
            <div className="admin-team-foot"><span>Showing {filteredTeams.length} {filteredTeams.length === 1 ? 'team' : 'teams'}</span><span>Each member belongs to one team at a time.</span></div>
            <p className="admin-team-notice"><strong>Team access:</strong> A team controls which team-scoped records members can access. Their role controls which actions they can take.</p>
            {props.teamHistoryUser && <div className="admin-history-panel"><div className="admin-screen-heading"><div><h3>Team history: {props.teamHistoryUser.name}</h3><p>Past and current team assignments.</p></div><button className="admin-user-secondary" onClick={() => props.setTeamHistoryUser(null)}>Close history</button></div><div className="table"><table><thead><tr><th>Team</th><th>From</th><th>Until</th><th>Changed by</th></tr></thead><tbody>{props.teamHistory.map(entry => <tr key={entry.id}><td>{entry.team_name}</td><td>{entry.started_at}</td><td>{entry.ended_at  ??  'Current'}</td><td>{entry.changed_by  ??  'Not recorded'}</td></tr>)}</tbody></table></div></div>}
        </section>}

        {props.section === 'audit' && <section className="admin-screen-panel admin-audit-screen">
            <div className="admin-audit-heading"><div><span className="writer-eyebrow">SECURITY &amp; HISTORY</span><h2 className="heading-with-icon"><AppIcon name="events"/>{props.auditTarget ? `Activity for ${props.auditTarget.name}` : 'Activity & audit'}</h2><p>See who changed access or workspace settings, and when.</p></div><a className="admin-audit-export action-with-icon" href={auditExportUrl} download><AppIcon name="download"/>Download CSV</a></div>
            <div className="admin-audit-kpis"><article><span><AppIcon name="events"/>Events found</span><strong>{props.auditTotal}</strong></article><article><span><AppIcon name="access"/>Access changes</span><strong>{props.auditAccessChanges}</strong></article><article><span><AppIcon name="page"/>Events on this page</span><strong>{props.audit.length}</strong></article></div>
            <form className="admin-audit-filters" onSubmit={event => {event.preventDefault(); props.onFilterAudit(props.auditTarget);}}>
                <label>From<input type="date" value={props.auditFrom} onChange={event => props.setAuditFrom(event.target.value)} required={Boolean(props.auditTo)} /></label>
                <label>To<input type="date" min={props.auditFrom || undefined} value={props.auditTo} onChange={event => props.setAuditTo(event.target.value)} required={Boolean(props.auditFrom)} /></label>
                <label>Person<select value={props.auditTarget?.id ?? ''} onChange={event => props.setAuditTarget(props.auditPeople.find(person => person.id === Number(event.target.value)))}><option value="">All people</option>{props.auditPeople.map(person => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label>
                <label>Activity<select value={props.auditAction} onChange={event => props.setAuditAction(event.target.value)}><option value="">All activity</option>{props.auditActions.map(action => <option value={action} key={action}>{titleCase(action.replaceAll('.', ' '))}</option>)}</select></label>
                <div className="admin-audit-filter-actions"><button type="button" className="admin-user-secondary" onClick={props.onClearAuditFilters}>Clear filters</button><button type="submit">Apply filters</button></div>
            </form>
            <div className="table admin-audit-table"><table><thead><tr><th>Time</th><th>Person</th><th>Activity</th><th>Details</th><th>Changed by</th></tr></thead><tbody>{props.audit.map(entry => {
                const subjectPerson = entry.subject_type === 'user' ? props.auditPeople.find(person => person.id === entry.subject_id) : undefined;
                const date = new Date(entry.created_at.replace(' ', 'T') + (entry.created_at.endsWith('Z') ? '' : 'Z'));
                const personName = entry.subject_name || subjectPerson?.name || (entry.subject_type ? `${titleCase(entry.subject_type)} ${entry.subject_id ?? ''}` : 'Workspace');
                const actorName = entry.actor_name || props.auditPeople.find(person => person.id === entry.actor_id)?.name || (entry.actor_id ? `User ${entry.actor_id}` : 'System');
                return <tr key={entry.id}><td>{date.toLocaleString(undefined, {timeZone: props.user.timezone || 'UTC', dateStyle: 'medium', timeStyle: 'short'})}</td><td><span className="admin-audit-person"><span className="admin-user-avatar">{initials(personName)}</span><span><strong>{personName}</strong>{entry.subject_email && <small>{entry.subject_email}</small>}</span></span></td><td><span className="admin-audit-event"><i aria-hidden="true"></i>{titleCase(entry.action.replaceAll('.', ' '))}</span></td><td>{entry.subject_type ? `${titleCase(entry.subject_type)}${entry.subject_id ? ` #${entry.subject_id}` : ''}` : 'Workspace activity'}</td><td>{actorName}</td></tr>;
            })}</tbody></table>{props.audit.length === 0 && <p className="admin-users-empty empty-with-icon"><AppIcon name="inbox"/>No activity matches these filters.</p>}</div>
            <div className="admin-users-pagination"><span>Showing {props.auditTotal === 0 ? 0 : (props.auditPage - 1) * 10 + 1}–{Math.min(props.auditPage * 10, props.auditTotal)} of {props.auditTotal} events</span><div><button className="admin-user-secondary" disabled={props.auditPage <= 1} onClick={() => props.onShowAudit(props.auditTarget, props.auditPage - 1)}>Previous</button><span>Page {props.auditPage} of {props.auditLastPage}</span><button className="admin-user-secondary" disabled={props.auditPage >= props.auditLastPage} onClick={() => props.onShowAudit(props.auditTarget, props.auditPage + 1)}>Next</button></div></div>
        </section>}

        {props.creatingUser && <AdminDialog label="Add a user" onClose={() => props.setCreatingUser(false)}><section className="admin-user-dialog"><div className="admin-user-dialog-heading"><span className="writer-eyebrow">NEW TEAM MEMBER</span><h2>Add a user</h2><p>Create the account, then send a password setup link from the user menu.</p></div><form className="admin-user-form" onSubmit={props.onCreateUser}><label>Full name<input value={props.name} onChange={event => props.setName(event.target.value)} autoComplete="name" required /></label><label>Email address<input type="email" value={props.email} onChange={event => props.setEmail(event.target.value)} autoComplete="email" required /></label><label>Team (optional)<select value={props.newUserTeamId} onChange={event => props.setNewUserTeamId(event.target.value)}><option value="">Choose later</option>{props.teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label><label>Role (optional)<select value={props.newUserRoleId} onChange={event => props.setNewUserRoleId(event.target.value)}><option value="">Choose later</option>{props.roles.map(role => <option key={role.id} value={role.id}>{role.name}</option>)}</select></label><div className="admin-user-form-actions"><button type="button" className="admin-user-secondary" onClick={() => props.setCreatingUser(false)}>Cancel</button><button type="submit">Create user</button></div></form></section></AdminDialog>}

        {creatingTeam && <AdminDialog label="Create team" onClose={() => setCreatingTeam(false)}><section className="admin-user-dialog"><div className="admin-user-dialog-heading"><span className="writer-eyebrow">WORKSPACE ORGANIZATION</span><h2>Create team</h2><p>Add a team to organize workspace members.</p></div><form className="admin-user-form" onSubmit={event => {props.onCreateTeam(event); setCreatingTeam(false);}}><label>Team name<input value={props.teamName} onChange={event => props.setTeamName(event.target.value)} required placeholder="For example, Sales" /></label><div className="admin-user-form-actions"><button type="button" className="admin-user-secondary" onClick={() => setCreatingTeam(false)}>Cancel</button><button type="submit">Create team</button></div></form></section></AdminDialog>}

        {managedTeam && <AdminDialog label={`Manage ${managedTeam.name}`} drawer onClose={() => setManagedTeam(null)}><section className="admin-user-dialog admin-user-drawer"><div className="admin-user-dialog-heading"><span className="writer-eyebrow">TEAM MANAGEMENT</span><h2>Manage team</h2><div className="admin-user-identity"><span className="admin-user-avatar">{initials(managedTeam.name)}</span><span><strong>{managedTeam.name}</strong><small>{props.users.filter(person => person.team_id === managedTeam.id).length} members</small></span></div></div><div className="admin-user-form"><label>Team lead<select defaultValue={managedTeam.team_lead_id ?? ''} onChange={event => {const id=event.target.value ? Number(event.target.value) : null; void props.onSetTeamLead(managedTeam, id);}}><option value="">No team lead</option>{props.users.filter(person => person.team_id === managedTeam.id || !person.team_id).map(person => <option value={person.id} key={person.id}>{person.name}</option>)}</select></label><h3>Team members</h3>{props.users.filter(person => person.team_id === managedTeam.id).map(person => <div className="admin-user-identity" key={person.id}><span className="admin-user-avatar">{initials(person.name)}</span><span><strong>{person.name}</strong><small>{person.email}</small></span><button type="button" className="link" onClick={() => void props.onSetTeamMembership(person, null)}>Remove</button></div>)}{props.users.filter(person => person.team_id === managedTeam.id).length === 0 && <p>No members yet. Add people to this team.</p>}<div className="admin-user-form-actions"><button type="button" className="admin-user-secondary" onClick={() => setManagedTeam(null)}>Done</button><button type="button" onClick={() => {setSelectedNewMembers([]); setAddingMembers(true);}}>Add members</button></div></div></section></AdminDialog>}
        {addingMembers && managedTeam && <AdminDialog label={`Add members to ${managedTeam.name}`} onClose={() => setAddingMembers(false)}><section className="admin-user-dialog"><div className="admin-user-dialog-heading"><span className="writer-eyebrow">TEAM MEMBERS</span><h2>Add members</h2><p>Select people who are not assigned to a team.</p></div><form className="admin-user-form" onSubmit={event => {event.preventDefault(); void (async () => {for (const id of selectedNewMembers) {const person = props.users.find(item => item.id === id); if (person) await props.onSetTeamMembership(person, managedTeam.id);} setAddingMembers(false);})();}}>{props.users.filter(person => !person.team_id).map(person => <label className="admin-user-identity" key={person.id}><input type="checkbox" checked={selectedNewMembers.includes(person.id)} onChange={event => setSelectedNewMembers(event.target.checked ? [...selectedNewMembers, person.id] : selectedNewMembers.filter(id => id !== person.id))} /><span><strong>{person.name}</strong><small>{person.email}</small></span></label>)}{props.users.filter(person => !person.team_id).length === 0 && <p>Everyone is already assigned to a team.</p>}<div className="admin-user-form-actions"><button type="button" className="admin-user-secondary" onClick={() => setAddingMembers(false)}>Cancel</button><button type="submit" disabled={!selectedNewMembers.length}>Add selected</button></div></form></section></AdminDialog>}

        {props.editing && <AdminDialog label={`Manage ${props.editing.name}`} drawer onClose={() => props.setEditing(null)}><section className="admin-user-dialog admin-user-drawer"><div className="admin-user-dialog-heading"><span className="writer-eyebrow">USER ACCESS</span><h2>Manage user</h2><div className="admin-user-identity"><span className="admin-user-avatar">{initials(props.editing.name)}</span><span><strong>{props.editing.name}</strong><small>{props.editing.email}  /  {props.editing.status}</small></span></div></div><form className="admin-user-form" onSubmit={props.onSaveProfile} key={props.editing.id}>
            <section className="admin-user-section"><h3>Profile and account</h3><label>Full name<input name="name" defaultValue={props.editing.name} autoComplete="name" required readOnly={!canEditCurrentProfile} /></label><label>Email address<input name="email" type="email" defaultValue={props.editing.email} autoComplete="email" required readOnly={!props.canManageUserAccess} /></label><div className="admin-user-fields-row"><label>Team<select name="team_id" defaultValue={props.editing.team_id ?? ''} disabled={!props.canManageUserAccess}><option value="">Unassigned</option>{props.teams.map(team => <option key={team.id} value={team.id}>{team.name}</option>)}</select></label><label>Account status<select name="status" defaultValue={props.editing.status} disabled={!props.canManageUserAccess}><option value="active">Active</option><option value="invited">Invited</option><option value="inactive">Inactive</option><option value="suspended">Suspended</option></select></label></div>{!props.canManageUserAccess && <p className="admin-user-help">Role, team and account status are managed by a Super Admin.</p>}</section>
            {props.canManageUserAccess && <><section className="admin-user-section"><div className="admin-user-access-heading"><div><h3>Assigned roles</h3><p>Role access is inherited unless changed below.</p></div><details className="admin-user-add-role"><summary className="action-with-icon"><AppIcon name="plus"/>Add role</summary><div>{props.roles.map(role => <label key={role.id}><input type="checkbox" checked={props.selectedRoles.includes(role.id)} onChange={event => props.setSelectedRoles(event.target.checked ? [...props.selectedRoles, role.id] : props.selectedRoles.filter(id => id !== role.id))} />{role.name}</label>)}</div></details></div><div className="admin-user-role-chips">{props.roles.filter(role => props.selectedRoles.includes(role.id)).map(role => <span className="admin-user-role-chip" key={role.id}>{role.name}<button type="button" aria-label={`Remove ${role.name} role`} onClick={() => props.setSelectedRoles(props.selectedRoles.filter(id => id !== role.id))}>×</button></span>)}{props.selectedRoles.length === 0 && <span className="admin-user-muted">No role assigned</span>}</div></section>
            <section className="admin-user-section"><div className="admin-user-access-heading"><div><h3>Individual access</h3><p>Choose whether each action inherits, allows or denies access.</p></div><button type="button" className="admin-user-secondary" onClick={() => props.setOverrides({})}>Reset to role</button></div>{props.editing.is_super_admin ? <p className="admin-user-help">Super Admin has full workspace access. Individual overrides do not apply.</p> : <div className="admin-user-access-modules">{moduleNames.map(module => <section className="admin-user-access-module" key={module}><h4>{titleCase(module)}</h4>{props.catalog.filter(item => item.module === module).map(permission => {const value = props.overrides[permission.id] ?? 'inherit'; const roleNames = props.roles.filter(role => props.selectedRoles.includes(role.id)).map(role => role.name); return <label className="admin-user-access-row" key={permission.id}><span><strong>{titleCase(module)} / {titleCase(permission.action)}</strong><small>{value === 'inherit' ? roleNames.length ? `Inherited from ${roleNames.join(', ')}` : 'No role access' : value === 'deny' ? 'Personal override · denied' : 'Personal override'}</small></span><select aria-label={`${module} ${permission.action} individual access`} value={value} onChange={event => props.setOverrides({...props.overrides, [permission.id]: event.target.value})}><option value="inherit">Inherit from role</option><option value="own">Allow · Own</option><option value="assigned">Allow · Assigned</option><option value="team">Allow · Team</option><option value="organization">Allow · Organization</option><option value="deny">Deny</option></select></label>;})}</section>)}</div>}</section></>}
            <details className="admin-user-more"><summary>Additional profile details</summary><label>Phone<input name="phone" defaultValue={props.editing.phone  ??  ''} autoComplete="tel" /></label><label>Job title<input name="job_title" defaultValue={props.editing.job_title  ??  ''} /></label><label>Department<input name="department" defaultValue={props.editing.department  ??  ''} /></label><label>Joining date<input name="joining_date" type="date" defaultValue={props.editing.joining_date  ??  ''} /></label></details>
            <details className="admin-user-more"><summary>Account actions</summary><div className="admin-user-action-list"><button type="button" className="link" onClick={() => props.onShowAudit(props.editing!)}>View activity</button><button type="button" className="link" onClick={() => props.onShowTeamHistory(props.editing!)}>Team history</button><button type="button" className="link" onClick={() => props.onOpenOverrides(props.editing!)}>Open full permissions</button><a href={`/admin/users/${props.editing.id}/photo`} target="_blank" rel="noreferrer">View photo</a><label>Upload profile photo<input type="file" accept="image/jpeg,image/png,image/webp" onChange={event => props.onUploadPhoto(props.editing!, event.target.files?.[0])} /></label><button type="button" className="link" onClick={() => props.onSendLink(props.editing!)}>Send password link</button><button type="button" className="link" onClick={() => props.onRevoke(props.editing!)}>Revoke sessions</button><button type="button" className="link" onClick={() => props.onChangeAdmin(props.editing!)}>{props.editing.is_super_admin ? 'Remove admin access' : 'Make admin'}</button><button type="button" className="link" onClick={() => props.onArchive(props.editing!)}>Archive user</button>{props.editing.status !== 'inactive' && <button type="button" className="link" onClick={() => props.onStatusChange(props.editing!, 'inactive')}>Deactivate user</button>}{props.editing.status === 'active' ? <button type="button" className="link" onClick={() => props.onStatusChange(props.editing!, 'suspended')}>Suspend user</button> : <button type="button" className="link" onClick={() => props.onStatusChange(props.editing!, 'active')}>Activate user</button>}</div></details>
            {props.userAccessLoading && <p className="admin-user-help" role="status">Loading this user's access…</p>}
            {canEditCurrentProfile && <div className="admin-user-form-actions"><button type="button" className="admin-user-secondary" onClick={() => props.setEditing(null)}>Cancel</button><button type="submit" disabled={props.userAccessLoading}>Save changes</button></div>}
        </form></section></AdminDialog>}
    </div>;
}
