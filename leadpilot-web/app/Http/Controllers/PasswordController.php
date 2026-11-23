<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Auth\Events\PasswordReset;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Str;
use Illuminate\Validation\Rules\Password as PasswordRule;

class PasswordController extends Controller
{
    public function send(Request $request, int $id): JsonResponse
    {
        $actor = $request->user();
        abort_unless($actor->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($actor, 'user_management', 'manage', $actor->organization_id), true), 403);
        $mailerName = config('mail.default');
        $transport = config('mail.mailers.'.$mailerName.'.transport');
        if (! in_array($transport, ['smtp', 'ses', 'ses-v2', 'mailgun', 'postmark', 'resend', 'sendmail'], true) && ! (app()->environment('testing') && $transport === 'array')) {
            return response()->json(['message' => 'Configure a secure mail transport before sending password links.'], 503);
        }
        $result = DB::transaction(function () use ($actor, $id): string {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
            abort_unless($current && $current->session_version === $actor->session_version && in_array('organization', app(PermissionResolver::class)->scopes($current, 'user_management', 'manage', $actor->organization_id), true), 403);
            $user = User::where('organization_id', $actor->organization_id)->whereKey($id)->lockForUpdate()->firstOrFail();
            if (! $current->is_super_admin) {
                abort_if($user->is_super_admin || $user->id === $current->id || $user->status !== 'invited' || DB::table('user_roles')->where('user_id', $user->id)->exists(), 403);
            }
            if (! in_array($user->status, ['active', 'invited'], true)) {
                return 'ineligible';
            }
            $result = Password::sendResetLink(['email' => $user->email]);
            if ($result === Password::RESET_LINK_SENT) {
                DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'user.password_link_sent', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);
            }

            return $result;
        });
        if ($result !== Password::RESET_LINK_SENT) {
            return response()->json(['message' => 'Unable to send a link. Check account status or try again later.'], 422);
        }

        return response()->json(['message' => 'Password setup link sent.']);
    }

    public function reset(Request $request): JsonResponse
    {
        $data = $request->validate(['email' => ['required', 'email'], 'token' => ['required', 'string'], 'password' => ['required', 'confirmed', PasswordRule::min(12)]]);
        $result = DB::transaction(function () use ($data): string {
            $user = User::where('email', $data['email'])->lockForUpdate()->first();
            if (! $user || ! in_array($user->status, ['active', 'invited'], true)) {
                return Password::INVALID_TOKEN;
            }

            return Password::reset($data, function (User $user, string $password): void {
                $user->password = $password;
                if ($user->status === 'invited') {
                    $user->status = 'active';
                }
                $user->setRememberToken(Str::random(60));
                $user->session_version++;
                $user->save();
                DB::table('sessions')->where('user_id', $user->id)->delete();
                DB::table('audit_logs')->insert(['organization_id' => $user->organization_id, 'actor_id' => $user->id, 'action' => 'auth.password_reset', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);
                event(new PasswordReset($user));
            });
        });

        return $result === Password::PASSWORD_RESET
            ? response()->json(['message' => 'Password updated.'])
            : response()->json(['message' => 'Invalid or expired password link.'], 422);
    }
}
