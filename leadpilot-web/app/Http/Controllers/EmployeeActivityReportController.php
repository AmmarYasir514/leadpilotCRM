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
use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;
use Symfony\Component\HttpFoundation\StreamedResponse;

class EmployeeActivityReportController extends Controller
{
    public function document(Request $request, int $userId, string $format): StreamedResponse
    {
        abort_unless(in_array($format, ['pdf', 'xlsx'], true), 404);
        $actor = $request->user();
        $resolver = app(PermissionResolver::class);
        abort_unless($actor->organization_id && in_array('organization', $resolver->scopes($actor, 'analytics', 'export', $actor->organization_id), true) && in_array('organization', $resolver->scopes($actor, 'audit_logs', 'export', $actor->organization_id), true), 403);
        $report = $this->show($request, $userId)->getData(true);

        if ($format === 'pdf') {
            $options = new Options;
            $options->setIsRemoteEnabled(false);
            $options->setIsPhpEnabled(false);
            $pdf = new Dompdf($options);
            $pdf->loadHtml(view('reports.daily-activity', ['report' => $report])->render());
            $pdf->render();
            $contents = $pdf->output();

            return response()->streamDownload(static function () use ($contents): void {
                echo $contents;
            }, 'leadpilot-daily-activity.pdf', ['Content-Type' => 'application/pdf', 'Cache-Control' => 'no-store']);
        }

        return response()->streamDownload(static function () use ($report): void {
            $writer = new Writer;
            $writer->openToFile('php://output');
            $writer->addRow(Row::fromValues(['Daily recorded activity', $report['date'], $report['timezone']]));
            $name = preg_match('/^[\s\x00-\x1f]*[=+@-]/u', $report['employee_name']) ? "'".$report['employee_name'] : $report['employee_name'];
            $writer->addRow(Row::fromValues(['Employee', $name]));
            $writer->addRow(Row::fromValues(['Recorded events', $report['total']]));
            $writer->addRow(Row::fromValues(['Previous day recorded events', $report['previous_day_total']]));
            $writer->addRow(Row::fromValues(['Action', 'Events']));
            foreach ($report['actions'] as $action) {
                $label = preg_match('/^[\s\x00-\x1f]*[=+@-]/u', $action['action']) ? "'".$action['action'] : $action['action'];
                $writer->addRow(Row::fromValues([$label, (int) $action['event_count']]));
            }
            $writer->close();
        }, 'leadpilot-daily-activity.xlsx', ['Content-Type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'Cache-Control' => 'no-store']);
    }

    public function export(Request $request, int $userId): StreamedResponse
    {
        $actor = $request->user();
        $resolver = app(PermissionResolver::class);
        abort_unless($actor->organization_id && in_array('organization', $resolver->scopes($actor, 'analytics', 'export', $actor->organization_id), true) && in_array('organization', $resolver->scopes($actor, 'audit_logs', 'export', $actor->organization_id), true), 403);
        $report = $this->show($request, $userId)->getData(true);

        return response()->streamDownload(function () use ($report): void {
            $output = fopen('php://output', 'w');
            $write = static function (array $fields) use ($output): void {
                $safe = array_map(static function ($value): string {
                    $value = (string) $value;

                    return preg_match('/^[\s\x00-\x1f]*[=+@-]/u', $value) ? "'".$value : $value;
                }, $fields);
                fputcsv($output, $safe, ',', '"', '');
            };
            $write(['Daily recorded activity report', $report['date'], $report['timezone']]);
            $write(['Employee', $report['employee_name']]);
            $write(['Recorded events', $report['total']]);
            $write(['Previous day recorded events', $report['previous_day_total']]);
            $write(['Action', 'Events']);
            foreach ($report['actions'] as $action) {
                $write([$action['action'], $action['event_count']]);
            }
            fclose($output);
        }, 'leadpilot-daily-activity.csv', ['Content-Type' => 'text/csv; charset=UTF-8', 'Cache-Control' => 'no-store']);
    }

    public function show(Request $request, int $userId): JsonResponse
    {
        $actor = $request->user();
        $resolver = app(PermissionResolver::class);
        abort_unless($actor->organization_id && in_array('organization', $resolver->scopes($actor, 'analytics', 'view', $actor->organization_id), true) && in_array('organization', $resolver->scopes($actor, 'audit_logs', 'view', $actor->organization_id), true), 403);
        $data = $request->validate(['date' => ['required', 'date_format:Y-m-d']]);
        $employee = User::where('organization_id', $actor->organization_id)->findOrFail($userId);
        $day = CarbonImmutable::parse($data['date'], $actor->timezone ?: 'UTC')->startOfDay();
        $countForDay = function (CarbonImmutable $date) use ($actor, $userId): int {
            return DB::table('audit_logs')->where('organization_id', $actor->organization_id)->where('actor_id', $userId)
                ->where('created_at', '>=', $date->utc())->where('created_at', '<', $date->addDay()->utc())->count();
        };
        $actions = DB::table('audit_logs')->where('organization_id', $actor->organization_id)->where('actor_id', $userId)
            ->where('created_at', '>=', $day->utc())->where('created_at', '<', $day->addDay()->utc())
            ->select('action')->selectRaw('count(*) as event_count')->groupBy('action')->orderBy('action')->get();

        $canExport = in_array('organization', $resolver->scopes($actor, 'analytics', 'export', $actor->organization_id), true) && in_array('organization', $resolver->scopes($actor, 'audit_logs', 'export', $actor->organization_id), true);

        return response()->json(['employee_name' => $employee->name, 'date' => $data['date'], 'timezone' => $actor->timezone ?: 'UTC', 'total' => $countForDay($day), 'previous_day_total' => $countForDay($day->subDay()), 'actions' => $actions, 'can_export' => $canExport]);
    }
}
