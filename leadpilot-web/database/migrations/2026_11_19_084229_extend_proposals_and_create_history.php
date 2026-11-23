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
        Schema::table('proposals', function (Blueprint $table): void {
            $table->date('proposal_date')->nullable();
            $table->string('job_url', 2048)->nullable();
            $table->unsignedInteger('connects_normal')->default(0);
            $table->unsignedInteger('connects_boosted')->default(0);
        });
        Schema::create('proposal_history', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->foreignId('proposal_id')->constrained()->restrictOnDelete();
            $table->foreignId('actor_id')->nullable()->constrained('users')->restrictOnDelete();
            $table->string('from_status', 40)->nullable();
            $table->string('to_status', 40);
            $table->decimal('old_bid', 14, 2)->nullable();
            $table->decimal('new_bid', 14, 2)->nullable();
            $table->char('old_currency', 3)->nullable();
            $table->char('new_currency', 3)->nullable();
            $table->timestamp('created_at');
            $table->index(['organization_id', 'proposal_id', 'id']);
        });
        DB::table('proposals')->orderBy('id')->chunkById(100, function ($proposals): void {
            foreach ($proposals as $proposal) {
                DB::table('proposal_history')->insert(['organization_id' => $proposal->organization_id, 'proposal_id' => $proposal->id, 'actor_id' => null, 'from_status' => null, 'to_status' => $proposal->status, 'new_bid' => $proposal->bid, 'new_currency' => $proposal->currency, 'created_at' => now()]);
            }
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('proposal_history');
        Schema::table('proposals', fn (Blueprint $table) => $table->dropColumn(['proposal_date', 'job_url', 'connects_normal', 'connects_boosted']));
    }
};
