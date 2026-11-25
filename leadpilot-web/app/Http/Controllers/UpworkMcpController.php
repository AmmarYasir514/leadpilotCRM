<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use Carbon\Carbon;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Str;

class UpworkMcpController extends Controller
{
    private const REGISTRATION = 'https://www.upwork.com/register';

    private const AUTH = 'https://www.upwork.com/ab/account-security/oauth2/authorize';

    private const TOKEN = 'https://www.upwork.com/api/v3/oauth2/token';

    private function authorizeUser(Request $request): void
    {
        $u = $request->user();
        abort_unless($u->organization_id && app(PermissionResolver::class)->scopes($u, 'proposals', 'view', $u->organization_id), 403);
    }

    private function identity(Request $request): array
    {
        return ['organization_id' => $request->user()->organization_id, 'user_id' => $request->user()->id];
    }

    public function jobPreferences(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        $saved = DB::table('upwork_job_preferences')->where($this->identity($request))->first();

        return response()->json(['preferences' => $saved ? json_decode($saved->preferences, true) : null])->header('Cache-Control', 'no-store');
    }

    public function saveJobPreferences(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        $validated = $request->validate([
            'preferences' => ['required', 'array:keywords,targetSkills,countries,fixedMinimum,hourlyMinimum,weights,importedSearch,prioritizeHighScore,autoRefresh'],
            'preferences.keywords' => ['nullable', 'string', 'max:2000'],
            'preferences.targetSkills' => ['nullable', 'string', 'max:2000'],
            'preferences.countries' => ['required', 'string', 'max:2000'],
            'preferences.fixedMinimum' => ['required', 'string', 'max:30'],
            'preferences.hourlyMinimum' => ['required', 'string', 'max:30'],
            'preferences.prioritizeHighScore' => ['sometimes', 'boolean'],
            'preferences.autoRefresh' => ['sometimes', 'boolean'],
            'preferences.weights' => ['required', 'array:skills,budget,competition,age'],
            'preferences.weights.skills' => ['required', 'numeric', 'min:0', 'max:100'],
            'preferences.weights.budget' => ['required', 'numeric', 'min:0', 'max:100'],
            'preferences.weights.competition' => ['required', 'numeric', 'min:0', 'max:100'],
            'preferences.weights.age' => ['required', 'numeric', 'min:0', 'max:100'],
            'preferences.importedSearch' => ['nullable', 'array:query,fixedRanges,hourlyMinimum,regions,hires,proposals,experience,verified,sort,jobTypes,warnings'],
            'preferences.importedSearch.query' => ['nullable', 'string', 'max:2000'],
            'preferences.importedSearch.fixedRanges' => ['nullable', 'array', 'max:50'],
            'preferences.importedSearch.fixedRanges.*' => ['string', 'max:100'],
            'preferences.importedSearch.hourlyMinimum' => ['nullable', 'string', 'max:30'],
            'preferences.importedSearch.regions' => ['nullable', 'array', 'max:50'],
            'preferences.importedSearch.regions.*' => ['string', 'max:100'],
            'preferences.importedSearch.hires' => ['nullable', 'string', 'max:100'],
            'preferences.importedSearch.proposals' => ['nullable', 'string', 'max:100'],
            'preferences.importedSearch.experience' => ['nullable', 'string', 'max:100'],
            'preferences.importedSearch.verified' => ['nullable', 'boolean'],
            'preferences.importedSearch.sort' => ['nullable', 'string', 'max:100'],
            'preferences.importedSearch.jobTypes' => ['nullable', 'string', 'max:200'],
            'preferences.importedSearch.warnings' => ['nullable', 'array', 'max:50'],
            'preferences.importedSearch.warnings.*' => ['string', 'max:500'],
        ]);

        $identity = $this->identity($request);
        DB::transaction(function () use ($identity, $validated): void {
            $saved = DB::table('upwork_job_preferences')->where($identity)->lockForUpdate()->first();
            $values = ['preferences' => json_encode($validated['preferences'], JSON_THROW_ON_ERROR), 'updated_at' => now()];
            if ($saved) {
                DB::table('upwork_job_preferences')->where('id', $saved->id)->update($values);
            } else {
                DB::table('upwork_job_preferences')->insert($identity + $values + ['created_at' => now()]);
            }
        });

        return response()->json(['preferences' => $validated['preferences']]);
    }

