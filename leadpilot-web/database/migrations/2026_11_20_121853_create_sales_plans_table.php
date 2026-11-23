<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('sales_plans', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained();
            $table->foreignId('user_id')->constrained();
            $table->unsignedSmallInteger('lead_target');
            $table->unsignedTinyInteger('view_rate');
            $table->unsignedTinyInteger('lead_rate');
            $table->unsignedTinyInteger('close_rate');
            $table->timestamps();
            $table->unique(['organization_id', 'user_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('sales_plans');
    }
};
