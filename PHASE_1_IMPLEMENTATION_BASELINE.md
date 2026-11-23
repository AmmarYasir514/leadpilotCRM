# LeadPilot CRM 2.0 — implementation baseline

## Product direction

LeadPilot 2.0 is a new, authenticated, multi-user web application. The supplied master document specifies Laravel for server-side authorization and React, TypeScript and Tailwind for the administration interface. The existing Python/Tkinter application is a single-user desktop product; its SQLite database and workflows are the legacy migration source, not a secure multi-user backend. Keep the desktop application and its data intact until migration has been designed and verified.

## Release gate

Complete, test and obtain approval for each roadmap phase before starting the next. The phase numbering in the detailed feature sections differs from the final implementation order; use the final implementation order for delivery. Implement the Super Admin foundation in the first release, including the necessary database structures and security checks, rather than postponing them to later database or security phases.

## Phase 1 — Foundation, database, authentication and Super Admin

1. Establish a separate Laravel application and database, with repeatable setup, migrations, configuration and automated tests. Keep credentials and application keys outside source control.
2. Model organizations and users with stable identifiers, status, timestamps and archival support. Establish the organizational boundary before accepting business records. Do not grant a future platform administrator implicit access to tenant business records.
3. Implement authenticated sessions, login, logout, failed-login throttling, session revocation and immediate rejection of suspended, deactivated or archived users. Never record passwords, tokens or message contents in audit records.
4. Provide a controlled, interactive installation command to create the first organization and Super Admin; do not supply a default production password. Prevent setup from creating another initial administrator after initialization.
5. Implement protected server-side Super Admin management: create and edit users, status changes, secure password setup/reset, session revocation, profile and team/role assignment foundations, and activity/audit records. Preserve historical records. Enforce the last active Super Admin invariant transactionally, including concurrent requests.
6. Deliver an accessible administration interface backed by real endpoints. Only authorized administrators can invoke these operations. Do not represent unfinished integrations, reports or performance metrics as functional.
7. Test the installation flow, authentication and status enforcement, user management, privilege escalation attempts, session revocation, audit redaction, organization boundaries and last-administrator protection. Document reproducible setup and deployment prerequisites.

Acceptance requires working end-to-end functionality, passing tests, a security review and user approval. Email delivery, secure invitation/reset token lifetime, organizational bootstrap and supported database must be specified and verified during implementation. Development-only delivery must not silently become production delivery.

## Subsequent roadmap

2. Dynamic roles, permissions and team management, with backend and query-level enforcement and immediate effect of permission changes.
3. Leads, clients and sales pipeline, with ownership, assignment and scoped access.
4. Upwork jobs, proposals and bidding records.
5. Follow-ups, tasks and meetings.
6. AI lead generation.
7. AI sales agent and proposal intelligence, respecting the requesting user's permissions.
8. Employee activity and performance analytics using real events and data.
9. Reports, integrations and SaaS readiness.
10. Security, QA, data migration and Cloudways deployment.

## Legacy assessment

The existing application opens a local SQLite database directly and creates proposals, leads, settings, meetings, reports and follow-up events in its startup routine. The README explicitly states that there are no user accounts, permissions or synchronization. Existing `account` and `member` text fields cannot be assumed to identify authenticated users. A later migration must inventory the actual source database, map identities with administrator review, preserve relationships and history, and validate counts and backups before any cutover. Never migrate or overwrite a user's live database implicitly.

## Current environment

At assessment time PHP, Composer, Node.js and npm were not available on PATH. Python is available. A Laravel/React application cannot be installed or validated until the required toolchains are available; installing dependencies and establishing the application are the next Phase 1 implementation steps. No Phase 1 security or functionality is claimed complete by this baseline.
