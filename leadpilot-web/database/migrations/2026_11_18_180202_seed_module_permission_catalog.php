<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        $modules = ['dashboard', 'leads', 'sales_pipeline', 'clients', 'upwork_jobs', 'proposals', 'bidding_records', 'follow_ups', 'tasks', 'meetings', 'ai_lead_generation', 'ai_sales_agent', 'analytics', 'reports', 'team_management', 'integrations', 'settings', 'user_management', 'audit_logs'];
        $actions = ['view', 'create', 'edit', 'delete', 'export', 'import', 'assign', 'approve', 'manage'];
        foreach ($modules as $module) {
            foreach ($actions as $action) {
                DB::table('permissions')->insertOrIgnore(['module' => $module, 'action' => $action]);
            }
        }
    }

    public function down(): void {}
};
