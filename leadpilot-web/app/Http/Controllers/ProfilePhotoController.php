<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use App\Models\User;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\HttpFoundation\StreamedResponse;

class ProfilePhotoController extends Controller
{
    private function target(User $actor, int $id, string $action, bool $lock = false): User
    {
        $scopes = $actor->organization_id ? app(PermissionResolver::class)->scopes($actor, 'user_management', $action, $actor->organization_id) : [];
        $allowedScopes = $action === 'view' ? ['organization', 'team', 'own'] : ['organization', 'team'];
        abort_unless(array_intersect($scopes, $allowedScopes), 403);
        $query = User::where('organization_id', $actor->organization_id)->whereKey($id);
        if (! in_array('organization', $scopes, true)) {
            $query->where(function ($query) use ($actor, $scopes, $action): void {
                $query->whereRaw('1 = 0');
                if ($actor->team_id && in_array('team', $scopes, true)) {
                    $query->orWhere('team_id', $actor->team_id);
                }
                if ($action === 'view' && in_array('own', $scopes, true)) {
                    $query->orWhere('id', $actor->id);
                }
            });
        }
        if ($lock) {
            $query->lockForUpdate();
        }
        $target = $query->firstOrFail();
        abort_if($action === 'edit' && ! $actor->is_super_admin && ($target->is_super_admin || $target->id === $actor->id), 403);

        return $target;
    }

    public function show(Request $request, int $id): StreamedResponse
    {
        $user = $this->target($request->user(), $id, 'view');
        abort_unless($user->profile_photo_path && Storage::disk('local')->exists($user->profile_photo_path), 404);

        return Storage::disk('local')->response($user->profile_photo_path, null, ['X-Content-Type-Options' => 'nosniff', 'Cache-Control' => 'private, no-store']);
    }

    public function store(Request $request, int $id): JsonResponse
    {
        $user = $this->target($request->user(), $id, 'edit');
        $request->validate(['photo' => ['required', 'image', 'mimes:jpg,jpeg,png,webp', 'max:2048']]);
        $path = $request->file('photo')->store('profile-photos', 'local');
        if (! $path) {
            abort(500, 'Could not save photo.');
        }
        try {
            $oldPath = DB::transaction(function () use ($request, $user, $path): ?string {
                $actor = $request->user();
                DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
                $current = User::where('organization_id', $actor->organization_id)->whereKey($actor->id)->lockForUpdate()->first();
                abort_unless($current && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
                $user = $this->target($current, $user->id, 'edit', true);
                $oldPath = $user->profile_photo_path;
                $user->profile_photo_path = $path;
                $user->save();
                DB::table('audit_logs')->insert(['organization_id' => $user->organization_id, 'actor_id' => $request->user()->id, 'action' => 'user.photo_updated', 'subject_type' => 'user', 'subject_id' => $user->id, 'created_at' => now()]);

                return $oldPath;
            });
        } catch (\Throwable $exception) {
            Storage::disk('local')->delete($path);
            throw $exception;
        }
        if ($oldPath) {
            Storage::disk('local')->delete($oldPath);
        }

        return response()->json(['message' => 'Photo updated.']);
    }
}
