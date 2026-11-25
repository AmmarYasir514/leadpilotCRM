<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\Meeting;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;

class MeetingHistoryController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $user = $request->user();
        abort_unless($user->organization_id && app(PermissionResolver::class)->scopes($user, 'meetings', 'view', $user->organization_id), 403);

        $meetings = Meeting::query()
            ->where('organization_id', $user->organization_id)
            ->where('user_id', $user->id)
            ->where('starts_at', '<', now())
            ->orderByDesc('starts_at')
            ->get()
            ->map(fn (Meeting $meeting) => [
                'id' => $meeting->id,
                'provider' => $meeting->provider,
                'title' => $meeting->title,
                'starts_at' => $meeting->starts_at?->toIso8601String(),
                'ends_at' => $meeting->ends_at?->toIso8601String(),
                'attendees' => $meeting->attendees ?? [],
                'meeting_url' => $meeting->meeting_url,
            ]);

        return response()->json(['meetings' => $meetings]);
    }
}