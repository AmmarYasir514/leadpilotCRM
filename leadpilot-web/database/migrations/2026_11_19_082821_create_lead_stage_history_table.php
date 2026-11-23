<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::create('lead_stage_history', function (Blueprint $table) {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->foreignId('lead_id')->constrained()->restrictOnDelete();
            $table->foreignId('actor_id')->nullable()->constrained('users')->restrictOnDelete();
            $table->string('from_status', 40)->nullable();
            $table->string('to_status', 40);
            $table->timestamp('created_at');
            $table->index(['organization_id', 'lead_id', 'id']);
        });
        DB::table('leads')->orderBy('id')->chunkById(100, function ($leads): void {
            foreach ($leads as $lead) {
                DB::table('lead_stage_history')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $lead->id, 'actor_id' => null, 'from_status' => null, 'to_status' => $lead->status, 'created_at' => now()]);
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('lead_stage_history');
    }
};
