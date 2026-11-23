<?php

namespace App\Console\Commands;

use App\Models\User;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Validator;
use Illuminate\Validation\Rules\Password;

class SetupSuperAdmin extends Command
{
    protected $signature = 'leadpilot:setup';

    protected $description = 'Create the initial organization and Super Admin interactively';

    public function handle(): int
    {
        if (! $this->input->isInteractive()) {
            $this->error('Interactive setup is required.');

            return self::FAILURE;
        }
        if (DB::table('organizations')->exists() || User::withTrashed()->exists()) {
            $this->error('Setup is already complete or user data exists.');

            return self::FAILURE;
        }
        $organization = $this->ask('Organization name');
        $name = $this->ask('Administrator full name');
        $email = strtolower(trim((string) $this->ask('Administrator email')));
        $password = $this->secret('Administrator password (at least 12 characters)');
        $confirmation = $this->secret('Confirm password');
        $validator = Validator::make(compact('organization', 'name', 'email', 'password', 'confirmation'), [
            'organization' => ['required', 'string', 'max:255'],
            'name' => ['required', 'string', 'max:255'],
            'email' => ['required', 'email', 'max:255', 'unique:users,email'],
            'password' => ['required', 'string', Password::min(12)],
            'confirmation' => ['required', 'same:password'],
        ]);
        if ($validator->fails()) {
            foreach ($validator->errors()->all() as $error) {
                $this->error($error);
            }

            return self::FAILURE;
        }
        DB::transaction(function () use ($organization, $name, $email, $password): void {
            $orgId = DB::table('organizations')->insertGetId(['id' => 1, 'name' => $organization, 'created_at' => now(), 'updated_at' => now()]);
            foreach (['Admin', 'Sales Manager', 'Business Development Executive', 'Sales Representative', 'Viewer'] as $roleName) {
                DB::table('roles')->insert(['organization_id' => $orgId, 'name' => $roleName, 'created_at' => now(), 'updated_at' => now()]);
            }
            $user = new User;
            $user->name = $name;
            $user->email = $email;
            $user->password = $password;
            $user->organization_id = $orgId;
            $user->status = 'active';
            $user->is_super_admin = true;
            $user->save();
            DB::table('audit_logs')->insert(['organization_id' => $orgId, 'actor_id' => $user->id, 'action' => 'setup.completed', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);
        });
        $this->info('Initial Super Admin created.');

        return self::SUCCESS;
    }
}
