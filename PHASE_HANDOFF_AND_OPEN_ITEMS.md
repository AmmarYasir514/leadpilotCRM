# LeadPilot CRM 2.0 ? phase handoff and deferred work

Recorded 2026-11-18. This register tracks unfinished work and does not mark any phase complete or approve a release. The master document's approval gate remains in effect until the user approves a change to that sequence.

## Phase 1 ? foundation, authentication and Super Admin

The Laravel application, local database, interactive first-administrator setup, login/logout, account-status checks, user management, password-link flow, audit foundation and basic team/role management exist. They are not yet verified as production-ready.

Before accepting Phase 1: review and test the actual browser flows for setup, authentication, user management and permissions; verify that setup and email links work in the target environment; review the security and accessibility of the administration area; and test the last-active-Super-Admin invariant and concurrent changes against the selected production database. Configure a real mail transport and verify invitation and password-reset delivery without storing secrets or tokens in logs. The target mail account and production database details are not yet provided.

The current tests use SQLite; they do not prove server-database concurrency behavior. A high-severity development dependency advisory was reported in the frontend toolchain. Recheck the lockfile and available fixes, document an appropriate mitigation if necessary, and re-audit before deployment. Do not claim production readiness based only on local tests.

Some capabilities named in the master document's Super Admin section require modules that do not exist yet; implement and test those with their owning phases below, rather than inventing placeholder data or treating them as delivered now.

## Phase 2 ? roles, permissions and teams

Complete the default and custom role lifecycle, organization-scoped role and permission management, team management, individual overrides, server-side authorization, and permission changes for active sessions. The current permission resolver and matrix are a foundation; confirm scopes and enforce them in real endpoints and queries, including authorization for administration where appropriate. Test denial, escalation, organization isolation, role/override changes and team access. Preserve the protected last active Super Admin.


Status as of 2026-11-19: **in progress, not marked complete**. Team reassignment history and protection against deleting teams with history are implemented. Remaining work includes a full authorization/security review of existing administrative actions, server-database concurrency verification, and browser-level verification. Later CRM record scopes must be implemented with their owning modules.

## Phase 3 ? leads, clients and sales pipeline

Implement ownership and assignment, scoped lead access, team visibility and query-level enforcement. Add lead reassignment and preserve assignment history. Link relevant events to authenticated users. Apply and test the Phase 2 permission model on every endpoint and database query.

## Phase 4 ? Upwork jobs, proposals and bidding records

Build database-driven jobs, proposal and bidding workflows, access controls, submission/outcome tracking and activity events. Migrate legacy functionality only through a separately planned and tested process.

## Phase 5 ? follow-ups, tasks and meetings

Implement task and follow-up assignment, reassignment history, meetings, permissions and actual activity events. Link events to users and authorized organization records.

## Phases 6?7 ? AI lead generation and sales agent

Implement AI features and management controls with permissions, scoped record access, human approval where required, usage tracking and budgets. AI must never bypass the initiating user's access rights.

## Phase 8 ? employee activity and performance

Complete user activity timelines, meaningful events for the modules as they become available, audit-log filtering/export, employee performance metrics and targets using actual database data. Define retention and protect audit records; exclude passwords, tokens and confidential content. Do not equate login duration with productivity.

## Phase 9 ? reports, integrations and SaaS readiness

Implement authorized reports and exports, external integrations, organization settings and tenant isolation. Clearly distinguish platform and organization administrators without exposing unrelated tenant data. Configure and validate operational mail/integrations in the intended environment.

## Phase 10 ? security, QA, migration and deployment

Perform full security and authorization testing, dependency audits, production-like concurrency tests and operational checks. Inventory and map legacy desktop records and identities with administrator review; test backups, relationships, record counts and recovery before cutover. Deploy only after readiness and approval.

## Email decision ? user update

The user does not yet have a business email account and intends to purchase one later. Do not request or invent provider credentials now. Configure and verify real invitation/password-reset delivery once the provider is selected. A local Python SMTP testing environment was installed under the user-local LeadPilotToolchain and its localhost SMTP handshake was verified; it is not a real email delivery service. A downloaded Mailpit binary was blocked by Windows Application Control and was not run. The application is not yet configured to use a local test inbox.

## Dependency audit update ? 2026-11-19

