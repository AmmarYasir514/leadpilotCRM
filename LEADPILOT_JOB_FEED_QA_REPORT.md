# LeadPilot - Job feed and QA update

## Implemented
- Find New Job cards use a circular quick-check score and visual treatment inspired by the selected fourth design; existing actions and score details remain available.
- Automatic refresh runs while the signed-in LeadPilot browser page remains open, including when navigating to another CRM section. The displayed countdown is based on the scheduled time. Requests use the existing official MCP connection for Most Recent and Best Matches.
- New jobs are prepended, known jobs are updated without duplication when an Upwork identity is available, and the visible rolling list is capped at 50. Refresh failures pause automatic refresh, retain prior results, and require user action to resume.

## Verified
- Vite production build: passed.
- Five Node tests: passed; cover 2-7 minute delay bounds, deduplication, rolling feed ordering and 50-item cap, keyword title matching, and missing keywords.
- Live CRM browser: 16 jobs loaded; score rings rendered; countdown changed from 6:47 to 6:42 after navigating to Dashboard and back. This demonstrates countdown across CRM sections, not a complete timed automatic refresh cycle.

## Limits and outstanding work
- Browser-based refresh cannot run once the LeadPilot page/browser is closed, the machine sleeps, the session expires, or connectivity is lost. Browser background throttling can delay timers. This is not a server-side worker or a push notification. The rolling list is held in page memory and resets on reload.
- The actual scheduled refresh cycle, a 50-plus live job stream, responsiveness at multiple viewport sizes, and the error/429 response in a real account have not been fully tested. Manual tests must be completed before calling this production-ready.
- Upwork's published MCP guidance discourages polling every few minutes. Random intervals do not establish compliance or guarantee account safety; automatic refresh can be switched off in Find New Job. https://support.upwork.com/hc/en-us/articles/56577997707923-Rate-limits-for-Upwork-MCP
- Master developer instructions list phases 1-10 covering authentication, access control, dashboard, activity, performance, assignments, AI permissions, database, admin UI/UX, and security/testing. This task did not implement or verify all remaining work across those phases. Consult PHASE_HANDOFF_AND_OPEN_ITEMS.md and the master document for the existing inventory; those documents may contain older status and require a fresh audit against the current application.
- Full backend, tenant/security, accessibility, responsive UI, production environment and integration regression testing remain outstanding. PHP test execution was not available from the current PATH during this task. No claim of full software QA or completion is made.
