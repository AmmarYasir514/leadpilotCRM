<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

return new class extends Migration
{
    public function up(): void
    {
        foreach (DB::table('organizations')->pluck('id') as $orgId) {
            foreach (['Admin', 'Sales Manager', 'Business Development Executive', 'Sales Representative', 'Viewer'] as $name) {
                DB::table('roles')->insertOrIgnore(['organization_id' => $orgId, 'name' => $name, 'created_at' => now(), 'updated_at' => now()]);
            }
        }
    }

    public function down(): void {}
};
