<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('follow_up_cycles', function (Blueprint $table) {
            $table->id();
            $table->foreignId('organization_id')->constrained();
            $table->foreignId('lead_id')->constrained()->cascadeOnDelete();
            $table->string('stage')->default('Chat started');
            $table->json('cadence');
            $table->unsignedTinyInteger('completed')->default(0);
            $table->timestamp('anchor_at');
            $table->timestamps();
            $table->unique(['organization_id', 'lead_id']);
        });
        Schema::create('follow_up_events', function (Blueprint $table) {
            $table->id();
            $table->foreignId('organization_id')->constrained();
            $table->foreignId('lead_id')->constrained()->cascadeOnDelete();
            $table->foreignId('actor_id')->nullable()->constrained('users')->nullOnDelete();
            $table->string('action');
            $table->text('note')->nullable();
            $table->timestamp('created_at');
            $table->index(['organization_id', 'lead_id', 'created_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('follow_up_events');
        Schema::dropIfExists('follow_up_cycles');
    }
};
