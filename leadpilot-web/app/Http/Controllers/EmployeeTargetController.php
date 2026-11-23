<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;
use Illuminate\Validation\ValidationException;

class EmployeeTargetController extends Controller
{
    private function authorizeManager(User $actor, string $action): void
    {
        abort_unless($actor->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($actor, 'analytics', $action, $actor->organization_id), true), 403);
    }

    public function employees(Request $request): JsonResponse
    {
        $actor = $request->user();
        $this->authorizeManager($actor, 'view');

        return response()->json(User::where('organization_id', $actor->organization_id)->orderBy('name')->paginate(25, ['id', 'name', 'status']));
    }

    public function index(Request $request, int $userId): JsonResponse
    {
        $actor = $request->user();
        $this->authorizeManager($actor, 'view');
        User::where('organization_id', $actor->organization_id)->findOrFail($userId);

        return response()->json(DB::table('employee_targets')->where('organization_id', $actor->organization_id)->where('user_id', $userId)->orderByDesc('period_start')->paginate(25));
    }

    public function history(Request $request, int $userId): JsonResponse
    {
        $actor = $request->user();
        $this->authorizeManager($actor, 'view');
        User::where('organization_id', $actor->organization_id)->findOrFail($userId);

        return response()->json(DB::table('employee_target_history')->where('organization_id', $actor->organization_id)->where('user_id', $userId)->orderByDesc('id')->paginate(25));
    }

    public function store(Request $request, int $userId): JsonResponse
    {
        $actor = $request->user();
        $this->authorizeManager($actor, 'manage');
        $data = $request->validate([
            'metric' => ['required', Rule::in(['daily_leads', 'weekly_proposals', 'monthly_proposals', 'followups', 'interviews', 'revenue', 'deals'])],
            'period_start' => ['required', 'date_format:Y-m-d'],
            'period_end' => ['required', 'date_format:Y-m-d', 'after_or_equal:period_start'],
            'target_value' => ['required', 'numeric', 'min:0', 'max:999999999999.99', Rule::when($request->input('metric') !== 'revenue', ['integer'])],
            'currency' => ['nullable', 'required_if:metric,revenue', 'prohibited_unless:metric,revenue', 'regex:/^[A-Z]{3}$/'],
        ]);
        $start = CarbonImmutable::parse($data['period_start']);
        $end = CarbonImmutable::parse($data['period_end']);
        $validPeriod = match ($data['metric']) {
            'daily_leads' => $start->isSameDay($end),
            'weekly_proposals' => $end->equalTo($start->addDays(6)),
            'monthly_proposals' => $start->isSameDay($start->startOfMonth()) && $end->isSameDay($start->endOfMonth()),
            default => true,
        };
        if (! $validPeriod) {
            throw ValidationException::withMessages(['period_end' => 'Choose one day, seven days, or a full calendar month for daily, weekly, or monthly targets respectively.']);
        }
        DB::transaction(function () use ($actor, $userId, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $this->authorizeManager($actor, 'manage');
            User::where('organization_id', $actor->organization_id)->whereKey($userId)->lockForUpdate()->firstOrFail();
            $key = ['organization_id' => $actor->organization_id, 'user_id' => $userId, 'metric' => $data['metric'], 'period_start' => $data['period_start'], 'period_end' => $data['period_end']];
            $previous = DB::table('employee_targets')->where($key)->lockForUpdate()->first();
            DB::table('employee_targets')->updateOrInsert($key, fn (bool $exists) => array_merge(['target_value' => $data['target_value'], 'currency' => $data['currency'] ?? null, 'updated_by' => $actor->id, 'updated_at' => now()], $exists ? [] : ['created_at' => now()]));
            DB::table('employee_target_history')->insert(array_merge($key, ['actor_id' => $actor->id, 'action' => $previous ? 'updated' : 'created', 'old_value' => $previous?->target_value, 'new_value' => $data['target_value'], 'old_currency' => $previous?->currency, 'new_currency' => $data['currency'] ?? null, 'created_at' => now()]));
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'employee.target_saved', 'subject_type' => 'user', 'subject_id' => $userId, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Target saved.']);
    }

    public function destroy(Request $request, int $userId, int $targetId): JsonResponse
    {
        $actor = $request->user();
        $this->authorizeManager($actor, 'manage');
        DB::transaction(function () use ($actor, $userId, $targetId): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $this->authorizeManager($actor, 'manage');
            User::where('organization_id', $actor->organization_id)->findOrFail($userId);
            $target = DB::table('employee_targets')->where('organization_id', $actor->organization_id)->where('user_id', $userId)->where('id', $targetId)->lockForUpdate()->first();
            abort_unless($target, 404);
            DB::table('employee_target_history')->insert(['organization_id' => $actor->organization_id, 'user_id' => $userId, 'actor_id' => $actor->id, 'action' => 'deleted', 'metric' => $target->metric, 'period_start' => $target->period_start, 'period_end' => $target->period_end, 'old_value' => $target->target_value, 'new_value' => null, 'old_currency' => $target->currency, 'new_currency' => null, 'created_at' => now()]);
            DB::table('employee_targets')->where('id', $targetId)->delete();
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'employee.target_deleted', 'subject_type' => 'user', 'subject_id' => $userId, 'created_at' => now()]);
        });

        return response()->json(['message' => 'Target removed.']);
    }
}
