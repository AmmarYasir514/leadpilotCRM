<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Tests\TestCase;

class UpworkMcpTest extends TestCase
{
    use RefreshDatabase;

    public function test_failed_send_is_reported_as_unconfirmed_without_retry(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push('', 503)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/upwork/mcp/send-message', ['view' => 'send-message', 'room_id' => 'room_example', 'message' => 'Example', 'confirmed' => true])->assertStatus(502)->assertSee('Check the conversation on Upwork');
        Http::assertSentCount(4);
    }

    public function test_sending_a_message_requires_explicit_confirmation_and_posts_only_once(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['status' => 'success']), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/upwork/mcp/send-message', ['view' => 'send-message', 'room_id' => 'room_example', 'message' => 'Example'])->assertUnprocessable();
        $this->getJson('/upwork/mcp/capabilities?view=send-message&room_id=room_example&message=Example&confirmed=1')->assertForbidden();
        Http::assertNothingSent();
        $this->postJson('/upwork/mcp/send-message', ['view' => 'send-message', 'room_id' => 'room_example', 'message' => 'Example', 'confirmed' => true])->assertOk();
        Http::assertSentCount(4);
        Http::assertSent(fn ($request) => data_get($request->data(), 'params.name') === 'upwork__send_message' && data_get($request->data(), 'params.arguments.params.message') === 'Example');
    }

    public function test_profile_sync_is_private_encrypted_and_removed_on_disconnect(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['data' => ['personalData' => ['firstName' => 'Example', 'title' => 'Designer'], 'skills' => []]]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/upwork/mcp/saved-profile')->assertOk()->assertJsonPath('profile.title', 'Designer');
        $this->assertStringNotContainsString('Designer', DB::table('upwork_mcp_snapshots')->value('profile'));
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/upwork/mcp/saved-profile')->assertJsonPath('profile', null);
        $this->withSession(['session_version' => 0])->actingAs($user)->deleteJson('/upwork/mcp/connection')->assertOk();
        $this->assertDatabaseCount('upwork_mcp_snapshots', 0);
    }

    public function test_submitted_proposals_show_view_status_from_upwork(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['data' => ['vendorProposals' => ['edges' => [['node' => ['id' => 'example', 'jobPosting' => ['title' => 'Example project'], 'viewedByClient' => true, 'private_field' => 'do not expose']]], 'pageInfo' => ['endCursor' => 'next']]], 'hasMore' => true]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/upwork/mcp/capabilities?view=proposals&proposal_status=Offered')->assertOk()->assertJsonPath('items.0.viewedByClient', true)->assertJsonPath('next_cursor', 'next')->assertDontSee('do not expose');
        Http::assertSent(fn ($request) => data_get($request->data(), 'params.name') === 'upwork__list_freelancer_proposals' && data_get($request->data(), 'params.arguments.params.status') === 'Offered');
        $this->getJson('/upwork/mcp/capabilities?view=proposals&proposal_status=Invalid')->assertUnprocessable();
        $this->assertDatabaseCount('proposals', 0);
    }

    public function test_sender_check_rejects_a_changed_conversation(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['data' => ['roomStories' => ['edges' => [['node' => ['id' => 'new-message', 'from_side' => 'client']]]]]]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/upwork/mcp/capabilities?view=conversation-detail&room_id=room_1&message_id=old-message')->assertStatus(409);
    }

    public function test_live_conversations_do_not_guess_that_another_sender_is_the_client(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['data' => ['rooms' => [['id' => 'room_1', 'last_message_from_self' => false, 'latestStory' => ['message' => 'Example']]]], 'hasMore' => true, 'next_cursor' => 'next']), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/upwork/mcp/capabilities?view=conversations')->assertOk()->assertJsonPath('items.0.last_message_side', null)->assertJsonPath('items.0.awaiting_reply_from', null)->assertJsonPath('next_cursor', 'next');
        $this->assertDatabaseCount('leads', 0);
    }

    public function test_live_jobs_are_limited_to_safe_fields_and_not_persisted(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['jobs' => [['title' => 'Example job', 'client' => ['secret' => 'private'], 'budget' => '$50']], 'hasMore' => true]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/upwork/mcp/capabilities?view=jobs')->assertOk()->assertJsonPath('items.0.title', 'Example job')->assertJsonPath('has_more', true)->assertDontSee('private')->assertHeader('Cache-Control', 'no-store, private');
        $this->assertDatabaseCount('leads', 0);
    }

    public function test_job_detail_returns_only_full_description_and_validates_job_id(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['data' => ['marketplaceJobPosting' => ['content' => ['description' => 'Complete job description'], 'client' => 'private client']]]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->getJson('/upwork/mcp/capabilities?view=job-detail&job_id=invalid')->assertUnprocessable();
        Http::assertNothingSent();
        $this->getJson('/upwork/mcp/capabilities?view=job-detail&job_id=~022123395077369691146')->assertOk()->assertJsonPath('description', 'Complete job description')->assertDontSee('private client');
        Http::assertSent(fn ($request) => data_get($request->data(), 'params.name') === 'upwork__find_jobs' && data_get($request->data(), 'params.arguments.action') === 'get');
    }

    public function test_jobs_feed_selects_recent_mode_and_rejects_unknown_modes(): void
    {
        Http::preventStrayRequests();
        $wrap = fn (array $value) => ['result' => ['content' => [['type' => 'text', 'text' => json_encode($value)]]]];
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => []], 200)->push('', 202)->push($wrap(['accounts' => [['role' => 'TALENT', 'org_uid' => 'freelancer']]]), 200)->push($wrap(['jobs' => []]), 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->getJson('/upwork/mcp/capabilities?view=jobs&mode=invalid')->assertUnprocessable();
        Http::assertNothingSent();
        $this->getJson('/upwork/mcp/capabilities?view=jobs&mode=most_recent')->assertOk();
        Http::assertSent(fn ($request) => data_get($request->data(), 'params.name') === 'upwork__find_jobs' && data_get($request->data(), 'params.arguments.params.mode') === 'most_recent');
    }

    public function test_capabilities_are_checked_with_the_current_users_connection(): void
    {
        Http::preventStrayRequests();
        Http::fake(['mcp.upwork.com/mcp' => Http::sequence()->push(['result' => ['protocolVersion' => '2025-03-26']], 200, ['Mcp-Session-Id' => 'session'])->push('', 202)->push("event: message\ndata: {\"jsonrpc\":\"2.0\",\"id\":2,\"result\":{\"tools\":[{\"name\":\"upwork__find_jobs\"}]}}\n\n", 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        DB::table('upwork_mcp_connections')->insert(['organization_id' => $org, 'user_id' => $user->id, 'client_id' => Crypt::encryptString('client'), 'access_token' => Crypt::encryptString('secret'), 'created_at' => now(), 'updated_at' => now()]);
        $this->getJson('/upwork/mcp/capabilities')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/upwork/mcp/capabilities')->assertStatus(422);
        $this->withSession(['session_version' => 0])->actingAs($user)->getJson('/upwork/mcp/capabilities')->assertOk()->assertJsonPath('tools.0', 'upwork__find_jobs')->assertDontSee('secret');
    }

    public function test_authorization_requires_valid_session_and_encrypts_user_connection(): void
    {
        config(['app.url' => 'https://leadpilot.example']);
        Http::preventStrayRequests();
        Http::fake(['www.upwork.com/register' => Http::response(['client_id' => 'example-client'], 201), 'www.upwork.com/api/v3/oauth2/token' => Http::response(['access_token' => 'private-access', 'refresh_token' => 'private-refresh', 'expires_in' => 3600], 200)]);
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->getJson('/upwork/mcp/status')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->get('/upwork/mcp/connect')->assertRedirect();
        $session = session('upwork_mcp_oauth');
        $this->assertNotEmpty($session['state']);
        $this->get('/upwork/mcp/callback?state=invalid&code=example')->assertForbidden();
        $this->get('/upwork/mcp/connect')->assertRedirect();
        $session = session('upwork_mcp_oauth');
        $this->get('/upwork/mcp/callback?state='.$session['state'].'&code=example')->assertRedirect('/?upwork_mcp=connected');
        $stored = DB::table('upwork_mcp_connections')->first();
        $this->assertNotEquals('private-access', $stored->access_token);
        $this->getJson('/upwork/mcp/status')->assertJsonPath('connected', true);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/upwork/mcp/status')->assertJsonPath('connected', false);
    }
}
