<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class LeadController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'leads', 'view', $actor->organization_id), 403);
        $filters = $request->validate(['search' => ['nullable', 'string', 'max:100'], 'status' => ['nullable', Rule::in(['new', 'qualified', 'contacted', 'follow-up', 'interview', 'negotiation', 'won', 'lost', 'dead'])], 'archived' => ['nullable', Rule::in(['yes', 'no'])], 'sort' => ['nullable', Rule::in(['newest', 'oldest', 'name', 'company'])]]);
        $query = DB::table('leads')->where('organization_id', $actor->organization_id)
            ->when(($filters['archived'] ?? 'no') === 'yes', fn ($q) => $q->whereNotNull('archived_at'), fn ($q) => $q->whereNull('archived_at'))
            ->when($filters['status'] ?? null, fn ($q, $status) => $q->where('status', $status))
            ->when($filters['search'] ?? null, fn ($q, $search) => $q->where(fn ($q) => $q->where('name', 'like', '%'.$search.'%')->orWhere('company', 'like', '%'.$search.'%')));

        $query = $resolver->constrain($query, $actor, 'leads', 'view', $actor->organization_id);
        match ($filters['sort'] ?? 'newest') {
            'oldest' => $query->orderBy('id'),
            'name' => $query->orderBy('name')->orderBy('id'),
            'company' => $query->orderBy('company')->orderBy('name')->orderBy('id'),
            default => $query->orderByDesc('id'),
        };

        return response()->json($query->paginate(25));
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['name' => ['required', 'string', 'max:255'], 'company' => ['nullable', 'string', 'max:255'], 'source' => ['nullable', 'string', 'max:100'], 'notes' => ['nullable', 'string', 'max:10000'], 'lead_date' => ['nullable', 'date_format:Y-m-d'], 'budget' => ['nullable', 'numeric', 'decimal:0,2', 'min:0', 'max:999999999999.99'], 'currency' => ['nullable', 'required_with:budget', 'regex:/^[A-Z]{3}$/']]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $scopes = app(PermissionResolver::class)->scopes($current, 'leads', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            $id = DB::table('leads')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'name' => $data['name'], 'company' => $data['company'] ?? null, 'source' => $data['source'] ?? null, 'status' => 'new', 'notes' => $data['notes'] ?? null, 'lead_date' => $data['lead_date'] ?? null, 'budget' => $data['budget'] ?? null, 'currency' => isset($data['budget']) ? ($data['currency'] ?? null) : null, 'created_at' => now(), 'updated_at' => now()]);
            DB::table('lead_assignment_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'from_user_id' => null, 'to_user_id' => $actor->id, 'actor_id' => $actor->id, 'created_at' => now()]);
            DB::table('lead_stage_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'actor_id' => $actor->id, 'from_status' => null, 'to_status' => 'new', 'created_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'lead.created', 'subject_type' => 'lead', 'subject_id' => $id, 'created_at' => now()]);

            return $id;
        });

        return response()->json(['id' => $id], 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['name' => ['required', 'string', 'max:255'], 'company' => ['nullable', 'string', 'max:255'], 'source' => ['nullable', 'string', 'max:100'], 'notes' => ['nullable', 'string', 'max:10000'], 'lead_date' => ['nullable', 'date_format:Y-m-d'], 'budget' => ['nullable', 'numeric', 'decimal:0,2', 'min:0', 'max:999999999999.99'], 'currency' => ['nullable', 'required_with:budget', 'regex:/^[A-Z]{3}$/'], 'status' => ['required', Rule::in(['new', 'qualified', 'contacted', 'follow-up', 'interview', 'negotiation', 'won', 'lost', 'dead'])]]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $query = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $id);
            $visible = $resolver->constrain(clone $query, $current, 'leads', 'view', $actor->organization_id)->exists();
            $editable = $resolver->constrain(clone $query, $current, 'leads', 'edit', $actor->organization_id)->exists();
            abort_unless($visible && $editable, 404);
            $lead = $query->lockForUpdate()->first();
            if (array_key_exists('budget', $data) && $data['budget'] === null) {
                $data['currency'] = null;
            }
            DB::table('leads')->where('id', $id)->update(array_merge($data, ['updated_at' => now()]));
            $action = $lead->status !== $data['status'] ? 'lead.status_changed' : 'lead.updated';
            if ($lead->status !== $data['status']) {
                DB::table('lead_stage_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'actor_id' => $actor->id, 'from_status' => $lead->status, 'to_status' => $data['status'], 'created_at' => now()]);
            }
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $action, 'subject_type' => 'lead', 'subject_id' => $id, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Lead updated.']);
    }

    public function assignees(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($actor, 'leads', 'assign', $actor->organization_id), true), 403);

        return response()->json(User::where('organization_id', $actor->organization_id)->where('status', 'active')->orderBy('name')->get(['id', 'name']));
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
            $query = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'leads', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'leads', 'delete', $actor->organization_id)->exists(), 404);
            $lead = $query->lockForUpdate()->first();
            if ((bool) $lead->archived_at !== (bool) $data['archived']) {
                DB::table('leads')->where('id', $id)->update(['archived_at' => $data['archived'] ? now() : null, 'updated_at' => now()]);
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $data['archived'] ? 'lead.archived' : 'lead.restored', 'subject_type' => 'lead', 'subject_id' => $id, 'created_at' => now()]);
            }
        });

        return response()->json(['message' => $data['archived'] ? 'Lead archived.' : 'Lead restored.']);
    }

    public function assign(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['user_id' => ['required', 'integer']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            abort_unless(in_array('organization', $resolver->scopes($current, 'leads', 'assign', $actor->organization_id), true), 403);
            $query = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'leads', 'view', $actor->organization_id)->exists(), 404);
            $lead = $query->lockForUpdate()->first();
            $target = User::where('organization_id', $actor->organization_id)->where('status', 'active')->whereKey($data['user_id'])->lockForUpdate()->firstOrFail();
            if ($lead->assigned_to !== $target->id) {
                DB::table('leads')->where('id', $id)->update(['assigned_to' => $target->id, 'team_id' => $target->team_id, 'updated_at' => now()]);
                DB::table('lead_assignment_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $id, 'from_user_id' => $lead->assigned_to, 'to_user_id' => $target->id, 'actor_id' => $actor->id, 'created_at' => now()]);
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'lead.reassigned', 'subject_type' => 'lead', 'subject_id' => $id, 'created_at' => now()]);
            }
        });

        return response()->json(['message' => 'Lead assignment updated.']);
    }

    public function history(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $query = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $id);
        abort_unless(app(PermissionResolver::class)->constrain($query, $actor, 'leads', 'view', $actor->organization_id)->exists(), 404);

        return response()->json(DB::table('lead_assignment_history')->where('organization_id', $actor->organization_id)->where('lead_id', $id)->orderByDesc('id')->paginate(25));
    }

    public function stageHistory(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $query = DB::table('leads')->where('organization_id', $actor->organization_id)->where('id', $id);
        abort_unless(app(PermissionResolver::class)->constrain($query, $actor, 'leads', 'view', $actor->organization_id)->exists(), 404);

        return response()->json(DB::table('lead_stage_history')->where('organization_id', $actor->organization_id)->where('lead_id', $id)->orderByDesc('id')->paginate(25));
    }

    public function client(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['client_id' => ['present', 'nullable', 'integer']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $lead = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $id);
            abort_unless($resolver->constrain(clone $lead, $current, 'leads', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $lead, $current, 'leads', 'edit', $actor->organization_id)->exists(), 404);
            if ($data['client_id'] !== null) {
                $client = DB::table('clients')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $data['client_id']);
                abort_unless($resolver->constrain($client, $current, 'clients', 'view', $actor->organization_id)->exists(), 404);
            }
            DB::table('leads')->where('id', $id)->update(['client_id' => $data['client_id'], 'updated_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'lead.client_changed', 'subject_type' => 'lead', 'subject_id' => $id, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Client link updated.']);
    }
}