    private function redirectUri(Request $request): string
    {
        $root = rtrim(config('app.url'), '/');
        if ($request->getSchemeAndHttpHost() === 'http://127.0.0.1:8137') {
            $root = 'http://127.0.0.1:8137';
        }abort_unless(str_starts_with($root, 'https://') || $root === 'http://127.0.0.1:8137', 503, 'Configure the public HTTPS application URL first.');

        return $root.'/upwork/mcp/callback';
    }

    public function status(Request $request): JsonResponse
    {
        $this->authorizeUser($request);

        return response()->json(['connected' => DB::table('upwork_mcp_connections')->where($this->identity($request))->exists()]);
    }

    public function connect(Request $request): RedirectResponse
    {
        $this->authorizeUser($request);
        $redirect = $this->redirectUri($request);
        try {
            $reg = Http::timeout(15)->acceptJson()->post(self::REGISTRATION, ['client_name' => 'LeadPilot CRM', 'redirect_uris' => [$redirect], 'grant_types' => ['authorization_code', 'refresh_token'], 'response_types' => ['code'], 'token_endpoint_auth_method' => 'none']);
        } catch (\Throwable $e) {
            return redirect('/?upwork_mcp=unavailable');
        }
        $client = $reg->json('client_id');
        if (! $reg->successful() || ! is_string($client) || strlen($client) > 2048 || $client === '') {
            return redirect('/?upwork_mcp=unavailable');
        }
        $state = Str::random(64);
        $verifier = Str::random(80);
        $request->session()->put('upwork_mcp_oauth', ['state' => $state, 'verifier' => $verifier, 'client_id' => $client, 'redirect' => $redirect, 'user_id' => $request->user()->id, 'organization_id' => $request->user()->organization_id, 'expires' => now()->addMinutes(10)->timestamp]);

        return redirect()->away(self::AUTH.'?'.http_build_query(['response_type' => 'code', 'client_id' => $client, 'redirect_uri' => $redirect, 'state' => $state, 'code_challenge' => rtrim(strtr(base64_encode(hash('sha256', $verifier, true)), '+/', '-_'), '='), 'code_challenge_method' => 'S256', 'resource' => 'https://mcp.upwork.com/mcp']));
    }

    public function callback(Request $request): RedirectResponse
    {
        $this->authorizeUser($request);
        $saved = $request->session()->pull('upwork_mcp_oauth');
        abort_unless(is_array($saved) && $saved['user_id'] === $request->user()->id && $saved['organization_id'] === $request->user()->organization_id && $saved['expires'] >= now()->timestamp && is_string($request->input('state')) && hash_equals($saved['state'], $request->input('state')), 403);
        $code = $request->input('code');
        if (! is_string($code) || $code === '') {
            return redirect('/?upwork_mcp=cancelled');
        }
        try {
            $res = Http::asForm()->timeout(20)->post(self::TOKEN, ['grant_type' => 'authorization_code', 'client_id' => $saved['client_id'], 'redirect_uri' => $saved['redirect'], 'code' => $code, 'code_verifier' => $saved['verifier']]);
        } catch (\Throwable $e) {
            return redirect('/?upwork_mcp=failed');
        }
        $access = $res->json('access_token');
        if (! $res->successful() || ! is_string($access) || $access === '') {
            return redirect('/?upwork_mcp=failed');
        }$refresh = $res->json('refresh_token');
        $expires = $res->json('expires_in');
        DB::table('upwork_mcp_connections')->updateOrInsert($this->identity($request), ['client_id' => Crypt::encryptString($saved['client_id']), 'access_token' => Crypt::encryptString($access), 'refresh_token' => is_string($refresh) && $refresh !== '' ? Crypt::encryptString($refresh) : null, 'expires_at' => is_numeric($expires) ? now()->addSeconds(max(1, (int) $expires))->toDateTimeString() : null, 'updated_at' => now(), 'created_at' => now()]);

        return redirect('/?upwork_mcp=connected');
    }

