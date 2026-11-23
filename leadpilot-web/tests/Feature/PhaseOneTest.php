<?php

namespace Tests\Feature;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\Storage;
use Tests\TestCase;

class PhaseOneTest extends TestCase
{
    use RefreshDatabase;

    public function test_follow_up_default_timings_are_personal_and_do_not_change_existing_cycles(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $unauthorized = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $lead = $this->postJson('/leads', ['name' => 'Client'])->assertCreated()->json('id');
        $url = '/leads/'.$lead.'/follow-up-cycle';
        $this->getJson('/follow-up-preferences')->assertOk()->assertJsonPath('cadence', [24, 48, 48, 72, 72]);
        $this->putJson('/follow-up-preferences', ['cadence' => [0]])->assertUnprocessable();
        $this->putJson('/follow-up-preferences', ['cadence' => [8, 16]])->assertOk();
        $this->getJson($url)->assertOk()->assertJsonPath('default_cadence', [8, 16]);
        $this->putJson($url, ['action' => 'start', 'cadence' => [8, 16]])->assertOk();
        $this->putJson('/follow-up-preferences', ['cadence' => [24]])->assertOk();
        $this->getJson($url)->assertOk()->assertJsonPath('cycle.cadence', [8, 16]);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/follow-up-preferences')->assertOk()->assertJsonPath('cadence', [24, 48, 48, 72, 72]);
        $this->withSession(['session_version' => 0])->actingAs($unauthorized)->putJson('/follow-up-preferences', ['cadence' => [24]])->assertForbidden();
    }

    public function test_confirmed_closed_deal_updates_linked_lead_and_stops_followups(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Closed deal test', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $outsider = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $lead = $this->postJson('/leads', ['name' => 'Client'])->assertCreated()->json('id');
        $this->putJson('/leads/'.$lead.'/follow-up-cycle', ['action' => 'start', 'cadence' => [24]])->assertOk();
        $payload = ['title' => 'Project', 'lead_id' => $lead, 'deal_value' => '1200.00', 'currency' => 'USD', 'closed_on' => now()->toDateString()];
        $this->withSession(['session_version' => 0])->actingAs($outsider)->postJson('/deals/closed', $payload)->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/deals/closed', $payload)->assertCreated();
        $this->assertDatabaseHas('leads', ['id' => $lead, 'status' => 'won']);
        $this->assertDatabaseHas('deals', ['lead_id' => $lead, 'status' => 'won', 'deal_value_cents' => 120000]);
        $this->getJson('/leads/'.$lead.'/follow-up-cycle')->assertOk()->assertJsonPath('cycle.closed', true);
        $this->getJson('/deals?status=won')->assertOk()->assertJsonCount(1, 'data');
    }

    public function test_follow_up_cycle_tracks_timing_and_stops_when_deal_closes(): void
    {
        $this->travelTo(Carbon::parse('2026-01-01 12:00:00', 'UTC'));
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $foreign = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $lead = $this->postJson('/leads', ['name' => 'Client'])->assertCreated()->json('id');
        $url = '/leads/'.$lead.'/follow-up-cycle';
        $this->putJson($url, ['action' => 'start', 'cadence' => [0]])->assertUnprocessable();
        $this->putJson($url, ['action' => 'start', 'cadence' => [24, 48, 48, 72, 72]])->assertOk()->assertJsonPath('cycle.due_at', '2026-01-02T12:00:00+00:00');
        $this->getJson('/follow-up-cycles')->assertOk()->assertJsonCount(1, 'data')->assertJsonPath('data.0.lead_id', $lead);
        $this->travel(25)->hours();
        $this->putJson($url, ['action' => 'sent'])->assertOk()->assertJsonPath('cycle.completed', 1)->assertJsonPath('cycle.due_at', '2026-01-04T13:00:00+00:00');
        $this->putJson('/admin/employees/'.$admin->id.'/targets', ['metric' => 'followups', 'period_start' => '2026-01-02', 'period_end' => '2026-01-02', 'target_value' => 2])->assertOk();
        $this->getJson('/admin/employees/'.$admin->id.'/sales-performance?from=2026-01-02&to=2026-01-02')->assertOk()->assertJsonPath('followups_marked_sent', 1)->assertJsonPath('targets.0.percent', 50);
        $this->putJson($url, ['action' => 'reply'])->assertOk()->assertJsonPath('cycle.completed', 0);
        $this->putJson($url, ['action' => 'configure', 'cadence' => [5, 10]])->assertOk()->assertJsonPath('cycle.due_at', '2026-01-02T18:00:00+00:00');
        $this->putJson($url, ['action' => 'stage', 'stage' => 'Meeting booked'])->assertOk()->assertJsonPath('cycle.due_at', null);
        $this->putJson($url, ['action' => 'sent'])->assertUnprocessable();
        $this->putJson($url, ['action' => 'stage', 'stage' => 'Chat started'])->assertOk();
        $deal = $this->postJson('/deals', ['title' => 'Project', 'lead_id' => $lead])->assertCreated()->json('id');
        $this->patchJson('/deals/'.$deal, ['title' => 'Project', 'status' => 'won', 'closed_on' => '2026-01-02', 'deal_value' => '100', 'currency' => 'USD'])->assertOk();
        $this->getJson($url)->assertOk()->assertJsonPath('cycle.closed', true)->assertJsonPath('cycle.due_at', null);
        $this->getJson('/follow-up-cycles')->assertOk()->assertJsonCount(0, 'data');
        $this->putJson($url, ['action' => 'sent'])->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($foreign)->getJson($url)->assertNotFound();
        $this->getJson('/follow-up-cycles')->assertOk()->assertJsonCount(0, 'data');
    }

