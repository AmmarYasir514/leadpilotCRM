<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class DealController extends Controller
{
    private function cents(mixed $value): ?int
    {
        if ($value === null) {
            return null;
        }
        [$whole, $fraction] = array_pad(explode('.', (string) $value, 2), 2, '');

        return ((int) $whole * 100) + (int) str_pad($fraction, 2, '0');
    }

    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        abort_unless($resolver->scopes($actor, 'sales_pipeline', 'view', $actor->organization_id), 403);

        $filters = $request->validate(['status' => ['nullable', Rule::in(['won'])]]);
        $query = DB::table('deals')->where('organization_id', $actor->organization_id);
        if (! empty($filters['status'])) {
            $query->where('status', $filters['status']);
        }
        $deals = $resolver->constrain($query, $actor, 'sales_pipeline', 'view', $actor->organization_id)->orderByDesc('id')->paginate(25);
        $deals->through(static function ($deal) {
            foreach (['deal_value'] as $field) {
                $cents = $deal->{$field.'_cents'};
                $deal->{$field} = $cents === null ? null : intdiv((int) $cents, 100).'.'.str_pad((string) ((int) $cents % 100), 2, '0', STR_PAD_LEFT);
                unset($deal->{$field.'_cents'});
            }

            unset($deal->realized_revenue_cents);

            return $deal;
        });

        return response()->json($deals);
    }

    public function storeClosed(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'lead_id' => ['nullable', 'integer'], 'deal_value' => ['required', 'numeric', 'decimal:0,2', 'regex:/^\d+(?:\.\d{1,2})?$/', 'min:0', 'max:999999999999.99'], 'currency' => ['required', 'regex:/^[A-Z]{3}$/'], 'closed_on' => ['required', 'date_format:Y-m-d', 'before_or_equal:today']]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $scopes = $resolver->scopes($current, 'sales_pipeline', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            if (! empty($data['lead_id'])) {
                $query = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $data['lead_id']);
                abort_unless($resolver->constrain(clone $query, $current, 'leads', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'leads', 'edit', $actor->organization_id)->exists(), 404);
                $lead = $query->lockForUpdate()->first();
                if ($lead->status !== 'won') {
                    DB::table('leads')->where('id', $lead->id)->update(['status' => 'won', 'updated_at' => now()]);
                    DB::table('lead_stage_history')->insert(['organization_id' => $actor->organization_id, 'lead_id' => $lead->id, 'actor_id' => $actor->id, 'from_status' => $lead->status, 'to_status' => 'won', 'created_at' => now()]);
                }
            }
            $id = DB::table('deals')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'lead_id' => $data['lead_id'] ?? null, 'title' => $data['title'], 'status' => 'won', 'deal_value_cents' => $this->cents($data['deal_value']), 'currency' => $data['currency'], 'closed_on' => $data['closed_on'], 'created_at' => now(), 'updated_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'deal.created', 'subject_type' => 'deal', 'subject_id' => $id, 'created_at' => now()]);
            return $id;
        });
        return response()->json(['id' => $id], 201);
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'lead_id' => ['nullable', 'integer'], 'deal_value' => ['nullable', 'numeric', 'decimal:0,2', 'regex:/^\d+(?:\.\d{1,2})?$/', 'min:0', 'max:999999999999.99'], 'currency' => ['nullable', 'required_with:deal_value', 'regex:/^[A-Z]{3}$/']]);
        $id = DB::transaction(function () use ($actor, $data): int {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $scopes = $resolver->scopes($current, 'sales_pipeline', 'create', $actor->organization_id);
            abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            if (! empty($data['lead_id'])) {
                $lead = DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('id', $data['lead_id']);
                abort_unless($resolver->constrain($lead, $current, 'leads', 'view', $actor->organization_id)->exists(), 404);
            }
            $id = DB::table('deals')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'lead_id' => $data['lead_id'] ?? null, 'title' => $data['title'], 'status' => 'open', 'deal_value_cents' => $this->cents($data['deal_value'] ?? null), 'currency' => isset($data['deal_value']) ? ($data['currency'] ?? null) : null, 'created_at' => now(), 'updated_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'deal.created', 'subject_type' => 'deal', 'subject_id' => $id, 'created_at' => now()]);

            return $id;
        });

        return response()->json(['id' => $id], 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'status' => ['required', Rule::in(['open', 'won', 'lost'])], 'deal_value' => ['nullable', 'required_if:status,won', 'numeric', 'decimal:0,2', 'regex:/^\d+(?:\.\d{1,2})?$/', 'min:0', 'max:999999999999.99'], 'realized_revenue' => ['prohibited'], 'currency' => ['nullable', 'required_with:deal_value', 'regex:/^[A-Z]{3}$/'], 'closed_on' => ['nullable', 'required_unless:status,open', 'prohibited_if:status,open', 'date_format:Y-m-d']]);
        DB::transaction(function () use ($actor, $id, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            $query = DB::table('deals')->where('organization_id', $actor->organization_id)->where('id', $id);
            abort_unless($resolver->constrain(clone $query, $current, 'sales_pipeline', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $query, $current, 'sales_pipeline', 'edit', $actor->organization_id)->exists(), 404);
            $old = $query->lockForUpdate()->first();
            $data['deal_value'] = $data['deal_value'] ?? null;
            $data['currency'] = $data['deal_value'] !== null ? ($data['currency'] ?? null) : null;
            $data['closed_on'] = $data['closed_on'] ?? null;
            $data['deal_value_cents'] = $this->cents($data['deal_value']);
            unset($data['deal_value']);
            DB::table('deals')->where('id', $id)->update(array_merge($data, ['updated_at' => now()]));
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => $old->status !== $data['status'] ? 'deal.status_changed' : 'deal.updated', 'subject_type' => 'deal', 'subject_id' => $id, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Deal saved.']);
    }
}
