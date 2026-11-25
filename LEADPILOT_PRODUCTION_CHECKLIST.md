# LeadPilot production checklist

Saved Nov 25, 2026 from the LeadPilot web quality audit. Do these when LeadPilot web moves to production, not while it is local.

- [ ] Move the database from SQLite to MySQL or PostgreSQL, with Redis for sessions, cache and queue, so many users can save at once.
- [ ] Do the performance work: add indexes on filtered columns (assigned_to, status, lead_id, team_id, archived_at with organization_id), page long lists, add caching and split the large front-end bundle so pages load faster.
- [ ] Set the security settings for a live server: APP_DEBUG off, HTTPS only, secure cookies, production .env with real secrets kept out of git, and run composer and npm dependency audits.
- [ ] Add a README section that explains how the code is organised (folders, main modules, where each feature lives).