The current npm audit reported zero known vulnerabilities for the full dependency tree and for production dependencies. This supersedes the earlier recorded development-dependency advisory for the present lockfile; re-run audits before release because advisory data changes.

## Upwork browser and legacy workflow preference ? user clarification

The user wants LeadPilot 2.0 to build on the existing Python CRM workflows with modern technology and features. For Upwork-related operation, the user prefers the already open browser and profile where their Upwork account is signed in, rather than creating a new browser/profile. Browser access, permissions, hosting constraints and a safe implementation must be validated when the Upwork integration is developed; do not assume a web application can access the user browser profile automatically. Keep the existing CRM and data intact, and preserve its read-only Upwork behavior unless the user explicitly requests and authorizes a change. The user also asked about browser verification: only the unauthenticated CRM login screen has been inspected so far; end-to-end administrator, role and team workflows remain to be verified.

## Browser verification update ? 2026-11-19

Using a temporary isolated database and synthetic accounts, verified browser login/logout, user creation, team creation/assignment, role creation/assignment, role permission save and reload, individual deny override, last active Super Admin protection, and a limited user seeing only their permitted team after sign-in. The temporary test database was removed afterward. These checks did not use Upwork or the user's CRM data. Real mail delivery, target-database concurrency, comprehensive accessibility, and remaining workflows are not covered by this browser check.

## Phase 3 start — 2026-11-19

The user approved proceeding while Phase 2 production-like concurrency verification and real email delivery remain open. The master document labels Phase 3 as the Super Admin dashboard, while its delivery roadmap lists leads and pipeline as the third module; both remain in scope. A first dashboard section now displays real organization-scoped user counts and users who signed in today, restricted to Super Admins. The latter is not a measure of current activity. Sales KPIs, filters, employee performance profiles, and leads/pipeline remain unimplemented. This phase is in progress and is not complete. Dashboard access and tenant isolation have automated tests; this dashboard has not yet received browser verification.

## Dashboard progress — 2026-11-19

A separate Super Admin dashboard screen now shows current user counts, recorded activity today, a team filter, and a paginated employee list. Organization isolation and team filtering are covered by automated tests. Sales metrics are explicitly unavailable until their source modules exist. Date, user, source, and sales-stage filters, full employee performance profiles, actual sales metrics, and browser verification remain incomplete. Phase 3 is not complete.

## Phase 3 progress and verification order — 2026-11-19

The user requested browser verification at the end of implementation for each phase. Do not treat it as completed or omit it. The dashboard now has a date range for recorded security and administration audit event counts (UTC), and an employee profile showing existing account information and recent recorded events. Current account counts remain current regardless of the date range. Date-based sales metrics, sales source/stage filtering and sales performance profiles remain dependent on future modules. Automated tests cover date validation, tenant isolation and profile access; browser verification remains pending until implementation is ready.

## Phase 3 browser check and Phase 4 start — 2026-11-19

With a disposable local SQLite database and sample account, checked sign-in, dashboard user counts, opening an employee profile, selecting its filter, date range audit event count, and sign-out in the CRM browser. This did not exercise the team selector with multiple teams, non-admin browser access, pagination, or future-module metrics. Automated tests cover dashboard authorization and tenant isolation. The sample database was removed. The user authorized moving on with future-module dashboard dependencies pending, not marking those dependencies implemented.

Phase 4 activity monitoring is in progress. Existing security events now support server-side date and action filters, with a Super Admin interface. Exports, retention, timezone support and future business events remain open and must be built and verified. Phase 4 browser verification belongs at the end of its implementation.

## Phase 4 export and local preview — 2026-11-19

Activity CSV export is implemented with organization-scoped view and export authorization, existing action/date filters, and spreadsheet-formula escaping; automated tests cover isolation and denied access. Configurable retention, timezone-aware timelines, full filtering and pagination, future module events, and end-of-phase browser verification remain open. A separate sample-only local preview database was created under the user-local LeadPilotToolchain; it is separate from the real CRM data and must not be represented as a production account.

## Phase 4 retention and timezone — 2026-11-19

