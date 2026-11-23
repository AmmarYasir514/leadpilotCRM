<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Illuminate\Validation\ValidationException;
use Symfony\Component\HttpFoundation\StreamedResponse;

class UpworkProfileController extends Controller
{
    public function show(Request $request): JsonResponse
    {
        abort_unless($request->user()->organization_id, 403);

        return response()->json(DB::table('upwork_profiles')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id)->first());
    }

    public function store(Request $request): JsonResponse
    {
        abort_unless($request->user()->organization_id, 403);
        $data = $request->validate([
            'url' => ['required', 'string', 'max:2048', 'url:https'],
            'location' => ['nullable', 'string', 'max:255'], 'hourly_rate' => ['nullable', 'string', 'max:255'],
            'name' => ['nullable', 'string', 'max:255'], 'title' => ['nullable', 'string', 'max:255'],
            'description' => ['nullable', 'string', 'max:20000'], 'skills' => ['nullable', 'string', 'max:3000'],
            'job_success' => ['nullable', 'string', 'max:255'], 'rating' => ['nullable', 'string', 'max:255'],
            'hours' => ['nullable', 'string', 'max:255'], 'projects' => ['nullable', 'string', 'max:255'], 'earnings' => ['nullable', 'string', 'max:255'],
        ]);
        $parts = parse_url($data['url']);
        if (! in_array(strtolower($parts['host'] ?? ''), ['www.upwork.com', 'upwork.com'], true) || ! preg_match('~^/(?:freelancers/[^/]+|nx/find-work/profile)/?$~i', $parts['path'] ?? '')) {
            throw ValidationException::withMessages(['url' => 'Use an Upwork freelancer profile URL.']);
        }
        $data['url'] = 'https://'.strtolower($parts['host']).$parts['path'];
        $identity = ['organization_id' => $request->user()->organization_id, 'user_id' => $request->user()->id];
        DB::table('upwork_profiles')->updateOrInsert($identity, $data + ['updated_at' => now(), 'created_at' => now()]);

        return response()->json(['message' => 'Profile saved.']);
    }

    public function photo(Request $request): StreamedResponse
    {
        abort_unless($request->user()->organization_id, 403);
        $profile = DB::table('upwork_profiles')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id)->first();
        abort_unless($profile && $profile->photo_path && Storage::disk('local')->exists($profile->photo_path), 404);

        return Storage::disk('local')->response($profile->photo_path, null, ['X-Content-Type-Options' => 'nosniff', 'Cache-Control' => 'private, no-store']);
    }

    public function uploadPhoto(Request $request): JsonResponse
    {
        abort_unless($request->user()->organization_id, 403);
        $request->validate(['photo' => ['required', 'image', 'mimes:jpg,jpeg,png,webp', 'max:2048']]);
        $query = DB::table('upwork_profiles')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id);
        $profile = $query->first();
        abort_unless($profile, 404, 'Save the profile before uploading a photo.');
        $path = $request->file('photo')->store('upwork-profile-photos', 'local');
        if (! $path) {
            abort(500, 'Could not save the photo.');
        }
        try {
            $query->update(['photo_path' => $path, 'updated_at' => now()]);
        } catch (\Throwable $exception) {
            Storage::disk('local')->delete($path);
            throw $exception;
        }
        if ($profile->photo_path) {
            Storage::disk('local')->delete($profile->photo_path);
        }

        return response()->json(['message' => 'Photo saved.']);
    }
}
