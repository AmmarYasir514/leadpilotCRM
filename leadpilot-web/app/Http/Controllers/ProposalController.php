<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class ProposalController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'proposals', 'view', $actor->organization_id), 403);
        $query = DB::table('proposals')->where('organization_id', $actor->organization_id);
        if ($request->boolean('submitted_only')) {
            $query->where(function ($query) {
                $query->whereNotNull('submitted_at')->orWhereNotNull('upwork_proposal_id')->orWhereIn('status', ['submitted', 'viewed', 'responded', 'interview', 'hired', 'lost']);
            })->where('status', '!=', 'draft');
        }

        if ($request->boolean('drafts_only') && ! $request->boolean('submitted_only')) {
            $query->where('status', 'draft');
        }

        return response()->json($resolver->constrain($query, $actor, 'proposals', 'view', $actor->organization_id)->orderByDesc('id')->paginate(25));
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'lead_id' => ['nullable', 'integer'], 'bid' => ['nullable', 'numeric', 'decimal:0,2', 'min:0', 'max:999999999999.99'], 'currency' => ['nullable', 'required_with:bid', 'regex:/^[A-Z]{3}$/'], 'notes' => ['nullable', 'string', 'max:10000'], 'job_description' => ['nullable', 'string', 'max:20000'], 'writing_instructions' => ['nullable', 'string', 'max:10000'], 'cover_letter' => ['nullable', 'string', 'max:30000'], 'proposal_date' => ['nullable', 'date_format:Y-m-d'], 'job_url' => ['nullable', 'url:http,https', 'max:2048'], 'connects_normal' => ['sometimes', 'integer', 'min:0', 'max:100000'], 'connects_boosted' => ['sometimes', 'integer', 'min:0', 'max:100000']]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $scopes = $resolver->scopes($current, 'proposals', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            if (! empty($data['lead_id'])) {
                $lead = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $data['lead_id']);
                abort_unless($resolver->constrain($lead, $current, 'leads', 'view', $actor->organization_id)->exists(), 404);
            }
            $id = DB::table('proposals')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'lead_id' => $data['lead_id'] ?? null, 'title' => $data['title'], 'status' => 'draft', 'bid' => $data['bid'] ?? null, 'currency' => isset($data['bid']) ? ($data['currency'] ?? null) : null, 'notes' => $data['notes'] ?? null, 'job_description' => $data['job_description'] ?? null, 'writing_instructions' => $data['writing_instructions'] ?? null, 'cover_letter' => $data['cover_letter'] ?? null, 'proposal_date' => $data['proposal_date'] ?? null, 'job_url' => $data['job_url'] ?? null, 'connects_normal' => $data['connects_normal'] ?? 0, 'connects_boosted' => $data['connects_boosted'] ?? 0, 'created_at' => now(), 'updated_at' => now()]);
            DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $id, 'actor_id' => $actor->id, 'from_status' => null, 'to_status' => 'draft', 'new_bid' => $data['bid'] ?? null, 'new_currency' => isset($data['bid']) ? ($data['currency'] ?? null) : null, 'created_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'proposal.created', 'subject_type' => 'proposal', 'subject_id' => $id, 'created_at' => now()]);

            return $id;
        });

        return response()->json(['id' => $id], 201);
    }

    public function history(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $query = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('id', $id);
        abort_unless(app(PermissionResolver::class)->constrain($query, $actor, 'proposals', 'view', $actor->organization_id)->exists(), 404);

        return response()->json(DB::table('proposal_history')->where('organization_id', $actor->organization_id)->where('proposal_id', $id)->orderByDesc('id')->paginate(25));
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'status' => ['required', Rule::in(['draft', 'submitted', 'viewed', 'responded', 'interview', 'hired', 'lost', 'archived'])], 'bid' => ['nullable', 'numeric', 'decimal:0,2', 'min:0', 'max:999999999999.99'], 'currency' => ['nullable', 'required_with:bid', 'regex:/^[A-Z]{3}$/'], 'notes' => ['nullable', 'string', 'max:10000'], 'job_description' => ['nullable', 'string', 'max:20000'], 'writing_instructions' => ['nullable', 'string', 'max:10000'], 'cover_letter' => ['nullable', 'string', 'max:30000'], 'proposal_date' => ['nullable', 'date_format:Y-m-d'], 'job_url' => ['nullable', 'url:http,https', 'max:2048'], 'connects_normal' => ['sometimes', 'integer', 'min:0', 'max:100000'], 'connects_boosted' => ['sometimes', 'integer', 'min:0', 'max:100000']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $query = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'proposals', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'proposals', 'edit', $actor->organization_id)->exists(), 404);
            $previous = $query->lockForUpdate()->first();
            if (array_key_exists('bid', $data) && $data['bid'] === null) {
                $data['currency'] = null;
            }
            $nextBid = array_key_exists('bid', $data) ? $data['bid'] : $previous->bid;
            $nextCurrency = array_key_exists('currency', $data) ? $data['currency'] : $previous->currency;
            if ($previous->status !== $data['status'] || (string) $previous->bid !== (string) $nextBid || $previous->currency !== $nextCurrency) {
                DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $id, 'actor_id' => $actor->id, 'from_status' => $previous->status, 'to_status' => $data['status'], 'old_bid' => $previous->bid, 'new_bid' => $nextBid, 'old_currency' => $previous->currency, 'new_currency' => $nextCurrency, 'created_at' => now()]);
            }
            if ($data['status'] === 'submitted' && ! $previous->submitted_at) {
                $data['submitted_at'] = now();
            }
            DB::table('proposals')->where('id', $id)->update(array_merge($data, ['updated_at' => now()]));
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $previous->status !== $data['status'] ? 'proposal.status_changed' : 'proposal.updated', 'subject_type' => 'proposal', 'subject_id' => $id, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Proposal updated. No external submission was made.']);
    }
}