Implemented per-user IANA timezone settings for security activity table display and audit date-filter boundaries. Dashboard date counts and CSV timestamps remain explicitly UTC; complete timeline-wide timezone consistency remains open. Added opt-in organization retention of routine auth.login/auth.logout events only, with a minimum 30-day period and indefinite retention by default. Security and administrative events are not pruned. The daily Laravel scheduled command requires an operational scheduler in the target environment; no scheduler has been installed or verified. The preview database was migrated. Phase 4 browser verification remains pending until implementation is ready; future business events remain tied to their modules.

## Phase 4 timezone and activity navigation — 2026-11-19

The dashboard now uses the signed-in administrator's selected timezone for today counts, activity date boundaries, employee activity timestamps and displayed recent activity. Super Admin activity history now supports pagination and preserves the selected employee for filtering and CSV export. CSV timestamps intentionally remain labeled UTC. Automated tests cover dashboard and audit date boundaries in Asia/Karachi; browser verification is still reserved for the end of implementation. Scheduler configuration, future business activity events and remaining production readiness remain open.

## Phase 4 retention hardening — 2026-11-19

Retention cleanup now rechecks each organization's current setting while holding the same organization lock used by settings changes, and records an audit event when routine events are removed. Disabled retention and security event preservation are covered by automated tests. Authorized delegated activity viewers now have date/action filtering and pagination. The selected production scheduler is still unconfigured and server-database concurrency has not been proven. Browser verification remains pending until phase implementation is ready.

## Phase 4 browser check — 2026-11-19

Using a disposable local SQLite database and a separate test-session cookie, verified sign-in, saving Asia/Karachi timezone, configuring 90-day retention and persistence after reload, filtering auth.login activity, and a filtered CSV export. This did not verify scheduled execution, cleanup at the scheduled time, delegated-user browser flows, pagination with multiple pages, or future business events. Automated tests cover authorization and retention pruning; target-environment scheduler and server-database concurrency are still open. User's preview data was not used as the test database.

## Phase 4 delegated viewer browser verification — 2026-11-19

A disposable test database containing more than 25 synthetic events and a separate test session verified that a user with organization activity-view permission can open the second page, and is denied CSV export and the Super Admin dashboard without the required permissions. This supplements the earlier admin browser check. Production scheduling and future module events remain pending; no production scheduler is installed and Phase 4 is not represented as fully complete.

## Phase 5 started — 2026-11-19

With the user's approval to continue while cloud hosting is not yet purchased, started employee performance management. Employee targets can be stored per employee, metric and date range, with revenue currency and organization-scoped analytics permissions; changes are audited. A Super Admin target form is available in the employee dashboard profile. Automated tests cover validation, tenant isolation, authorization, updates and audit. Target editing by delegated managers has an API but no dedicated manager UI yet; delete/history, precise period rules, real performance metrics, charts, reports and browser verification remain open. Actual performance must be connected to later modules, without fabricated figures. Cloud scheduling, business email and Phase 4 future events remain pending.

## Phase 5 targets progress — 2026-11-19

Organization-authorized analytics viewers can list employees and view targets; managers with analytics manage permission can save and remove them. Removal is audited. Daily targets require one day, weekly targets seven days, and monthly targets a full calendar month. Automated tests cover delegated permissions and invalid durations. Detailed target change history, reports, progress charts and real performance figures remain open; later business-module integrations and end-of-phase browser verification remain pending.

## Phase 5 target change history — 2026-11-19

Target creation, changes and deletion now retain previous/new values and currencies, actor, period and time in an organization-scoped history. History is visible to authorized analytics viewers and remains after target deletion. Automated tests cover updates, deletion and cross-organization access. History starts with changes made after this feature was installed; earlier target changes cannot be reconstructed. Reports, real business performance data, charts and end-of-phase browser verification remain open.

## Phase 5 daily activity report — 2026-11-19

Added an employee daily recorded security/administration event report with previous-day comparison and selected-timezone boundaries. Access requires both organization analytics-view and audit-view permissions; tenant isolation and timezone behavior have automated coverage. It must not be interpreted as productivity or sales performance. Sales reports, progress charts, PDF/Excel/CSV report exports, future-module metrics and end-of-phase browser verification remain open.

## Phase 5 daily report CSV — 2026-11-19

The daily recorded activity report now supports CSV export for users with organization analytics and audit view/export permissions. Automated tests cover unauthorized access, timezone/date isolation and spreadsheet-formula escaping. PDF and native Excel exports, charts, business performance reports and future module metrics remain open. Phase 5 browser verification has not yet been performed.

