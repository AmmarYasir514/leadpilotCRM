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
        Schema::create('lead_assignment_history', function (Blueprint $table) {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->foreignId('lead_id')->constrained()->restrictOnDelete();
            $table->foreignId('from_user_id')->nullable()->constrained('users')->restrictOnDelete();
            $table->foreignId('to_user_id')->constrained('users')->restrictOnDelete();
            $table->foreignId('actor_id')->constrained('users')->restrictOnDelete();
            $table->timestamp('created_at');
            $table->index(['organization_id', 'lead_id', 'id']);
        });
        DB::table('leads')->orderBy('id')->chunkById(100, function ($leads): void {
            foreach ($leads as $lead) {
                DB::table('lead_assignment_history')->insert(['organization_id' => $lead->organization_id, 'lead_id' => $lead->id, 'from_user_id' => null, 'to_user_id' => $lead->assigned_to, 'actor_id' => $lead->created_by, 'created_at' => $lead->created_at]);
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('lead_assignment_history');
    }
};
