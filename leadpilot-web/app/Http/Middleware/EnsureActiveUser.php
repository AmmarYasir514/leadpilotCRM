<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Symfony\Component\HttpFoundation\Response;

class EnsureActiveUser
{
    public function handle(Request $request, Closure $next): Response
    {
        $user = $request->user();
        if ($user) {
            $user->refresh();
        }
        if ($user && ($user->status !== 'active' || $user->trashed() || $request->session()->get('session_version') !== $user->session_version)) {
            Auth::logout();
            $request->session()->invalidate();
            $request->session()->regenerateToken();

            return redirect()->route('login');
        }

        if ($user && (! $user->last_activity_at || $user->last_activity_at->lt(now()->subMinutes(5)))) {
            $user->last_activity_at = now();
            $user->save();
        }

        return $next($request);
    }
}
