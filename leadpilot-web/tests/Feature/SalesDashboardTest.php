<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class SalesDashboardTest extends TestCase
{
    use RefreshDatabase;

    public function test_admin_sees_only_eligible_due_cycles_and_own_organization(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $otherOrg = DB::table('organizations')->insertGetId(['name' => 'Other', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $otherOrg, 'is_super_admin' => true]);
        $lead = DB::table('leads')->insertGetId(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'name' => 'Example lead', 'status' => 'new', 'created_at' => now(), 'updated_at' => now()]);
        DB::table('follow_up_cycles')->insert(['organization_id' => $org, 'lead_id' => $lead, 'stage' => 'Chat started', 'cadence' => json_encode([24]), 'completed' => 0, 'anchor_at' => now()->subHours(25), 'created_at' => now(), 'updated_at' => now()]);
        $this->getJson('/admin/dashboard/sales-overview')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/admin/dashboard/sales-overview')->assertOk()->assertJsonPath('leads', 0)->assertJsonPath('due_count', 0)->assertDontSee('Example lead');
        $this->withSession(['session_version' => 0])->actingAs($admin)->getJson('/admin/dashboard/sales-overview')->assertOk()->assertJsonPath('leads', 1)->assertJsonPath('due_count', 1)->assertJsonPath('due.0.name', 'Example lead');
        DB::table('follow_up_cycles')->where('lead_id', $lead)->update(['stage' => 'Meeting booked']);
        $this->getJson('/admin/dashboard/sales-overview')->assertJsonPath('due_count', 0);
        $admin->is_super_admin = false;
        $admin->save();
        $this->getJson('/admin/dashboard/sales-overview')->assertForbidden();
    }
}
