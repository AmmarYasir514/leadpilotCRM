<?php

namespace App\Console\Commands;

use App\Services\FollowUpScheduler;
use App\Support\SystemTimezone;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use PDO;
use PDOException;
use Throwable;

#[Signature('leadpilot:import-desktop {--path= : Path to the desktop leadpilot.db (only a read-only copy is opened)} {--owner= : Email or id of the user who will own the imported leads} {--organization= : Organization id (defaults to the owner organization)} {--timezone= : Time zone of the times saved by the desktop app (defaults to this computer time zone)}')]
#[Description('Import leads and their follow-up cycle state from the LeadPilot desktop database. Safe to run again: already imported leads are skipped.')]
class ImportDesktopLeads extends Command
{
    private const STATUSES = ['new', 'qualified', 'contacted', 'follow-up', 'interview', 'negotiation', 'won', 'lost', 'dead'];

    public function handle(): int
    {
        $path = (string) $this->option('path');
        if ($path === '' || ! is_file($path)) {
            $this->error('Desktop database not found: '.$path);

            return self::FAILURE;
        }
        $ownerOption = (string) $this->option('owner');
        $owner = ctype_digit($ownerOption) ? DB::table('users')->where('id', (int) $ownerOption)->first() : DB::table('users')->where('email', $ownerOption)->first();
        if (! $owner) {
            $this->error('Owner not found. Pass --owner=<email or user id>.');

            return self::FAILURE;
        }
        $organization = (int) ($this->option('organization') ?: $owner->organization_id);
        if (! $organization || (int) $owner->organization_id !== $organization || ! DB::table('organizations')->where('id', $organization)->exists()) {
            $this->error('The owner must belong to the chosen organization.');

            return self::FAILURE;
        }
        $timezone = trim((string) $this->option('timezone')) ?: SystemTimezone::get();
        if (! SystemTimezone::valid($timezone)) {
            $this->error('Unknown time zone: '.$timezone);

            return self::FAILURE;
        }
        $this->line('Desktop times are read as '.$timezone.' time.');

        // Work on a temporary copy opened read-only, so the desktop database itself is never opened for writing.
        $copy = tempnam(sys_get_temp_dir(), 'lp_desktop_');
        try {
            copy($path, $copy);
            if (is_file($path.'-wal')) {
                copy($path.'-wal', $copy.'-wal');
            }
            $source = new PDO('sqlite:'.$copy, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC, PDO::SQLITE_ATTR_OPEN_FLAGS => PDO::SQLITE_OPEN_READONLY]);
            if (! $source->query("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'leads'")->fetchColumn()) {
                $source = null;
                $this->error('This file has no leads table, so it is not a LeadPilot desktop database: '.$path);

                return self::FAILURE;
            }
            $cadence = $this->cadence($source);
            $rows = $source->query('SELECT * FROM leads ORDER BY id')->fetchAll();
            $source = null;
        } catch (PDOException) {
            $source = null;
            $this->error('Could not read this file as a LeadPilot desktop database (it may be damaged or a different kind of file): '.$path);

            return self::FAILURE;
        } finally {
            @unlink($copy);
            @unlink($copy.'-wal');
            @unlink($copy.'-shm');
        }