## Phase 5 activity PDF and Excel exports — 2026-11-19

Added native PDF and XLSX downloads for the existing daily recorded activity report, using Dompdf and OpenSpout. Both require the same analytics and audit view/export permissions as CSV; tests verify authorization, file signatures, and Excel formula protection. An activity count comparison chart shows selected day and previous day and is explicitly not a productivity or sales chart. Sales progress charts, sales performance reports and their exports remain blocked on real leads, proposals and sales data; do not call those implemented. Browser verification is pending until phase implementation is ready. Composer reported no advisories at install time.

## Daily activity reporting feature verification — 2026-11-19

Using a disposable local database and distinct session cookie, browser-verified sign-in, employee selection, daily report, comparison chart, and CSV/XLSX/PDF responses with correct file signatures. Automated suite has 48 passing tests, including export authorization and tenant isolation. Exported reports now identify the employee; old preview and production records were not used in verification. This completes this bounded daily recorded-activity reporting feature for the current local implementation, not all of Phase 5 or production readiness. Future sales reporting, charts, source modules, target-environment testing, mail and scheduler remain open.

## Leads foundation started — 2026-11-19

At the user's request to build the modules required for sales reporting, added organization-scoped lead creation and listing, permissions for own/assigned/team/organization scopes, lead-created audit events, and workspace-wide dashboard lead counts. Creating a lead assigns it to the actor; clients, editing, lead stages, reassignment/history, record deletion, sales and proposal modules, performance reports, migration of legacy data, broader scope tests and browser verification remain open. Lead counts in the admin dashboard are explicitly workspace-wide and do not follow team/employee filters. Preview database migrated without importing user data.

## Leads editing and assignment progress — 2026-11-19

Lead fields and legacy-inspired statuses can be updated under scoped view/edit permissions. Organization-wide lead assign permission permits reassignment to active users of the same organization; assignment history is recorded and exposed to users who can view the lead. Existing leads' initial assignment was backfilled using creation metadata, which does not prove any earlier reassignment history. Tests cover own/foreign access, status events and cross-organization assignment denial. Leads archive/delete, budget, date fields, search/filters, client relationships, complete stage history, broader scope/concurrency testing, and end-of-module browser verification remain open. Sales/proposal modules and Phase 5 reports remain incomplete.

## Leads workflow increment and browser check — 2026-11-19

Added scoped lead search and stage filters, lead date, budget/currency, reversible archive/restore, and stage-change history. Dashboard lead counts exclude archived records. Stage history for leads existing at migration is a snapshot at migration time with unknown actor, not reconstructed history. Browser-verified in a disposable database: create with budget, edit stage, reassign, view stage history, archive, filter archived, and restore; a validation-rule defect found during this check was fixed and covered with a positive budget test. Automated tests: 49 tests, 371 assertions. The module is not 100%: client relationships, proposals/sales, comprehensive scope and concurrent database testing, and legacy migration remain open. Preview database migrated without importing the real legacy database.

## Client and proposal workflow increment — 2026-11-19

Added organization- and scope-protected client create/list/edit and explicit lead-client linking/unlinking with client visibility checks. Added scoped proposal draft create/list/edit, optional visible lead association, bid and currency, manually recorded statuses and submitted timestamp, audit events, and workspace-wide proposal dashboard counts. No Upwork submission or messaging is performed. Automated tests cover denied permissions, tenant isolation, foreign lead/client linking and dashboard counts; 51 tests and 407 assertions pass. Browser verification for these new workflows remains pending until the module is ready. Clients still need lifecycle/history and proposal records still need fuller legacy fields, status/assignment history, bid/connects, safe migration and real sales reporting; do not claim either complete. Preview database was migrated only; legacy data remains untouched.

## Client/proposal lifecycle and initial sales summary — 2026-11-19

Added reversible client archive/restore with scoped permissions; existing links remain and new links to archived clients are denied. Added proposal date, HTTP(S) job URL, normal and boosted connects, and paginated status/bid change history. Existing proposals receive a current-state snapshot with unknown actor at migration, not fabricated prior history. Added a permission-protected employee lead/proposal date-range summary and equal-length previous-period comparison; it counts records created by the employee (including archived) and manually recorded submission timestamps, and labels current lead status and manual submission accurately. It is not a complete sales performance report: deals, revenue, rates, target achievement, history/assignment coverage and report exports remain incomplete. No Upwork submission occurs. 52 tests / 429 assertions and frontend build pass. Browser verification is deferred until these modules are ready per user preference. Preview migrations applied; actual legacy database untouched.

