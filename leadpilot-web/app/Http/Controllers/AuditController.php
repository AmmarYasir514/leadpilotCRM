<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Carbon\CarbonImmutable;
use Illuminate\Database\Query\Builder;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Symfony\Component\HttpFoundation\StreamedResponse;

class AuditController extends Controller
{
    public function index(Request $request): JsonResponse
    {
        $filtered = $this->filteredQuery($request);
        $accessChanges = (clone $filtered)->where(function (Builder $query): void {
            $query->where('action', 'like', '%role%')
                ->orWhere('action', 'like', '%permission%')
                ->orWhere('action', 'like', '%override%')
                ->orWhere('action', 'like', '%super_admin%')
                ->orWhere('action', 'like', '%team%')
                ->orWhere('action', 'like', '%user.status_%');
        })->count();
        $page = (clone $filtered)
            ->select('audit_logs.*')
            ->selectSub(DB::table('users as audit_actor')->select('name')->whereColumn('audit_actor.id', 'audit_logs.actor_id')->limit(1), 'actor_name')
            ->selectSub(DB::table('users as audit_subject')->select('name')->whereColumn('audit_subject.id', 'audit_logs.subject_id')->where('audit_logs.subject_type', 'user')->limit(1), 'subject_name')
            ->selectSub(DB::table('users as audit_subject_email')->select('email')->whereColumn('audit_subject_email.id', 'audit_logs.subject_id')->where('audit_logs.subject_type', 'user')->limit(1), 'subject_email')
            ->orderByDesc('audit_logs.id')
            ->paginate(10);
        $actor = $request->user();
        $people = User::where('organization_id', $actor->organization_id)->orderBy('name')->get(['id', 'name', 'email']);
        $actions = DB::table('audit_logs')->where('organization_id', $actor->organization_id)->distinct()->orderBy('action')->pluck('action');

        return response()->json($page->toArray() + ['access_changes' => $accessChanges, 'people' => $people, 'actions' => $actions]);
    }

    public function export(Request $request): StreamedResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($actor, 'audit_logs', 'export', $actor->organization_id), true), 403);
        $query = $this->filteredQuery($request)->orderBy('id');

        return response()->streamDownload(function () use ($query): void {
            $output = fopen('php://output', 'w');
            fputcsv($output, ['Time (UTC)', 'Action', 'Actor ID', 'Record type', 'Record ID'], ',', '"', '');
            foreach ($query->cursor() as $entry) {
                $fields = [$entry->created_at, $entry->action, $entry->actor_id, $entry->subject_type, $entry->subject_id];
                $safe = array_map(static function ($value) {
                    $value = (string) ($value ?? '');

                    return preg_match('/^[\s\x00-\x1f]*[=+@-]/u', $value) ? "'".$value : $value;
                }, $fields);
                fputcsv($output, $safe, ',', '"', '');
            }
            fclose($output);
        }, 'leadpilot-activity.csv', ['Content-Type' => 'text/csv; charset=UTF-8', 'Cache-Control' => 'no-store']);
    }

    private function filteredQuery(Request $request): Builder
    {
        $actor = $request->user();
        abort_unless($actor->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($actor, 'audit_logs', 'view', $actor->organization_id), true), 403);
        $data = $request->validate([
            'user_id' => ['nullable', 'integer', 'min:1'],
            'action' => ['nullable', 'string', 'max:100'],
            'from' => ['nullable', 'date_format:Y-m-d', 'required_with:to'],
            'to' => ['nullable', 'date_format:Y-m-d', 'required_with:from', 'after_or_equal:from'],
        ]);
        $query = DB::table('audit_logs')->where('organization_id', $actor->organization_id);
        if (! empty($data['user_id'])) {
            User::withTrashed()->where('organization_id', $actor->organization_id)->findOrFail($data['user_id']);
            $query->where(function ($query) use ($data): void {
                $query->where('actor_id', $data['user_id'])->orWhere(function ($query) use ($data): void {
                    $query->where('subject_type', 'user')->where('subject_id', $data['user_id']);
                });
            });
        }
        if (! empty($data['action'])) {
            $query->where('action', $data['action']);
        }
        if (! empty($data['from']) && ! empty($data['to'])) {
            $timezone = $actor->timezone ?: 'UTC';
            $query->where('created_at', '>=', CarbonImmutable::parse($data['from'], $timezone)->startOfDay()->utc())
                ->where('created_at', '<', CarbonImmutable::parse($data['to'], $timezone)->addDay()->startOfDay()->utc());
        }

        return $query;
    }
}
