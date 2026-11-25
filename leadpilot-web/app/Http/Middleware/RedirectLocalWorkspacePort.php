<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class RedirectLocalWorkspacePort
{
    /**
     * Handle an incoming request.
     *
     * @param  Closure(Request): (Response)  $next
     */
    public function handle(Request $request, Closure $next): Response
    {
        if (in_array($request->getHost(), ['127.0.0.1', 'localhost'], true) && $request->getPort() === 8000) {
            return redirect()->to('http://127.0.0.1:8137'.$request->getRequestUri(), 307);
        }

        return $next($request);
    }
}
