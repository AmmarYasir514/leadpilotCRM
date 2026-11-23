<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('proposals', function (Blueprint $table): void {
            $table->text('job_description')->nullable();
            $table->text('writing_instructions')->nullable();
            $table->text('cover_letter')->nullable();
        });
    }

    public function down(): void
    {
        Schema::table('proposals', function (Blueprint $table): void {
            $table->dropColumn(['job_description', 'writing_instructions', 'cover_letter']);
        });
    }
};
