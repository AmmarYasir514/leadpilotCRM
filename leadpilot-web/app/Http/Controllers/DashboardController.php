<?php

namespace App\Http\Controllers;

use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class DashboardController extends Controller
{
    public function salesOverview(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);
        $org = $actor->organization_id;
        $month = now($actor->timezone ?: 'UTC')->startOfMonth()->utc();
        $nextMonth = now($actor->timezone ?: 'UTC')->startOfMonth()->addMonth()->utc();
        $leads = DB::table('leads')->where('organization_id', $org)->whereNull('archived_at');
        $stages = (clone $leads)->select('status')->selectRaw('count(*) as total')->groupBy('status')->pluck('total', 'status');
        $cycles = DB::table('follow_up_cycles')->join('leads', 'leads.id', '=', 'follow_up_cycles.lead_id')
            ->leftJoin('users', 'users.id', '=', 'leads.assigned_to')
            ->where('follow_up_cycles.organization_id', $org)->where('leads.organization_id', $org)->whereNull('leads.archived_at')
            ->whereNotIn('leads.status', ['won', 'lost', 'dead'])->where('follow_up_cycles.stage', '<>', 'Meeting booked')
            ->whereNotExists(fn ($q) => $q->selectRaw('1')->from('deals')->whereColumn('deals.lead_id', 'leads.id')->whereColumn('deals.organization_id', 'leads.organization_id')->whereIn('deals.status', ['won', 'lost']))
            ->select('leads.name', 'users.name as owner', 'follow_up_cycles.stage', 'follow_up_cycles.cadence', 'follow_up_cycles.completed', 'follow_up_cycles.anchor_at')->cursor();
        $due = [];
        $dueCount = 0;
        foreach ($cycles as $cycle) {
            $cadence = json_decode($cycle->cadence, true);
            if (! is_array($cadence) || ! isset($cadence[$cycle->completed]) || ! is_numeric($cadence[$cycle->completed])) {
                continue;
            }
            $dueAt = CarbonImmutable::parse($cycle->anchor_at, 'UTC')->addHours((int) $cadence[$cycle->completed]);
            if ($dueAt->isFuture()) {
                continue;
            }
            $dueCount++;
            $due[] = ['name' => $cycle->name, 'owner' => $cycle->owner, 'stage' => $cycle->stage, 'due_at' => $dueAt->toIso8601String()];
            usort($due, fn ($a, $b) => strcmp($a['due_at'], $b['due_at']));
            $due = array_slice($due, 0, 5);
        }
        $plan = DB::table('sales_plans')->where('organization_id', $org)->where('user_id', $actor->id)->first();

        return response()->json([
            'leads' => (clone $leads)->count(),
            'proposals' => DB::table('proposals')->where('organization_id', $org)->whereNotNull('submitted_at')->count(),
            'due_count' => $dueCount,
            'closed_deals' => DB::table('deals')->where('organization_id', $org)->where('status', 'won')->count(),
            'due' => $due,
            'stages' => $stages,
            'monthly_leads' => (clone $leads)->where('created_by', $actor->id)->where('created_at', '>=', $month)->where('created_at', '<', $nextMonth)->count(),
            'lead_target' => $plan?->lead_target,
            'activity' => DB::table('audit_logs')->where('organization_id', $org)->whereIn('action', ['lead.created', 'lead.status_changed', 'proposal.status_changed', 'deal.created', 'deal.status_changed'])->orderByDesc('id')->limit(5)->get(['action', 'created_at']),
        ]);
    }

    public function index(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);
        $filters = $request->validate([
            'team_id' => ['nullable', 'integer', Rule::exists('teams', 'id')->where('organization_id', $actor->organization_id)],
            'user_id' => ['nullable', 'integer', Rule::exists('users', 'id')->where('organization_id', $actor->organization_id)->whereNull('deleted_at')],
            'from' => ['nullable', 'date_format:Y-m-d', 'required_with:to'],
            'to' => ['nullable', 'date_format:Y-m-d', 'required_with:from', 'after_or_equal:from'],
        ]);
        $users = User::query()->where('organization_id', $actor->organization_id)
            ->when($filters['team_id'] ?? null, fn ($query, $id) => $query->where('team_id', $id))
            ->when($filters['user_id'] ?? null, fn ($query, $id) => $query->where('id', $id));
        $timezone = $actor->timezone ?: 'UTC';
        $today = now($timezone)->startOfDay()->utc();

        $audit = null;
        if (! empty($filters['from']) && ! empty($filters['to'])) {
            $audit = DB::table('audit_logs')->where('organization_id', $actor->organization_id)
                ->whereIn('actor_id', (clone $users)->select('id'))
                ->where('created_at', '>=', CarbonImmutable::parse($filters['from'], $timezone)->startOfDay()->utc())
                ->where('created_at', '<', CarbonImmutable::parse($filters['to'], $timezone)->addDay()->startOfDay()->utc());
        }

        return response()->json([
            'total_users' => (clone $users)->count(),
            'active_users' => (clone $users)->where('status', 'active')->count(),
            'suspended_users' => (clone $users)->where('status', 'suspended')->count(),
            'signed_in_today' => (clone $users)->where('last_login_at', '>=', $today)->count(),
            'active_today' => (clone $users)->where('last_activity_at', '>=', $today)->count(),
            'total_leads' => DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->count(),
            'leads_added_today' => DB::table('leads')->where('organization_id', $actor->organization_id)->whereNull('archived_at')->where('created_at', '>=', $today)->count(),
            'total_proposals' => DB::table('proposals')->where('organization_id', $actor->organization_id)->count(),
            'proposals_submitted_today' => DB::table('proposals')->where('organization_id', $actor->organization_id)->where('submitted_at', '>=', $today)->count(),
            'deals_won' => DB::table('deals')->where('organization_id', $actor->organization_id)->where('status', 'won')->count(),
            'deals_lost' => DB::table('deals')->where('organization_id', $actor->organization_id)->where('status', 'lost')->count(),
            'closed_value_by_currency' => DB::table('deals')->where('organization_id', $actor->organization_id)->where('status', 'won')->whereNotNull('deal_value_cents')->whereNotNull('currency')->select('currency')->selectRaw('SUM(deal_value_cents) as cents')->groupBy('currency')->orderBy('currency')->get()->map(static fn ($row) => ['currency' => $row->currency, 'cents' => (string) $row->cents]),
            'recorded_events_in_range' => $audit?->count(),
            'employees' => (clone $users)->orderBy('name')->paginate(25, ['id', 'name', 'status', 'team_id', 'last_activity_at']),
            'teams' => DB::table('teams')->where('organization_id', $actor->organization_id)->orderBy('name')->get(['id', 'name']),
        ]);
    }

    public function employee(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);
        $employee = User::query()->where('organization_id', $actor->organization_id)
            ->select(['id', 'name', 'email', 'status', 'team_id', 'job_title', 'department', 'joining_date', 'last_login_at', 'last_activity_at'])
            ->findOrFail($id);
        $activity = DB::table('audit_logs')->where('organization_id', $actor->organization_id)
            ->where('actor_id', $employee->id)->orderByDesc('id')->limit(10)->get(['action', 'created_at']);

        return response()->json(['employee' => $employee, 'recent_activity' => $activity]);
    }
}
