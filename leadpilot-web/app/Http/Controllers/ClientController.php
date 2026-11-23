<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class ClientController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'clients', 'view', $actor->organization_id), 403);
        $filters = $request->validate(['archived' => ['nullable', Rule::in(['yes', 'no'])]]);
        $query = DB::table('clients')->where('organization_id', $actor->organization_id)
            ->when(($filters['archived'] ?? 'no') === 'yes', fn ($q) => $q->whereNotNull('archived_at'), fn ($q) => $q->whereNull('archived_at'));

        return response()->json($resolver->constrain($query, $actor, 'clients', 'view', $actor->organization_id)->orderBy('name')->paginate(25));
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['name' => ['required', 'string', 'max:255'], 'company' => ['nullable', 'string', 'max:255'], 'email' => ['nullable', 'email', 'max:255'], 'phone' => ['nullable', 'string', 'max:50']]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $scopes = app(PermissionResolver::class)->scopes($current, 'clients', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            $id = DB::table('clients')->insertGetId(array_merge($data, ['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'created_at' => now(), 'updated_at' => now()]));
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'client.created', 'subject_type' => 'client', 'subject_id' => $id, 'created_at' => now()]);

            return $id;
        });

        return response()->json(['id' => $id], 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['name' => ['required', 'string', 'max:255'], 'company' => ['nullable', 'string', 'max:255'], 'email' => ['nullable', 'email', 'max:255'], 'phone' => ['nullable', 'string', 'max:50']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $query = DB::table('clients')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'clients', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'clients', 'edit', $actor->organization_id)->exists(), 404);
            DB::table('clients')->where('id', $id)->update(array_merge($data, ['updated_at' => now()]));
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'client.updated', 'subject_type' => 'client', 'subject_id' => $id, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Client updated.']);
    }

    public function archive(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['archived' => ['required', 'boolean']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $query = DB::table('clients')->where('organization_id', $actor->organization_id)->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'clients', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'clients', 'delete', $actor->organization_id)->exists(), 404);
            $client = $query->lockForUpdate()->first();
            if ((bool) $client->archived_at !== (bool) $data['archived']) {
                DB::table('clients')->where('id', $id)->update(['archived_at' => $data['archived'] ? now() : null, 'updated_at' => now()]);
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $data['archived'] ? 'client.archived' : 'client.restored', 'subject_type' => 'client', 'subject_id' => $id, 'created_at' => now()]);
            }
        });

        return response()->json(['message' => $data['archived'] ? 'Client archived.' : 'Client restored.']);
    }
}
