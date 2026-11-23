<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Carbon\CarbonImmutable;
use Dompdf\Dompdf;
use Dompdf\Options;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\ValidationException;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;
use Symfony\Component\HttpFoundation\StreamedResponse;

class SalesPerformanceController extends Controller
{
    public function overview(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        foreach (['analytics', 'leads', 'proposals', 'sales_pipeline'] as $module) {
            abort_unless(in_array('organization', $resolver->scopes($actor, $module, 'view', $actor->organization_id), true), 403);
        }
        $dates = $request->validate(['from' => ['required', 'date_format:Y-m-d'], 'to' => ['required', 'date_format:Y-m-d', 'after_or_equal:from']]);
        $zone = $actor->timezone ?: 'UTC';
        $start = CarbonImmutable::parse($dates['from'], $zone)->startOfDay();
        $end = CarbonImmutable::parse($dates['to'], $zone)->startOfDay();
        if ($start->diffInDays($end) > 365) {
            throw ValidationException::withMessages(['to' => 'Choose a date range of at most 366 days.']);
        }
        $daily = [];
        for ($day = $start; $day <= $end; $day = $day->addDay()) {
            $daily[$day->toDateString()] = ['date' => $day->toDateString(), 'leads' => 0, 'proposals' => 0, 'followups' => 0];
        }
        $org = $actor->organization_id;
        $until = $end->addDay()->utc();
        $sources = [
            'leads' => DB::table('leads')->where('organization_id', $org)->where('created_at', '>=', $start->utc())->where('created_at', '<', $until)->select('created_at as happened_at'),
            'proposals' => DB::table('proposals')->where('organization_id', $org)->where('submitted_at', '>=', $start->utc())->where('submitted_at', '<', $until)->select('submitted_at as happened_at'),
            'followups' => DB::table('follow_up_events')->where('organization_id', $org)->where('action', 'sent')->where('created_at', '>=', $start->utc())->where('created_at', '<', $until)->select('created_at as happened_at'),
        ];
        foreach ($sources as $metric => $query) {
            foreach ($query->cursor() as $row) {
                $date = CarbonImmutable::parse($row->happened_at, 'UTC')->setTimezone($zone)->toDateString();
                if (isset($daily[$date])) {
                    $daily[$date][$metric]++;
                }
            }
        }
        $closed = DB::table('deals')->where('organization_id', $org)->whereBetween('closed_on', [$dates['from'], $dates['to']]);

        return response()->json([
            'from' => $dates['from'], 'to' => $dates['to'], 'timezone' => $zone,
            'leads' => array_sum(array_column($daily, 'leads')),
            'proposals' => array_sum(array_column($daily, 'proposals')),
            'followups' => array_sum(array_column($daily, 'followups')),
            'won' => (clone $closed)->where('status', 'won')->count(),
            'lost' => (clone $closed)->where('status', 'lost')->count(),
            'daily' => array_values($daily),
        ])->header('Cache-Control', 'no-store');
    }