## Sales reporting and deals increment — 2026-11-19

Added scoped manual deal records with open/won/lost status, closing dates, deal values and separately recorded realized revenue. Amounts are stored in minor units and currencies are reported separately; these records are not a payment ledger. Employee sales reports now include current-period won/lost deals, win rate, manually recorded revenue, recorded proposal response/interview conversion rates, comparable previous-period lead/proposal counts, exact-period target achievement and CSV/XLSX/PDF exports. Revenue targets match currency; follow-up and interview target achievement remains unavailable until corresponding source modules exist. Proposal conversion relies on recorded status history and does not reconstruct older missing history or submit anything to Upwork. Report figures reflect records created by the employee and current deal state; they are not historical accounting snapshots.

Browser-verified the feature in an isolated disposable database: sign-in, deal creation and update, target creation, report figures and CSV/XLSX/PDF response signatures. Automated suite: 53 tests and 465 assertions passed; frontend build and TypeScript checks passed. The preview database migration was applied without importing legacy data. Remaining work includes payment tracking/accounting, deal assignment and history, complete team and broader sales reports, follow-up and interview metrics, comprehensive module and production-environment verification, and legacy data migration. Do not mark the entire phase or software complete on this basis.

## Sales cycle scope correction and follow-up increment — 2026-11-19

User clarified that the CRM ends at client/deal closing and records only the agreed project amount; payment tracking and post-close financial management are out of scope. Closed-deal reporting and targets now use agreed deal value, not realized revenue. Historical realized-revenue data was retained in the database but is no longer exposed or included in reports; no legacy database import was performed.

The old Python code uses a default follow-up cadence of 24, 48, 48, 72, 72 hours, up to ten steps of 1–720 hours, with the first delay after conversation start and later delays after the previous marked-sent follow-up. Client replies and sales-stage changes reset the cycle; meeting-booked pauses it, and closed leads or linked closed deals stop it. Added a manually operated lead follow-up cycle with per-lead customizable timing, stage, notes and recent events, scope checks, and follow-up target/report counts based on manually marked sent events. Browser checks used a disposable copy of the preview database: starting, changing timing, marking sent, recording a reply, pausing for a meeting and closing a linked deal. Automated tests cover timing, closure, permissions and target calculation.

This increment is not the full old workflow: cadence defaults are per lead rather than a saved workspace-wide setting, there is no consolidated due/overdue follow-up queue or automatic client-reply detection, and no messages or notifications are sent automatically. Opening an individual lead displays its due time. Client/deal status synchronization, existing legacy data migration, broader browser/permission checks and production readiness remain open. Meeting/interview target achievement is not yet connected. Follow-up and deal events are manually entered; no Upwork browser automation was added.

## Legacy application feature review and proposal writer increment — 2026-11-19

Reviewed the legacy desktop feature map, core workflow functions and the proposal writer, AI, drafting, job parser, follow-up, meetings, reporting and settings implementations against the current web app and master scope. The old app contains proposal job capture/parsing, reusable templates, AI generate/revise, voice input, saved drafts and manual Upwork submission recording; it also contains follow-up message drafting, customizable follow-up timing, read-only Upwork clipboard imports, meetings and Google Calendar, planning, monthly reports, CSV import/export, backup and restore. Legacy AI requires a separately configured OpenAI API credential and sends supplied text to the provider. Existing Windows credential storage is machine-local and must not be reused as a shared server secret or exposed to users.

Added scoped job-description, writing-instructions and cover-letter storage to web proposal records, with editable form fields and copy action. Repaired the proposal table to display connects and its existing history action. This is manual writing and storage, not the legacy AI generator, voice workflow, template manager or Upwork integration. Browser-tested create, history and reopening a draft in a disposable preview database. Automated suite: 55 tests, 498 assertions; TypeScript and frontend build pass. Preview migration applied without importing real legacy records.

