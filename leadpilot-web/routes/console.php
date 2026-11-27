<?php

use Illuminate\Foundation\Inspiring;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Schedule;

Schedule::command('leadpilot:prune-activity')->daily()->withoutOverlapping();
// Follow-up reminders: schedules due dates and logs reminders only. It never sends a message to a client.
Schedule::command('leadpilot:follow-ups')->everyFiveMinutes()->withoutOverlapping(10);

Artisan::command('inspire', function () {
    $this->comment(Inspiring::quote());
})->purpose('Display an inspiring quote');
