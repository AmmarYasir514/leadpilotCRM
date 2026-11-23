<?php

namespace App\Http\Controllers;

use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;

class SalesPlanController extends Controller
{
    public function show(Request $request): JsonResponse
    {
        $user = $request->user();
        abort_unless($user->organization_id, 403);

        return response()->json(DB::table('sales_plans')->where('organization_id', $user->organization_id)->where('user_id', $user->id)->first());
    }

    public function save(Request $request): JsonResponse
    {
        $user = $request->user();
        abort_unless($user->organization_id, 403);
        $data = $request->validate(['lead_target' => ['required', 'integer', 'min:1', 'max:200'], 'view_rate' => ['required', 'integer', 'min:1', 'max:100'], 'lead_rate' => ['required', 'integer', 'min:1', 'max:100'], 'close_rate' => ['required', 'integer', 'min:0', 'max:100']]);
        DB::table('sales_plans')->updateOrInsert(['organization_id' => $user->organization_id, 'user_id' => $user->id], $data + ['updated_at' => now(), 'created_at' => now()]);

        return response()->json(['message' => 'Plan saved.']);
    }
}
