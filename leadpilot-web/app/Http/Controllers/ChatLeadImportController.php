<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class ChatLeadImportController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'leads', 'view', $actor->organization_id), 403);
        $visible = $resolver->constrain(DB::table('leads')->where('organization_id', $actor->organization_id), $actor, 'leads', 'view', $actor->organization_id)->select('id');
        $chats = DB::table('imported_chat_leads')->where('organization_id', $actor->organization_id)->where('user_id', $actor->id)->whereIn('lead_id', $visible)->get(['lead_id', 'room_id', 'last_preview', 'display_time', 'updated_at', 'sender', 'activity_at', 'reminder_hours']);
        $chats->each(function ($chat) use ($actor): void {
            $lead = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $chat->lead_id)->first(['status']);
            $closed = in_array($lead?->status, ['won', 'lost', 'dead'], true) || DB::table('deals')->where('organization_id', $actor->organization_id)->where('lead_id', $chat->lead_id)->whereIn('status', ['won', 'lost'])->exists();
            $meeting = DB::table('follow_up_cycles')->where('organization_id', $actor->organization_id)->where('lead_id', $chat->lead_id)->where('stage', 'Meeting booked')->exists();
            $chat->due_at = $chat->activity_at ? Carbon::parse($chat->activity_at, 'UTC')->addHours($chat->reminder_hours)->toIso8601String() : null;
            $chat->activity_status = $closed ? 'closed' : ($meeting ? 'paused' : (! $chat->sender || ! $chat->activity_at ? 'needs_confirmation' : (Carbon::parse($chat->due_at)->isFuture() ? 'waiting' : ($chat->sender === 'client' ? 'reply_due' : 'follow_up_due'))));
        });

        return response()->json($chats);
    }

    public function confirm(Request $request, int $leadId): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['sender' => ['required', Rule::in(['client', 'self'])], 'activity_at' => ['required', 'date', 'before_or_equal:now'], 'reminder_hours' => ['required', 'integer', 'min:1', 'max:720']]);
        $resolver = app(PermissionResolver::class);
        $query = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $leadId)->whereNull('archived_at');
        abort_unless($resolver->constrain(clone $query, $actor, 'leads', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $actor, 'leads', 'edit', $actor->organization_id)->exists(), 404);
        $updated = DB::table('imported_chat_leads')->where('organization_id', $actor->organization_id)->where('user_id', $actor->id)->where('lead_id', $leadId)->update(['sender' => $data['sender'], 'activity_at' => Carbon::parse($data['activity_at'])->utc()->toDateTimeString(), 'reminder_hours' => $data['reminder_hours']]);
        abort_unless($updated, 404);

        return response()->json(['message' => 'Activity confirmed.']);
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['rows' => ['required', 'array', 'min:1', 'max:200'], 'rows.*.url' => ['required', 'string', 'max:2048', 'url:https'], 'rows.*.name' => ['required', 'string', 'max:255'], 'rows.*.text' => ['nullable', 'string', 'max:2000'], 'rows.*.timestamp' => ['nullable', 'string', 'max:255']]);
        foreach ($data['rows'] as &$row) {
            $url = parse_url($row['url']);
            if (! in_array(strtolower($url['host'] ?? ''), ['upwork.com', 'www.upwork.com'], true) || ! preg_match('~^/ab/messages/rooms/(room_[a-zA-Z0-9_-]+)/?$~', $url['path'] ?? '', $match)) {
                throw ValidationException::withMessages(['rows' => 'A conversation link is invalid.']);
            }$row['room_id'] = $match[1];
        }unset($row);
        $counts = DB::transaction(function () use ($actor, $data) {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $scopes = $resolver->scopes($current, 'leads', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            $added = 0;
            $updated = 0;
            foreach ($data['rows'] as $row) {
                $query = DB::table('imported_chat_leads')->where('organization_id', $actor->organization_id)->where('user_id', $actor->id)->where('room_id', $row['room_id']);
                $existing = $query->first();
                if ($existing) {
                    $visible = $resolver->constrain(DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $existing->lead_id), $current, 'leads', 'edit', $actor->organization_id)->exists();
                    if (! $visible) {
                        continue;
                    }$changed = $existing->last_preview !== ($row['text'] ?? null) || $existing->display_time !== ($row['timestamp'] ?? null);
                    $query->update(['last_preview' => $row['text'] ?? null, 'display_time' => $row['timestamp'] ?? null, 'updated_at' => now()] + ($changed ? ['sender' => null, 'activity_at' => null] : []));
                    $updated++;

                    continue;
                }
                $name = trim($row['name']);
                if ($name === '') {
                    throw ValidationException::withMessages(['rows' => 'A conversation name is empty.']);
                }$id = DB::table('leads')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'name' => $name, 'source' => 'Upwork', 'status' => 'new', 'created_at' => now(), 'updated_at' => now()]);
                DB::table('lead_assignment_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'from_user_id' => null, 'to_user_id' => $actor->id, 'actor_id' => $actor->id, 'created_at' => now()]);
                DB::table('lead_stage_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'actor_id' => $actor->id, 'from_status' => null, 'to_status' => 'new', 'created_at' => now()]);
                DB::table('imported_chat_leads')->insert(['organization_id' => $actor->organization_id, 'user_id' => $actor->id, 'lead_id' => $id, 'room_id' => $row['room_id'], 'last_preview' => $row['text'] ?? null, 'display_time' => $row['timestamp'] ?? null, 'created_at' => now(), 'updated_at' => now()]);
                $added++;
            }

            return ['created' => $added, 'updated' => $updated];
        });

        return response()->json($counts);
    }
}
