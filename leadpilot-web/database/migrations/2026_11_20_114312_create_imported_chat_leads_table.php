<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('imported_chat_leads', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained();
            $table->foreignId('user_id')->constrained();
            $table->foreignId('lead_id')->constrained()->cascadeOnDelete();
            $table->string('room_id');
            $table->text('last_preview')->nullable();
            $table->string('display_time')->nullable();
            $table->timestamps();
            $table->unique(['organization_id', 'user_id', 'room_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('imported_chat_leads');
    }
};