Legacy features still needing implementation or integration include AI proposal generation/revision, follow-up AI drafts, templates, voice, job-text parser/import and duplicate handling, safe read-only Upwork connection using the user's existing browser, full follow-up due queue and settings, meetings and calendar, planner, backup/restore and safe legacy-data migration. Broader master scope additionally requires tasks/assignment workflows, AI permissions and usage monitoring, organization/team reporting, production mail/scheduler, hosting, and full security and production testing. The previous source implementation is not proof these features exist or work in the web application. Payment tracking remains outside scope; closed project value alone is recorded.

## AI writing integration increment — 2026-11-19

Added an AI writing assistant for proposal and follow-up drafts, configurable per-user style prompt and model, and voice instruction transcription through the OpenAI API. Each authorized user can save or remove their own encrypted API key; the key is never returned to the browser after saving. User-supplied job/client context, instructions and audio are transmitted to OpenAI only on explicit generation or transcription. AI outputs remain draft-only and can be reviewed/copied; no Upwork action is performed. The existing AI sales agent create permission protects these endpoints. Automated tests use mocked OpenAI requests and cover key encryption, permissions, generation and removal. Browser-checked saving style and a fake key in a disposable database. The real provider, real key, microphone and transcription flow have not been tested end-to-end, and this is not production-ready until HTTPS, deployment secret handling and usage controls are verified.

Still pending from the user's request: legacy browser-based read-only Upwork import using the existing browser/profile, proposal writer templates and automatic save integration, calendar/meeting workflows and Google account connection, AI usage tracking/budgets and comprehensive permission tests. Previous Google OAuth connection belongs to the desktop app and must not be assumed to transfer to the web app. Legacy real-data migration is not needed per user, who says it contains no significant data. Follow-up and proposal content are manually copied into records; no payment tracking is in scope.

## Product workflow increment — 2026-11-19

AI-generated or manually edited proposal drafts can now be saved directly from the AI writer into the existing permission-protected proposal records; the proposal list refreshes, and later edits must be made in that saved record. Follow-up cycles have a paginated list with lead, stage, upcoming/due status and access to the existing cycle controls. Results are scoped to leads the user is allowed to view and exclude archived, paused and closed leads/deals; completed cycles can still appear labelled complete. List ordering is by last cycle activity, not due time. The microphone now stops after two minutes and releases its device on cleanup.

Automated checks passed: 56 tests / 520 assertions, including scoped queue behavior and closed/cross-organization cases. Frontend build and TypeScript pass. Browser verification was attempted against a disposable database, but browser navigation did not complete; the new UI was not end-to-end verified. Real OpenAI calls and microphone capture remain unverified. Existing major gaps remain as documented above, including legacy Upwork read-only import, calendar/meetings, full follow-up management and production readiness.

## Local AI settings access and workflow improvements — 2026-11-19

Started the local preview and opened the AI settings for the user. The preview database had no organization or users, so initialized an explicitly local preview administrator using the interactive setup command; this is a preview account and must not be used for production hosting. The user was instructed to enter the API key directly into the application; no real key was read or inspected by the assistant.

Added a user-triggered clipboard paste control for copied job text in the AI writer; this does not read or automate Upwork and is not the full legacy import. Follow-up cycle actions now disable their buttons while a request is in flight and notify the follow-up list to refresh. Frontend TypeScript/build and full automated suite passed (56 tests, 520 assertions). Live AI, microphone, clipboard, browser import and external calendar end-to-end verification remain pending. Production requires proper administrator credentials, HTTPS and deployment-specific secret handling.

## Local AI connection troubleshooting — 2026-11-19

The local preview server had stopped, so it was restarted as a hidden local process. Fixed PHP's missing CA configuration using a locally installed trusted CA bundle; TLS verification remains enabled. A test request reached OpenAI but returned HTTP 401. The key had been provided in conversation, and the entered key was removed from application settings after the failed test; no key or provider response details were saved to this document. User should revoke the exposed key at the provider and supply a replacement directly through the application's key field. Failure cause beyond HTTP 401 was not established, and live generation is not verified. Added sanitized, actionable provider error messages and automated authorization-failure coverage.

## AI live connection and personal follow-up defaults — 2026-11-19

After the user entered a replacement API key directly, one real proposal generation request succeeded. No key was inspected or recorded. This establishes one live text-generation path only; microphone transcription and live follow-up generation were not verified. Subsequent browser request reported an unauthenticated session. The local preview remains a development account and is not production hosting.

