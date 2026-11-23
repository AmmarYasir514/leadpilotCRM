<?php

namespace App\Http\Controllers;

use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Illuminate\Support\Str;
use Illuminate\Validation\ValidationException;

class AuthController extends Controller
{
    public function login(Request $request): JsonResponse
    {
        $credentials = $request->validate(['email' => ['required', 'email'], 'password' => ['required', 'string']]);
        $key = Str::transliterate(Str::lower($credentials['email']).'|'.$request->ip());
        if (RateLimiter::tooManyAttempts($key, 5)) {
            throw ValidationException::withMessages(['email' => 'Too many attempts. Try again later.']);
        }
        if (! Auth::attempt(['email' => $credentials['email'], 'password' => $credentials['password'], 'status' => 'active'])) {
            RateLimiter::hit($key, 60);
            $target = User::where('email', $credentials['email'])->first();
            if ($target) {
                DB::table('audit_logs')->insert(['organization_id' => $target->organization_id, 'actor_id' => null, 'action' => 'auth.login_failed', 'subject_type' => 'user', 'subject_id' => $target->id, 'created_at' => now()]);
            }
            throw ValidationException::withMessages(['email' => 'Invalid credentials or inactive account.']);
        }
        RateLimiter::clear($key);
        $request->session()->regenerate();
        $user = $request->user();
        $request->session()->put('session_version', $user->session_version);
        $user->last_login_at = now();
        $user->save();
        DB::table('audit_logs')->insert(['organization_id' => $user->organization_id, 'actor_id' => $user->id, 'action' => 'auth.login', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);

        return response()->json(['user' => $user]);
    }

    public function logout(Request $request): JsonResponse
    {
        $user = $request->user();
        DB::table('audit_logs')->insert(['organization_id' => $user->organization_id, 'actor_id' => $user->id, 'action' => 'auth.logout', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);
        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return response()->json(['message' => 'Signed out']);
    }
}
