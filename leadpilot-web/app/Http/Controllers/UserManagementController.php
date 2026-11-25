<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class UserManagementController extends Controller
{
    private function authorizeAdmin(Request $request, string $action): User
    {
        $actor = $request->user();
        $scopes = $actor->organization_id ? app(PermissionResolver::class)->scopes($actor, 'user_management', $action, $actor->organization_id) : [];
        abort_unless(in_array('organization', $scopes, true) || ($action === 'edit' && $actor->team_id && in_array('team', $scopes, true)), 403);

        return $actor;
    }

    private function lockAuthorizedAdmin(User $actor, string $action): void
    {
        DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
        $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
        abort_unless($current && $current->session_version === $actor->session_version, 403);
        $scopes = app(PermissionResolver::class)->scopes($current, 'user_management', $action, $actor->organization_id);
        abort_unless(in_array('organization', $scopes, true) || ($action === 'edit' && $current->team_id && in_array('team', $scopes, true)), 403);
    }

    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        $scopes = $actor->organization_id ? app(PermissionResolver::class)->scopes($actor, 'user_management', 'view', $actor->organization_id) : [];
        abort_unless(array_intersect($scopes, ['own', 'team', 'organization']), 403);
        $filters = $request->validate([
            'search' => ['nullable', 'string', 'max:255'],
            'status' => ['nullable', Rule::in(['active', 'invited', 'inactive', 'suspended'])],
            'team_id' => ['nullable', 'integer', Rule::exists('teams', 'id')->where('organization_id', $actor->organization_id)],
            'role_id' => ['nullable', 'integer', Rule::exists('roles', 'id')->where('organization_id', $actor->organization_id)],
        ]);
        $search = trim($filters['search'] ?? '');
        $query = User::where('organization_id', $actor->organization_id);
        if (! in_array('organization', $scopes, true)) {
            $query->where(function ($query) use ($scopes, $actor): void {
                $query->whereRaw('1 = 0');
                if (in_array('own', $scopes, true)) {
                    $query->orWhere('id', $actor->id);
                }
                if ($actor->team_id && in_array('team', $scopes, true)) {
                    $query->orWhere('team_id', $actor->team_id);
                }
            });
        }

        return response()->json($query
            ->with(['roles' => fn ($roles) => $roles->where('roles.organization_id', $actor->organization_id)->select('roles.id', 'roles.name')])
            ->when($search !== '', fn ($query) => $query->where(fn ($query) => $query->where('name', 'like', '%'.$search.'%')->orWhere('email', 'like', '%'.$search.'%')))
            ->when(! empty($filters['status']), fn ($query) => $query->where('status', $filters['status']))
            ->when(! empty($filters['team_id']), fn ($query) => $query->where('team_id', $filters['team_id']))
            ->when(! empty($filters['role_id']), fn ($query) => $query->whereExists(function ($subquery) use ($filters): void {
                $subquery->selectRaw('1')->from('user_roles')->whereColumn('user_roles.user_id', 'users.id')->where('user_roles.role_id', $filters['role_id']);
            }))
            ->orderBy('name')->paginate(25));
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $this->authorizeAdmin($request, 'create');
        $request->merge(['email' => strtolower(trim((string) $request->input('email')))]);
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'max:255', 'unique:users,email'],
            'team_id' => ['nullable', 'integer', Rule::exists('teams', 'id')->where('organization_id', $actor->organization_id)],
            'role_ids' => ['sometimes', 'array'],
            'role_ids.*' => ['integer', 'distinct', Rule::exists('roles', 'id')->where('organization_id', $actor->organization_id)],
        ]);
        $user = DB::transaction(function () use ($actor, $data): User {
            $this->lockAuthorizedAdmin($actor, 'create');
            $user = new User;
            $user->name = $data['name'];
            $user->email = strtolower($data['email']);
            $user->password = Hash::make(Str::random(64));
            $user->organization_id = $actor->organization_id;
            $user->status = 'invited';
            $user->created_by = $actor->id;
            $user->team_id = $data['team_id'] ?? null;
            $user->save();
            if ($user->team_id !== null) {
                DB::table('team_membership_history')->insert(['organization_id' => $actor->organization_id, 'team_id' => $user->team_id, 'user_id' => $user->id, 'changed_by' => $actor->id, 'started_at' => now()]);
            }
            if (! empty($data['role_ids'])) {
                $now = now();
                DB::table('user_roles')->insert(array_map(fn (int $roleId): array => ['user_id' => $user->id, 'role_id' => $roleId, 'created_at' => $now, 'updated_at' => $now], $data['role_ids']));
            }
            $this->audit($actor, $user, 'user.created');

            return $user;
        });

        return response()->json($user, 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $this->authorizeAdmin($request, 'edit');
        if ($request->has('email')) {
            $request->merge(['email' => strtolower(trim((string) $request->input('email')))]);
        }
        $data = $request->validate([
            'name' => ['required', 'string', 'max:255'],
            'email' => ['sometimes', 'required', 'email', 'max:255', Rule::unique('users', 'email')->ignore($id)],
            'status' => ['required', Rule::in(['active', 'invited', 'inactive', 'suspended'])],
            'phone' => ['nullable', 'string', 'max:50'],
            'job_title' => ['nullable', 'string', 'max:255'],
            'department' => ['nullable', 'string', 'max:255'],
            'joining_date' => ['nullable', 'date'],
            'team_id' => ['sometimes', 'nullable', 'integer', Rule::exists('teams', 'id')->where('organization_id', $actor->organization_id)],
            'is_super_admin' => ['sometimes', 'boolean'],
        ]);
        $user = DB::transaction(function () use ($actor, $data, $id): User {
            $this->lockAuthorizedAdmin($actor, 'edit');
            $currentActor = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->firstOrFail();
            $scopes = app(PermissionResolver::class)->scopes($currentActor, 'user_management', 'edit', $actor->organization_id);
            $targetQuery = User::where('organization_id', $actor->organization_id)->whereKey($id);
            if (! in_array('organization', $scopes, true)) {
                $targetQuery->where('team_id', $currentActor->team_id);
            }
            $user = $targetQuery->lockForUpdate()->firstOrFail();
            abort_if(! $currentActor->is_super_admin && ($user->is_super_admin || $user->id === $actor->id || array_key_exists('is_super_admin', $data) || array_key_exists('email', $data) || array_key_exists('team_id', $data) || $data['status'] !== $user->status), 403);
            $willBeAdmin = $data['is_super_admin'] ?? $user->is_super_admin;
            if ($user->is_super_admin && $user->status === 'active' && ($data['status'] !== 'active' || ! $willBeAdmin)) {
                $count = User::where('organization_id', $actor->organization_id)->where('is_super_admin', true)->where('status', 'active')->count();
                if ($count <= 1) {
                    throw ValidationException::withMessages(['status' => 'The last active Super Admin cannot be deactivated.']);
                }
            }
            if ((bool) $willBeAdmin !== $user->is_super_admin) {
                $user->is_super_admin = $willBeAdmin;
                $user->setRememberToken(Str::random(60));
                $user->session_version++;
                DB::table('sessions')->where('user_id', $user->id)->delete();
                $this->audit($actor, $user, $willBeAdmin ? 'user.super_admin_granted' : 'user.super_admin_removed');
            }
            $previousStatus = $user->status;
            $previousTeam = $user->team_id;
            $user->name = $data['name'];
            if (isset($data['email']) && strtolower($data['email']) !== $user->email) {
                DB::table('password_reset_tokens')->where('email', $user->email)->delete();
                DB::table('sessions')->where('user_id', $user->id)->delete();
                $user->email = strtolower($data['email']);
                $user->setRememberToken(Str::random(60));
                $user->session_version++;
            }
            $user->status = $data['status'];
            if ($user->status !== 'active' && $previousStatus !== $user->status) {
                $user->setRememberToken(Str::random(60));
                $user->session_version++;
            }
            foreach (['phone', 'job_title', 'department', 'joining_date', 'team_id'] as $field) {
                if (array_key_exists($field, $data)) {
                    $user->$field = $data[$field];
                }
            }
            $user->save();
            if ($previousTeam !== $user->team_id) {
                DB::table('team_membership_history')->where('user_id', $user->id)->whereNull('ended_at')->update(['ended_at' => now()]);
                if ($user->team_id !== null) {
                    DB::table('team_membership_history')->insert(['organization_id' => $actor->organization_id, 'team_id' => $user->team_id, 'user_id' => $user->id, 'changed_by' => $actor->id, 'started_at' => now()]);
                }
                $this->audit($actor, $user, 'user.team_changed');
            }
            if ($user->status !== 'active' && $previousStatus !== $user->status) {
                DB::table('sessions')->where('user_id', $user->id)->delete();
                DB::table('password_reset_tokens')->where('email', $user->email)->delete();
            }
            $this->audit($actor, $user, 'user.updated');
            if ($previousStatus !== $user->status) {
                $this->audit($actor, $user, 'user.status_'.$user->status);
            }

            return $user;
        });

        return response()->json($user);
    }

    public function revokeSessions(Request $request, int $id): JsonResponse
    {
        $actor = $this->authorizeAdmin($request, 'manage');
        DB::transaction(function () use ($actor, $id): void {
            $this->lockAuthorizedAdmin($actor, 'manage');
            $user = User::where('organization_id', $actor->organization_id)->whereKey($id)->lockForUpdate()->firstOrFail();
            abort_if(! $actor->is_super_admin && ($user->is_super_admin || $user->id === $actor->id), 403);
            DB::table('sessions')->where('user_id', $user->id)->delete();
            $user->setRememberToken(Str::random(60));
            $user->session_version++;
            $user->save();
            $this->audit($actor, $user, 'user.sessions_revoked');
        });

        return response()->json(['message' => 'Sessions revoked.']);
    }

    public function archive(Request $request, int $id): JsonResponse
    {
        $actor = $this->authorizeAdmin($request, 'delete');
        DB::transaction(function () use ($actor, $id): void {
            $this->lockAuthorizedAdmin($actor, 'delete');
            $user = User::where('organization_id', $actor->organization_id)->whereKey($id)->lockForUpdate()->firstOrFail();
            abort_if(! $actor->is_super_admin && ($user->is_super_admin || $user->id === $actor->id), 403);
            if ($user->is_super_admin && $user->status === 'active' && User::where('organization_id', $actor->organization_id)->where('is_super_admin', true)->where('status', 'active')->count() <= 1) {
                throw ValidationException::withMessages(['user' => 'The last active Super Admin cannot be archived.']);
            }
            DB::table('sessions')->where('user_id', $user->id)->delete();
            DB::table('password_reset_tokens')->where('email', $user->email)->delete();
            $user->setRememberToken(Str::random(60));
            $user->save();
            $user->delete();
            DB::table('team_membership_history')->where('user_id', $user->id)->whereNull('ended_at')->update(['ended_at' => now()]);
            $this->audit($actor, $user, 'user.archived');
        });

        return response()->json(['message' => 'User archived.']);
    }

    private function audit(User $actor, User $subject, string $action): void
    {
        DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $action, 'subject_type' => 'user', 'subject_id' => $subject->id, 'created_at' => now()]);
    }
}