Added authenticated per-user default follow-up timing with the legacy default 24, 48, 48, 72, 72 hours, configurable from 1 to 10 steps of 1–720 hours. New cycles load the signed-in user's preference; existing cycles retain their current settings. Preferences require lead view/edit access and are isolated by user and organization. Automated tests cover defaults, invalid values, saved settings, isolation, permissions and existing-cycle preservation. Applied the migration to the preview database. Full suite 58 tests and 538 assertions passed; TypeScript and frontend build passed. The new settings UI has not yet been browser-verified. External Upwork import, calendar, production readiness and remaining module work stay open.

## Preview reset incident and test isolation — 2026-11-19

During the previous turn, a test command inherited DB_DATABASE pointing to the local preview SQLite file. PHPUnit environment values were not forced over the inherited environment and RefreshDatabase reset that preview database. This removed the preview account and its saved AI settings; no matching backup was found in the checked local toolchain/temp locations. The legacy database was not the target. Recreated the local preview administrator with the existing preview credentials; the user's replacement OpenAI key must be entered again through the app, and was not recovered or read.

Added forced test database environment values and a TestCase guard that refuses to run unless the effective database is in-memory SQLite. Verified a test invocation with preview DB inherited now refuses safely, then ran the suite with explicit in-memory SQLite (59 tests / 543 assertions). Browser-verified saving and reloading new default follow-up timing, then restored its default; fixed a loading race so the settings button remains disabled until saved preferences load. Added a mocked audio transcription endpoint test including permission denial; real microphone and OpenAI transcription are still unverified because the preview API setting was lost. No Upwork import or Google Calendar integration was completed in this increment. Legacy Windows vault contains a calendar refresh credential, but it has not been transferred or used by the web app; per-user authorization and safe integration remain required.

## Live voice verification — 2026-11-19

With the user's replacement key and authorization, tested the transcription endpoint against OpenAI using locally synthesized sample speech; returned text matched the sample. Also exercised the actual browser Record/Stop flow using a simulated microphone stream containing the synthetic speech, and verified that transcription was appended to the instruction field. This does not verify the user's physical microphone or device permission. The temporary test recording was removed; no key was inspected or recorded. The user was asked asynchronously whether they can check the physical microphone.

The prior preview-database incident and test-isolation guard remain documented above. Both client and refresh credentials for the legacy Google Calendar connection are present in the Windows credential vault, but have not been copied into the web app or used as a shared credential. Safe user-specific web integration, Upwork read-only import, and their end-to-end verification remain incomplete.

## Copied Upwork proposal import — 2026-11-19

Added a read-only copied-text proposal import, based on the legacy English proposals-list parser. The user copies the page in their existing Upwork browser, pastes the text, reviews/edits/removes extracted title, date and status rows, then explicitly imports them. It does not automate the browser or change Upwork. Import requires both proposals create and import permissions; duplicate titles created by the same user are skipped, with no automatic updates to existing proposals. Imported status is a snapshot; no historical submitted timestamp or activity is invented. The parser is best-effort, English-layout dependent, capped at 100 rows and is not the legacy automatic browser scan or job-details importer.

Browser-verified the extraction/review with synthetic text; automated tests verify authorization, import, duplicate skipping, snapshot submitted timestamp and validation. Full suite 60 tests / 550 assertions, TypeScript and build passed. Importing real Upwork data and Google Calendar integration remain unverified/incomplete. User confirmed their physical microphone and transcription work. The preview-database test guard remains mandatory; tests must use explicit in-memory settings.

## Google Calendar integration implementation — 2026-11-19

Added per-user Google Calendar connection, OAuth state and PKCE validation, encrypted refresh-token storage, listing up to 100 events and explicitly creating an event with an optional Google Meet request, plus local disconnect. Meetings permissions are enforced. OAuth client configuration is required through GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET and GOOGLE_CALENDAR_REDIRECT_URI. The previous desktop OAuth client is an installed-app client and was not reused or copied as a web client. Google web OAuth setup and user consent are still required; no live Google account, real event or Google Meet creation has been tested. Test fakes cover scoped authorization, state rejection, token encryption, event listing and create-event payload. The preview migration was run without running tests against that database. Frontend build and TypeScript passed; full test suite passed before the final targeted test addition and the calendar targeted tests passed afterward.

