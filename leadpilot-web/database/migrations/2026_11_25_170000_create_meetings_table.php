<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('meetings', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained();
            $table->foreignId('user_id')->constrained()->cascadeOnDelete();
            $table->string('provider');
            $table->string('title');
            $table->timestamp('starts_at');
            $table->timestamp('ends_at')->nullable();
            $table->json('attendees')->nullable();
            $table->string('meeting_url')->nullable();
            $table->string('external_id')->nullable();
            $table->timestamps();
            $table->index(['organization_id', 'user_id', 'starts_at']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('meetings');
    }
};