    public function disconnect(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        DB::transaction(function () use ($request): void {
            DB::table('upwork_mcp_snapshots')->where($this->identity($request))->delete();
            DB::table('upwork_mcp_connections')->where($this->identity($request))->delete();
        });

        return response()->json(['message' => 'Disconnected from LeadPilot. Revoke access in Upwork if desired.']);
    }

    public function savedProfile(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        $snapshot = DB::table('upwork_mcp_snapshots')->where($this->identity($request))->first();

        return response()->json(['profile' => $snapshot ? json_decode(Crypt::decryptString($snapshot->profile), true) : null, 'synced_at' => $snapshot?->updated_at])->header('Cache-Control', 'no-store');
    }

    public function syncProfile(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        $identity = $this->identity($request);
        $original = DB::table('upwork_mcp_connections')->where($identity)->first();
        abort_unless($original, 422, 'Connect Upwork first.');
        $request->merge(['view' => 'profile']);
        $result = $this->capabilities($request);
        if ($result->getStatusCode() !== 200) {
            return $result;
        }
        $profile = $result->getData(true)['profile'] ?? null;
        if (! is_array($profile)) {
            return response()->json(['message' => 'Upwork did not return a usable profile.'], 502);
        }
        DB::transaction(function () use ($identity, $profile, $original): void {
            $connection = DB::table('upwork_mcp_connections')->where($identity)->lockForUpdate()->first();
            abort_unless($connection && $connection->id === $original->id && hash_equals($original->client_id, $connection->client_id), 409, 'Upwork connection changed. Please sync again.');
            DB::table('upwork_mcp_snapshots')->updateOrInsert($identity, ['profile' => Crypt::encryptString(json_encode($profile, JSON_THROW_ON_ERROR)), 'updated_at' => now(), 'created_at' => now()]);
        });

        return $this->savedProfile($request);
    }

    public function deleteProfile(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        DB::table('upwork_mcp_snapshots')->where($this->identity($request))->delete();

        return response()->json(['message' => 'Saved Upwork profile removed.']);
    }

