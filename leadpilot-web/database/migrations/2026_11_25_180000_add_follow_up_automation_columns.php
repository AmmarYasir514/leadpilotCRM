<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('follow_up_cycles', function (Blueprint $table): void {
            $table->timestamp('next_due_at')->nullable();
            $table->timestamp('reminded_at')->nullable();
            $table->index('next_due_at');
        });
        Schema::table('leads', function (Blueprint $table): void {
            $table->string('import_key', 100)->nullable();
            $table->unique(['organization_id', 'import_key']);
        });
    }

    public function down(): void
    {
        Schema::table('leads', function (Blueprint $table): void {
            $table->dropUnique(['organization_id', 'import_key']);
            $table->dropColumn('import_key');
        });
        Schema::table('follow_up_cycles', function (Blueprint $table): void {
            $table->dropIndex(['next_due_at']);
            $table->dropColumn(['next_due_at', 'reminded_at']);
        });
    }
};
