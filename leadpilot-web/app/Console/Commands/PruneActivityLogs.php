<?php

namespace App\Console\Commands;

use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

#[Signature('leadpilot:prune-activity')]
#[Description('Prune expired routine sign-in and sign-out events for organizations that enabled retention')]
class PruneActivityLogs extends Command
{
    /**
     * Execute the console command.
     */
    public function handle(): int
    {
        DB::table('organizations')->whereNotNull('activity_retention_days')->orderBy('id')->chunkById(100, function ($organizations): void {
            foreach ($organizations as $organization) {
                DB::transaction(function () use ($organization): void {
                    $current = DB::table('organizations')->where('id', $organization->id)->lockForUpdate()->first();
                    if (! $current || $current->activity_retention_days === null || $current->activity_retention_days < 30) {
                        return;
                    }
                    $removed = DB::table('audit_logs')->where('organization_id', $current->id)
                        ->whereIn('action', ['auth.login', 'auth.logout'])
                        ->where('created_at', '<', now()->subDays($current->activity_retention_days))
                        ->delete();
                    if ($removed > 0) {
                        DB::table('audit_logs')->insert(['organization_id' => $current->id, 'actor_id' => null, 'action' => 'activity.retention_cleanup', 'subject_type' => 'organization', 'subject_id' => $current->id, 'created_at' => now()]);
                    }
                });
            }
        });

        return self::SUCCESS;
    }
}
