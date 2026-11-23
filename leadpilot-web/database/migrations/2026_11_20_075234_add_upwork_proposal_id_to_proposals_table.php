<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('proposals', function (Blueprint $table) {
            $table->string('upwork_proposal_id', 40)->nullable();
            $table->unique(['organization_id', 'created_by', 'upwork_proposal_id'], 'proposals_upwork_owner_unique');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('proposals', function (Blueprint $table) {
            $table->dropUnique('proposals_upwork_owner_unique');
            $table->dropColumn('upwork_proposal_id');
        });
    }
};