    public function test_google_calendar_loads_events_for_connected_user(): void
    {
        config()->set('services.google_calendar', ['client_id' => 'demo', 'client_secret' => 'secret', 'redirect_uri' => 'http://localhost/calendar/callback']);
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('calendar_connections')->insert(['organization_id' => $org, 'user_id' => $admin->id, 'encrypted_refresh_token' => Crypt::encryptString('refresh-value'), 'created_at' => now(), 'updated_at' => now()]);
        Http::fake(['oauth2.googleapis.com/*' => Http::response(['access_token' => 'access-value'], 200), 'www.googleapis.com/*' => Http::response(['id' => 'new-event', 'items' => [['id' => 'event-1', 'summary' => 'Meeting']]], 200)]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/calendar/events')->assertOk()->assertJsonPath('events.0.title', 'Meeting');
        $this->postJson('/calendar/events', ['title' => 'Call', 'start' => '2026-01-01T10:00:00Z', 'end' => '2026-01-01T11:00:00Z', 'create_meet' => true])->assertCreated()->assertJsonPath('id', 'new-event');
        Http::assertSent(fn ($request) => str_contains($request->url(), 'conferenceDataVersion=1') && $request['conferenceData']['createRequest']['conferenceSolutionKey']['type'] === 'hangoutsMeet');
    }

    public function test_calendar_configuration_requires_admin_and_encrypts_secrets(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $data = ['client_id' => 'example-client', 'client_secret' => 'example-secret', 'redirect_uri' => 'http://127.0.0.1:8137/calendar/callback'];
        $this->withSession(['session_version' => 0])->actingAs($member)->putJson('/calendar/configuration', $data)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/calendar/configuration', $data)->assertOk()->assertDontSee('example-secret');
        $this->assertNotSame('example-secret', DB::table('calendar_app_configs')->value('encrypted_client_secret'));
        $this->getJson('/calendar/status')->assertOk()->assertJsonPath('configured', true);
    }

    public function test_google_calendar_unconnected_user_cannot_load_events(): void
    {
        config()->set('services.google_calendar', ['client_id' => 'demo', 'client_secret' => 'secret', 'redirect_uri' => 'http://localhost/calendar/callback']);
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/calendar/events')->assertUnprocessable();
    }

    public function test_google_calendar_connection_is_scoped_and_state_is_checked(): void
    {
        config()->set('services.google_calendar', ['client_id' => 'example-client', 'client_secret' => 'example-secret', 'redirect_uri' => 'http://localhost/calendar/callback']);
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/calendar/status')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->getJson('/calendar/status')->assertOk()->assertJsonPath('connected', false);
        $connect = $this->get('/calendar/connect')->assertRedirect();
        parse_str(parse_url($connect->headers->get('Location'), PHP_URL_QUERY), $params);
        $this->get('/calendar/callback?state=wrong&code=demo')->assertForbidden();
        $connect = $this->get('/calendar/connect')->assertRedirect();
        parse_str(parse_url($connect->headers->get('Location'), PHP_URL_QUERY), $params);
        Http::fake(['oauth2.googleapis.com/*' => Http::response(['refresh_token' => 'private-refresh'], 200)]);
        $this->get('/calendar/callback?state='.$params['state'].'&code=demo')->assertRedirect('/?calendar=connected');
        $this->assertNotSame('private-refresh', DB::table('calendar_connections')->value('encrypted_refresh_token'));
        $this->getJson('/calendar/status')->assertOk()->assertJsonPath('connected', true)->assertDontSee('private-refresh');
        $this->deleteJson('/calendar/connection')->assertOk();
        $this->getJson('/calendar/status')->assertJsonPath('connected', false);
    }

    public function test_voice_transcription_requires_permission_and_sends_audio_to_provider(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $wav = 'RIFF'.pack('V', 36).'WAVEfmt '.pack('VvvVVvv', 16, 1, 1, 8000, 16000, 2, 16).'data'.pack('V', 0);
        $audio = UploadedFile::fake()->createWithContent('sample.wav', $wav);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/ai-writer/transcribe', ['audio' => $audio])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        Http::fake(['api.openai.com/*' => Http::response(['text' => 'Please keep it short.'], 200)]);
        $this->postJson('/ai-writer/transcribe', ['audio' => $audio])->assertOk()->assertJsonPath('text', 'Please keep it short.');
        Http::assertSent(fn ($request) => str_contains($request->url(), '/audio/transcriptions'));
    }

    public function test_ai_writer_reports_auth_failure_without_provider_details(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        Http::fake(['api.openai.com/*' => Http::response(['error' => ['message' => 'sensitive provider detail']], 401)]);
        $this->postJson('/ai-writer/generate', ['job' => 'Example job'])->assertStatus(502)->assertJsonPath('message', 'OpenAI rejected the API key. Check or replace the key in AI settings.')->assertDontSee('sensitive provider detail');
    }

    public function test_ai_writer_protects_keys_and_requires_permission(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $key = 'sk-test_abcdefghijklmnopqrstuv';
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/ai-writer/settings')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->putJson('/ai-writer/settings', ['api_key' => $key, 'style_prompt' => 'Be concise', 'model' => 'gpt-4o-mini'])->assertOk()->assertJsonPath('has_key', true)->assertJsonMissing(['api_key' => $key]);
        $this->assertNotSame($key, DB::table('user_ai_settings')->value('encrypted_key'));
        Http::fake(['api.openai.com/*' => Http::response(['choices' => [['message' => ['content' => 'A draft']]]], 200)]);
        $this->postJson('/ai-writer/generate', ['job' => 'Example job'])->assertOk()->assertJsonPath('draft', 'A draft');
        Http::assertSent(fn ($request) => $request->hasHeader('Authorization', 'Bearer '.$key) && $request['model'] === 'gpt-4o-mini');
        $this->postJson('/ai-writer/generate', ['kind' => 'followup', 'job' => 'Last message'])->assertOk()->assertJsonPath('draft', 'A draft');
        Http::assertSent(fn ($request) => str_contains($request['messages'][0]['content'] ?? '', 'follow-up message'));
        $this->postJson('/ai-writer/generate', ['kind' => 'unknown', 'job' => 'x'])->assertUnprocessable();
        $this->putJson('/ai-writer/settings', ['remove_key' => true, 'model' => 'gpt-4o-mini'])->assertOk()->assertJsonPath('has_key', false);
        $this->postJson('/ai-writer/generate', ['job' => 'Example job'])->assertUnprocessable();
    }

    public function test_job_summary_requires_permission_and_caches_job_details(): void
    {
        Http::preventStrayRequests();
        $org = DB::table('organizations')->insertGetId(['name' => 'Summary test', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $job = ['title' => 'Build a store', 'description' => 'Create a Shopify store', 'skills' => ['Shopify']];
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/ai-writer/job-summary', $job)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->postJson('/ai-writer/job-summary', $job)->assertUnprocessable();
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        Http::fake(['api.openai.com/*' => Http::response(['choices' => [['message' => ['content' => 'The client needs a Shopify store.']]]], 200)]);
        $this->postJson('/ai-writer/job-summary', $job)->assertOk()->assertJsonPath('summary', 'The client needs a Shopify store.')->assertJsonPath('cached', false);
        $this->postJson('/ai-writer/job-summary', $job)->assertOk()->assertJsonPath('cached', true);
        Http::assertSentCount(1);
        Http::assertSent(fn ($request) => str_contains($request['messages'][1]['content'], 'Shopify') && str_contains($request['messages'][1]['content'], 'Build a store'));
    }

    public function test_ai_job_match_uses_only_current_users_profile_and_validates_output(): void
    {
        Http::preventStrayRequests();
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/ai-writer/job-match', ['job' => 'Example'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        $this->postJson('/ai-writer/job-match', ['job' => 'Example'])->assertStatus(422);
        DB::table('upwork_profiles')->insert(['organization_id' => $org, 'user_id' => $admin->id, 'url' => 'https://www.upwork.com/freelancers/example', 'name' => 'Example', 'title' => 'Shopify Designer', 'description' => 'Build stores', 'created_at' => now(), 'updated_at' => now()]);
        Http::fake(['api.openai.com/*' => Http::response(['choices' => [['message' => ['content' => json_encode(['match_percent' => 82, 'rationale' => 'Relevant design', 'gaps' => 'Check delivery'])]]]], 200)]);
        $this->postJson('/ai-writer/job-match', ['job' => 'Need a Shopify store'])->assertOk()->assertJsonPath('match_percent', 82)->assertJsonPath('gaps', 'Check delivery');
        Http::assertSent(fn ($request) => str_contains($request['messages'][1]['content'], 'Shopify Designer') && str_contains($request['messages'][1]['content'], 'Need a Shopify store'));
        $this->postJson('/ai-writer/job-match', ['job' => 'Need a Shopify store'])->assertOk()->assertJsonPath('cached', true);
        Http::assertSentCount(1);
        DB::table('upwork_profiles')->where('user_id', $admin->id)->update(['description' => 'New profile']);
        $this->postJson('/ai-writer/job-match', ['job' => 'Need a Shopify store'])->assertOk()->assertJsonPath('cached', false);
        $this->postJson('/ai-writer/job-match', ['job' => 'Different job'])->assertOk()->assertJsonPath('cached', false);
        Http::assertSentCount(3);
        $this->travel(25)->hours();
        $this->postJson('/ai-writer/job-match', ['job' => 'Different job'])->assertOk()->assertJsonPath('cached', false);
        Http::assertSentCount(4);

    }

    public function test_copied_upwork_proposal_import_requires_permissions_and_skips_duplicates(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $rows = [['title' => 'Build a website', 'proposal_date' => '2026-01-15', 'status' => 'viewed']];
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/proposals/import', ['rows' => $rows])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/proposals/import', ['rows' => $rows])->assertOk()->assertJsonPath('added', 1);
        $this->assertDatabaseHas('proposals', ['organization_id' => $org, 'title' => 'Build a website', 'status' => 'viewed', 'submitted_at' => null]);
        $this->postJson('/proposals/import', ['rows' => $rows])->assertOk()->assertJsonPath('skipped', 1);
        $this->postJson('/proposals/import', ['rows' => [['title' => 'Test', 'status' => 'hired']]])->assertUnprocessable();
    }

    public function test_proposal_writing_content_is_saved_and_scoped(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $foreign = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $id = $this->postJson('/proposals', ['title' => 'Website', 'job_description' => 'Job details', 'writing_instructions' => 'Keep it short', 'cover_letter' => 'Hello client'])->assertCreated()->json('id');
        $this->getJson('/proposals')->assertOk()->assertJsonPath('data.0.cover_letter', 'Hello client')->assertJsonPath('data.0.job_description', 'Job details');
        $this->patchJson('/proposals/'.$id, ['title' => 'Website', 'status' => 'draft', 'cover_letter' => 'Revised'])->assertOk();
        $this->assertDatabaseHas('proposals', ['id' => $id, 'cover_letter' => 'Revised', 'job_description' => 'Job details']);
        $this->withSession(['session_version' => 0])->actingAs($foreign)->patchJson('/proposals/'.$id, ['title' => 'X', 'status' => 'draft', 'cover_letter' => 'No'])->assertNotFound();
    }

    public function test_deals_track_currency_separately_and_sales_export_enforces_access(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $foreign = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/deals', ['title' => 'Denied'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($foreign);
        $foreignLead = $this->postJson('/leads', ['name' => 'Foreign'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->postJson('/deals', ['title' => 'Hidden lead', 'lead_id' => $foreignLead])->assertNotFound();
        $this->postJson('/deals', ['title' => 'Invalid amount', 'deal_value' => '1e2', 'currency' => 'USD'])->assertUnprocessable();
        $deal = $this->postJson('/deals', ['title' => 'Deal', 'deal_value' => '10.10', 'currency' => 'USD'])->assertCreated()->json('id');
        $this->assertDatabaseHas('deals', ['id' => $deal, 'deal_value_cents' => 1010]);
        $this->patchJson('/deals/'.$deal, ['title' => 'Deal', 'status' => 'won'])->assertUnprocessable();
        $this->patchJson('/deals/'.$deal, ['title' => 'Deal', 'status' => 'open', 'realized_revenue' => '5.00', 'currency' => 'USD'])->assertUnprocessable();
        $this->patchJson('/deals/'.$deal, ['title' => 'Deal', 'status' => 'won', 'closed_on' => '2026-01-15', 'deal_value' => '0.30', 'currency' => 'USD'])->assertOk();
        $this->assertDatabaseHas('deals', ['id' => $deal, 'deal_value_cents' => 30]);
        $this->getJson('/deals')->assertOk()->assertJsonPath('data.0.deal_value', '0.30');
        DB::table('deals')->insert(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'title' => 'Euro deal', 'status' => 'won', 'closed_on' => '2026-01-15', 'deal_value_cents' => 200, 'currency' => 'EUR', 'created_at' => now(), 'updated_at' => now()]);
        DB::table('deals')->insert(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'title' => 'Lost', 'status' => 'lost', 'closed_on' => '2026-01-15', 'created_at' => now(), 'updated_at' => now()]);
        $this->putJson('/admin/employees/'.$admin->id.'/targets', ['metric' => 'deals', 'period_start' => '2026-01-15', 'period_end' => '2026-01-15', 'target_value' => 4])->assertOk();
        $base = '/admin/employees/'.$admin->id.'/sales-performance';
        $query = '?from=2026-01-15&to=2026-01-15';
        $this->getJson($base.$query)->assertOk()->assertJsonPath('deals_won', 2)->assertJsonPath('deals_lost', 1)->assertJsonPath('deal_win_rate', 66.67)->assertJsonPath('closed_value_by_currency.0.currency', 'EUR')->assertJsonPath('closed_value_by_currency.0.cents', '200')->assertJsonPath('closed_value_by_currency.1.currency', 'USD')->assertJsonPath('closed_value_by_currency.1.cents', '30')->assertJsonPath('targets.0.percent', 50);
        $csv = $this->get($base.'/export/csv'.$query)->assertOk()->streamedContent();
        $this->assertStringContainsString('0.30', $csv);
        $this->assertStringStartsWith('%PDF-', $this->get($base.'/export/pdf'.$query)->assertOk()->streamedContent());
        $this->assertStringStartsWith('PK', $this->get($base.'/export/xlsx'.$query)->assertOk()->streamedContent());
        $this->withSession(['session_version' => 0])->actingAs($member)->get($base.'/export/csv'.$query)->assertForbidden();
        $this->get($base.'/export/xlsx'.$query)->assertForbidden();
        $this->get($base.'/export/pdf'.$query)->assertForbidden();
    }

    public function test_sales_summary_uses_real_records_and_requires_organization_access(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true, 'timezone' => 'Asia/Karachi']);
        $member = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        DB::table('leads')->insert(['organization_id' => $org, 'created_by' => $member->id, 'assigned_to' => $member->id, 'name' => 'Lead', 'status' => 'qualified', 'created_at' => '2026-01-14 20:00:00', 'updated_at' => now()]);
        $proposal = DB::table('proposals')->insertGetId(['organization_id' => $org, 'created_by' => $member->id, 'assigned_to' => $member->id, 'title' => 'Proposal', 'status' => 'interview', 'created_at' => '2026-01-14 20:00:00', 'submitted_at' => '2026-01-14 21:00:00', 'updated_at' => now()]);
        DB::table('proposal_history')->insert(['organization_id' => $org, 'proposal_id' => $proposal, 'actor_id' => $member->id, 'from_status' => 'submitted', 'to_status' => 'interview', 'created_at' => '2026-01-14 22:00:00']);
        DB::table('leads')->insert(['organization_id' => $org, 'created_by' => $member->id, 'assigned_to' => $member->id, 'name' => 'Earlier lead', 'status' => 'new', 'created_at' => '2026-01-13 20:00:00', 'updated_at' => now()]);
        $url = '/admin/employees/'.$member->id.'/sales-performance?from=2026-01-15&to=2026-01-15';
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson($url)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson($url)->assertOk()->assertJsonPath('leads_created', 1)->assertJsonPath('leads_currently_qualified', 1)->assertJsonPath('proposals_created', 1)->assertJsonPath('proposals_manually_marked_submitted', 1)->assertJsonPath('recorded_response_rate', 100)->assertJsonPath('recorded_interview_rate', 100)->assertJsonPath('previous_from', '2026-01-14')->assertJsonPath('previous_leads_created', 1);
        $this->getJson('/admin/employees/'.$foreign->id.'/sales-performance?from=2026-01-15&to=2026-01-15')->assertNotFound();
        $this->getJson('/admin/employees/'.$member->id.'/sales-performance?from=2025-01-01&to=2026-02-01')->assertUnprocessable();
        DB::table('users')->where('id', $admin->id)->update(['timezone' => 'Europe/London']);
        $this->getJson('/admin/employees/'.$member->id.'/sales-performance?from=2026-03-28&to=2026-03-29')->assertOk()->assertJsonPath('previous_from', '2026-03-26')->assertJsonPath('previous_to', '2026-03-27');
    }

    public function test_proposals_are_scoped_and_submission_status_is_local_only(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/proposals', ['title' => 'Draft'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($foreign);
        $foreignLead = $this->postJson('/leads', ['name' => 'Foreign lead'])->assertCreated()->json('id');
        $foreignProposal = $this->postJson('/proposals', ['title' => 'Foreign proposal'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->postJson('/proposals', ['title' => 'Draft', 'lead_id' => $foreignLead])->assertNotFound();
        $lead = $this->postJson('/leads', ['name' => 'Lead'])->assertCreated()->json('id');
        $proposal = $this->postJson('/proposals', ['title' => 'Draft', 'lead_id' => $lead, 'bid' => 100, 'currency' => 'USD', 'proposal_date' => '2026-01-15', 'job_url' => 'https://example.test/job', 'connects_normal' => 5, 'connects_boosted' => 2])->assertCreated()->json('id');
        $this->getJson('/proposals')->assertOk()->assertJsonCount(1, 'data')->assertJsonMissing(['title' => 'Foreign proposal']);
        $this->patchJson('/proposals/'.$foreignProposal, ['title' => 'Hidden', 'status' => 'submitted'])->assertNotFound();
        $this->patchJson('/proposals/'.$proposal, ['title' => 'Draft', 'status' => 'submitted'])->assertOk()->assertJsonPath('message', 'Proposal updated. No external submission was made.');
        $this->assertDatabaseHas('proposals', ['id' => $proposal, 'status' => 'submitted']);
        $this->assertNotNull(DB::table('proposals')->where('id', $proposal)->value('submitted_at'));
        $this->assertDatabaseHas('proposals', ['id' => $proposal, 'connects_normal' => 5, 'connects_boosted' => 2]);
        $this->getJson('/proposals/'.$proposal.'/history')->assertOk()->assertJsonCount(2, 'data');
        $this->assertDatabaseHas('proposal_history', ['proposal_id' => $proposal, 'from_status' => 'draft', 'to_status' => 'submitted']);
        $this->getJson('/proposals/'.$foreignProposal.'/history')->assertNotFound();
        $this->postJson('/proposals', ['title' => 'Bad URL', 'job_url' => 'javascript:alert(1)'])->assertUnprocessable();
        $this->getJson('/admin/dashboard')->assertOk()->assertJsonPath('total_proposals', 1)->assertJsonPath('proposals_submitted_today', 1);
    }

    public function test_client_records_and_lead_links_require_access_and_organization_match(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/clients', ['name' => 'Client'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($foreign);
        $foreignClient = $this->postJson('/clients', ['name' => 'Foreign client'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $client = $this->postJson('/clients', ['name' => 'Local client', 'email' => 'client@example.test'])->assertCreated()->json('id');
        $lead = $this->postJson('/leads', ['name' => 'Local lead'])->assertCreated()->json('id');
        $this->putJson('/leads/'.$lead.'/client', ['client_id' => $foreignClient])->assertNotFound();
        $this->putJson('/leads/'.$lead.'/client', ['client_id' => $client])->assertOk();
        $this->assertDatabaseHas('leads', ['id' => $lead, 'client_id' => $client]);
        $this->putJson('/clients/'.$client.'/archive', ['archived' => true])->assertOk();
        $this->assertDatabaseHas('leads', ['id' => $lead, 'client_id' => $client]);
        $this->getJson('/clients')->assertOk()->assertJsonCount(0, 'data');
        $this->putJson('/leads/'.$lead.'/client', ['client_id' => $client])->assertNotFound();
        $this->putJson('/clients/'.$client.'/archive', ['archived' => false])->assertOk();
        $this->getJson('/clients')->assertOk()->assertJsonCount(1, 'data')->assertJsonMissing(['name' => 'Foreign client']);
        $this->patchJson('/clients/'.$client, ['name' => 'Changed client'])->assertOk();
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'action' => 'client.updated', 'subject_id' => $client]);
        $this->putJson('/leads/'.$lead.'/client', ['client_id' => null])->assertOk();
        $this->assertDatabaseHas('leads', ['id' => $lead, 'client_id' => null]);
        foreach ([['clients', 'view'], ['leads', 'view'], ['leads', 'edit'], ['leads', 'create']] as [$module, $action]) {
            $permission = DB::table('permissions')->where('module', $module)->where('action', $action)->value('id');
            DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'own']);
        }
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/clients')->assertOk()->assertJsonCount(0, 'data');
        $this->putJson('/leads/'.$lead.'/client', ['client_id' => $client])->assertNotFound();
        $ownLead = $this->postJson('/leads', ['name' => 'Own'])->assertCreated()->json('id');
        $this->putJson('/leads/'.$ownLead.'/client', ['client_id' => $client])->assertNotFound();
    }

    public function test_leads_are_created_and_viewed_only_with_scoped_permissions(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org]);
        $peer = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/leads', ['name' => 'Own lead'])->assertForbidden();
        foreach (['create', 'view'] as $action) {
            $permission = DB::table('permissions')->where('module', 'leads')->where('action', $action)->value('id');
            DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'own']);
        }
        $id = $this->postJson('/leads', ['name' => 'Own lead', 'assigned_to' => $peer->id])->assertCreated()->json('id');
        $this->assertDatabaseHas('leads', ['id' => $id, 'organization_id' => $org, 'created_by' => $user->id, 'assigned_to' => $user->id]);
        foreach ([[$org, $peer], [$other, $foreign]] as [$organization, $owner]) {
            DB::table('leads')->insert(['organization_id' => $organization, 'created_by' => $owner->id, 'assigned_to' => $owner->id, 'name' => 'Hidden lead', 'status' => 'new', 'created_at' => now(), 'updated_at' => now()]);
        }
        $this->getJson('/leads')->assertOk()->assertJsonCount(1, 'data')->assertJsonPath('data.0.name', 'Own lead');
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $user->id, 'action' => 'lead.created', 'subject_id' => $id]);
        $edit = DB::table('permissions')->where('module', 'leads')->where('action', 'edit')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $edit, 'allowed' => true, 'scope' => 'own']);
        $payload = ['name' => 'Updated lead', 'status' => 'qualified'];
        $this->patchJson('/leads/'.$id, $payload)->assertOk();
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $user->id, 'action' => 'lead.status_changed', 'subject_id' => $id]);
        $this->assertDatabaseHas('lead_stage_history', ['lead_id' => $id, 'actor_id' => $user->id, 'from_status' => 'new', 'to_status' => 'qualified']);
        $this->getJson('/leads/'.$id.'/stage-history')->assertOk()->assertJsonCount(2, 'data');
        $hiddenId = DB::table('leads')->where('created_by', $peer->id)->value('id');
        $this->patchJson('/leads/'.$hiddenId, $payload)->assertNotFound();
        $this->putJson('/leads/'.$id.'/assignment', ['user_id' => $peer->id])->assertForbidden();
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/leads/'.$id.'/assignment', ['user_id' => $foreign->id])->assertNotFound();
        $this->putJson('/leads/'.$id.'/assignment', ['user_id' => $peer->id])->assertOk();
        $this->assertDatabaseHas('lead_assignment_history', ['lead_id' => $id, 'from_user_id' => $user->id, 'to_user_id' => $peer->id]);
        $this->getJson('/leads/'.$id.'/assignment-history')->assertOk()->assertJsonCount(2, 'data');
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/dashboard')->assertOk()->assertJsonPath('total_leads', 2)->assertJsonPath('leads_added_today', 2);
        $this->getJson('/leads?search=Updated&status=qualified')->assertOk()->assertJsonCount(1, 'data');
        $this->postJson('/leads', ['name' => 'Budget test', 'budget' => 100])->assertUnprocessable();
        $budgetLead = $this->postJson('/leads', ['name' => 'Budget test', 'budget' => 100, 'currency' => 'USD'])->assertCreated()->json('id');
        $this->assertDatabaseHas('leads', ['id' => $budgetLead, 'budget' => 100, 'currency' => 'USD']);
        $this->putJson('/leads/'.$id.'/archive', ['archived' => true])->assertOk();
        $this->getJson('/leads?search=Updated')->assertOk()->assertJsonCount(0, 'data');
        $this->getJson('/leads?search=Updated&archived=yes')->assertOk()->assertJsonCount(1, 'data');
        $this->patchJson('/leads/'.$id, $payload)->assertNotFound();
        $this->putJson('/leads/'.$id.'/archive', ['archived' => false])->assertOk();
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'action' => 'lead.restored', 'subject_id' => $id]);
    }

    public function test_daily_activity_report_respects_permissions_timezone_and_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true, 'timezone' => 'Asia/Karachi']);
        $employee = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        DB::table('audit_logs')->insert([
            ['organization_id' => $org, 'actor_id' => $employee->id, 'action' => 'example.today', 'created_at' => '2026-01-14 20:00:00'],
            ['organization_id' => $org, 'actor_id' => $employee->id, 'action' => 'example.previous', 'created_at' => '2026-01-13 20:00:00'],
            ['organization_id' => $other, 'actor_id' => $foreign->id, 'action' => 'example.foreign', 'created_at' => '2026-01-14 20:00:00'],
        ]);
        $this->withSession(['session_version' => 0])->actingAs($employee)->getJson('/admin/employees/'.$employee->id.'/activity-report?date=2026-01-15')->assertForbidden();
        $this->get('/admin/employees/'.$employee->id.'/activity-report/export?date=2026-01-15')->assertForbidden();
        $this->get('/admin/employees/'.$employee->id.'/activity-report/export/pdf?date=2026-01-15')->assertForbidden();
        $this->get('/admin/employees/'.$employee->id.'/activity-report/export/xlsx?date=2026-01-15')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/employees/'.$foreign->id.'/activity-report?date=2026-01-15')->assertNotFound();
        $this->getJson('/admin/employees/'.$employee->id.'/activity-report?date=2026-01-15')->assertOk()->assertJsonPath('total', 1)->assertJsonPath('previous_day_total', 1)->assertJsonPath('actions.0.action', 'example.today');
        DB::table('audit_logs')->insert(['organization_id' => $org, 'actor_id' => $employee->id, 'action' => '=danger', 'created_at' => '2026-01-14 20:00:00']);
        $csv = $this->get('/admin/employees/'.$employee->id.'/activity-report/export?date=2026-01-15')->assertOk()->streamedContent();
        $this->assertStringContainsString('example.today', $csv);
        $this->assertStringContainsString("'=danger", $csv);
        $this->assertStringNotContainsString('example.foreign', $csv);
        $this->assertStringNotContainsString('example.previous', $csv);
        $pdf = $this->get('/admin/employees/'.$employee->id.'/activity-report/export/pdf?date=2026-01-15')->assertOk()->streamedContent();
        $this->assertStringStartsWith('%PDF-', $pdf);
        $xlsx = $this->get('/admin/employees/'.$employee->id.'/activity-report/export/xlsx?date=2026-01-15')->assertOk()->streamedContent();
        $this->assertStringStartsWith('PK', $xlsx);
        $file = tempnam(sys_get_temp_dir(), 'leadpilot-xlsx-');
        file_put_contents($file, $xlsx);
        try {
            $archive = new \ZipArchive;
            $this->assertTrue($archive->open($file));
            $sheet = $archive->getFromName('xl/worksheets/sheet1.xml');
            $this->assertIsString($sheet);
            $this->assertStringNotContainsString('<f>', $sheet);
            $archive->close();
        } finally {
            unlink($file);
        }
    }

    public function test_employee_targets_require_permission_and_stay_in_the_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        $payload = ['metric' => 'daily_leads', 'period_start' => '2026-01-01', 'period_end' => '2026-01-01', 'target_value' => 5];
        $this->withSession(['session_version' => 0])->actingAs($member)->putJson('/admin/employees/'.$member->id.'/targets', $payload)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/employees/'.$foreign->id.'/targets', $payload)->assertNotFound();
        $this->putJson('/admin/employees/'.$member->id.'/targets', $payload)->assertOk();
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['target_value' => 8]))->assertOk();
        $this->assertDatabaseCount('employee_targets', 1);
        $this->assertDatabaseHas('employee_targets', ['user_id' => $member->id, 'target_value' => 8]);
        $this->assertDatabaseHas('employee_target_history', ['user_id' => $member->id, 'action' => 'created', 'new_value' => 5]);
        $this->assertDatabaseHas('employee_target_history', ['user_id' => $member->id, 'action' => 'updated', 'old_value' => 5, 'new_value' => 8]);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'action' => 'employee.target_saved']);
        $this->getJson('/admin/employees/'.$member->id.'/targets')->assertOk()->assertJsonPath('data.0.user_id', $member->id);
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['metric' => 'revenue']))->assertUnprocessable();
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['target_value' => 1.5]))->assertUnprocessable();
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['period_end' => '2026-01-02']))->assertUnprocessable();
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['metric' => 'weekly_proposals', 'period_end' => '2026-01-02']))->assertUnprocessable();
        $this->putJson('/admin/employees/'.$member->id.'/targets', array_merge($payload, ['metric' => 'monthly_proposals', 'period_end' => '2026-01-30']))->assertUnprocessable();
        $targetId = DB::table('employee_targets')->value('id');
        $view = DB::table('permissions')->where('module', 'analytics')->where('action', 'view')->value('id');
        $manage = DB::table('permissions')->where('module', 'analytics')->where('action', 'manage')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $member->id, 'permission_id' => $view, 'allowed' => true, 'scope' => 'organization']);
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/admin/performance/employees')->assertOk();
        $this->getJson('/admin/employees/'.$member->id.'/targets')->assertOk();
        $this->deleteJson('/admin/employees/'.$member->id.'/targets/'.$targetId)->assertForbidden();
        DB::table('user_permission_overrides')->insert(['user_id' => $member->id, 'permission_id' => $manage, 'allowed' => true, 'scope' => 'organization']);
        $this->deleteJson('/admin/employees/'.$member->id.'/targets/'.$targetId)->assertOk();
        $this->assertDatabaseMissing('employee_targets', ['id' => $targetId]);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $member->id, 'action' => 'employee.target_deleted']);
        $this->assertDatabaseHas('employee_target_history', ['user_id' => $member->id, 'action' => 'deleted', 'old_value' => 8]);
        $this->getJson('/admin/employees/'.$member->id.'/target-history')->assertOk()->assertJsonPath('data.0.action', 'deleted');
        $this->getJson('/admin/employees/'.$foreign->id.'/target-history')->assertNotFound();
    }

    public function test_activity_retention_is_opt_in_and_preserves_security_events(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($user)->putJson('/admin/activity-retention', ['days' => 30])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/activity-retention', ['days' => 29])->assertUnprocessable();
        $this->putJson('/admin/activity-retention', ['days' => 30])->assertOk();
        foreach ([[$org, 'auth.login'], [$org, 'auth.login_failed'], [$other, 'auth.login']] as [$organization, $action]) {
            DB::table('audit_logs')->insert(['organization_id' => $organization, 'action' => $action, 'created_at' => now()->subDays(60)]);
        }
        $this->artisan('leadpilot:prune-activity')->assertSuccessful();
        $this->assertDatabaseMissing('audit_logs', ['organization_id' => $org, 'action' => 'auth.login']);
        $this->assertDatabaseHas('audit_logs', ['organization_id' => $org, 'action' => 'auth.login_failed']);
        $this->assertDatabaseHas('audit_logs', ['organization_id' => $other, 'action' => 'auth.login']);
        $this->assertDatabaseHas('audit_logs', ['organization_id' => $org, 'action' => 'activity.retention_cleanup']);
        $this->putJson('/admin/activity-retention', ['days' => null])->assertOk();
        DB::table('audit_logs')->insert(['organization_id' => $org, 'action' => 'auth.logout', 'created_at' => now()->subDays(60)]);
        $this->artisan('leadpilot:prune-activity')->assertSuccessful();
        $this->assertDatabaseHas('audit_logs', ['organization_id' => $org, 'action' => 'auth.logout']);
    }

    public function test_user_timezone_changes_audit_date_boundaries(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/account/timezone', ['timezone' => 'Bad/Zone'])->assertUnprocessable();
        $this->putJson('/account/timezone', ['timezone' => 'Asia/Karachi'])->assertOk();
        DB::table('audit_logs')->insert(['organization_id' => $org, 'action' => 'timezone.test', 'created_at' => '2026-01-14 20:00:00']);
        $this->getJson('/admin/audit?from=2026-01-15&to=2026-01-15')->assertOk()->assertJsonFragment(['action' => 'timezone.test']);
        $this->getJson('/admin/audit?from=2026-01-14&to=2026-01-14')->assertOk()->assertJsonMissing(['action' => 'timezone.test']);
        DB::table('audit_logs')->where('organization_id', $org)->where('action', 'timezone.test')->update(['actor_id' => $admin->id]);
        $this->getJson('/admin/dashboard?from=2026-01-15&to=2026-01-15')->assertOk()->assertJsonPath('recorded_events_in_range', 1);
        $this->getJson('/admin/dashboard?from=2026-01-14&to=2026-01-14')->assertOk()->assertJsonPath('recorded_events_in_range', 0);
    }

    public function test_dashboard_is_restricted_and_counts_only_the_admins_organization(): void
    {
        $organization = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $organization, 'is_super_admin' => true, 'status' => 'active', 'last_login_at' => now()]);
        $member = User::factory()->create(['organization_id' => $organization, 'status' => 'active']);
        User::factory()->create(['organization_id' => $organization, 'status' => 'suspended']);
        $foreignUser = User::factory()->create(['organization_id' => $other, 'status' => 'active', 'last_login_at' => now()]);

        $this->getJson('/admin/dashboard')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/admin/dashboard')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/dashboard')->assertOk()->assertJsonFragment([
            'total_users' => 3, 'active_users' => 2, 'suspended_users' => 1, 'signed_in_today' => 1,
        ]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $organization, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $foreignTeam = DB::table('teams')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        DB::table('users')->where('id', $member->id)->update(['team_id' => $team]);
        $this->getJson('/admin/dashboard?team_id='.$team)->assertOk()->assertJsonPath('total_users', 1)->assertJsonPath('employees.data.0.id', $member->id);
        $this->getJson('/admin/dashboard?team_id='.$foreignTeam)->assertUnprocessable();
        $this->getJson('/admin/dashboard?user_id='.$member->id)->assertOk()->assertJsonPath('total_users', 1)->assertJsonPath('employees.data.0.id', $member->id);
        $this->getJson('/admin/dashboard?user_id='.$foreignUser->id)->assertUnprocessable();
        DB::table('audit_logs')->insert([
            ['organization_id' => $organization, 'actor_id' => $member->id, 'action' => 'test.event', 'created_at' => '2026-01-15 12:00:00'],
            ['organization_id' => $other, 'actor_id' => $foreignUser->id, 'action' => 'test.foreign', 'created_at' => '2026-01-15 12:00:00'],
        ]);
        $this->getJson('/admin/dashboard?from=2026-01-15&to=2026-01-15&user_id='.$member->id)->assertOk()->assertJsonPath('recorded_events_in_range', 1);
        $this->getJson('/admin/dashboard?from=2026-01-16&to=2026-01-15')->assertUnprocessable();
        $this->getJson('/admin/dashboard/employees/'.$member->id)->assertOk()->assertJsonPath('employee.id', $member->id)->assertJsonPath('recent_activity.0.action', 'test.event');
        $this->getJson('/admin/dashboard/employees/'.$foreignUser->id)->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/admin/dashboard/employees/'.$admin->id)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/audit?from=2026-01-15&to=2026-01-15')->assertOk()->assertJsonFragment(['action' => 'test.event'])->assertJsonMissing(['action' => 'test.foreign']);
        $this->getJson('/admin/audit?from=2026-01-16&to=2026-01-15')->assertUnprocessable();
    }

    public function test_active_user_can_sign_in_and_session_is_authenticated(): void
    {
        $user = User::factory()->create(['password' => 'long-secure-password', 'status' => 'active']);
        $this->postJson('/login', ['email' => $user->email, 'password' => 'long-secure-password'])->assertOk();
        $this->assertAuthenticatedAs($user);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $user->id, 'action' => 'auth.login']);
    }

    public function test_inactive_user_cannot_sign_in(): void
    {
        $user = User::factory()->create(['password' => 'long-secure-password', 'status' => 'suspended']);
        $this->postJson('/login', ['email' => $user->email, 'password' => 'long-secure-password'])->assertUnprocessable();
        $this->assertGuest();
    }

    public function test_suspended_user_loses_existing_session_access(): void
    {
        $user = User::factory()->create(['status' => 'active']);
        $this->withSession(['session_version' => 0])->actingAs($user);
        DB::table('users')->where('id', $user->id)->update(['status' => 'suspended']);
        $this->get('/me')->assertRedirect('/login');
        $this->assertGuest();
    }

    public function test_initial_setup_requires_interactive_terminal(): void
    {
        $this->artisan('leadpilot:setup', ['--no-interaction' => true])->assertFailed();
        $this->assertDatabaseCount('users', 0);
    }

    public function test_admin_can_create_user_and_regular_user_cannot(): void
    {
        $organization = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $organization, 'is_super_admin' => true]);
        $regular = User::factory()->create(['organization_id' => $organization]);
        $this->withSession(['session_version' => 0])->actingAs($regular)->postJson('/admin/users', ['name' => 'New User', 'email' => 'new@example.test'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users', ['name' => 'New User', 'email' => 'new@example.test', 'is_super_admin' => true])->assertCreated();
        $this->assertDatabaseHas('users', ['email' => 'new@example.test', 'is_super_admin' => false, 'status' => 'invited']);
    }

    public function test_last_super_admin_is_protected_and_other_organizations_are_isolated(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $otherOrg = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true, 'status' => 'active']);
        $other = User::factory()->create(['organization_id' => $otherOrg]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$admin->id, ['name' => $admin->name, 'status' => 'suspended'])->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$other->id, ['name' => 'Changed', 'status' => 'suspended'])->assertNotFound();
        $this->assertDatabaseHas('users', ['id' => $admin->id, 'status' => 'active']);
    }

    public function test_invitation_sets_password_once_and_activates_account(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'invited']);
        Notification::fake();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/password-link')->assertOk();
        Notification::assertSentTo($user, ResetPassword::class, function ($notification) use ($user): bool {
            $payload = ['email' => $user->email, 'token' => $notification->token, 'password' => 'new-secure-password', 'password_confirmation' => 'new-secure-password'];
            $this->postJson('/reset-password', $payload)->assertOk();
            $this->postJson('/reset-password', $payload)->assertUnprocessable();

            return true;
        });
        $this->assertDatabaseHas('users', ['id' => $user->id, 'status' => 'active']);
        $this->assertTrue(Hash::check('new-secure-password', $user->fresh()->password));
    }

    public function test_suspended_account_cannot_use_a_previously_issued_password_link(): void
    {
        $user = User::factory()->create(['status' => 'active']);
        $token = Password::createToken($user);
        $user->status = 'suspended';
        $user->save();
        $this->postJson('/reset-password', ['email' => $user->email, 'token' => $token, 'password' => 'new-secure-password', 'password_confirmation' => 'new-secure-password'])->assertUnprocessable();
    }

    public function test_admin_can_update_profile_archive_user_and_revoke_sessions(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        DB::table('sessions')->insert(['id' => 'example-session', 'user_id' => $user->id, 'payload' => '', 'last_activity' => 1]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => 'Updated', 'status' => 'active', 'phone' => '123', 'job_title' => 'Sales'])->assertOk();
        $this->assertDatabaseHas('users', ['id' => $user->id, 'name' => 'Updated', 'phone' => '123', 'job_title' => 'Sales']);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/revoke-sessions')->assertOk();
        $this->assertDatabaseMissing('sessions', ['id' => 'example-session']);
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$admin->id)->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$user->id)->assertOk();
        $this->assertSoftDeleted('users', ['id' => $user->id]);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'subject_id' => $user->id, 'action' => 'user.archived']);
    }

    public function test_non_admin_and_other_organization_cannot_revoke_or_archive_users(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $regular = User::factory()->create(['organization_id' => $org]);
        $target = User::factory()->create(['organization_id' => $other]);
        $this->withSession(['session_version' => 0])->actingAs($regular)->postJson('/admin/users/'.$target->id.'/revoke-sessions')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$target->id.'/revoke-sessions')->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$target->id)->assertNotFound();
    }

    public function test_failed_login_audit_omits_password_and_actor(): void
    {
        $user = User::factory()->create(['status' => 'active']);
        $this->postJson('/login', ['email' => $user->email, 'password' => 'incorrect-secret'])->assertUnprocessable();
        $entry = DB::table('audit_logs')->where('action', 'auth.login_failed')->first();
        $this->assertNotNull($entry);
        $this->assertNull($entry->actor_id);
        $this->assertSame($user->id, $entry->subject_id);
        $this->assertStringNotContainsString('incorrect-secret', json_encode($entry));
    }

    public function test_revoked_session_remains_invalid_even_if_session_record_is_restored(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/revoke-sessions')->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($user)->get('/me')->assertRedirect('/login');
        $this->assertGuest();
    }

    public function test_audit_logs_are_restricted_to_admin_and_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $otherOrg = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $regular = User::factory()->create(['organization_id' => $org]);
        $other = User::factory()->create(['organization_id' => $otherOrg]);
        DB::table('audit_logs')->insert(['organization_id' => $org, 'actor_id' => $admin->id, 'action' => 'local.event', 'created_at' => now()]);
        DB::table('audit_logs')->insert(['organization_id' => $otherOrg, 'actor_id' => $other->id, 'action' => 'foreign.event', 'created_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($regular)->getJson('/admin/audit')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/audit')->assertOk()->assertJsonFragment(['action' => 'local.event'])->assertJsonMissing(['action' => 'foreign.event']);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/audit?user_id='.$other->id)->assertNotFound();
        DB::table('audit_logs')->insert(['organization_id' => $org, 'actor_id' => $admin->id, 'action' => '=danger', 'created_at' => now()]);
        $export = $this->get('/admin/audit/export');
        $export->assertOk()->assertHeader('content-type', 'text/csv; charset=UTF-8');
        $this->assertStringContainsString('local.event', $export->streamedContent());
        $this->assertStringNotContainsString('foreign.event', $export->streamedContent());
        $this->assertStringContainsString("'=danger", $export->streamedContent());
        $this->withSession(['session_version' => 0])->actingAs($regular)->get('/admin/audit/export')->assertForbidden();
    }

    public function test_initial_setup_creates_one_admin_with_a_hashed_password(): void
    {
        $this->artisan('leadpilot:setup')
            ->expectsQuestion('Organization name', 'Example')
            ->expectsQuestion('Administrator full name', 'Owner')
            ->expectsQuestion('Administrator email', 'owner@example.test')
            ->expectsQuestion('Administrator password (at least 12 characters)', 'secure-example-password')
            ->expectsQuestion('Confirm password', 'secure-example-password')
            ->assertSuccessful();
        $user = User::where('email', 'owner@example.test')->firstOrFail();
        $this->assertTrue($user->is_super_admin);
        $this->assertTrue(Hash::check('secure-example-password', $user->password));
        $this->artisan('leadpilot:setup')->assertFailed();
        $this->assertDatabaseCount('users', 1);
    }

    public function test_email_change_revokes_sessions_and_old_password_links(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $oldEmail = $user->email;
        Password::createToken($user);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'email' => 'UPDATED@EXAMPLE.TEST', 'status' => 'active'])->assertOk();
        $this->assertDatabaseHas('users', ['id' => $user->id, 'email' => 'updated@example.test', 'session_version' => 1]);
        $this->assertDatabaseMissing('password_reset_tokens', ['email' => $oldEmail]);
        $this->withSession(['session_version' => 0])->actingAs($user)->get('/me')->assertRedirect('/login');
    }

    public function test_super_admin_role_changes_are_authorized_and_last_admin_is_protected(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true, 'status' => 'active']);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $this->withSession(['session_version' => 0])->actingAs($user)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'is_super_admin' => true])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$admin->id, ['name' => $admin->name, 'status' => 'active', 'is_super_admin' => false])->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'is_super_admin' => true])->assertOk();
        $this->assertDatabaseHas('users', ['id' => $user->id, 'is_super_admin' => true, 'session_version' => 1]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'is_super_admin' => false])->assertOk();
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'subject_id' => $user->id, 'action' => 'user.super_admin_removed']);
    }

    public function test_teams_are_organization_scoped_and_assignment_is_authorized(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $foreignTeam = DB::table('teams')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/admin/teams', ['name' => 'Sales'])->assertForbidden();
        $team = $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/teams', ['name' => 'Sales'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'team_id' => $foreignTeam])->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'team_id' => $team])->assertOk();
        $this->assertDatabaseHas('users', ['id' => $user->id, 'team_id' => $team]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/teams')->assertJsonMissing(['name' => 'Foreign']);
    }

    public function test_profile_photos_are_private_validated_and_organization_scoped(): void
    {
        Storage::fake('local');
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        $bad = UploadedFile::fake()->createWithContent('bad.txt', 'not an image');
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/photo', ['photo' => $bad])->assertUnprocessable();
        $image = UploadedFile::fake()->createWithContent('photo.png', base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='));
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/photo', ['photo' => $image])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($admin)->get('/admin/users/'.$user->id.'/photo')->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($admin)->get('/admin/users/'.$foreign->id.'/photo')->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($user)->get('/admin/users/'.$user->id.'/photo')->assertForbidden();
    }

    public function test_password_links_cannot_be_sent_through_aliased_log_mailer(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'invited']);
        config(['mail.default' => 'custom-log', 'mail.mailers.custom-log.transport' => 'log']);
        Notification::fake();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/password-link')->assertStatus(503);
        Notification::assertNothingSent();
        $this->assertDatabaseMissing('password_reset_tokens', ['email' => $user->email]);
    }

    public function test_login_throttles_repeated_failed_attempts(): void
    {
        $user = User::factory()->create(['status' => 'active', 'password' => 'correct-password-here']);
        foreach (range(1, 5) as $attempt) {
            $this->postJson('/login', ['email' => $user->email, 'password' => 'wrong-password'])->assertUnprocessable();
        }
        $this->postJson('/login', ['email' => $user->email, 'password' => 'correct-password-here'])->assertUnprocessable()->assertJsonValidationErrors('email');
        $this->assertGuest();
    }

    public function test_suspension_records_actor_and_invalidates_password_link(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        Password::createToken($user);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'suspended'])->assertOk();
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'subject_id' => $user->id, 'action' => 'user.status_suspended']);
        $this->assertDatabaseMissing('password_reset_tokens', ['email' => $user->email]);
    }

    public function test_editing_invited_user_does_not_cancel_existing_invitation(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'invited']);
        $token = Password::createToken($user);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => 'Updated name', 'status' => 'invited'])->assertOk();
        $this->postJson('/reset-password', ['email' => $user->email, 'token' => $token, 'password' => 'new-secure-password', 'password_confirmation' => 'new-secure-password'])->assertOk();
        $this->assertDatabaseHas('users', ['id' => $user->id, 'name' => 'Updated name', 'status' => 'active']);
    }

    public function test_roles_are_scoped_and_only_admins_can_assign_them(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $foreign = DB::table('roles')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/admin/roles', ['name' => 'Sales'])->assertForbidden();
        $role = $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/roles', ['name' => 'Sales'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/users/'.$user->id.'/roles', ['role_ids' => [$foreign]])->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/users/'.$user->id.'/roles', ['role_ids' => [$role]])->assertOk();
        $this->assertDatabaseHas('user_roles', ['user_id' => $user->id, 'role_id' => $role]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/users/'.$user->id.'/roles')->assertJsonFragment(['name' => 'Sales']);
    }

    public function test_permission_changes_apply_immediately_and_overrides_deny_access(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $role = DB::table('roles')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $foreignRole = DB::table('roles')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $permission = DB::table('permissions')->where('module', 'leads')->where('action', 'view')->value('id');
        DB::table('user_roles')->insert(['user_id' => $user->id, 'role_id' => $role, 'created_at' => now(), 'updated_at' => now()]);
        $resolver = app(PermissionResolver::class);
        $this->assertSame([], $resolver->scopes($user, 'leads', 'view', $org));
        $payload = ['permissions' => [['id' => $permission, 'scope' => 'own']]];
        $this->withSession(['session_version' => 0])->actingAs($user)->putJson('/admin/roles/'.$role.'/permissions', $payload)->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/roles/'.$foreignRole.'/permissions', $payload)->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/roles/'.$role.'/permissions', $payload)->assertOk();
        $this->assertSame(['own'], $resolver->scopes($user, 'leads', 'view', $org));
        $this->assertSame([], $resolver->scopes($user, 'leads', 'view', $other));
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/users/'.$user->id.'/permissions/'.$permission, ['allowed' => false])->assertOk();
        $this->assertSame([], $resolver->scopes($user, 'leads', 'view', $org));
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/users/'.$user->id.'/permissions/'.$permission, ['allowed' => true, 'scope' => 'team'])->assertOk();
        $this->assertSame(['team'], $resolver->scopes($user, 'leads', 'view', $org));
        $user->status = 'suspended';
        $user->save();
        $this->assertSame([], $resolver->scopes($user, 'leads', 'view', $org));
    }

    public function test_record_scope_never_returns_another_organization(): void
    {
        Schema::create('permission_test_records', function (Blueprint $table): void {
            $table->id();
            $table->unsignedBigInteger('organization_id');
            $table->unsignedBigInteger('created_by')->nullable();
            $table->unsignedBigInteger('assigned_to')->nullable();
            $table->unsignedBigInteger('team_id')->nullable();
        });
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $permission = DB::table('permissions')->where('module', 'leads')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'own']);
        DB::table('permission_test_records')->insert([['organization_id' => $org, 'created_by' => $user->id], ['organization_id' => $other, 'created_by' => $user->id], ['organization_id' => $org, 'created_by' => null]]);
        $unscoped = DB::table('permission_test_records')->where('created_by', $user->id)->orWhere('organization_id', $other);
        $query = app(PermissionResolver::class)->constrain($unscoped, $user, 'leads', 'view', $org);
        $this->assertSame(1, $query->count());
        $this->assertSame($org, $query->first()->organization_id);
    }

    public function test_admin_can_remove_all_role_permissions_and_assignments(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $role = DB::table('roles')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $permission = DB::table('permissions')->where('module', 'leads')->where('action', 'view')->value('id');
        DB::table('role_permissions')->insert(['role_id' => $role, 'permission_id' => $permission, 'scope' => 'own']);
        DB::table('user_roles')->insert(['user_id' => $user->id, 'role_id' => $role, 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/roles/'.$role.'/permissions', ['permissions' => []])->assertOk();
        $this->assertDatabaseMissing('role_permissions', ['role_id' => $role, 'permission_id' => $permission]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/admin/users/'.$user->id.'/roles', ['role_ids' => []])->assertOk();
        $this->assertDatabaseMissing('user_roles', ['user_id' => $user->id, 'role_id' => $role]);
    }

    public function test_individual_override_can_be_viewed_and_removed_only_by_own_organization_admin(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $regular = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        $permission = DB::table('permissions')->where('module', 'leads')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $regular->id, 'permission_id' => $permission, 'allowed' => false]);
        $this->withSession(['session_version' => 0])->actingAs($regular)->getJson('/admin/users/'.$regular->id.'/permissions')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/users/'.$foreign->id.'/permissions')->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$foreign->id.'/permissions/'.$permission)->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/users/'.$regular->id.'/permissions')->assertOk()->assertJsonFragment(['permission_id' => $permission]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$regular->id.'/permissions/'.$permission)->assertOk();
        $this->assertDatabaseMissing('user_permission_overrides', ['user_id' => $regular->id, 'permission_id' => $permission]);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'subject_id' => $regular->id, 'action' => 'user.permission_override_removed']);
    }

    public function test_role_lifecycle_is_scoped_and_cannot_delete_assigned_roles(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $role = DB::table('roles')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $foreign = DB::table('roles')->insertGetId(['organization_id' => $other, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        DB::table('user_roles')->insert(['user_id' => $user->id, 'role_id' => $role, 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->patchJson('/admin/roles/'.$role, ['name' => 'Changed'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/roles/'.$foreign, ['name' => 'Changed'])->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/roles/'.$role)->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/roles/'.$role, ['name' => 'Development'])->assertOk();
        DB::table('user_roles')->where('role_id', $role)->delete();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/roles/'.$role)->assertOk();
        $this->assertDatabaseMissing('roles', ['id' => $role]);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'action' => 'role.deleted', 'subject_id' => $role]);
    }

    public function test_team_changes_are_scoped_and_preserve_membership_history(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $foreign = DB::table('teams')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $member = User::factory()->create(['organization_id' => $org, 'team_id' => $team]);
        $this->withSession(['session_version' => 0])->actingAs($member)->patchJson('/admin/teams/'.$team, ['name' => 'Changed'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/teams/'.$foreign, ['name' => 'Changed'])->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/teams/'.$team)->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/teams/'.$team, ['name' => 'Growth'])->assertOk();
        $member->delete();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/teams/'.$team)->assertUnprocessable();
        $this->assertDatabaseHas('teams', ['id' => $team, 'name' => 'Growth']);
        $this->assertDatabaseHas('audit_logs', ['actor_id' => $admin->id, 'subject_id' => $team, 'action' => 'team.renamed']);
    }

    public function test_audit_access_is_enforced_by_live_organization_permission(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org]);
        $permission = DB::table('permissions')->where('module', 'audit_logs')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'organization']);
        DB::table('audit_logs')->insert(['organization_id' => $org, 'actor_id' => $user->id, 'action' => 'visible.event', 'created_at' => now()]);
        DB::table('audit_logs')->insert(['organization_id' => $other, 'action' => 'foreign.event', 'created_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/audit')->assertOk()->assertJsonFragment(['action' => 'visible.event'])->assertJsonMissing(['action' => 'foreign.event']);
        $this->get('/admin/audit/export')->assertForbidden();
        $exportPermission = DB::table('permissions')->where('module', 'audit_logs')->where('action', 'export')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $exportPermission, 'allowed' => true, 'scope' => 'organization']);
        $export = $this->get('/admin/audit/export?action=visible.event')->assertOk();
        $this->assertStringContainsString('visible.event', $export->streamedContent());
        $this->assertStringNotContainsString('foreign.event', $export->streamedContent());
        DB::table('user_permission_overrides')->where('user_id', $user->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/audit')->assertForbidden();
        $this->get('/admin/audit/export')->assertForbidden();
        DB::table('user_permission_overrides')->where('user_id', $user->id)->where('permission_id', $permission)->update(['allowed' => true, 'scope' => 'own']);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/audit')->assertForbidden();
    }

    public function test_team_permissions_are_enforced_per_action_and_change_immediately(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $foreign = DB::table('teams')->insertGetId(['organization_id' => $other, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $permission = DB::table('permissions')->where('module', 'team_management')->where('action', 'create')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'organization']);
        $team = $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/admin/teams', ['name' => 'Sales'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/teams')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($user)->patchJson('/admin/teams/'.$team, ['name' => 'Changed'])->assertForbidden();
        DB::table('user_permission_overrides')->where('user_id', $user->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/admin/teams', ['name' => 'No access'])->assertForbidden();
        $view = DB::table('permissions')->where('module', 'team_management')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $user->id, 'permission_id' => $view, 'allowed' => true, 'scope' => 'organization']);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/teams')->assertOk()->assertJsonMissing(['id' => $foreign]);
        DB::table('user_permission_overrides')->where('user_id', $user->id)->where('permission_id', $view)->update(['scope' => 'own']);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/admin/teams')->assertForbidden();
    }

    public function test_delegated_user_access_is_scoped_and_cannot_escalate(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $target = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $foreign = User::factory()->create(['organization_id' => $other, 'status' => 'active']);
        foreach (['view', 'create', 'edit'] as $action) {
            $permission = DB::table('permissions')->where('module', 'user_management')->where('action', $action)->value('id');
            DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'organization']);
        }
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users')->assertOk()->assertJsonMissing(['email' => $foreign->email]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users', ['name' => 'New', 'email' => 'new-user@example.test', 'is_super_admin' => true])->assertCreated();
        $this->assertDatabaseHas('users', ['email' => 'new-user@example.test', 'is_super_admin' => false]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$target->id, ['name' => 'Updated', 'status' => 'active'])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$target->id, ['name' => 'Updated', 'status' => 'active', 'is_super_admin' => true])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$target->id, ['name' => 'Updated', 'status' => 'active', 'email' => 'attacker@example.test'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$admin->id, ['name' => 'Changed', 'status' => 'active'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$foreign->id, ['name' => 'Changed', 'status' => 'active'])->assertNotFound();
        $edit = DB::table('permissions')->where('module', 'user_management')->where('action', 'edit')->value('id');
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $edit)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$target->id, ['name' => 'Changed', 'status' => 'active'])->assertForbidden();
    }

    public function test_delegated_manager_can_only_invite_unprivileged_unassigned_accounts(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $newUser = User::factory()->create(['organization_id' => $org, 'status' => 'invited']);
        $activeUser = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $foreignUser = User::factory()->create(['organization_id' => $other, 'status' => 'invited']);
        $role = DB::table('roles')->insertGetId(['organization_id' => $org, 'name' => 'Manager', 'created_at' => now(), 'updated_at' => now()]);
        $privileged = User::factory()->create(['organization_id' => $org, 'status' => 'invited']);
        DB::table('user_roles')->insert(['user_id' => $privileged->id, 'role_id' => $role, 'created_at' => now(), 'updated_at' => now()]);
        $permission = DB::table('permissions')->where('module', 'user_management')->where('action', 'manage')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'organization']);
        Notification::fake();
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$newUser->id.'/password-link')->assertOk();
        Notification::assertSentTo($newUser, ResetPassword::class);
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$activeUser->id.'/password-link')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$privileged->id.'/password-link')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$foreignUser->id.'/password-link')->assertNotFound();
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$newUser->id.'/password-link')->assertForbidden();
    }

    public function test_user_list_team_and_own_scopes_do_not_expose_other_teams_or_organizations(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $second = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $member = User::factory()->create(['organization_id' => $org, 'team_id' => $team]);
        $otherMember = User::factory()->create(['organization_id' => $org, 'team_id' => $second]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        $permission = DB::table('permissions')->where('module', 'user_management')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'team']);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users')->assertOk()->assertJsonFragment(['email' => $member->email])->assertJsonMissing(['email' => $otherMember->email])->assertJsonMissing(['email' => $foreign->email]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users?search='.urlencode($otherMember->email))->assertOk()->assertJsonMissing(['email' => $otherMember->email]);
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $permission)->update(['scope' => 'own']);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users')->assertOk()->assertJsonFragment(['email' => $manager->email])->assertJsonMissing(['email' => $member->email]);
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users')->assertForbidden();
    }

    public function test_team_scoped_edit_cannot_modify_other_teams_or_privileged_fields(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $member = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $outside = User::factory()->create(['organization_id' => $org, 'team_id' => $other, 'status' => 'active']);
        $admin = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active', 'is_super_admin' => true]);
        $permission = DB::table('permissions')->where('module', 'user_management')->where('action', 'edit')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'team']);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$member->id, ['name' => 'Updated', 'status' => 'active'])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$outside->id, ['name' => 'Changed', 'status' => 'active'])->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$admin->id, ['name' => 'Changed', 'status' => 'active'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$member->id, ['name' => 'Changed', 'status' => 'active', 'is_super_admin' => true])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$member->id, ['name' => 'Changed', 'status' => 'active', 'email' => 'x@example.test'])->assertForbidden();
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/users/'.$member->id, ['name' => 'Changed', 'status' => 'active'])->assertForbidden();
    }

    public function test_user_filters_remain_within_authorized_team_and_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $foreignOrg = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $otherTeam = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $foreignTeam = DB::table('teams')->insertGetId(['organization_id' => $foreignOrg, 'name' => 'Foreign', 'created_at' => now(), 'updated_at' => now()]);
        $role = DB::table('roles')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $member = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $outside = User::factory()->create(['organization_id' => $org, 'team_id' => $otherTeam, 'status' => 'active']);
        foreach ([$member, $outside] as $user) {
            DB::table('user_roles')->insert(['user_id' => $user->id, 'role_id' => $role, 'created_at' => now(), 'updated_at' => now()]);
        }
        $permission = DB::table('permissions')->where('module', 'user_management')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'team']);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users?role_id='.$role.'&status=active')->assertOk()->assertJsonFragment(['email' => $member->email])->assertJsonMissing(['email' => $outside->email]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users?team_id='.$otherTeam)->assertOk()->assertJsonMissing(['email' => $outside->email]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users?team_id='.$foreignTeam)->assertUnprocessable();
    }

    public function test_team_changes_preserve_history_and_cannot_delete_previous_team(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $first = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'First', 'created_at' => now(), 'updated_at' => now()]);
        $second = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Second', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org, 'status' => 'active']);
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'team_id' => $first])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'team_id' => (string) $first])->assertOk();
        $this->assertSame(1, DB::table('team_membership_history')->where('user_id', $user->id)->count());
        $this->withSession(['session_version' => 0])->actingAs($admin)->patchJson('/admin/users/'.$user->id, ['name' => $user->name, 'status' => 'active', 'team_id' => $second])->assertOk();
        $this->assertSame(1, DB::table('team_membership_history')->where('user_id', $user->id)->where('team_id', $first)->whereNotNull('ended_at')->count());
        $this->assertSame(1, DB::table('team_membership_history')->where('user_id', $user->id)->where('team_id', $second)->whereNull('ended_at')->count());
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/teams/'.$first)->assertUnprocessable();
        $this->withSession(['session_version' => 0])->actingAs($admin)->deleteJson('/admin/users/'.$user->id)->assertOk();
        $this->assertSame(0, DB::table('team_membership_history')->where('user_id', $user->id)->whereNull('ended_at')->count());
    }

    public function test_team_history_is_authorized_and_organization_scoped(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Sales', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $member = User::factory()->create(['organization_id' => $org]);
        $foreign = User::factory()->create(['organization_id' => $other]);
        DB::table('team_membership_history')->insert(['organization_id' => $org, 'team_id' => $team, 'user_id' => $member->id, 'changed_by' => $admin->id, 'started_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/admin/users/'.$member->id.'/team-history')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/users/'.$foreign->id.'/team-history')->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/users/'.$member->id.'/team-history')->assertOk()->assertJsonFragment(['team_name' => 'Sales']);
    }

    public function test_replacing_profile_photo_keeps_latest_file_and_removes_previous_file(): void
    {
        Storage::fake('local');
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $user = User::factory()->create(['organization_id' => $org]);
        $imageBytes = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=');
        $first = UploadedFile::fake()->createWithContent('first.png', $imageBytes);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/photo', ['photo' => $first])->assertOk();
        $oldPath = $user->fresh()->profile_photo_path;
        Storage::disk('local')->assertExists($oldPath);
        $second = UploadedFile::fake()->createWithContent('second.png', $imageBytes);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/admin/users/'.$user->id.'/photo', ['photo' => $second])->assertOk();
        $newPath = $user->fresh()->profile_photo_path;
        $this->assertNotSame($oldPath, $newPath);
        Storage::disk('local')->assertMissing($oldPath);
        Storage::disk('local')->assertExists($newPath);
    }

    public function test_team_scoped_management_cannot_access_other_teams_or_histories(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'First', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $target = User::factory()->create(['organization_id' => $org, 'team_id' => $other]);
        foreach (['view', 'edit'] as $action) {
            $permission = DB::table('permissions')->where('module', 'team_management')->where('action', $action)->value('id');
            DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'team']);
        }
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/teams')->assertOk()->assertJsonFragment(['name' => 'First'])->assertJsonMissing(['name' => 'Other']);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/teams/'.$team, ['name' => 'Renamed'])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/teams/'.$other, ['name' => 'Changed'])->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($manager)->getJson('/admin/users/'.$target->id.'/team-history')->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/teams', ['name' => 'Extra'])->assertForbidden();
        $permission = DB::table('permissions')->where('module', 'team_management')->where('action', 'edit')->value('id');
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $permission)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->patchJson('/admin/teams/'.$team, ['name' => 'Denied'])->assertForbidden();
    }

    public function test_team_scoped_photo_access_respects_boundaries_and_live_revocation(): void
    {
        Storage::fake('local');
        $org = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $team = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'First', 'created_at' => now(), 'updated_at' => now()]);
        $otherTeam = DB::table('teams')->insertGetId(['organization_id' => $org, 'name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $manager = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'status' => 'active']);
        $member = User::factory()->create(['organization_id' => $org, 'team_id' => $team]);
        $outside = User::factory()->create(['organization_id' => $org, 'team_id' => $otherTeam]);
        $admin = User::factory()->create(['organization_id' => $org, 'team_id' => $team, 'is_super_admin' => true]);
        foreach (['view', 'edit'] as $action) {
            $permission = DB::table('permissions')->where('module', 'user_management')->where('action', $action)->value('id');
            DB::table('user_permission_overrides')->insert(['user_id' => $manager->id, 'permission_id' => $permission, 'allowed' => true, 'scope' => 'team']);
        }
        $bytes = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=');
        $image = UploadedFile::fake()->createWithContent('photo.png', $bytes);
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$member->id.'/photo', ['photo' => $image])->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($manager)->get('/admin/users/'.$member->id.'/photo')->assertOk();
        $this->withSession(['session_version' => 0])->actingAs($manager)->get('/admin/users/'.$outside->id.'/photo')->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($manager)->postJson('/admin/users/'.$admin->id.'/photo', ['photo' => UploadedFile::fake()->createWithContent('photo.png', $bytes)])->assertForbidden();
        $view = DB::table('permissions')->where('module', 'user_management')->where('action', 'view')->value('id');
        DB::table('user_permission_overrides')->where('user_id', $manager->id)->where('permission_id', $view)->update(['allowed' => false, 'scope' => null]);
        $this->withSession(['session_version' => 0])->actingAs($manager)->get('/admin/users/'.$member->id.'/photo')->assertForbidden();
    }
}
