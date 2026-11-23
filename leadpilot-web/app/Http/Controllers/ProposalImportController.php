<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Validation\Rule;

class ProposalImportController extends Controller
{
    public function refreshViews(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate([
            'ids' => ['present', 'array', 'max:500'], 'ids.*' => ['required', 'string', 'regex:/^[0-9]{1,40}$/', 'distinct'],
            'matches' => ['sometimes', 'array', 'max:500'], 'matches.*.id' => ['required', 'string', 'regex:/^[0-9]{1,40}$/', 'distinct'],
            'matches.*.title' => ['required', 'string', 'max:250'], 'matches.*.proposal_date' => ['required', 'date_format:Y-m-d'],
        ]);
        $result = DB::transaction(function () use ($actor, $data): array {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            foreach (['view', 'edit', 'import'] as $action) {
                abort_unless($resolver->scopes($current, 'proposals', $action, $actor->organization_id), 403);
            }
            $updated = 0;
            $matched = 0;
            $matches = collect($data['matches'] ?? [])->keyBy('id');
            foreach ($data['ids'] as $upworkId) {
                $base = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $actor->id)->where('upwork_proposal_id', $upworkId);
                $record = $resolver->constrain(clone $base, $current, 'proposals', 'view', $actor->organization_id)->first();
                if (! $record && $matches->has($upworkId)) {
                    $hint = $matches->get($upworkId);
                    $normalize = fn (string $title): string => mb_strtolower(trim(preg_replace('/\s+/u', ' ', $title)));
                    $candidates = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $actor->id)
                        ->whereNull('upwork_proposal_id')->where('proposal_date', $hint['proposal_date'])->limit(200)->get();
                    if ($candidates->count() < 200) {
                        $sameTitle = $candidates->filter(fn ($candidate): bool => $normalize($candidate->title) === $normalize($hint['title']));
                        if ($sameTitle->count() === 1) {
                            $candidate = $sameTitle->first();
                            $base = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $actor->id)->where('id', $candidate->id)->whereNull('upwork_proposal_id');
                            $record = $resolver->constrain(clone $base, $current, 'proposals', 'view', $actor->organization_id)->first();
                        }
                    }
                }
                if (! $record || ! $resolver->constrain(clone $base, $current, 'proposals', 'edit', $actor->organization_id)->exists()) {
                    continue;
                }
                $matched++;
                if ($record->status !== 'submitted') {
                    continue;
                }
                $changed = DB::table('proposals')->where('id', $record->id)->where('status', 'submitted')->update(['status' => 'viewed', 'upwork_proposal_id' => $upworkId, 'updated_at' => now()]);
                if (! $changed) {
                    continue;
                }
                DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $record->id, 'actor_id' => $actor->id, 'from_status' => 'submitted', 'to_status' => 'viewed', 'created_at' => now()]);
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'proposal.status_changed', 'subject_type' => 'proposal', 'subject_id' => $record->id, 'created_at' => now()]);
                $updated++;
            }

            return ['updated' => $updated, 'matched' => $matched, 'unmatched' => count($data['ids']) - $matched];
        });

        return response()->json($result);
    }

    public function storeSubmitted(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate([
            'upwork_proposal_id' => ['required', 'string', 'regex:/^[0-9]{1,40}$/'],
            'title' => ['required', 'string', 'max:255'],
            'job_description' => ['nullable', 'string', 'max:20000'],
            'cover_letter' => ['required', 'string', 'max:30000'],
            'notes' => ['nullable', 'string', 'max:10000'],
            'job_url' => ['nullable', 'url:http,https', 'max:2048'],
        ]);
        $result = DB::transaction(function () use ($actor, $data): array {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            foreach (['create', 'import'] as $action) {
                $scopes = $resolver->scopes($current, 'proposals', $action, $actor->organization_id);
                abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            }
            $existing = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $actor->id)->where('upwork_proposal_id', $data['upwork_proposal_id'])->first();
            if ($existing) {
                return ['id' => $existing->id, 'created' => false];
            }
            if (! empty($data['job_url'])) {
                $drafts = DB::table('proposals')->where('organization_id', $actor->organization_id)
                    ->where('created_by', $actor->id)->where('status', 'draft')->where('job_url', $data['job_url'])->lockForUpdate()->get();
                abort_if($drafts->count() > 1, 409, 'Several drafts match this job. Review them before importing.');
                if ($drafts->count() === 1) {
                    $draft = $drafts->first();
                    $allowed = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('id', $draft->id);
                    abort_unless($resolver->constrain(clone $allowed, $current, 'proposals', 'view', $actor->organization_id)->exists() && $resolver->constrain(clone $allowed, $current, 'proposals', 'edit', $actor->organization_id)->exists(), 403);
                    DB::table('proposals')->where('id', $draft->id)->update([
                        'status' => 'submitted', 'upwork_proposal_id' => $data['upwork_proposal_id'],
                        'cover_letter' => $data['cover_letter'], 'job_description' => $draft->job_description ?: ($data['job_description'] ?? null),
                        'notes' => $draft->notes ?: ($data['notes'] ?? null), 'updated_at' => now(),
                    ]);
                    DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $draft->id, 'actor_id' => $actor->id, 'from_status' => 'draft', 'to_status' => 'submitted', 'created_at' => now()]);
                    DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'proposal.status_changed', 'subject_type' => 'proposal', 'subject_id' => $draft->id, 'created_at' => now()]);

                    return ['id' => $draft->id, 'created' => true];
                }
            }
            $id = DB::table('proposals')->insertGetId([
                'organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id,
                'team_id' => $current->team_id, 'title' => $data['title'], 'status' => 'submitted',
                'upwork_proposal_id' => $data['upwork_proposal_id'], 'job_description' => $data['job_description'] ?? null,
                'cover_letter' => $data['cover_letter'], 'notes' => $data['notes'] ?? null, 'job_url' => $data['job_url'] ?? null,
                'created_at' => now(), 'updated_at' => now(),
            ]);
            DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $id, 'actor_id' => $actor->id, 'from_status' => null, 'to_status' => 'submitted', 'created_at' => now()]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'proposal.imported', 'subject_type' => 'proposal', 'subject_id' => $id, 'created_at' => now()]);

            return ['id' => $id, 'created' => true];
        });

        return response()->json($result, $result['created'] ? 201 : 200);
    }

    public function store(Request $request): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id, 403);
        $data = $request->validate(['rows' => ['required', 'array', 'min:1', 'max:100'], 'rows.*.title' => ['required', 'string', 'max:250'], 'rows.*.proposal_date' => ['nullable', 'date_format:Y-m-d'], 'rows.*.status' => ['required', Rule::in(['submitted', 'viewed', 'responded', 'interview', 'archived'])]]);
        $result = DB::transaction(function () use ($actor, $data): array {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            $resolver = app(PermissionResolver::class);
            foreach (['create', 'import'] as $action) {
                $scopes = $resolver->scopes($current, 'proposals', $action, $actor->organization_id);
                abort_unless(array_intersect($scopes, ['own', 'assigned', 'organization']) || ($current->team_id && in_array('team', $scopes, true)), 403);
            }
            $added = 0;
            $skipped = 0;
            foreach ($data['rows'] as $row) {
                $title = trim(preg_replace('/\s+/u', ' ', $row['title']));
                if ($title === '') {
                    $skipped++;

                    continue;
                }
                $exists = DB::table('proposals')->where('organization_id', $actor->organization_id)->where('created_by', $actor->id)->whereRaw('LOWER(TRIM(title)) = ?', [mb_strtolower($title)])->exists();
                if ($exists) {
                    $skipped++;

                    continue;
                }
                $id = DB::table('proposals')->insertGetId(['organization_id' => $actor->organization_id, 'created_by' => $actor->id, 'assigned_to' => $actor->id, 'team_id' => $current->team_id, 'title' => $title, 'status' => $row['status'], 'proposal_date' => $row['proposal_date'] ?? null, 'notes' => 'Imported from user-reviewed copied Upwork text.', 'created_at' => now(), 'updated_at' => now()]);
                DB::table('proposal_history')->insert(['organization_id' => $actor->organization_id, 'proposal_id' => $id, 'actor_id' => null, 'from_status' => null, 'to_status' => $row['status'], 'created_at' => now()]);
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'proposal.imported', 'subject_type' => 'proposal', 'subject_id' => $id, 'created_at' => now()]);
                $added++;
            }

            return compact('added', 'skipped');
        });

        return response()->json($result);
    }
}
