# LeadPilot Dev - End of Session Checklist

Added Nov 25, 2026 at Ammar Yasir's request.

## At the end of every work session (or when work is wrapped up)

1. Push all updates to GitHub: https://github.com/AmmarYasir514/leadpilotCRM (branch: main).
   - Run `git status` and review what changed.
   - Never commit secrets: .env, API keys, tokens, passwords, database files (*.sqlite, *.db) or backups that contain data.
   - Commit with a clear message describing the session's work, then `git push origin main`.
   - Confirm the push worked (`git status` shows main is up to date with origin/main).
2. Report to Ammar and CEO what was pushed (commit id and summary).

## Standing rules (always)

- Back up any file before editing it (dated _BACKUP_ copy).
- Never touch leadpilot_qa.py, run_qa_parallel.py or QA_reports.
- Never edit live data directly; back up a database before any change.
- Never send, submit or click anything on Upwork. Never send messages or emails.