    public function capabilities(Request $request): JsonResponse
    {
        $this->authorizeUser($request);
        $request->validate(['view' => ['nullable', 'in:jobs,job-detail,conversations,conversation-detail,profile,proposals,send-message'], 'job_id' => ['required_if:view,job-detail', 'nullable', 'string', 'max:32', 'regex:/^~0[0-9]{10,}$/'], 'mode' => ['nullable', 'in:best_match,most_recent'], 'cursor' => ['nullable', 'string', 'max:2048'], 'proposal_status' => ['nullable', 'in:Accepted,Declined,Withdrawn,Offered,Activated,Archived,Hired,Pending'], 'room_id' => ['required_if:view,conversation-detail,send-message', 'nullable', 'string', 'max:255', 'regex:/^[a-zA-Z0-9_-]+$/'], 'message_id' => ['required_if:view,conversation-detail', 'nullable', 'string', 'max:255'], 'message' => ['required_if:view,send-message', 'nullable', 'string', 'max:10240'], 'confirmed' => ['accepted_if:view,send-message']]);
        if ($request->input('view') === 'send-message') {
            abort_unless($request->isMethod('post') && app(PermissionResolver::class)->scopes($request->user(), 'leads', 'edit', $request->user()->organization_id), 403);
        }
        if (in_array($request->input('view'), ['conversations', 'conversation-detail'], true)) {
            abort_unless(app(PermissionResolver::class)->scopes($request->user(), 'leads', 'view', $request->user()->organization_id), 403);
        }
        $connection = DB::table('upwork_mcp_connections')->where($this->identity($request))->first();
        if (! $connection) {
            return response()->json(['message' => 'Connect Upwork first.'], 422);
        }

        try {
            $access = Crypt::decryptString($connection->access_token);
            if ($connection->expires_at && now()->addMinute()->gte(Carbon::parse($connection->expires_at))) {
                if (! $connection->refresh_token) {
                    return response()->json(['message' => 'Your Upwork connection has expired. Please reconnect.'], 401);
                }
                $refresh = Http::asForm()->timeout(20)->withoutRedirecting()->post(self::TOKEN, ['grant_type' => 'refresh_token', 'client_id' => Crypt::decryptString($connection->client_id), 'refresh_token' => Crypt::decryptString($connection->refresh_token)]);
                if (! $refresh->successful() || ! is_string($refresh->json('access_token'))) {
                    return response()->json(['message' => 'Your Upwork connection needs to be reconnected.'], 401);
                }
                $access = $refresh->json('access_token');
                $newRefresh = $refresh->json('refresh_token');
                DB::table('upwork_mcp_connections')->where('id', $connection->id)->update(['access_token' => Crypt::encryptString($access), 'refresh_token' => is_string($newRefresh) && $newRefresh !== '' ? Crypt::encryptString($newRefresh) : $connection->refresh_token, 'expires_at' => is_numeric($refresh->json('expires_in')) ? now()->addSeconds((int) $refresh->json('expires_in')) : null, 'updated_at' => now()]);
            }
            $http = fn () => Http::withToken($access)->timeout(20)->withoutRedirecting()->withHeaders(['Accept' => 'application/json, text/event-stream', 'MCP-Protocol-Version' => '2025-03-26']);
            $init = $http()->post('https://mcp.upwork.com/mcp', ['jsonrpc' => '2.0', 'id' => 1, 'method' => 'initialize', 'params' => ['protocolVersion' => '2025-03-26', 'capabilities' => new \stdClass, 'clientInfo' => ['name' => 'LeadPilot', 'version' => '1.0']]]);
            if (! $init->successful()) {
                return response()->json(['message' => 'Upwork could not verify this connection.', 'provider_status' => $init->status()], 502);
            }
            $session = $init->header('Mcp-Session-Id');
            $headers = $session ? ['Mcp-Session-Id' => $session] : [];
            $http()->withHeaders($headers)->post('https://mcp.upwork.com/mcp', ['jsonrpc' => '2.0', 'method' => 'notifications/initialized']);
            if ($request->filled('view')) {
                $call = function (string $name, array $arguments) use ($http, $headers): array {
                    $response = $http()->withHeaders($headers)->post('https://mcp.upwork.com/mcp', ['jsonrpc' => '2.0', 'id' => 2, 'method' => 'tools/call', 'params' => ['name' => $name, 'arguments' => (object) $arguments]]);
                    if (! $response->successful()) {
                        throw new \RuntimeException('Upwork request failed');
                    }
                    $body = $response->json();
                    if (! is_array($body)) {
                        preg_match('/^data:\s*(\{.*\})\s*$/m', $response->body(), $match);
                        $body = json_decode($match[1] ?? '', true);
                    }
                    $result = data_get($body, 'result');
                    if (! is_array($result) || ! empty($result['isError'])) {
                        throw new \RuntimeException('Upwork tool failed');
                    }
                    $data = $result['structuredContent'] ?? null;
                    if (! is_array($data)) {
                        $data = json_decode(data_get($result, 'content.0.text', ''), true);
                    }
                    if (! is_array($data) || (($data['status'] ?? '') === 'error')) {
                        throw new \RuntimeException('Upwork response invalid');
                    }

                    return $data;
                };
                $accounts = $call('upwork__list_accounts', []);
                $talents = array_values(array_filter($accounts['accounts'] ?? [], fn ($account) => ($account['role'] ?? '') === 'TALENT' && ! empty($account['org_uid'])));
                if (count($talents) !== 1) {
                    return response()->json(['message' => 'A single freelancer account is required for this preview.'], 422);
                }
                $org = $talents[0]['org_uid'];
                if ($request->input('view') === 'send-message') {
                    try {
                        $sent = $call('upwork__send_message', ['action' => 'send', 'org_uid' => $org, 'params' => ['room_id' => $request->input('room_id'), 'message' => $request->input('message')]]);
                    } catch (\Throwable $e) {
                        return response()->json(['message' => 'Upwork did not confirm delivery. Check the conversation on Upwork before trying again.'], 502);
                    }
                    if (($sent['status'] ?? null) !== 'success') {
                        return response()->json(['message' => 'Upwork did not confirm delivery. Check the conversation on Upwork before trying again.'], 502);
                    }

                    return response()->json(['message' => 'Message sent to Upwork.']);
                }
                if ($request->input('view') === 'profile') {
                    $data = $call('upwork__get_profile', ['action' => 'get', 'org_uid' => $org]);
                    $profile = data_get($data, 'data', []);
                    $personal = $profile['personalData'] ?? [];

                    return response()->json(['profile' => ['name' => trim(($personal['firstName'] ?? '').' '.($personal['lastName'] ?? '')), 'title' => $personal['title'] ?? null, 'description' => $personal['description'] ?? null, 'hourly_rate' => data_get($personal, 'chargeRate.displayValue'), 'location' => data_get($personal, 'location.country'), 'skills' => array_values(array_filter(array_map(fn ($skill) => $skill['prettyName'] ?? $skill['skill'] ?? null, $profile['skills'] ?? []), 'is_string')), 'job_success' => $data['job_success_score'] ?? data_get($profile, 'job_success_score'), 'url' => $profile['profile_url'] ?? null]])->header('Cache-Control', 'no-store');
                }
                if ($request->input('view') === 'proposals') {
                    $params = ['limit' => 25, 'status' => $request->input('proposal_status', 'Accepted')];
                    if ($request->filled('cursor')) {
                        $params['cursor'] = $request->input('cursor');
                    }
                    $data = $call('upwork__list_freelancer_proposals', ['action' => 'list', 'org_uid' => $org, 'params' => $params]);
                    $nodes = data_get($data, 'data.vendorProposals.edges', []);
                    $items = array_map(function ($edge): array {
                        $node = $edge['node'] ?? [];
                        $item = collect($node)->only(['id', 'status', 'status_label', 'createdDateTime', 'viewedByClient'])->all();
                        $item['jobPosting'] = collect($node['jobPosting'] ?? [])->only(['id', 'title'])->all();

                        return $item;
                    }, $nodes);

                    return response()->json(['items' => $items, 'has_more' => (bool) ($data['hasMore'] ?? false), 'next_cursor' => $data['next_cursor'] ?? data_get($data, 'data.vendorProposals.pageInfo.endCursor')])->header('Cache-Control', 'no-store');
                }
                if ($request->input('view') === 'job-detail') {
                    $data = $call('upwork__find_jobs', ['action' => 'get', 'org_uid' => $org, 'params' => ['id' => $request->input('job_id')]]);
                    $description = data_get($data, 'data.marketplaceJobPosting.content.description');
                    if (! is_string($description) || trim($description) === '') {
                        return response()->json(['message' => 'The full description is unavailable from Upwork.'], 422)->header('Cache-Control', 'no-store');
                    }

                    return response()->json(['description' => $description, 'client_rating' => data_get($data, 'client_record.feedback_score'), 'client_review_count' => data_get($data, 'client_record.feedback_count'), 'client_hire_rate' => data_get($data, 'client_record.hire_rate_percent'), 'client_hires' => data_get($data, 'client_record.contracts_total'), 'client_jobs_posted' => data_get($data, 'client_record.jobs_posted'), 'connects_cost' => data_get($data, 'connects_cost'), 'job_hired' => data_get($data, 'data.marketplaceJobPosting.activityStat.jobActivity.totalHired'), 'job_interviews' => data_get($data, 'data.marketplaceJobPosting.activityStat.jobActivity.totalInvitedToInterview')])->header('Cache-Control', 'no-store');
                }
                if ($request->input('view') === 'jobs') {
                    $data = $call('upwork__find_jobs', ['action' => 'smart_search', 'org_uid' => $org, 'params' => ['limit' => 10, 'mode' => $request->input('mode', 'best_match')]]);
                    $jobs = array_map(function ($job) {
                        $item = collect($job)->only(['title', 'description_snippet', 'budget', 'job_type', 'skills', 'url', 'published_date', 'proposals_tier', 'applied'])->all();
                        if (isset($job['hiring_now']) && is_bool($job['hiring_now'])) {
                            $item['hiring_now'] = $job['hiring_now'];
                        }
                        $item['client_country'] = data_get($job, 'client.country');
                        $item['payment_verification'] = data_get($job, 'client.verification_status');

                        return $item;
                    }, $data['jobs'] ?? []);

                    return response()->json(['items' => $jobs, 'has_more' => (bool) ($data['hasMore'] ?? false)])->header('Cache-Control', 'no-store');
                }
                if ($request->input('view') === 'conversation-detail') {
                    $data = $call('upwork__get_messages', ['action' => 'list_messages', 'org_uid' => $org, 'params' => ['room_id' => $request->input('room_id'), 'limit' => 1]]);
                    $message = data_get($data, 'data.roomStories.edges.0.node');
                    if (! is_array($message)) {
                        return response()->json(['message' => 'No last message was returned by Upwork.'], 422)->header('Cache-Control', 'no-store');
                    }
                    if (($message['id'] ?? null) !== $request->input('message_id')) {
                        return response()->json(['message' => 'The conversation changed. Refresh it before checking the sender.'], 409)->header('Cache-Control', 'no-store');
                    }
                    $side = $message['from_side'] ?? null;
                    if (! in_array($side, ['client', 'freelancer'], true)) {
                        $side = ($message['from_self'] ?? null) === true ? 'freelancer' : null;
                    }

                    return response()->json(['last_message_side' => $side])->header('Cache-Control', 'no-store');
                }
                $params = ['limit' => 100];
                if ($request->filled('cursor')) {
                    $params['cursor'] = $request->input('cursor');
                }
                $data = $call('upwork__get_messages', ['action' => 'list_rooms', 'org_uid' => $org, 'params' => $params]);
                $rooms = array_map(fn ($room) => ['id' => $room['id'] ?? null, 'name' => $room['roomName'] ?? null, 'last_activity' => $room['lastActivity'] ?? null, 'last_message' => data_get($room, 'latestStory.message'), 'last_message_id' => data_get($room, 'latestStory.id'), 'last_message_at' => data_get($room, 'latestStory.createdDateTime'), 'last_message_side' => in_array($room['last_message_side'] ?? null, ['client', 'freelancer'], true) ? $room['last_message_side'] : (($room['last_message_from_self'] ?? null) === true ? 'freelancer' : null), 'awaiting_reply_from' => in_array($room['awaiting_reply_from'] ?? null, ['you', 'them'], true) ? $room['awaiting_reply_from'] : null], data_get($data, 'data.rooms', []));

                return response()->json(['items' => $rooms, 'has_more' => (bool) ($data['hasMore'] ?? false), 'next_cursor' => $data['next_cursor'] ?? null])->header('Cache-Control', 'no-store');
            }
            $result = $http()->withHeaders($headers)->post('https://mcp.upwork.com/mcp', ['jsonrpc' => '2.0', 'id' => 2, 'method' => 'tools/list', 'params' => new \stdClass]);
            if (! $result->successful()) {
                return response()->json(['message' => 'Upwork could not list available features.', 'provider_status' => $result->status()], 502);
            }
            $body = $result->json();
            if (! is_array($body)) {
                preg_match('/^data:\s*(\{.*\})\s*$/m', $result->body(), $match);
                $body = json_decode($match[1] ?? '', true);
            }
            $tools = data_get($body, 'result.tools');
            if (! is_array($tools)) {
                return response()->json(['message' => 'Upwork returned an unexpected response.'], 502);
            }

            return response()->json(['tools' => array_values(array_filter(array_map(fn ($tool) => is_array($tool) ? ($tool['name'] ?? null) : null, $tools), 'is_string'))]);
        } catch (\Throwable $e) {
            return response()->json(['message' => 'Unable to reach Upwork. Please try again.'], 502);
        }
    }
}