        $stats = ['source' => count($rows), 'imported' => 0, 'skipped' => 0, 'duplicates' => 0, 'cycles' => 0, 'mismatch' => 0];
        $seen = [];
        DB::transaction(function () use ($rows, $owner, $organization, $timezone, $cadence, &$stats, &$seen): void {
            foreach ($rows as $row) {
                $key = 'desktop:'.$row['id'];
                if (isset($seen[$key])) {
                    $stats['duplicates']++;
                    $this->warn(sprintf('Desktop lead id %s appears more than once in the file; only the first copy was used.', $row['id']));

                    continue;
                }
                $seen[$key] = true;
                if (DB::table('leads')->where('organization_id', $organization)->where('import_key', $key)->exists()) {
                    $stats['skipped']++;

                    continue;
                }
                $status = strtolower(trim((string) ($row['status'] ?? '')));
                $status = in_array($status, self::STATUSES, true) ? $status : 'new';
                $created = $this->time($row['created_at'] ?? null, 'UTC') ?? now();
                $leadId = DB::table('leads')->insertGetId([
                    'organization_id' => $organization, 'created_by' => $owner->id, 'assigned_to' => $owner->id, 'team_id' => $owner->team_id,
                    'name' => mb_substr(trim((string) $row['name']) ?: 'Unnamed lead', 0, 255),
                    'company' => trim((string) ($row['company'] ?? '')) !== '' ? mb_substr(trim($row['company']), 0, 255) : null,
                    'source' => mb_substr(trim((string) ($row['source'] ?? '')) ?: 'LeadPilot desktop', 0, 100),
                    'status' => $status, 'notes' => $this->notes($row),
                    'lead_date' => preg_match('/^\d{4}-\d{2}-\d{2}/', (string) ($row['lead_date'] ?? '')) ? substr($row['lead_date'], 0, 10) : null,
                    'budget' => (float) ($row['budget'] ?? 0) > 0 ? $row['budget'] : null,
                    'import_key' => $key, 'created_at' => $created, 'updated_at' => now(),
                ]);
                DB::table('lead_stage_history')->insert(['organization_id' => $organization, 'lead_id' => $leadId, 'actor_id' => null, 'from_status' => null, 'to_status' => $status, 'created_at' => now()]);

                $stage = in_array($row['sales_stage'] ?? null, FollowUpScheduler::STAGES, true) ? $row['sales_stage'] : 'Chat started';
                $anchor = $this->time($row['fu_anchor'] ?? null, $timezone) ?? $this->time($row['chat_start'] ?? null, $timezone) ?? $this->time($row['lead_date'] ?? null, $timezone) ?? $created;
                $cycle = (object) ['stage' => $stage, 'cadence' => $cadence, 'completed' => max(0, min((int) ($row['fu_count'] ?? 0), count($cadence))), 'anchor_at' => $anchor->format('Y-m-d H:i:s')];
                $due = FollowUpScheduler::dueAt($cycle, in_array($status, FollowUpScheduler::CLOSED_STATUSES, true));
                DB::table('follow_up_cycles')->insert(['organization_id' => $organization, 'lead_id' => $leadId, 'stage' => $stage, 'cadence' => json_encode($cadence), 'completed' => $cycle->completed, 'anchor_at' => $cycle->anchor_at, 'next_due_at' => $due?->format('Y-m-d H:i:s'), 'created_at' => now(), 'updated_at' => now()]);
                DB::table('follow_up_events')->insert(['organization_id' => $organization, 'lead_id' => $leadId, 'actor_id' => null, 'action' => 'imported', 'note' => sprintf('Imported from LeadPilot desktop lead #%d. Stage: %s. Follow-ups done: %d of %d.', $row['id'], $stage, $cycle->completed, count($cadence)), 'created_at' => now()]);

                // The desktop app stores its own next due time; check ours matches it.
                $desktopDue = $this->time($row['next_followup'] ?? null, $timezone)?->format('Y-m-d H:i');
                if ($desktopDue !== $due?->format('Y-m-d H:i')) {
                    $stats['mismatch']++;
                    $this->warn(sprintf('Lead #%d due time differs: desktop %s, web %s (UTC).', $row['id'], $desktopDue ?? 'none', $due?->format('Y-m-d H:i') ?? 'none'));
                }
                $stats['imported']++;
                $stats['cycles']++;
            }
        });

        $this->info(sprintf('Source leads: %d. Imported: %d. Skipped (already imported): %d. Duplicate source ids skipped: %d. Follow-up cycles created: %d. Due time mismatches: %d.', $stats['source'], $stats['imported'], $stats['skipped'], $stats['duplicates'], $stats['cycles'], $stats['mismatch']));

        return self::SUCCESS;
    }

    private function cadence(PDO $source): array
    {
        try {
            $value = $source->query("SELECT v FROM settings WHERE k = 'fu_cadence'")->fetchColumn();
        } catch (Throwable) {
            $value = false;
        }
        $hours = $value ? array_map('intval', array_filter(array_map('trim', explode(',', (string) $value)), 'strlen')) : [];
        $valid = $hours && count($hours) <= 10 && min($hours) >= 1 && max($hours) <= 720;

        return $valid ? array_values($hours) : FollowUpScheduler::DEFAULT_CADENCE;
    }

    /** Desktop times look like "2026-11-17 00:49" in local time; return them in UTC. */
    private function time(?string $value, string $timezone): ?Carbon
    {
        $value = trim((string) $value);
        if ($value === '') {
            return null;
        }
        try {
            return Carbon::parse($value, $timezone)->utc();
        } catch (Throwable) {
            return null;
        }
    }

    private function notes(array $row): ?string
    {
        $parts = array_filter([
            trim((string) ($row['notes'] ?? '')),
            trim((string) ($row['job_title'] ?? '')) !== '' ? 'Job: '.trim($row['job_title']) : '',
            trim((string) ($row['closed_reason'] ?? '')) !== '' ? 'Closed reason: '.trim($row['closed_reason']) : '',
            'Imported from LeadPilot desktop (lead #'.$row['id'].').',
        ]);

        return mb_substr(implode("\n", $parts), 0, 10000);
    }
}