    public function show(Request $request, int $userId): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        foreach (['analytics', 'leads', 'proposals', 'sales_pipeline'] as $module) {
            abort_unless(in_array('organization', $resolver->scopes($actor, $module, 'view', $actor->organization_id), true), 403);
        }
        $data = $request->validate(['from' => ['required', 'date_format:Y-m-d'], 'to' => ['required', 'date_format:Y-m-d', 'after_or_equal:from']]);
        $start = CarbonImmutable::parse($data['from'], $actor->timezone ?: 'UTC')->startOfDay();
        $end = CarbonImmutable::parse($data['to'], $actor->timezone ?: 'UTC')->startOfDay();
        $calendarDays = (int) CarbonImmutable::parse($data['from'], 'UTC')->diffInDays(CarbonImmutable::parse($data['to'], 'UTC'));
        if ($calendarDays > 365) {
            throw ValidationException::withMessages(['to' => 'Choose a date range of at most 366 days.']);
        }
        $employee = User::where('organization_id', $actor->organization_id)->findOrFail($userId);
        $leads = DB::table('leads')->where('organization_id', $actor->organization_id)->where('created_by', $userId)->where('created_at', '>=', $start->utc())->where('created_at', '<', $end->addDay()->utc());
        $proposals = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $userId);
        $previousStart = $start->subDays($calendarDays + 1);
        $deals = DB::table('deals')->where('organization_id', $actor->organization_id)->where('created_by', $userId)->whereBetween('closed_on', [$data['from'], $data['to']]);
        $won = (clone $deals)->where('status', 'won')->count();
        $lost = (clone $deals)->where('status', 'lost')->count();
        $revenue = (clone $deals)->where('status', 'won')->whereNotNull('deal_value_cents')->whereNotNull('currency')->select('currency')->selectRaw('SUM(deal_value_cents) as cents')->groupBy('currency')->orderBy('currency')->get();
        $leadsCreated = (clone $leads)->count();
        $proposalsCreated = (clone $proposals)->where('created_at', '>=', $start->utc())->where('created_at', '<', $end->addDay()->utc())->count();
        $submitted = (clone $proposals)->where('submitted_at', '>=', $start->utc())->where('submitted_at', '<', $end->addDay()->utc());
        $submittedCount = (clone $submitted)->count();
        $withRecordedStage = static function ($query, array $statuses) use ($end): int {
            return $query->whereExists(function ($history) use ($statuses, $end): void {
                $history->selectRaw('1')->from('proposal_history')->whereColumn('proposal_history.proposal_id', 'proposals.id')->whereColumn('proposal_history.organization_id', 'proposals.organization_id')->whereNotNull('proposal_history.actor_id')->whereIn('proposal_history.to_status', $statuses)->whereColumn('proposal_history.created_at', '>=', 'proposals.submitted_at')->where('proposal_history.created_at', '<', $end->addDay()->utc());
            })->count();
        };
        $responded = $withRecordedStage(clone $submitted, ['responded', 'interview']);
        $interviewed = $withRecordedStage(clone $submitted, ['interview']);
        $viewed = $withRecordedStage(clone $submitted, ['viewed']);
        $hired = $withRecordedStage(clone $submitted, ['hired']);
        $leadStages = (clone $leads)->select('status')->selectRaw('count(*) as total')->groupBy('status')->pluck('total', 'status');
        $sequenceCounts = ['completed' => 0, 'in_progress' => 0, 'overdue' => 0];
        $sequences = DB::table('follow_up_cycles')->join('leads', 'leads.id', '=', 'follow_up_cycles.lead_id')
            ->where('follow_up_cycles.organization_id', $actor->organization_id)->where('leads.organization_id', $actor->organization_id)
            ->where('leads.created_by', $userId)->whereNull('leads.archived_at')->whereNotIn('leads.status', ['won', 'lost', 'dead'])
            ->whereNotExists(fn ($query) => $query->selectRaw('1')->from('deals')->whereColumn('deals.lead_id', 'leads.id')->whereColumn('deals.organization_id', 'leads.organization_id')->whereIn('deals.status', ['won', 'lost']))
            ->select('follow_up_cycles.stage', 'follow_up_cycles.cadence', 'follow_up_cycles.completed', 'follow_up_cycles.anchor_at')->cursor();
        foreach ($sequences as $sequence) {
            $cadence = json_decode($sequence->cadence, true);
            if (! is_array($cadence) || ! count($cadence)) {
                continue;
            }
            if ($sequence->completed >= count($cadence)) {
                $sequenceCounts['completed']++;

                continue;
            }
            $sequenceCounts['in_progress']++;
            if ($sequence->stage !== 'Meeting booked' && isset($cadence[$sequence->completed]) && CarbonImmutable::parse($sequence->anchor_at, 'UTC')->addHours((int) $cadence[$sequence->completed])->isPast()) {
                $sequenceCounts['overdue']++;
            }
        }
        $followups = DB::table('follow_up_events')->where('organization_id', $actor->organization_id)->where('actor_id', $userId)->where('action', 'sent')->where('created_at', '>=', $start->utc())->where('created_at', '<', $end->addDay()->utc())->count();
        $targets = DB::table('employee_targets')->where('organization_id', $actor->organization_id)->where('user_id', $userId)->where('period_start', $data['from'])->where('period_end', $data['to'])->get();
        $achievement = $targets->map(function ($target) use ($leadsCreated, $proposalsCreated, $won, $revenue, $followups): array {
            $actual = match ($target->metric) {
                'daily_leads' => $leadsCreated,
                'weekly_proposals', 'monthly_proposals' => $proposalsCreated,
                'deals' => $won,
                'followups' => $followups,
                'revenue' => $revenue->firstWhere('currency', $target->currency)?->cents,
                default => null,
            };
            if ($target->metric === 'revenue' && $actual !== null) {
                $actual = (int) $actual / 100;
            }
            $value = (float) $target->target_value;

            return ['metric' => $target->metric, 'target' => $target->target_value, 'currency' => $target->currency, 'actual' => $actual, 'percent' => $actual !== null && $value > 0 ? round(((float) $actual / $value) * 100, 2) : null];
        });
        $canExport = true;
        foreach (['analytics', 'leads', 'proposals', 'sales_pipeline'] as $module) {
            $canExport = $canExport && in_array('organization', $resolver->scopes($actor, $module, 'export', $actor->organization_id), true);
        }

        return response()->json([
            'employee_name' => $employee->name, 'from' => $data['from'], 'to' => $data['to'], 'timezone' => $actor->timezone ?: 'UTC',
            'leads_created' => $leadsCreated,
            'leads_currently_qualified' => (clone $leads)->whereIn('status', ['qualified', 'contacted', 'follow-up', 'interview', 'negotiation', 'won'])->count(),
            'proposals_created' => $proposalsCreated,
            'proposals_manually_marked_submitted' => $submittedCount,
            'recorded_response_count' => $responded, 'recorded_interview_count' => $interviewed,
            'recorded_viewed_count' => $viewed, 'recorded_hired_count' => $hired,
            'recorded_view_rate' => $submittedCount > 0 ? round($viewed * 100 / $submittedCount, 2) : null,
            'recorded_connects_used' => (int) (clone $submitted)->selectRaw('COALESCE(SUM(connects_normal + connects_boosted), 0) as total')->value('total'),
            'lead_stages' => $leadStages, 'followup_sequences_current' => $sequenceCounts,
            'recorded_response_rate' => $submittedCount > 0 ? round($responded * 100 / $submittedCount, 2) : null,
            'recorded_interview_rate' => $submittedCount > 0 ? round($interviewed * 100 / $submittedCount, 2) : null,
            'previous_from' => $previousStart->toDateString(), 'previous_to' => $start->subDay()->toDateString(),
            'previous_leads_created' => DB::table('leads')->where('organization_id', $actor->organization_id)->where('created_by', $userId)->where('created_at', '>=', $previousStart->utc())->where('created_at', '<', $start->utc())->count(),
            'previous_proposals_created' => (clone $proposals)->where('created_at', '>=', $previousStart->utc())->where('created_at', '<', $start->utc())->count(),
            'followups_marked_sent' => $followups,
            'deals_won' => $won, 'deals_lost' => $lost, 'deal_win_rate' => $won + $lost > 0 ? round($won * 100 / ($won + $lost), 2) : null,
            'closed_value_by_currency' => $revenue->map(static fn ($row) => ['currency' => $row->currency, 'cents' => (string) $row->cents]),
            'targets' => $achievement,
            'can_export' => $canExport,
        ]);
    }

    public function export(Request $request, int $userId, string $format): StreamedResponse
    {
        abort_unless(in_array($format, ['csv', 'xlsx', 'pdf'], true), 404);
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $resolver = app(PermissionResolver::class);
        foreach (['analytics', 'leads', 'proposals', 'sales_pipeline'] as $module) {
            abort_unless(in_array('organization', $resolver->scopes($actor, $module, 'export', $actor->organization_id), true), 403);
        }
        $report = $this->show($request, $userId)->getData(true);
        $rows = [
            ['Employee', $report['employee_name']], ['From', $report['from']], ['To', $report['to']], ['Timezone', $report['timezone']],
            ['Leads created', $report['leads_created']], ['Currently qualified or later', $report['leads_currently_qualified']],
            ['Proposals created', $report['proposals_created']], ['Proposals manually marked submitted', $report['proposals_manually_marked_submitted']],
            ['Recorded response rate of submitted cohort (%)', $report['recorded_response_rate'] ?? 'Not available'], ['Recorded interview rate of submitted cohort (%)', $report['recorded_interview_rate'] ?? 'Not available'],
            ['Previous period', $report['previous_from'].' to '.$report['previous_to']],
            ['Previous period leads created', $report['previous_leads_created']], ['Previous period proposals created', $report['previous_proposals_created']],
            ['Follow-ups manually marked sent', $report['followups_marked_sent']],
            ['Deals won', $report['deals_won']], ['Deals lost', $report['deals_lost']], ['Closed deal win rate (%)', $report['deal_win_rate'] ?? 'Not available'],
        ];
        foreach ($report['closed_value_by_currency'] as $revenue) {
            $cents = (int) $revenue['cents'];
            $rows[] = ['Closed deal value '.$revenue['currency'], intdiv($cents, 100).'.'.str_pad((string) ($cents % 100), 2, '0', STR_PAD_LEFT)];
        }
        foreach ($report['targets'] as $target) {
            $rows[] = ['Target '.$target['metric'].' '.($target['currency'] ?? ''), 'Goal: '.$target['target'].'; actual: '.($target['actual'] ?? 'Not available').'; achievement: '.($target['percent'] === null ? 'Not available' : $target['percent'].'%')];
        }
        $rows[] = ['Note', 'Closed deal value is the agreed project amount, not a payment. Currencies are not converted. Submission status is manually recorded.'];
        $rows[] = ['Target definitions', 'Follow-up targets use manually marked sent events; proposal targets use proposals created; deals use won deals; revenue targets use closed deal value in the matching currency. Only exact date ranges are compared.'];
        $rows[] = ['Conversion definitions', 'Recorded response and interview rates use proposals marked submitted in the period with later recorded status events by period end; older unrecorded events are not inferred.'];
        $safe = static fn ($value) => preg_match('/^[\s\x00-\x1f]*[=+@-]/u', (string) $value) ? "'".(string) $value : (string) $value;
        if ($format === 'pdf') {
            $options = new Options;
            $options->setIsRemoteEnabled(false);
            $options->setIsPhpEnabled(false);
            $pdf = new Dompdf($options);
            $pdf->loadHtml(view('reports.sales-performance', ['report' => $report, 'generatedAt' => now($actor->timezone ?: 'UTC')->format('d M Y, H:i')])->render());
            $pdf->render();
            $contents = $pdf->output();

            return response()->streamDownload(static function () use ($contents): void {
                echo $contents;
            }, 'leadpilot-sales-report.pdf', ['Content-Type' => 'application/pdf', 'Cache-Control' => 'no-store']);
        }
        if ($format === 'xlsx') {
            return response()->streamDownload(static function () use ($rows, $safe): void {
                $writer = new Writer;
                $writer->openToFile('php://output');
                foreach ($rows as $row) {
                    $writer->addRow(Row::fromValues(array_map($safe, $row)));
                }
                $writer->close();
            }, 'leadpilot-sales-report.xlsx', ['Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Cache-Control' => 'no-store']);
        }

        return response()->streamDownload(static function () use ($rows, $safe): void {
            $output = fopen('php://output', 'w');
            foreach ($rows as $row) {
                fputcsv($output, array_map($safe, $row), ',', '"', '');
            }
            fclose($output);
        }, 'leadpilot-sales-report.csv', ['Content-Type' => 'text/csv; charset=UTF-8', 'Cache-Control' => 'no-store']);
    }
}
