<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class GoogleCalendarController extends Controller
{
    private function authorized(Request $request, string $action): void
    {
        $user = $request->user();
        abort_unless($user->organization_id && app(PermissionResolver::class)->scopes($user, 'meetings', $action, $user->organization_id), 403);
    }

    private function config(Request $request): array
    {
        $stored = DB::table('calendar_app_configs')->where('organization_id', $request->user()->organization_id)->first();
        $data = $stored ? ['client_id' => Crypt::decryptString($stored->encrypted_client_id), 'client_secret' => Crypt::decryptString($stored->encrypted_client_secret), 'redirect_uri' => $stored->redirect_uri] : config('services.google_calendar');
        abort_unless(! empty($data['client_id']) && ! empty($data['client_secret']) && ! empty($data['redirect_uri']), 503, 'Google Calendar setup is not configured.');

        return $data;
    }

    private function connection(Request $request): ?object
    {
        return DB::table('calendar_connections')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id)->first();
    }

    public function status(Request $request): JsonResponse
    {
        $this->authorized($request, 'view');

        $stored = DB::table('calendar_app_configs')->where('organization_id', $request->user()->organization_id)->exists();

        return response()->json(['connected' => (bool) $this->connection($request), 'configured' => $stored || (bool) (config('services.google_calendar.client_id') && config('services.google_calendar.client_secret') && config('services.google_calendar.redirect_uri'))]);
    }

    public function configure(Request $request): JsonResponse
    {
        $user = $request->user();
        abort_unless($user->organization_id && $user->is_super_admin, 403);
        $data = $request->validate(['client_id' => ['required', 'string', 'max:255', 'regex:/^[a-zA-Z0-9._-]+$/'], 'client_secret' => ['required', 'string', 'max:255', 'regex:/^[a-zA-Z0-9._-]+$/'], 'redirect_uri' => ['required', 'string', 'url:http,https', 'max:255']]);
        $host = parse_url($data['redirect_uri'], PHP_URL_HOST);
        abort_unless(str_starts_with($data['redirect_uri'], 'https://') || in_array($host, ['127.0.0.1', 'localhost'], true), 422);
        DB::table('calendar_app_configs')->updateOrInsert(['organization_id' => $user->organization_id], ['encrypted_client_id' => Crypt::encryptString($data['client_id']), 'encrypted_client_secret' => Crypt::encryptString($data['client_secret']), 'redirect_uri' => $data['redirect_uri'], 'created_at' => now(), 'updated_at' => now()]);

        return response()->json(['message' => 'Calendar app configured.']);
    }

    public function connect(Request $request): RedirectResponse
    {
        $this->authorized($request, 'create');
        $config = $this->config($request);
        $state = Str::random(64);
        $verifier = Str::random(80);
        $request->session()->put('calendar_oauth', ['state' => $state, 'verifier' => $verifier, 'user_id' => $request->user()->id, 'expires' => now()->addMinutes(10)->timestamp]);
        $params = ['client_id' => $config['client_id'], 'redirect_uri' => $config['redirect_uri'], 'response_type' => 'code', 'scope' => 'https://www.googleapis.com/auth/calendar.events', 'access_type' => 'offline', 'prompt' => 'consent', 'state' => $state, 'code_challenge' => rtrim(strtr(base64_encode(hash('sha256', $verifier, true)), '+/', '-_'), '='), 'code_challenge_method' => 'S256'];

        return redirect()->away('https://accounts.google.com/o/oauth2/v2/auth?'.http_build_query($params));
    }

    public function callback(Request $request): RedirectResponse
    {
        $this->authorized($request, 'create');
        $config = $this->config($request);
        $saved = $request->session()->pull('calendar_oauth');
        abort_unless(is_array($saved) && $saved['user_id'] === $request->user()->id && $saved['expires'] >= now()->timestamp && is_string($request->input('state')) && hash_equals($saved['state'], $request->input('state')), 403);
        if (! is_string($request->input('code')) || $request->input('code') === '') {
            return redirect('/?calendar=cancelled');
        }
        try {
            $response = Http::asForm()->timeout(20)->post('https://oauth2.googleapis.com/token', ['code' => $request->input('code'), 'client_id' => $config['client_id'], 'client_secret' => $config['client_secret'], 'redirect_uri' => $config['redirect_uri'], 'grant_type' => 'authorization_code', 'code_verifier' => $saved['verifier']]);
        } catch (\Throwable $e) {
            Log::error('Google Calendar token exchange failed', ['error' => $e::class, 'detail' => Str::limit($e->getMessage(), 200)]);
            return redirect('/?calendar=failed');
        }
        $refresh = $response->json('refresh_token');
        if (! $response->successful() || ! is_string($refresh) || $refresh === '') {
            return redirect('/?calendar=failed');
        }
        DB::table('calendar_connections')->updateOrInsert(['organization_id' => $request->user()->organization_id, 'user_id' => $request->user()->id], ['encrypted_refresh_token' => Crypt::encryptString($refresh), 'created_at' => now(), 'updated_at' => now()]);

        return redirect('/?calendar=connected');
    }

    private function accessToken(Request $request): string
    {
        $config = $this->config($request);
        $connection = $this->connection($request);
        abort_unless($connection, 422, 'Connect your Google Calendar first.');
        try {
            $response = Http::asForm()->timeout(20)->post('https://oauth2.googleapis.com/token', ['client_id' => $config['client_id'], 'client_secret' => $config['client_secret'], 'refresh_token' => Crypt::decryptString($connection->encrypted_refresh_token), 'grant_type' => 'refresh_token']);
        } catch (\Throwable $e) {
            Log::error('Google Calendar token refresh failed', ['error' => $e::class, 'detail' => Str::limit($e->getMessage(), 200)]);
            abort(502, 'Could not connect to Google Calendar.');
        }
        abort_unless($response->successful() && is_string($response->json('access_token')), 502, 'Google Calendar authorization failed. Please reconnect.');

        return $response->json('access_token');
    }

    public function events(Request $request): JsonResponse
    {
        $this->authorized($request, 'view');
        $token = $this->accessToken($request);
        try {
            $response = Http::withToken($token)->timeout(20)->get('https://www.googleapis.com/calendar/v3/calendars/primary/events', ['timeMin' => now()->subDays(7)->toRfc3339String(), 'timeMax' => now()->addDays(60)->toRfc3339String(), 'singleEvents' => 'true', 'orderBy' => 'startTime', 'maxResults' => 100]);
        } catch (\Throwable $e) {
            Log::error('Google Calendar events request failed', ['error' => $e::class, 'detail' => Str::limit($e->getMessage(), 200)]);
            abort(502, 'Could not load calendar events.');
        }
        abort_unless($response->successful(), 502, 'Google Calendar could not load events.');

        return response()->json(['events' => collect($response->json('items', []))->map(fn ($item) => ['id' => $item['id'] ?? '', 'title' => $item['summary'] ?? '(No title)', 'start' => $item['start']['dateTime'] ?? $item['start']['date'] ?? null, 'end' => $item['end']['dateTime'] ?? $item['end']['date'] ?? null, 'link' => $item['hangoutLink'] ?? $item['htmlLink'] ?? null])]);
    }

    public function createEvent(Request $request): JsonResponse
    {
        $this->authorized($request, 'create');
        $data = $request->validate(['title' => ['required', 'string', 'max:255'], 'start' => ['required', 'date'], 'end' => ['required', 'date', 'after:start'], 'create_meet' => ['required', 'boolean']]);
        $token = $this->accessToken($request);
        $body = ['summary' => $data['title'], 'start' => ['dateTime' => Carbon::parse($data['start'])->toRfc3339String()], 'end' => ['dateTime' => Carbon::parse($data['end'])->toRfc3339String()]];
        if ($data['create_meet']) {
            $body['conferenceData'] = ['createRequest' => ['requestId' => (string) Str::uuid(), 'conferenceSolutionKey' => ['type' => 'hangoutsMeet']]];
        }
        try {
            $response = Http::withToken($token)->timeout(20)->post('https://www.googleapis.com/calendar/v3/calendars/primary/events?conferenceDataVersion=1&sendUpdates=none', $body);
        } catch (\Throwable $e) {
            Log::error('Google Calendar event create failed', ['error' => $e::class, 'detail' => Str::limit($e->getMessage(), 200)]);
            abort(502, 'Could not create the calendar event. Check Google Calendar before retrying.');
        }
        abort_unless($response->successful(), 502, 'Google Calendar could not create the event.');

        return response()->json(['id' => $response->json('id'), 'link' => $response->json('hangoutLink') ?? $response->json('htmlLink')], 201);
    }

    public function disconnect(Request $request): JsonResponse
    {
        $this->authorized($request, 'create');
        DB::table('calendar_connections')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id)->delete();

        return response()->json(['message' => 'Disconnected from LeadPilot. Google account access may also be removed in Google settings.']);
    }
}
