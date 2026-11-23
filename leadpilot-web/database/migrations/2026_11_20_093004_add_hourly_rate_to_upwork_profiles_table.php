<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('upwork_profiles', function (Blueprint $table): void {
            $table->string('hourly_rate')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('upwork_profiles', function (Blueprint $table): void {
            $table->dropColumn('hourly_rate');
        });
    }
};
