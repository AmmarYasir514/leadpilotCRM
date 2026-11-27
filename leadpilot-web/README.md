# LeadPilot CRM 2.0 ? development setup

This application is under active development and is not ready for production. The legacy desktop CRM uses a separate database and is not migrated automatically.

## Requirements

PHP 8.3 or later with SQLite, OpenSSL, mbstring, fileinfo, curl and zip extensions; Composer; Node.js and npm. For a shared production deployment, use a supported server database and configure TLS, secure sessions, backups, mail and environment secrets.

## Install

From this directory run:

```sh
composer install
npm ci
cp .env.example .env
php artisan key:generate
php artisan migrate
npm run build
php artisan leadpilot:setup
php artisan serve
```

On Windows, use `copy .env.example .env` instead of `cp`. The setup command prompts for the organization and initial Super Admin credentials; it has no default password. Run it only after migrations. Back up any existing database before changes. Do not commit `.env` or expose the development server publicly.

## Invitations and password resets

Configure a real mail transport and `APP_URL` in `.env` before sending invitations. The default log mailer is intentionally refused for password links. New accounts start as invited; an administrator sends a setup link from User Management. Links expire and are single-use. Administrators can revoke sessions or suspend accounts.

## Checks

```sh
php artisan test
npm run build
npx tsc --noEmit
```

The current SQLite development tests do not establish concurrency guarantees for a production server database. The frontend development dependencies currently report a high-severity Picomatch advisory; check `npm audit` and update when a compatible fix is available.

## Knowledge Base and AI Writer PDF limits

When using the **Use my knowledge base** writing source in the AI Writer, the following limits and rules apply:

- **Maximum 5 projects per draft:** You can manually select up to 5 projects (or leave all unchecked and mention project names in your instructions, up to 5 matched projects).
- **PDF file limits (per project):** Up to 5 MB file size and up to 15 pages per PDF.
- **Extracted text limit (per PDF):** Up to 30,000 characters of extracted text are stored per PDF.
- **Combined OpenAI payload cap:** Up to 100,000 characters total across all selected project data sent to OpenAI. If the combined JSON exceeds 100,000 characters, generation returns an error asking you to select fewer projects rather than silently truncating text.
- **Prompt handling:** Selected project data (`name`, `summary`, `skills`, `links`, and extracted `pdf_text`) is appended as JSON reference data alongside your job details and instructions in the OpenAI user message, and the system prompt instructs OpenAI to treat project documents as reference data, not instructions.
