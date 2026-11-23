<?php

namespace App\Authorization;

use App\Models\User;
use Illuminate\Database\Query\Builder;
use Illuminate\Support\Facades\DB;

class PermissionResolver
{
    /** @return list<string> */
    public function scopes(User $user, string $module, string $action, int $organizationId): array
    {
        $current = User::whereKey($user->id)->where('organization_id', $organizationId)->where('status', 'active')->first();
        if (! $current) {
            return [];
        }
        $permission = DB::table('permissions')->where('module', $module)->where('action', $action)->first();
        if (! $permission) {
            return [];
        }
        if ($current->is_super_admin) {
            return ['organization'];
        }
        $override = DB::table('user_permission_overrides')->where('user_id', $current->id)->where('permission_id', $permission->id)->first();
        if ($override) {
            return $override->allowed && in_array($override->scope, ['own', 'assigned', 'team', 'organization'], true) ? [$override->scope] : [];
        }

        return DB::table('role_permissions')->join('roles', 'roles.id', '=', 'role_permissions.role_id')
            ->join('user_roles', 'user_roles.role_id', '=', 'roles.id')
            ->where('roles.organization_id', $organizationId)->where('user_roles.user_id', $current->id)
            ->where('role_permissions.permission_id', $permission->id)
            ->whereIn('role_permissions.scope', ['own', 'assigned', 'team', 'organization'])
            ->distinct()->pluck('role_permissions.scope')->all();
    }

    /** Apply as the final query constraint before fetching records. */
    public function constrain(Builder $query, User $user, string $module, string $action, int $organizationId): Builder
    {
        $scopes = $this->scopes($user, $module, $action, $organizationId);
        $query = DB::query()->fromSub($query, 'scoped_records');
        $query->where('organization_id', $organizationId);
        if (in_array('organization', $scopes, true)) {
            return $query;
        }
        $current = User::whereKey($user->id)->where('organization_id', $organizationId)->first();

        return $query->where(function (Builder $q) use ($scopes, $current): void {
            $q->whereRaw('1 = 0');
            if ($current && in_array('own', $scopes, true)) {
                $q->orWhere('created_by', $current->id);
            }
            if ($current && in_array('assigned', $scopes, true)) {
                $q->orWhere('assigned_to', $current->id);
            }
            if ($current && $current->team_id && in_array('team', $scopes, true)) {
                $q->orWhere('team_id', $current->team_id);
            }
        });
    }
}
