<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('roles', function (Blueprint $table): void {
            $table->id();
            $table->foreignId('organization_id')->constrained()->restrictOnDelete();
            $table->string('name');
            $table->timestamps();
            $table->unique(['organization_id', 'name']);
        });
        Schema::create('permissions', function (Blueprint $table): void {
            $table->id();
            $table->string('module');
            $table->string('action');
            $table->unique(['module', 'action']);
        });
        Schema::create('role_permissions', function (Blueprint $table): void {
            $table->foreignId('role_id')->constrained()->cascadeOnDelete();
            $table->foreignId('permission_id')->constrained()->restrictOnDelete();
            $table->string('scope')->default('own');
            $table->primary(['role_id', 'permission_id']);
        });
        Schema::create('user_roles', function (Blueprint $table): void {
            $table->foreignId('user_id')->constrained()->restrictOnDelete();
            $table->foreignId('role_id')->constrained()->restrictOnDelete();
            $table->timestamps();
            $table->primary(['user_id', 'role_id']);
        });
        Schema::create('user_permission_overrides', function (Blueprint $table): void {
            $table->foreignId('user_id')->constrained()->restrictOnDelete();
            $table->foreignId('permission_id')->constrained()->restrictOnDelete();
            $table->boolean('allowed');
            $table->string('scope')->nullable();
            $table->primary(['user_id', 'permission_id']);
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('user_permission_overrides');
        Schema::dropIfExists('user_roles');
        Schema::dropIfExists('role_permissions');
        Schema::dropIfExists('permissions');
        Schema::dropIfExists('roles');
    }
};
