<?php

namespace App\Console\Commands;

use App\Services\FollowUpScheduler;
use Illuminate\Console\Attributes\Description;
use Illuminate\Console\Attributes\Signature;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Log;
use Throwable;

#[Signature('leadpilot:follow-ups')]
#[Description('Schedule follow-up due dates and log reminders when they are due. Never sends any message to a client.')]
class RunFollowUpAutomation extends Command
{
    public function handle(FollowUpScheduler $scheduler): int
    {
        // Only one run at a time, and a second run skips cleanly. The lock uses the file cache, not the database,
        // so waiting runs never write to SQLite while the active run is inside a transaction.
        // A busy lock means another run is working: skip quietly. A lock error is a real problem: log it and fail loudly.
        try {
            $lock = Cache::store('file')->lock('leadpilot:follow-ups', 600);
            $acquired = $lock->get();
        } catch (Throwable $e) {
            Log::error('Follow-up run could not use its lock, so no reminders were checked.', ['error' => $e->getMessage()]);
            $this->error('Follow-up run failed: the lock folder could not be used ('.$e->getMessage().'). No reminders were checked. Make sure storage/framework/cache/locks is a folder the app can write to.');

            return self::FAILURE;
        }
        if (! $acquired) {
            $this->info('Another follow-up run is already in progress, so this run was skipped. Nothing was changed.');

            return self::SUCCESS;
        }
        try {
            $s = $scheduler->run();
        } finally {
            try {
                $lock->release();
            } catch (Throwable) {
                $this->warn('Could not release the follow-up lock; it expires on its own within 10 minutes.');
            }
        }
        $this->info(sprintf('Follow-ups checked. Started: %d. Scheduled: %d. Paused: %d. Closed: %d. All steps done: %d. Reminders logged: %d. Messages sent: 0.', $s['started'], $s['scheduled'], $s['paused'], $s['closed'], $s['done'], $s['reminders']));

        return self::SUCCESS;
    }
}
