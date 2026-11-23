<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class AccessControlController extends Controller
{
    private function actor(Request $request): User
    {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);

        return $actor;
    }

    public function roles(Request $request): JsonResponse
    {
        $actor = $this->actor($request);

        return response()->json(DB::table('roles')->where('organization_id', $actor->organization_id)->orderBy('name')->get());
    }

    public function storeRole(Request $request): JsonResponse
    {
        $actor = $this->actor($request);
        $data = $request->validate(['name' => ['required', 'string', 'max:100', Rule::unique('roles')->where('organization_id', $actor->organization_id)]]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $currentActor = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($currentActor && $currentActor->status === 'active' && $currentActor->is_super_admin && $currentActor->session_version === $actor->session_version, 403);
            if (DB::table('roles')->where('organization_id', $actor->organization_id)->where('name', $data['name'])->exists()) {
                throw ValidationException::withMessages(['name' => 'A role with this name already exists.']);
            }
            $id = DB::table('roles')->insertGetId(['organization_id' => $actor->organization_id, 'name' => $data['name'], 'created_at' => now(), 'updated_at' => now()]);
            $this->audit($actor, 'role.created', 'role', $id);

            return $id;
        });

        return response()->json(['id' => $id, 'name' => $data['name']], 201);
    }

    public function renameRole(Request $request, int $roleId): JsonResponse
    {
        $actor = $this->actor($request);
        $data = $request->validate(['name' => ['required', 'string', 'max:100', Rule::unique('roles')->where('organization_id', $actor->organization_id)->ignore($roleId)]]);
        DB::transaction(function () use ($actor, $roleId, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->is_super_admin && $current->session_version === $actor->session_version, 403);
            $role = DB::table('roles')->where('organization_id', $actor->organization_id)->where('id', $roleId)->lockForUpdate()->first();
            abort_unless($role, 404);
            if (DB::table('roles')->where('organization_id', $actor->organization_id)->where('name', $data['name'])->where('id', '!=', $roleId)->exists()) {
                throw ValidationException::withMessages(['name' => 'A role with this name already exists.']);
            }
            DB::table('roles')->where('id', $roleId)->update(['name' => $data['name'], 'updated_at' => now()]);
            $this->audit($actor, 'role.renamed', 'role', $roleId);
        });

        return response()->json(['message' => 'Role updated.']);
    }

    public function deleteRole(Request $request, int $roleId): JsonResponse
    {
        $actor = $this->actor($request);
        DB::transaction(function () use ($actor, $roleId): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->is_super_admin && $current->session_version === $actor->session_version, 403);
            $role = DB::table('roles')->where('organization_id', $actor->organization_id)->where('id', $roleId)->lockForUpdate()->first();
            abort_unless($role, 404);
            if (DB::table('user_roles')->where('role_id', $roleId)->exists()) {
                throw ValidationException::withMessages(['role' => 'Remove all role assignments before deletion.']);
            }
            DB::table('roles')->where('id', $roleId)->delete();
            $this->audit($actor, 'role.deleted', 'role', $roleId);
        });

        return response()->json(['message' => 'Role deleted.']);
    }

    public function assign(Request $request, int $userId): JsonResponse
    {
        $actor = $this->actor($request);
        $data = $request->validate(['role_ids' => ['present', 'array'], 'role_ids.*' => ['required', 'integer', 'distinct', Rule::exists('roles', 'id')->where('organization_id', $actor->organization_id)]]);
        DB::transaction(function () use ($actor, $userId, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $currentActor = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($currentActor && $currentActor->status === 'active' && $currentActor->is_super_admin && $currentActor->session_version === $actor->session_version, 403);
            $user = User::where('organization_id', $actor->organization_id)->whereKey($userId)->lockForUpdate()->firstOrFail();
            if (DB::table('roles')->where('organization_id', $actor->organization_id)->whereIn('id', $data['role_ids'])->count() !== count($data['role_ids'])) {
                throw ValidationException::withMessages(['role_ids' => 'One or more roles are no longer available.']);
            }
            DB::table('user_roles')->where('user_id', $user->id)->delete();
            foreach ($data['role_ids'] as $roleId) {
                DB::table('user_roles')->insert(['user_id' => $user->id, 'role_id' => $roleId, 'created_at' => now(), 'updated_at' => now()]);
            }
            $this->audit($actor, 'user.roles_updated', 'user', $user->id);
        });

        return response()->json(['message' => 'Roles updated.']);
    }

    public function userRoles(Request $request, int $userId): JsonResponse
    {
        $actor = $this->actor($request);
        $user = User::where('organization_id', $actor->organization_id)->findOrFail($userId);

        return response()->json(DB::table('roles')->join('user_roles', 'roles.id', '=', 'user_roles.role_id')->where('roles.organization_id', $actor->organization_id)->where('user_roles.user_id', $user->id)->select('roles.id', 'roles.name')->get());
    }

    public function permissions(Request $request): JsonResponse
    {
        $this->actor($request);

        return response()->json(DB::table('permissions')->orderBy('module')->orderBy('action')->get());
    }

    public function rolePermissions(Request $request, int $roleId): JsonResponse
    {
        $actor = $this->actor($request);
        abort_unless(DB::table('roles')->where('organization_id', $actor->organization_id)->where('id', $roleId)->exists(), 404);

        return response()->json(DB::table('role_permissions')->where('role_id', $roleId)->get());
    }

    public function replaceRolePermissions(Request $request, int $roleId): JsonResponse
    {
        $actor = $this->actor($request);
        $data = $request->validate([
            'permissions' => ['present', 'array'],
            'permissions.*.id' => ['required', 'integer', 'distinct', Rule::exists('permissions', 'id')],
            'permissions.*.scope' => ['required', Rule::in(['own', 'assigned', 'team', 'organization'])],
        ]);
        DB::transaction(function () use ($actor, $roleId, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->is_super_admin && $current->session_version === $actor->session_version, 403);
            abort_unless(DB::table('roles')->where('organization_id', $actor->organization_id)->where('id', $roleId)->exists(), 404);
            DB::table('role_permissions')->where('role_id', $roleId)->delete();
            foreach ($data['permissions'] as $item) {
                DB::table('role_permissions')->insert(['role_id' => $roleId, 'permission_id' => $item['id'], 'scope' => $item['scope']]);
            }
            $this->audit($actor, 'role.permissions_updated', 'role', $roleId);
        });

        return response()->json(['message' => 'Role permissions updated.']);
    }

    public function userOverrides(Request $request, int $userId): JsonResponse
    {
        $actor = $this->actor($request);
        $target = User::where('organization_id', $actor->organization_id)->findOrFail($userId);

        return response()->json(DB::table('user_permission_overrides')->where('user_id', $target->id)->get());
    }

    public function removeOverride(Request $request, int $userId, int $permissionId): JsonResponse
    {
        $actor = $this->actor($request);
        DB::transaction(function () use ($actor, $userId, $permissionId): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->is_super_admin && $current->session_version === $actor->session_version, 403);
            $target = User::where('organization_id', $actor->organization_id)->whereKey($userId)->lockForUpdate()->firstOrFail();
            abort_unless(DB::table('permissions')->where('id', $permissionId)->exists(), 404);
            DB::table('user_permission_overrides')->where('user_id', $target->id)->where('permission_id', $permissionId)->delete();
            $this->audit($actor, 'user.permission_override_removed', 'user', $target->id);
        });

        return response()->json(['message' => 'Permission override removed.']);
    }

    public function setOverride(Request $request, int $userId, int $permissionId): JsonResponse
    {
        $actor = $this->actor($request);
        $data = $request->validate(['allowed' => ['required', 'boolean'], 'scope' => ['nullable', Rule::in(['own', 'assigned', 'team', 'organization'])]]);
        if ($data['allowed'] && empty($data['scope'])) {
            throw ValidationException::withMessages(['scope' => 'Scope is required for an allowed override.']);
        }
        DB::transaction(function () use ($actor, $userId, $permissionId, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->is_super_admin && $current->session_version === $actor->session_version, 403);
            $target = User::where('organization_id', $actor->organization_id)->whereKey($userId)->lockForUpdate()->firstOrFail();
            abort_unless(DB::table('permissions')->where('id', $permissionId)->exists(), 404);
            abort_if($target->is_super_admin, 422, 'Super Admin access cannot be changed by overrides.');
            DB::table('user_permission_overrides')->updateOrInsert(['user_id' => $target->id, 'permission_id' => $permissionId], ['allowed' => $data['allowed'], 'scope' => $data['allowed'] ? $data['scope'] : null]);
            $this->audit($actor, 'user.permission_override_updated', 'user', $target->id);
        });

        return response()->json(['message' => 'Permission override updated.']);
    }

    private function audit(User $actor, string $action, string $type, int $id): void
    {
        DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $action, 'subject_type' => $type, 'subject_id' => $id, 'created_at' => now()]);
    }
}
