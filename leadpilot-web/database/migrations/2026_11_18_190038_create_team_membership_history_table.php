<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('team_membership_history', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->foreignId('team_id')->constrained()->restrictOnDelete();
            $table->foreignId('user_id')->constrained()->restrictOnDelete();
            $table->foreignId('changed_by')->nullable()->constrained('users')->restrictOnDelete();
            $table->timestamp('started_at');
            $table->timestamp('ended_at')->nullable();
            $table->index(['user_id', 'ended_at']);
        });
        DB::table('users')->whereNotNull('team_id')->orderBy('id')->chunkById(500, function ($users): void {
            foreach ($users as $user) {
                DB::table('team_membership_history')->insert(['organization_id' => $user->organization_id, 'team_id' => $user->team_id, 'user_id' => $user->id, 'changed_by' => null, 'started_at' => $user->created_at ?? now(), 'ended_at' => $user->deleted_at]);
            }
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('team_membership_history');
    }
};
