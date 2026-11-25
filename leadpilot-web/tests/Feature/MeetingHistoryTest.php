<?php

namespace Tests\Feature;

use App\Models\Meeting;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class MeetingHistoryTest extends TestCase
{
    use RefreshDatabase;

    public function test_guest_cannot_read_meeting_history(): void
    {
        $this->getJson('/meetings/history')->assertUnauthorized();
    }

    public function test_meeting_history_requires_meetings_view_permission(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Meetings workspace', 'created_at' => now(), 'updated_at' => now()]);
        $member = User::factory()->create(['organization_id' => $org, 'is_super_admin' => false]);

        $this->withSession(['session_version' => 0])->actingAs($member)->getJson('/meetings/history')->assertForbidden();
    }

    public function test_meeting_history_is_empty_when_the_user_has_no_past_records(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Meetings workspace', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);

        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/meetings/history')
            ->assertOk()
            ->assertJsonPath('meetings', []);
    }

    public function test_meeting_history_returns_only_the_current_users_past_meetings(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Meetings workspace', 'created_at' => now(), 'updated_at' => now()]);
        $otherOrg = DB::table('organizations')->insertGetId(['name' => 'Other workspace', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $colleague = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $outsider = User::factory()->create(['organization_id' => $otherOrg, 'is_super_admin' => true]);

        Meeting::query()->create([
            'organization_id' => $org,
            'user_id' => $admin->id,
            'provider' => 'zoom',
            'title' => 'Past Zoom review',
            'starts_at' => now()->subDay(),
            'ends_at' => now()->subDay()->addHour(),
            'attendees' => ['Alex'],
            'meeting_url' => 'https://zoom.example.test/j/123',
        ]);
        Meeting::query()->create([
            'organization_id' => $org,
            'user_id' => $admin->id,
            'provider' => 'zoom',
            'title' => 'Upcoming Zoom planning',
            'starts_at' => now()->addDay(),
            'ends_at' => now()->addDay()->addHour(),
        ]);
        Meeting::query()->create([
            'organization_id' => $org,
            'user_id' => $colleague->id,
            'provider' => 'zoom',
            'title' => 'Colleague Zoom',
            'starts_at' => now()->subHours(3),
        ]);
        Meeting::query()->create([
            'organization_id' => $otherOrg,
            'user_id' => $outsider->id,
            'provider' => 'zoom',
            'title' => 'Other org Zoom',
            'starts_at' => now()->subHours(2),
        ]);

        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/meetings/history')
            ->assertOk()
            ->assertJsonCount(1, 'meetings')
            ->assertJsonPath('meetings.0.title', 'Past Zoom review')
            ->assertJsonPath('meetings.0.provider', 'zoom')
            ->assertJsonPath('meetings.0.attendees.0', 'Alex');
    }
}