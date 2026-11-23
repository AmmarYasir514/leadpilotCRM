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
