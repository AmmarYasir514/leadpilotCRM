<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Tests\TestCase;

class UpworkProfileTest extends TestCase
{
    use RefreshDatabase;

    public function test_profile_is_saved_only_for_the_current_user_and_invalid_url_is_rejected(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->getJson('/upwork-profile')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->postJson('/upwork-profile', ['url' => 'https://evil.example/freelancers/a'])->assertUnprocessable();
        $this->postJson('/upwork-profile', ['url' => 'https://www.upwork.com/freelancers/~123', 'title' => 'Developer', 'hourly_rate' => '$10.00/hr', 'job_success' => '100% Job Success'])->assertOk();
        $this->getJson('/upwork-profile')->assertJsonPath('title', 'Developer')->assertJsonPath('hourly_rate', '$10.00/hr');
        $this->postJson('/upwork-profile', ['url' => 'https://www.upwork.com/freelancers/~123', 'title' => 'Designer'])->assertOk();
        $this->assertDatabaseCount('upwork_profiles', 1);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/upwork-profile')->assertExactJson([]);
    }

    public function test_profile_photo_is_private_to_its_owner_and_location_is_saved(): void
    {
        Storage::fake('local');
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->postJson('/upwork-profile', ['url' => 'https://www.upwork.com/freelancers/~123', 'location' => 'Mianwali, Pakistan'])->assertOk();
        $this->postJson('/upwork-profile/photo', ['photo' => UploadedFile::fake()->createWithContent('profile.png', base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/aXcAAAAASUVORK5CYII='))])->assertOk();
        $this->get('/upwork-profile/photo')->assertOk()->assertHeader('cache-control', 'no-store, private');
        $this->getJson('/upwork-profile')->assertJsonPath('location', 'Mianwali, Pakistan');
        $this->withSession(['session_version' => 0])->actingAs($other)->get('/upwork-profile/photo')->assertNotFound();
    }

    public function test_chat_import_creates_one_lead_per_room_and_refreshes_without_overwriting_lead(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $rows = [['url' => 'https://www.upwork.com/ab/messages/rooms/room_123?companyReference=1', 'name' => 'Client', 'text' => 'Hello', 'timestamp' => '10:00 AM']];
        $this->postJson('/chat-leads/import', ['rows' => $rows])->assertOk()->assertJsonPath('created', 1);
        $leadId = DB::table('imported_chat_leads')->value('lead_id');
        $this->putJson('/chat-leads/'.$leadId.'/activity', ['sender' => 'client', 'activity_at' => now()->subHours(25)->toIso8601String(), 'reminder_hours' => 24])->assertOk();
        $this->getJson('/chat-leads')->assertJsonPath('0.activity_status', 'reply_due');
        $this->postJson('/chat-leads/import', ['rows' => $rows])->assertOk();
        $this->getJson('/chat-leads')->assertJsonPath('0.activity_status', 'reply_due');
        $rows[0]['text'] = 'New message';
        $this->postJson('/chat-leads/import', ['rows' => $rows])->assertOk()->assertJsonPath('updated', 1);
        $this->assertDatabaseCount('leads', 1);
        $this->assertDatabaseCount('imported_chat_leads', 1);
        $this->assertDatabaseHas('imported_chat_leads', ['room_id' => 'room_123', 'last_preview' => 'New message']);
        $this->getJson('/chat-leads')->assertOk()->assertJsonFragment(['last_preview' => 'New message'])->assertJsonPath('0.activity_status', 'needs_confirmation');
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/chat-leads')->assertExactJson([]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $rows[0]['url'] = 'https://evil.example/ab/messages/rooms/room_123';
        $this->postJson('/chat-leads/import', ['rows' => $rows])->assertUnprocessable();
    }

    public function test_sales_plan_is_validated_and_scoped_to_the_current_user(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $owner = User::factory()->create(['organization_id' => $org]);
        $other = User::factory()->create(['organization_id' => $org]);
        $this->getJson('/sales-plan')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $this->putJson('/sales-plan', ['lead_target' => 10, 'view_rate' => 0, 'lead_rate' => 60, 'close_rate' => 20])->assertUnprocessable();
        $this->putJson('/sales-plan', ['lead_target' => 10, 'view_rate' => 30, 'lead_rate' => 60, 'close_rate' => 20])->assertOk();
        $this->getJson('/sales-plan')->assertJsonPath('lead_target', 10);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/sales-plan')->assertExactJson([]);
    }
}
