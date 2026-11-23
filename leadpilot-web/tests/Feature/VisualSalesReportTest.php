<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class VisualSalesReportTest extends TestCase
{
    use RefreshDatabase;

    public function test_employee_report_uses_recorded_proposal_events_and_connects(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $proposal = DB::table('proposals')->insertGetId(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'title' => 'Example', 'status' => 'viewed', 'submitted_at' => '2026-11-01 10:00:00', 'connects_normal' => 4, 'connects_boosted' => 3, 'created_at' => now(), 'updated_at' => now()]);
        DB::table('proposal_history')->insert(['organization_id' => $org, 'proposal_id' => $proposal, 'actor_id' => $admin->id, 'from_status' => 'submitted', 'to_status' => 'viewed', 'created_at' => '2026-11-02 10:00:00']);
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/employees/'.$admin->id.'/sales-performance?from=2026-11-01&to=2026-11-30')->assertOk()->assertJsonPath('recorded_viewed_count', 1)->assertJsonPath('recorded_connects_used', 7)->assertJsonPath('recorded_view_rate', 100);
    }

    public function test_employee_pdf_is_generated_and_access_is_restricted(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $otherOrg = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $otherOrg, 'is_super_admin' => true]);
        $path = '/admin/employees/'.$admin->id.'/sales-performance/export/pdf?from=2026-11-01&to=2026-11-30';
        $this->getJson($path)->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($other)->get($path)->assertNotFound();
        $response = $this->withSession(['session_version' => 0])->actingAs($admin)->get($path)->assertOk()->assertHeader('Content-Type', 'application/pdf');
        $this->assertStringStartsWith('%PDF-', $response->streamedContent());
    }

    public function test_report_filters_dates_timezone_and_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $other = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true, 'timezone' => 'Asia/Karachi']);
        $otherUser = User::factory()->create(['organization_id' => $other, 'is_super_admin' => true]);
        $lead = DB::table('leads')->insertGetId(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'name' => 'Lead', 'status' => 'new', 'created_at' => '2026-10-31 20:00:00', 'updated_at' => now()]);
        DB::table('leads')->insert(['organization_id' => $other, 'created_by' => $otherUser->id, 'assigned_to' => $otherUser->id, 'name' => 'Other', 'status' => 'new', 'created_at' => '2026-11-01 04:00:00', 'updated_at' => now()]);
        DB::table('follow_up_events')->insert(['organization_id' => $org, 'lead_id' => $lead, 'actor_id' => $admin->id, 'action' => 'sent', 'created_at' => '2026-11-01 05:00:00']);
        DB::table('proposals')->insert(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'title' => 'Proposal', 'status' => 'submitted', 'submitted_at' => '2026-11-01 05:00:00', 'created_at' => now(), 'updated_at' => now()]);
        $this->getJson('/admin/sales-report/overview?from=2026-11-01&to=2026-11-01')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/sales-report/overview?from=2026-11-01&to=2026-11-01')->assertOk()->assertJsonPath('leads', 1)->assertJsonPath('proposals', 1)->assertJsonPath('followups', 1)->assertJsonPath('daily.0.date', '2026-11-01');
        $this->getJson('/admin/sales-report/overview?from=2024-01-01&to=2026-01-01')->assertUnprocessable();
        $admin->is_super_admin = false;
        $admin->save();
        $this->getJson('/admin/sales-report/overview?from=2026-11-01&to=2026-11-01')->assertForbidden();
    }
}
