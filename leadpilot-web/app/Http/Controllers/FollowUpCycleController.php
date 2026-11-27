<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Services\FollowUpScheduler;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class FollowUpCycleController extends Controller
{
    private const STAGES = FollowUpScheduler::STAGES;

    private function lead(Request $request, int $id, bool $edit = false): object
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        $query = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $id)->whereNull('archived_at');
        abort_unless($resolver->constrain(clone $query, $actor, 'leads', 'view', $actor->organization_id)->exists(), 404);
        if ($edit) {
            abort_unless($resolver->constrain(clone $query, $actor, 'leads', 'edit', $actor->organization_id)->exists(), 404);
        }

        return $query->first();
    }

    private function preference(Request $request): array
    {
        $user = $request->user();
        $stored = DB::table('follow_up_preferences')->where('organization_id', $user->organization_id)->where('user_id', $user->id)->value('cadence');

        return $stored ? json_decode($stored, true) : [24, 48, 48, 72, 72];
    }

    public function showPreference(Request $request): JsonResponse
    {
        $user = $request->user();
        abort_unless($user->organization_id && app(PermissionResolver::class)->scopes($user, 'leads', 'view', $user->organization_id), 403);

        return response()->json(['cadence' => $this->preference($request)]);
    }

    public function updatePreference(Request $request): JsonResponse
    {
        $user = $request->user();
        $resolver = app(PermissionResolver::class);
        abort_unless($user->organization_id && $resolver->scopes($user, 'leads', 'view', $user->organization_id) && $resolver->scopes($user, 'leads', 'edit', $user->organization_id), 403);
        $data = $request->validate(['cadence' => ['required', 'array', 'min:1', 'max:10'], 'cadence.*' => ['required', 'integer', 'min:1', 'max:720']]);
        DB::table('follow_up_preferences')->updateOrInsert(['organization_id' => $user->organization_id, 'user_id' => $user->id], ['cadence' => json_encode(array_values($data['cadence'])), 'updated_at' => now(), 'created_at' => now()]);

        return response()->json(['cadence' => array_values($data['cadence'])]);
    }

    public function queue(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'leads', 'view', $actor->organization_id), 403);
        $visible = $resolver->constrain(DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->whereNotIn('status', ['won', 'lost', 'dead']), $actor, 'leads', 'view', $actor->organization_id)->select('id');
        $cycles = DB::table('follow_up_cycles')->join('leads', 'leads.id', '=', 'follow_up_cycles.lead_id')
            ->where('follow_up_cycles.organization_id', $actor->organization_id)->whereIn('leads.id', $visible)
            ->whereNotIn('follow_up_cycles.stage', FollowUpScheduler::PAUSED_STAGES)
            ->whereNotExists(function ($query): void {
                $query->selectRaw('1')->from('deals')->whereColumn('deals.lead_id', 'leads.id')->whereColumn('deals.organization_id', 'leads.organization_id')->whereIn('deals.status', ['won', 'lost']);
            })
            ->select('follow_up_cycles.*', 'leads.name as lead_name')->orderBy('follow_up_cycles.anchor_at')->orderBy('follow_up_cycles.id')->paginate(25);
        $cycles->through(static function ($cycle) {
            $cadence = json_decode($cycle->cadence, true);
            $cycle->due_at = $cycle->completed < count($cadence) ? Carbon::parse($cycle->anchor_at, 'UTC')->addHours($cadence[$cycle->completed])->toIso8601String() : null;
            unset($cycle->cadence);

            return $cycle;
        });

        return response()->json($cycles);
    }

    public function show(Request $request, int $id): JsonResponse
    {
        $lead = $this->lead($request, $id);
        $cycle = DB::table('follow_up_cycles')->where('organization_id', $lead->organization_id)->where('lead_id', $id)->first();
        $events = DB::table('follow_up_events')->where('organization_id', $lead->organization_id)->where('lead_id', $id)->orderByDesc('id')->limit(50)->get();
        if (! $cycle) {
            return response()->json(['cycle' => null, 'events' => $events, 'default_cadence' => $this->preference($request)]);
        }
        $cadence = json_decode($cycle->cadence, true);
        $closed = in_array($lead->status, ['won', 'lost', 'dead'], true) || DB::table('deals')->where('organization_id', $lead->organization_id)->where('lead_id', $id)->whereIn('status', ['won', 'lost'])->exists();
        $cycle->cadence = $cadence;
        $cycle->closed = $closed;
        $cycle->paused = FollowUpScheduler::isPaused($cycle->stage);
        $cycle->due_at = FollowUpScheduler::dueAt($cycle, $closed)?->toIso8601String();

        return response()->json(['cycle' => $cycle, 'events' => $events]);
    }

    public function save(Request $request, int $id): JsonResponse
    {
        $data = $request->validate(['action' => ['required', Rule::in(['start', 'configure', 'sent', 'reply', 'stage'])], 'cadence' => ['required_if:action,start,configure', 'array', 'min:1', 'max:10'], 'cadence.*' => ['required', 'integer', 'min:1', 'max:720'], 'stage' => ['required_if:action,stage', Rule::in(self::STAGES)], 'note' => ['nullable', 'string', 'max:2000']]);
        DB::transaction(function () use ($request, $id, $data): void {
            $lead = $this->lead($request, $id, true);
            DB::table('organizations')->where('id', $lead->organization_id)->lockForUpdate()->first();
            $lead = $this->lead($request, $id, true);
            abort_if(in_array($lead->status, ['won', 'lost', 'dead'], true) || DB::table('deals')->where('organization_id', $lead->organization_id)->where('lead_id', $id)->whereIn('status', ['won', 'lost'])->exists(), 422, 'This lead is closed; follow-ups have stopped.');
            $query = DB::table('follow_up_cycles')->where('organization_id', $lead->organization_id)->where('lead_id', $id);
            $cycle = $query->lockForUpdate()->first();
            $action = $data['action'];
            if ($action === 'start') {
                abort_if($cycle, 422, 'Cycle already started.');
                DB::table('follow_up_cycles')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $id, 'stage' => 'Chat started', 'cadence' => json_encode($data['cadence']), 'completed' => 0, 'anchor_at' => now(), 'created_at' => now(), 'updated_at' => now()]);
            } else {
                abort_unless($cycle, 422, 'Start the cycle first.');
                $changes = ['updated_at' => now()];
                if ($action === 'configure') {
                    $changes['cadence'] = json_encode($data['cadence']);
                    $changes['completed'] = min($cycle->completed, count($data['cadence']));
                }
                if ($action === 'sent') {
                    abort_if(FollowUpScheduler::isPaused($cycle->stage) || $cycle->completed >= count(json_decode($cycle->cadence, true)), 422, 'No follow-up is currently scheduled.');
                    $changes['completed'] = $cycle->completed + 1;
                    $changes['anchor_at'] = now();
                }
                if ($action === 'reply') {
                    $changes['completed'] = 0;
                    $changes['anchor_at'] = now();
                }
                if ($action === 'stage' && $data['stage'] !== $cycle->stage) {
                    $changes['stage'] = $data['stage'];
                    $changes['completed'] = 0;
                    $changes['anchor_at'] = now();
                }
                $query->update($changes);
            }
            app(FollowUpScheduler::class)->refresh($lead->organization_id, $id);
            if ($action === 'stage' && $data['stage'] === $cycle->stage) {
                return; // Same stage chosen again: nothing changed, so nothing is logged (desktop fu_change_stage returns early).
            }
            DB::table('follow_up_events')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $id, 'actor_id' => $request->user()->id, 'action' => $action, 'note' => $data['note'] ?? null, 'created_at' => now()]);
        });

        return $this->show($request, $id);
    }
}
