LEADPILOT CRM v1.3 - UPWORK SALES WORKSPACE (WINDOWS DESKTOP)

WHAT IT IS
LeadPilot is a desktop sales workspace for Upwork business development.
It keeps your proposals, leads, follow-ups and client meetings in one place
on your own computer. It reminds you when follow-ups are due, shows how the
month is going against your targets, and makes a printable monthly report.

REQUIREMENTS
- Windows 10 or 11.
- Python 3.10 or newer, with "Add Python to PATH" selected during install.
  Tkinter and SQLite come with standard Python.
- Optional: the keyring package (python -m pip install keyring).
  It is needed to save your Upwork login and to connect Google Calendar.
  Both are stored in the Windows password vault (Credential Manager),
  never in a file. Everything else works without it.

HOW TO RUN
- First time: double-click Setup_LeadPilot.bat. It checks for Python and
  Tkinter (and tries to install Python with winget if it is missing),
  then opens LeadPilot.
- After that: double-click Run_LeadPilot_CRM.bat,
  or run this in the LeadPilot folder:  python leadpilot_crm.py

PAGES
- Overview: summary cards, the proposal pipeline by status, Upwork job
  details, the saved cover letter for each job, and the latest leads.
- Proposals: add, edit and delete proposals. Eight statuses from Draft to
  Hired, Lost and Archived. Normal and boosted connects. Duplicate check.
- Leads & Pipeline: add, edit and delete leads, with dates and notes.
- Follow-ups: automatic follow-up cycle (24, 48, 48, 72, 72 hours) or your
  own cycle, seven sales stages, overdue and due-soon highlights, lead notes,
  and Import from Upwork (reads your copied Upwork Messages list).
- Performance: monthly targets with sliders, how many proposals you need,
  and this month's progress.
- Meetings: schedule, edit, cancel and delete meetings, open the meeting
  link, and get an alert 15 minutes to 2 hours before a meeting.
- Reporting: monthly reports, saved automatically when a new month starts.
  Export to CSV, or Print / Save as PDF.
- Upwork Connection: save your Upwork login in the Windows vault and open
  Upwork.
- Data & Backup: CSV templates, import and export, backup and restore.
- Fresh Audit (its own button in the left menu): reads your Upwork
  Submitted proposals pages and adds or updates the jobs in LeadPilot.

WHERE YOUR DATA LIVES
All data stays on this computer, in:
  %USERPROFILE%\LeadPilotCRM\
- leadpilot.db   the database with all your records
- reports\       report pages made by Print / Save as PDF
- backups\       the safety copy saved before each restore
The Data & Backup page shows the exact database location.

GOOGLE CALENDAR (OPTIONAL)
- You need your own Google "OAuth client" file (type "Desktop app") from
  Google Cloud Console, and the keyring package.
- On the Meetings page, click Connect Google Calendar, choose that file,
  then sign in to Google in your browser.
- Meetings sync both ways: changes in LeadPilot go to Google, and Google
  events show in LeadPilot without duplicates. It syncs again every
  10 minutes while LeadPilot is open, or when you click Sync.
- Disconnect Google removes the events pulled from Google. Meetings you
  made in LeadPilot stay.

UPWORK FEATURES
- LeadPilot only reads from Upwork. It never sends proposals or messages,
  and never changes anything on Upwork.
- Fresh Audit and Import from Upwork work with the Upwork page open in your
  own browser, where you are already logged in. LeadPilot copies the page
  text (the same as pressing Ctrl+A and Ctrl+C) and reads it.
- These two features need Windows and Upwork's English pages.

BACKUP AND RESTORE
- Data & Backup > Create database backup saves a copy of your database
  wherever you choose.
- Data & Backup > Restore from backup replaces all current data with a
  backup file. Your current data is saved first in the backups folder,
  so you can undo it.
- Make regular backups.

QUALITY CHECKS (QA)
- Run_QA.bat runs the full test suite (leadpilot_qa.py).
- Run_QA_Parallel.bat runs the same suite in two parallel parts
  (run_qa_parallel.py), which is faster.
- The tests work on a copy of your data. Results are saved in the
  QA_reports folder.

LIMITS
- One computer only. There is no sync between team members or computers,
  and no user login or permissions.
- Do not type Upwork passwords or other secrets into notes or CSV files.
