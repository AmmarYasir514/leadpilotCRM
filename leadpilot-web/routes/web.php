<?php

use App\Authorization\PermissionResolver;
use App\Http\Controllers\AccessControlController;
use App\Http\Controllers\AiWriterController;
use App\Http\Controllers\AuditController;
use App\Http\Controllers\AuthController;
use App\Http\Controllers\ChatLeadImportController;
use App\Http\Controllers\ClientController;
use App\Http\Controllers\DashboardController;
use App\Http\Controllers\DealController;
use App\Http\Controllers\EmployeeActivityReportController;
use App\Http\Controllers\EmployeeTargetController;
use App\Http\Controllers\FollowUpCycleController;
use App\Http\Controllers\GoogleCalendarController;
use App\Http\Controllers\LeadController;
use App\Http\Controllers\MeetingHistoryController;
use App\Http\Controllers\PasswordController;
use App\Http\Controllers\PortfolioProjectController;
use App\Http\Controllers\ProfilePhotoController;
use App\Http\Controllers\ProposalController;
use App\Http\Controllers\ProposalImportController;
use App\Http\Controllers\SalesPerformanceController;
use App\Http\Controllers\SalesPlanController;
use App\Http\Controllers\TeamController;
use App\Http\Controllers\UpworkMcpController;
use App\Http\Controllers\UpworkProfileController;
use App\Http\Controllers\UserManagementController;
use App\Http\Middleware\EnsureActiveUser;
use App\Models\User;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Route;

