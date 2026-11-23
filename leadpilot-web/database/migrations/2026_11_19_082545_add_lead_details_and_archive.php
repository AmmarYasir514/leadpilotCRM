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
        Schema::table('leads', function (Blueprint $table): void {
            $table->date('lead_date')->nullable();
            $table->decimal('budget', 14, 2)->nullable();
            $table->char('currency', 3)->nullable();
            $table->timestamp('archived_at')->nullable();
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::table('leads', fn (Blueprint $table) => $table->dropColumn(['lead_date', 'budget', 'currency', 'archived_at']));
    }
};
