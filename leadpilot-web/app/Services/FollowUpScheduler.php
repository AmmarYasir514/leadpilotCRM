<?php

namespace App\Services;

use App\Support\SystemTimezone;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Follow-up timing rules, matching the LeadPilot desktop app (leadpilot_crm.py).
 * This class only schedules due dates and writes reminders. It never sends anything to a client.
 */
class FollowUpScheduler
{
    public const STAGES = ['Chat started', 'Proposal sent, awaiting response', 'Meeting requested, no reply yet', 'Meeting booked', 'Contract offer, awaiting offer from client', 'Offer sent, awaiting acceptance', 'Contract started'];

    /** Desktop STAGE_PAUSED: no follow-ups are due while a lead is in these stages. */
    public const PAUSED_STAGES = ['Meeting booked', 'Contract started'];

    public const CLOSED_STATUSES = ['won', 'lost', 'dead'];

    public const DEFAULT_CADENCE = [24, 48, 48, 72, 72];

    public static function isPaused(?string $stage): bool
    {
        return in_array($stage, self::PAUSED_STAGES, true);
    }

    public static function isClosed(object $lead): bool
    {
        return in_array($lead->status, self::CLOSED_STATUSES, true)
            || DB::table('deals')->where('organization_id', $lead->organization_id)->where('lead_id', $lead->id)->whereIn('status', ['won', 'lost'])->exists();
    }

    /** When the next follow-up is due, or null when the lead is closed, paused or every step is done (desktop _fu_next). */
    public static function dueAt(object $cycle, bool $closed): ?Carbon
    {
        $cadence = is_array($cycle->cadence) ? $cycle->cadence : json_decode($cycle->cadence, true);
        if ($closed || self::isPaused($cycle->stage) || $cycle->completed >= count($cadence)) {
            return null;
        }

        return Carbon::parse($cycle->anchor_at, 'UTC')->addHours((int) $cadence[$cycle->completed]);
    }

    /** Store the current due time for one lead's cycle. */
    public function refresh(int $organizationId, int $leadId): void
    {
        $lead = DB::table('leads')->where('organization_id', $organizationId)->where('id', $leadId)->first();
        $cycle = DB::table('follow_up_cycles')->where('organization_id', $organizationId)->where('lead_id', $leadId)->first();
        if (! $lead || ! $cycle) {
            return;
        }
        $due = self::dueAt($cycle, $lead->archived_at !== null || self::isClosed($lead));
        DB::table('follow_up_cycles')->where('id', $cycle->id)->update(['next_due_at' => $due?->format('Y-m-d H:i:s')]);
    }

    /**
     * The scheduled job. Starts a cycle for open leads that have none (desktop _fu_init_missing),
     * keeps every due time current, and writes one "due" reminder per follow-up step when it becomes due.
     */
    public function run(?Carbon $now = null): array
    {
        $now = ($now ?? now())->copy()->utc();
        // Lead dates are calendar days on this computer's clock (SystemTimezone), the same zone the desktop import uses.
        $stats = ['started' => 0, 'scheduled' => 0, 'paused' => 0, 'closed' => 0, 'done' => 0, 'reminders' => 0];
        DB::table('leads')->whereNull('archived_at')->orderBy('id')->chunkById(200, function ($leads) use ($now, &$stats): void {
            foreach ($leads as $lead) {
                DB::transaction(function () use ($lead, $now, &$stats): void {
                    $closed = self::isClosed($lead);
                    $cycle = DB::table('follow_up_cycles')->where('organization_id', $lead->organization_id)->where('lead_id', $lead->id)->lockForUpdate()->first();
                    if (! $cycle) {
                        if ($closed) {
                            $stats['closed']++;

                            return;
                        }
                        $anchor = $lead->lead_date ? Carbon::parse(substr((string) $lead->lead_date, 0, 10), SystemTimezone::get())->startOfDay()->utc() : Carbon::parse($lead->created_at ?? $now, 'UTC');
                        $id = DB::table('follow_up_cycles')->insertGetId(['organization_id' => $lead->organization_id, 'lead_id' => $lead->id, 'stage' => 'Chat started', 'cadence' => json_encode($this->cadenceFor($lead)), 'completed' => 0, 'anchor_at' => $anchor->format('Y-m-d H:i:s'), 'created_at' => $now, 'updated_at' => $now]);
                        DB::table('follow_up_events')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $lead->id, 'actor_id' => null, 'action' => 'auto_start', 'note' => 'Follow-up cycle started automatically. Nothing is sent to the client.', 'created_at' => $now]);
                        $cycle = DB::table('follow_up_cycles')->where('id', $id)->first();
                        $stats['started']++;
                    }
                    $due = self::dueAt($cycle, $closed);
                    $dueText = $due?->format('Y-m-d H:i:s');
                    $changes = [];
                    if ($cycle->next_due_at !== $dueText) {
                        $changes['next_due_at'] = $dueText;
                    }
                    if ($closed) {
                        $stats['closed']++;
                    } elseif (self::isPaused($cycle->stage)) {
                        $stats['paused']++;
                    } elseif ($due) {
                        $stats['scheduled']++;
                    } else {
                        $stats['done']++;
                    }
                    // One reminder per step: a step only changes when the clock restarts (sent, reply, stage change), so a reminder
                    // logged after the current anchor already covers this step, even if the timings are changed later.
                    if ($due && $due->lte($now) && ($cycle->reminded_at === null || Carbon::parse($cycle->reminded_at, 'UTC')->lte(Carbon::parse($cycle->anchor_at, 'UTC')))) {
                        $steps = count(json_decode($cycle->cadence, true));
                        DB::table('follow_up_events')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $lead->id, 'actor_id' => null, 'action' => 'due', 'note' => sprintf('Follow-up %d of %d is due. Write and send it yourself, then click Mark follow-up sent. Nothing was sent automatically.', $cycle->completed + 1, $steps), 'created_at' => $now]);
                        $changes['reminded_at'] = $now->format('Y-m-d H:i:s');
                        $stats['reminders']++;
                    }
                    if ($changes) {
                        DB::table('follow_up_cycles')->where('id', $cycle->id)->update($changes);
                    }
                });
            }
        });

        return $stats;
    }

    private function cadenceFor(object $lead): array
    {
        $stored = DB::table('follow_up_preferences')->where('organization_id', $lead->organization_id)->where('user_id', $lead->assigned_to)->value('cadence');

        return $stored ? json_decode($stored, true) : self::DEFAULT_CADENCE;
    }
}
