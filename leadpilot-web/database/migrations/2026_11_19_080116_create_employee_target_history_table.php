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
        Schema::create('employee_target_history', function (Blueprint $table) {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->foreignId('user_id')->constrained()->restrictOnDelete();
            $table->foreignId('actor_id')->constrained('users')->restrictOnDelete();
            $table->string('action', 16);
            $table->string('metric', 40);
            $table->date('period_start');
            $table->date('period_end');
            $table->decimal('old_value', 14, 2)->nullable();
            $table->decimal('new_value', 14, 2)->nullable();
            $table->char('old_currency', 3)->nullable();
            $table->char('new_currency', 3)->nullable();
            $table->timestamp('created_at');
            $table->index(['organization_id', 'user_id', 'id']);
        });
    }

    /**
     * Reverse the migrations.
     */
    public function down(): void
    {
        Schema::dropIfExists('employee_target_history');
    }
};
