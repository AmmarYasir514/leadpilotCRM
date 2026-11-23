<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    /**
     * Run the migrations.
     */
    public function up(): void
    {
        Schema::table('organizations', function (Blueprint $table): void {
            $table->unsignedInteger('activity_retention_days')->nullable();
        });
        Schema::table('users', function (Blueprint $table): void {
            $table->string('timezone', 64)->default('UTC');
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('users', fn (Blueprint $table) => $table->dropColumn('timezone'));
        Schema::table('organizations', fn (Blueprint $table) => $table->dropColumn('activity_retention_days'));
    }
};
