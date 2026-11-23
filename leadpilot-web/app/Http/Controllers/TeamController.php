<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class TeamController extends Controller
{
    private function actor(Request $request, string $action): User
    {
        $actor = $request->user();
        $scopes = $actor->organization_id ? app(PermissionResolver::class)->scopes($actor, 'team_management', $action, $actor->organization_id) : [];
        abort_unless(in_array('organization', $scopes, true) || (in_array($action, ['view', 'edit'], true) && $actor->team_id && in_array('team', $scopes, true)), 403);

        return $actor;
    }

    private function lockAuthorizedActor(User $actor, string $action): void
    {
        DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
        $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
        abort_unless($current && $current->session_version === $actor->session_version, 403);
        $scopes = app(PermissionResolver::class)->scopes($current, 'team_management', $action, $actor->organization_id);
        abort_unless(in_array('organization', $scopes, true) || ($action === 'edit' && $current->team_id && in_array('team', $scopes, true)), 403);
    }

    private function audit(User $actor, int $teamId, string $action): void
    {
        DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $action, 'subject_type' => 'team', 'subject_id' => $teamId, 'created_at' => now()]);
    }

    public function index(Request $request): JsonResponse
    {
        $actor = $this->actor($request, 'view');

        $scopes = app(PermissionResolver::class)->scopes($actor, 'team_management', 'view', $actor->organization_id);
        $query = DB::table('teams')->where('organization_id', $actor->organization_id);
        if (! in_array('organization', $scopes, true)) {
            $query->where('id', $actor->team_id);
        }

        return response()->json($query->orderBy('name')->get());
    }

    public function history(Request $request, int $userId): JsonResponse
    {
        $actor = $this->actor($request, 'view');
        abort_unless(in_array('organization', app(PermissionResolver::class)->scopes($actor, 'team_management', 'view', $actor->organization_id), true), 403);
        $user = User::withTrashed()->where('organization_id', $actor->organization_id)->findOrFail($userId);

        return response()->json(DB::table('team_membership_history')
            ->join('teams', 'team_membership_history.team_id', '=', 'teams.id')
            ->where('team_membership_history.organization_id', $actor->organization_id)
            ->where('teams.organization_id', $actor->organization_id)
            ->where('team_membership_history.user_id', $user->id)
            ->select('team_membership_history.id', 'team_membership_history.started_at', 'team_membership_history.ended_at', 'team_membership_history.changed_by', 'teams.name as team_name')
            ->orderByDesc('team_membership_history.id')->paginate(25));
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $this->actor($request, 'create');
        $data = $request->validate(['name' => ['required', 'string', 'max:255', Rule::unique('teams')->where('organization_id', $actor->organization_id)]]);
        $id = DB::transaction(function () use ($actor, $data): int {
            $this->lockAuthorizedActor($actor, 'create');
            $id = DB::table('teams')->insertGetId(['organization_id' => $actor->organization_id, 'name' => $data['name'], 'created_at' => now(), 'updated_at' => now()]);
            $this->audit($actor, $id, 'team.created');

            return $id;
        });

        return response()->json(['id' => $id, 'name' => $data['name']], 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $this->actor($request, 'edit');
        $data = $request->validate(['name' => ['required', 'string', 'max:255', Rule::unique('teams')->where('organization_id', $actor->organization_id)->ignore($id)]]);
        DB::transaction(function () use ($actor, $id, $data): void {
            $this->lockAuthorizedActor($actor, 'edit');
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->firstOrFail();
            $scopes = app(PermissionResolver::class)->scopes($current, 'team_management', 'edit', $actor->organization_id);
            $query = DB::table('teams')->where('organization_id', $actor->organization_id)->where('id', $id);
            if (! in_array('organization', $scopes, true)) {
                $query->where('id', $current->team_id);
            }
            $team = $query->lockForUpdate()->first();
            abort_unless($team, 404);
            DB::table('teams')->where('id', $id)->update(['name' => $data['name'], 'updated_at' => now()]);
            $this->audit($actor, $id, 'team.renamed');
        });

        return response()->json(['message' => 'Team updated.']);
    }

    public function destroy(Request $request, int $id): JsonResponse
    {
        $actor = $this->actor($request, 'delete');
        DB::transaction(function () use ($actor, $id): void {
            $this->lockAuthorizedActor($actor, 'delete');
            $team = DB::table('teams')->where('organization_id', $actor->organization_id)->where('id', $id)->lockForUpdate()->first();
            abort_unless($team, 404);
            if (User::withTrashed()->where('team_id', $id)->exists() || DB::table('team_membership_history')->where('team_id', $id)->exists()) {
                throw ValidationException::withMessages(['team' => 'A team with membership history cannot be deleted.']);
            }
            DB::table('teams')->where('id', $id)->delete();
            $this->audit($actor, $id, 'team.deleted');
        });

        return response()->json(['message' => 'Team deleted.']);
    }
}