Existing copied-text Upwork import still needs real signed-in Upwork verification; automatic capture from the user's existing browser is not implemented. An integrated browser attempt reached an Upwork login screen, not the user's already-signed-in browser, so no login or import was performed. The user was asked to share the existing signed-in tab and to sign into the Google Cloud account needed for setup. Neither integration should be marked 100% complete or production-ready.

## Google Cloud web OAuth setup — 2026-11-19

With the signed-in user's direction, created a web OAuth client in the existing Google Cloud project with the local preview callback. The first newly created client secret appeared in a tool result during inspection; it was disabled, and the unused client containing it was deleted. Created a replacement web client and transferred its credentials by browser clipboard into an organization-admin-only LeadPilot setup form; both client ID and client secret are encrypted in the database. No secret was intentionally recorded in these notes. The old desktop client was not modified. The Google consent account chooser was opened for the user; consent and a successful real Calendar connection are not yet confirmed. No calendar event was created. OAuth config permissions/encryption and calendar fakes passed; full isolated test suite 64 tests / 576 assertions. The automatic Upwork browser import remains incomplete and the user has not yet shared a signed-in Upwork tab.

## Live Google Calendar connection verified — 2026-11-19

The user completed Google consent for the new local preview web client. A read-only status/events check returned connected=true and HTTP 200 with four events; event details were not recorded here. This confirms the real account connection and read path. Real event creation, Meet link creation, event updates/deletions, multi-user production deployment, and automatic Upwork browser capture remain unverified/incomplete. The previous desktop connection was not modified.

## Upwork automatic sync approval requirement — 2026-11-19

The user requested automatic Upwork data retrieval immediately after account connection and confirmed they do not currently have Upwork API access. Official Upwork guidance says automated data collection, including browser tools and scraping, needs approved API access and that access is limited to the approved use case. Upwork also states eligibility requirements and personal/internal-use limits. Do not implement or activate automatic page scraping or bypass controls. The existing user-initiated copied-text import is partial and is not verified against the real account. The user should request API access through Upwork and the granted scopes must be verified before designing a real sync. The user's established preference is to use their existing signed-in browser and not open a new Upwork profile.

## Upwork job writing workflow increment — 2026-11-19

Added a job URL field and an Open job button to the AI writer. This opens a valid HTTPS Upwork job URL as a new tab in the browser currently displaying LeadPilot; it does not guarantee that browser has the user's existing Upwork profile. Added a copied-page text area and a best-effort extraction of job title, description, client information and screening questions, with editable fields. Extracted client information and questions are included in the AI writing context and saved proposal description; the job URL is saved with the proposal. Output must be reviewed, since real page formats can vary. Browser-tested one synthetic text fixture and verified title, description, client info and question fields. TypeScript and frontend build passed.

This does not implement the requested automatic reading of a signed-in Upwork browser. Copying visible page text remains a user action, real Upwork page verification remains pending, and client data/questions are not guaranteed to be recognized. Upwork's published automation guidance was previously reviewed. No Upwork profile, credentials or browser sessions were accessed by this increment.

## Onboarding reconnect verification - 2026-11-23

The user authorized disconnecting and reconnecting the existing Upwork account for a real test, and personally accepted the Upwork authorization terms. The connection was restored. The live connected-account onboarding was then opened manually using the connected callback state: the profile snapshot saved, the existing CRM profile was preserved, zero proposal previews were returned, and one conversation preview was synced to a lead. The live chat displayed the last available message without the technical wrapper tags. The knowledge-base skip, target screen, saving the existing target values (30 leads, 30% view rate, 60% lead rate, 20% close rate), and navigation to the existing dashboard were exercised. Dashboard showed 1 / 30 leads. No assumption that zero proposal previews means zero total history.

Pending for later verification: observe the actual OAuth callback landing automatically on onboarding without manually opening the callback state; verify a genuinely new LeadPilot user and Upwork authorization; test proposal history manual import with real data and multiple pages; verify remaining conversation pages and partial/error handling; and verify dashboard and follow-up counts against imported data with reliable timestamps and sender information. Full messages and complete proposal history are not automatically imported. The user chose to defer further verification.