Route::get('/', fn () => view('app'));
Route::get('/login', fn () => response()->json(['message' => 'Authentication required'], 401))->name('login');
Route::get('/reset-password/{token}', fn () => view('app'))->name('password.reset');
Route::post('/reset-password', [PasswordController::class, 'reset'])->middleware('throttle:5,1');
Route::post('/login', [AuthController::class, 'login'])->name('login.store');
Route::middleware(['auth', EnsureActiveUser::class])->group(function (): void {
    Route::get('/ai-writer/settings', [AiWriterController::class, 'show']);
    Route::put('/ai-writer/settings', [AiWriterController::class, 'update']);
    Route::post('/ai-writer/job-summary', [AiWriterController::class, 'jobSummary'])->middleware('throttle:10,1');
    Route::post('/ai-writer/job-match', [AiWriterController::class, 'jobMatch'])->middleware('throttle:10,1');
    Route::post('/ai-writer/generate', [AiWriterController::class, 'generate'])->middleware('throttle:10,1');
    Route::post('/ai-writer/transcribe', [AiWriterController::class, 'transcribe'])->middleware('throttle:10,1');
    Route::get('/upwork/mcp/status', [UpworkMcpController::class, 'status']);
    Route::get('/upwork/mcp/capabilities', [UpworkMcpController::class, 'capabilities'])->middleware('throttle:10,1');
    Route::post('/upwork/mcp/send-message', [UpworkMcpController::class, 'capabilities'])->middleware('throttle:10,1');
    Route::get('/upwork/mcp/saved-profile', [UpworkMcpController::class, 'savedProfile']);
    Route::post('/upwork/mcp/saved-profile', [UpworkMcpController::class, 'syncProfile'])->middleware('throttle:10,1');
    Route::delete('/upwork/mcp/saved-profile', [UpworkMcpController::class, 'deleteProfile']);
    Route::get('/upwork/mcp/connect', [UpworkMcpController::class, 'connect']);
    Route::get('/upwork/mcp/callback', [UpworkMcpController::class, 'callback']);
    Route::delete('/upwork/mcp/connection', [UpworkMcpController::class, 'disconnect']);
    Route::get('/upwork-profile/photo', [UpworkProfileController::class, 'photo']);
    Route::post('/upwork-profile/photo', [UpworkProfileController::class, 'uploadPhoto'])->middleware('throttle:20,1');
    Route::get('/upwork-profile', [UpworkProfileController::class, 'show']);
    Route::post('/upwork-profile', [UpworkProfileController::class, 'store'])->middleware('throttle:20,1');
    Route::get('/upwork/job-preferences', [UpworkMcpController::class, 'jobPreferences']);
    Route::put('/upwork/job-preferences', [UpworkMcpController::class, 'saveJobPreferences'])->middleware('throttle:20,1');
    Route::get('/portfolio-projects', [PortfolioProjectController::class, 'index']);
    Route::post('/portfolio-projects', [PortfolioProjectController::class, 'store'])->middleware('throttle:20,1');
    Route::post('/portfolio-projects/import-preview', [PortfolioProjectController::class, 'previewImport'])->middleware('throttle:20,1');
    Route::post('/portfolio-projects/import', [PortfolioProjectController::class, 'import'])->middleware('throttle:20,1');
    Route::post('/portfolio-projects/{id}', [PortfolioProjectController::class, 'update'])->middleware('throttle:20,1');
    Route::delete('/portfolio-projects/{id}', [PortfolioProjectController::class, 'destroy']);
    Route::get('/portfolio-projects/{id}/pdf', [PortfolioProjectController::class, 'pdf']);
    Route::put('/calendar/configuration', [GoogleCalendarController::class, 'configure']);
    Route::get('/calendar/status', [GoogleCalendarController::class, 'status']);
    Route::get('/calendar/connect', [GoogleCalendarController::class, 'connect']);
    Route::get('/calendar/callback', [GoogleCalendarController::class, 'callback']);
    Route::get('/calendar/events', [GoogleCalendarController::class, 'events']);
    Route::post('/calendar/events', [GoogleCalendarController::class, 'createEvent']);
    Route::delete('/calendar/connection', [GoogleCalendarController::class, 'disconnect']);
    Route::get('/meetings/history', [MeetingHistoryController::class, 'index']);
    Route::get('/deals', [DealController::class, 'index']);
    Route::post('/deals', [DealController::class, 'store']);
    Route::post('/deals/closed', [DealController::class, 'storeClosed']);
    Route::patch('/deals/{id}', [DealController::class, 'update']);
    Route::get('/clients', [ClientController::class, 'index']);
    Route::post('/clients', [ClientController::class, 'store']);
    Route::patch('/clients/{id}', [ClientController::class, 'update']);
    Route::put('/clients/{id}/archive', [ClientController::class, 'archive']);
    Route::post('/proposals/import', [ProposalImportController::class, 'store']);
    Route::post('/proposals/import-submitted', [ProposalImportController::class, 'storeSubmitted']);
    Route::post('/proposals/refresh-views', [ProposalImportController::class, 'refreshViews']);
    Route::get('/proposals', [ProposalController::class, 'index']);
    Route::post('/proposals', [ProposalController::class, 'store']);
    Route::patch('/proposals/{id}', [ProposalController::class, 'update']);
    Route::get('/proposals/{id}/history', [ProposalController::class, 'history']);
    Route::get('/follow-up-preferences', [FollowUpCycleController::class, 'showPreference']);
    Route::put('/follow-up-preferences', [FollowUpCycleController::class, 'updatePreference']);
    Route::put('/chat-leads/{leadId}/activity', [ChatLeadImportController::class, 'confirm'])->middleware('throttle:20,1');
    Route::get('/sales-plan', [SalesPlanController::class, 'show']);
    Route::put('/sales-plan', [SalesPlanController::class, 'save'])->middleware('throttle:20,1');
    Route::get('/chat-leads', [ChatLeadImportController::class, 'index']);
    Route::post('/chat-leads/import', [ChatLeadImportController::class, 'store'])->middleware('throttle:10,1');
    Route::get('/follow-up-cycles', [FollowUpCycleController::class, 'queue']);
    Route::get('/leads/{id}/follow-up-cycle', [FollowUpCycleController::class, 'show']);
    Route::put('/leads/{id}/follow-up-cycle', [FollowUpCycleController::class, 'save']);
    Route::get('/leads', [LeadController::class, 'index']);
    Route::post('/leads', [LeadController::class, 'store']);
    Route::get('/leads/assignees', [LeadController::class, 'assignees']);
    Route::patch('/leads/{id}', [LeadController::class, 'update']);
    Route::put('/leads/{id}/archive', [LeadController::class, 'archive']);
    Route::put('/leads/{id}/assignment', [LeadController::class, 'assign']);
    Route::get('/leads/{id}/assignment-history', [LeadController::class, 'history']);
    Route::get('/leads/{id}/stage-history', [LeadController::class, 'stageHistory']);
    Route::put('/leads/{id}/client', [LeadController::class, 'client']);
    Route::put('/account/timezone', function (Request $request) {
        $data = $request->validate(['timezone' => ['required', 'timezone']]);
        $user = $request->user();
        $user->timezone = $data['timezone'];
        $user->save();

        return response()->json(['timezone' => $user->timezone]);
    });
    Route::get('/account/preferences', function (Request $request) {
        return response()->json(['admin_theme' => $request->user()->admin_theme])->header('Cache-Control', 'no-store');
    });
    Route::put('/account/preferences', function (Request $request) {
        $data = $request->validate(['admin_theme' => ['sometimes', 'in:light,dark']]);
        abort_if($data === [], 422, 'Choose an account preference to update.');
        $user = $request->user();
        if (array_key_exists('admin_theme', $data)) {
            $user->admin_theme = $data['admin_theme'];
        }
        $user->save();

        return response()->json(['admin_theme' => $user->admin_theme])->header('Cache-Control', 'no-store');
    })->middleware('throttle:20,1');
    Route::get('/admin/activity-retention', function (Request $request) {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);

        return response()->json(['days' => DB::table('organizations')->where('id', $actor->organization_id)->value('activity_retention_days')]);
    });
    Route::put('/admin/activity-retention', function (Request $request) {
        $actor = $request->user();
        abort_unless($actor->is_super_admin && $actor->organization_id, 403);
        $data = $request->validate(['days' => ['present', 'nullable', 'integer', 'min:30', 'max:3650']]);
        DB::transaction(function () use ($actor, $data): void {
            DB::table('organizations')->where('id', $actor->organization_id)->lockForUpdate()->first();
            $current = User::whereKey($actor->id)->where('organization_id', $actor->organization_id)->lockForUpdate()->first();
            abort_unless($current && $current->is_super_admin && $current->status === 'active' && $current->session_version === $actor->session_version, 403);
            DB::table('organizations')->where('id', $actor->organization_id)->update(['activity_retention_days' => $data['days']]);
            DB::table('audit_logs')->insert(['organization_id' => $actor->organization_id, 'actor_id' => $actor->id, 'action' => 'activity.retention_updated', 'subject_type' => 'organization', 'subject_id' => $actor->organization_id, 'created_at' => now()]);
        });

        return response()->json(['days' => $data['days']]);
    });
    Route::get('/admin/dashboard', [DashboardController::class, 'index']);
    Route::get('/admin/dashboard/sales-overview', [DashboardController::class, 'salesOverview']);
    Route::get('/admin/dashboard/employees/{id}', [DashboardController::class, 'employee']);
    Route::get('/admin/performance/employees', [EmployeeTargetController::class, 'employees']);
    Route::get('/admin/sales-report/overview', [SalesPerformanceController::class, 'overview']);
    Route::get('/admin/employees/{userId}/activity-report', [EmployeeActivityReportController::class, 'show']);
    Route::get('/admin/employees/{userId}/activity-report/export', [EmployeeActivityReportController::class, 'export']);
    Route::get('/admin/employees/{userId}/activity-report/export/{format}', [EmployeeActivityReportController::class, 'document']);
    Route::get('/admin/employees/{userId}/sales-performance', [SalesPerformanceController::class, 'show']);
    Route::get('/admin/employees/{userId}/sales-performance/export/{format}', [SalesPerformanceController::class, 'export']);
    Route::get('/admin/employees/{userId}/targets', [EmployeeTargetController::class, 'index']);
    Route::get('/admin/employees/{userId}/target-history', [EmployeeTargetController::class, 'history']);
    Route::put('/admin/employees/{userId}/targets', [EmployeeTargetController::class, 'store']);
    Route::delete('/admin/employees/{userId}/targets/{targetId}', [EmployeeTargetController::class, 'destroy']);
    Route::get('/admin/users/{id}/photo', [ProfilePhotoController::class, 'show']);
    Route::post('/admin/users/{id}/photo', [ProfilePhotoController::class, 'store']);
    Route::post('/admin/users/{id}/password-link', [PasswordController::class, 'send'])->middleware('throttle:5,1');
    Route::post('/admin/users/{id}/revoke-sessions', [UserManagementController::class, 'revokeSessions']);
    Route::delete('/admin/users/{id}', [UserManagementController::class, 'archive']);
    Route::get('/admin/permissions', [AccessControlController::class, 'permissions']);
    Route::get('/admin/roles/{roleId}/permissions', [AccessControlController::class, 'rolePermissions']);
    Route::put('/admin/roles/{roleId}/permissions', [AccessControlController::class, 'replaceRolePermissions']);
    Route::get('/admin/users/{userId}/permissions', [AccessControlController::class, 'userOverrides']);
    Route::delete('/admin/users/{userId}/permissions/{permissionId}', [AccessControlController::class, 'removeOverride']);
    Route::put('/admin/users/{userId}/permissions/{permissionId}', [AccessControlController::class, 'setOverride']);
    Route::get('/admin/roles', [AccessControlController::class, 'roles']);
    Route::patch('/admin/roles/{roleId}', [AccessControlController::class, 'renameRole']);
    Route::delete('/admin/roles/{roleId}', [AccessControlController::class, 'deleteRole']);
    Route::post('/admin/roles', [AccessControlController::class, 'storeRole']);
    Route::get('/admin/users/{userId}/roles', [AccessControlController::class, 'userRoles']);
    Route::put('/admin/users/{userId}/roles', [AccessControlController::class, 'assign']);
    Route::get('/admin/users/{userId}/team-history', [TeamController::class, 'history']);
    Route::get('/admin/teams', [TeamController::class, 'index']);
    Route::patch('/admin/teams/{id}', [TeamController::class, 'update']);
    Route::delete('/admin/teams/{id}', [TeamController::class, 'destroy']);
    Route::post('/admin/teams', [TeamController::class, 'store']);
    Route::get('/admin/audit', [AuditController::class, 'index']);
    Route::get('/admin/audit/export', [AuditController::class, 'export']);
    Route::get('/admin/users', [UserManagementController::class, 'index']);
    Route::post('/admin/users', [UserManagementController::class, 'store']);
    Route::patch('/admin/users/{id}', [UserManagementController::class, 'update']);
    Route::post('/logout', [AuthController::class, 'logout'])->name('logout');
    Route::get('/me', function (Request $request) {
        $user = $request->user();
        $actions = [];
        foreach (['view', 'create', 'edit', 'delete'] as $action) {
            $teamScopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'team_management', $action, $user->organization_id) : [];
            $actions[$action] = in_array('organization', $teamScopes, true) || (in_array($action, ['view', 'edit'], true) && $user->team_id && in_array('team', $teamScopes, true));
        }

        $userActions = [];
        foreach (['view', 'create', 'edit', 'delete', 'manage'] as $action) {
            $scopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'user_management', $action, $user->organization_id) : [];
            $userActions[$action] = match ($action) {
                'view' => (bool) array_intersect($scopes, ['own', 'team', 'organization']),
                'edit' => in_array('organization', $scopes, true) || ($user->team_id && in_array('team', $scopes, true)),
                default => in_array('organization', $scopes, true),
            };
        }

        $editScopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'user_management', 'edit', $user->organization_id) : [];

        $performance = [];
        foreach (['view', 'manage'] as $action) {
            $performance[$action] = $user->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($user, 'analytics', $action, $user->organization_id), true);
        }
        $leadPermissions = [];
        foreach (['view', 'create', 'edit', 'delete'] as $action) {
            $scopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'leads', $action, $user->organization_id) : [];
            $leadPermissions[$action] = (bool) array_intersect($scopes, ['own', 'assigned', 'organization']) || (bool) ($user->team_id && in_array('team', $scopes, true));
        }
        $leadPermissions['assign'] = $user->organization_id && in_array('organization', app(PermissionResolver::class)->scopes($user, 'leads', 'assign', $user->organization_id), true);
        $clientPermissions = [];
        foreach (['view', 'create', 'edit', 'delete'] as $action) {
            $scopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'clients', $action, $user->organization_id) : [];
            $clientPermissions[$action] = (bool) array_intersect($scopes, ['own', 'assigned', 'organization']) || (bool) ($user->team_id && in_array('team', $scopes, true));
        }
        $proposalPermissions = [];
        foreach (['view', 'create', 'edit', 'import'] as $action) {
            $scopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'proposals', $action, $user->organization_id) : [];
            $proposalPermissions[$action] = (bool) array_intersect($scopes, ['own', 'assigned', 'organization']) || (bool) ($user->team_id && in_array('team', $scopes, true));
        }
        $dealPermissions = [];
        foreach (['view', 'create', 'edit'] as $action) {
            $scopes = $user->organization_id ? app(PermissionResolver::class)->scopes($user, 'sales_pipeline', $action, $user->organization_id) : [];
            $dealPermissions[$action] = (bool) array_intersect($scopes, ['own', 'assigned', 'organization']) || (bool) ($user->team_id && in_array('team', $scopes, true));
        }

        return response()->json(['user' => $user, 'team_permissions' => $actions, 'user_permissions' => $userActions, 'user_edit_organization' => in_array('organization', $editScopes, true), 'performance_permissions' => $performance, 'lead_permissions' => $leadPermissions, 'client_permissions' => $clientPermissions, 'proposal_permissions' => $proposalPermissions, 'deal_permissions' => $dealPermissions]);
    })->name('me');
});
