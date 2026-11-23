<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('upwork_profiles', function (Blueprint $table): void {
            $table->string('location')->nullable();
            $table->string('photo_path')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('upwork_profiles', function (Blueprint $table): void {
            $table->dropColumn(['location', 'photo_path']);
        });
    }
};
