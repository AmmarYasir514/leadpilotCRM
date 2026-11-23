<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('imported_chat_leads', function (Blueprint $table): void {
            $table->string('sender')->nullable();
            $table->timestamp('activity_at')->nullable();
            $table->unsignedSmallInteger('reminder_hours')->default(24);
        });
    }

    public function down(): void
    {
        Schema::table('imported_chat_leads', function (Blueprint $table): void {
            $table->dropColumn(['sender', 'activity_at', 'reminder_hours']);
        });
    }
};
