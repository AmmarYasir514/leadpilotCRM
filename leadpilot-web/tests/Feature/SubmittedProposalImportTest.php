<?php

namespace Tests\Feature;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class SubmittedProposalImportTest extends TestCase
{
    use RefreshDatabase;

    public function test_authorized_import_saves_once_with_proposal_text_and_history(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $payload = ['upwork_proposal_id' => '2122734205657980929', 'title' => 'Example job', 'job_description' => 'Build a site', 'cover_letter' => 'I can help.', 'notes' => 'Budget: $500'];
        $id = $this->postJson('/proposals/import-submitted', $payload)->assertCreated()->assertJsonPath('created', true)->json('id');
        $this->postJson('/proposals/import-submitted', $payload)->assertOk()->assertJsonPath('created', false)->assertJsonPath('id', $id);
        $this->assertDatabaseCount('proposals', 1);
        $this->assertDatabaseHas('proposals', ['id' => $id, 'status' => 'submitted', 'cover_letter' => 'I can help.', 'job_description' => 'Build a site']);
        $this->assertNull(DB::table('proposals')->where('id', $id)->value('submitted_at'));
        $this->assertDatabaseHas('proposal_history', ['proposal_id' => $id, 'to_status' => 'submitted']);
    }

    public function test_submitted_list_excludes_drafts_and_preserves_imported_records(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $this->postJson('/proposals', ['title' => 'Unsubmitted draft'])->assertCreated();
        $this->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '12345', 'title' => 'Submitted job', 'cover_letter' => 'Example'])->assertCreated();
        $this->getJson('/proposals?submitted_only=1')->assertOk()->assertJsonCount(1, 'data')->assertJsonPath('data.0.title', 'Submitted job');
        $this->getJson('/proposals')->assertOk()->assertJsonCount(2, 'data');
        $this->getJson('/proposals?drafts_only=1')->assertOk()->assertJsonCount(1, 'data')->assertJsonPath('data.0.title', 'Unsubmitted draft');
    }

    public function test_import_requires_permission_and_complete_fields(): void
    {
        $this->postJson('/proposals/import-submitted', [])->assertUnauthorized();
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $member = User::factory()->create(['organization_id' => $org]);
        $payload = ['upwork_proposal_id' => '12345', 'title' => 'Example', 'cover_letter' => 'Proposal'];
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/proposals/import-submitted', $payload)->assertForbidden();
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/proposals/import-submitted', ['upwork_proposal_id' => 'bad'])->assertUnprocessable()->assertJsonValidationErrors(['upwork_proposal_id', 'title', 'cover_letter']);
        $this->assertDatabaseCount('proposals', 0);
    }

    public function test_different_organizations_can_import_the_same_external_id_without_sharing_data(): void
    {
        $one = DB::table('organizations')->insertGetId(['name' => 'One', 'created_at' => now(), 'updated_at' => now()]);
        $two = DB::table('organizations')->insertGetId(['name' => 'Two', 'created_at' => now(), 'updated_at' => now()]);
        $first = User::factory()->create(['organization_id' => $one, 'is_super_admin' => true]);
        $second = User::factory()->create(['organization_id' => $two, 'is_super_admin' => true]);
        $payload = ['upwork_proposal_id' => '12345', 'title' => 'Example', 'cover_letter' => 'First'];
        $firstId = $this->withSession(['session_version' => 0])->actingAs($first)->postJson('/proposals/import-submitted', $payload)->assertCreated()->json('id');
        $payload['cover_letter'] = 'Second';
        $secondId = $this->withSession(['session_version' => 0])->actingAs($second)->postJson('/proposals/import-submitted', $payload)->assertCreated()->json('id');
        $this->assertNotSame($firstId, $secondId);
        $this->assertDatabaseHas('proposals', ['id' => $firstId, 'organization_id' => $one, 'cover_letter' => 'First']);
        $this->assertDatabaseHas('proposals', ['id' => $secondId, 'organization_id' => $two, 'cover_letter' => 'Second']);
    }

    public function test_import_updates_only_an_unambiguous_matching_draft_and_preserves_its_job_data(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $url = 'https://www.upwork.com/jobs/example_~022123395077369691146/';
        $draft = $this->postJson('/proposals', ['title' => 'Saved job', 'job_url' => $url, 'job_description' => 'Original complete description', 'notes' => 'Budget: $500'])->assertCreated()->json('id');
        $this->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '12345', 'title' => 'Saved job', 'job_url' => $url, 'cover_letter' => 'Actual submitted text'])->assertCreated()->assertJsonPath('id', $draft);
        $this->assertDatabaseCount('proposals', 1);
        $this->assertDatabaseHas('proposals', ['id' => $draft, 'status' => 'submitted', 'cover_letter' => 'Actual submitted text', 'job_description' => 'Original complete description', 'notes' => 'Budget: $500']);
    }

    public function test_import_does_not_guess_when_multiple_drafts_match(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $url = 'https://www.upwork.com/jobs/example_~022123395077369691146/';
        $this->postJson('/proposals', ['title' => 'First draft', 'job_url' => $url])->assertCreated();
        $this->postJson('/proposals', ['title' => 'Second draft', 'job_url' => $url])->assertCreated();
        $this->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '12345', 'title' => 'Example', 'job_url' => $url, 'cover_letter' => 'Text'])->assertStatus(409);
        $this->assertDatabaseCount('proposals', 2);
        $this->assertSame(2, DB::table('proposals')->where('status', 'draft')->count());
    }

    public function test_refresh_marks_only_owned_matching_submitted_proposals_viewed_without_regression(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $first = $this->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '101', 'title' => 'First', 'cover_letter' => 'Text'])->assertCreated()->json('id');
        $advanced = $this->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '102', 'title' => 'Second', 'cover_letter' => 'Text'])->assertCreated()->json('id');
        $this->patchJson('/proposals/'.$advanced, ['title' => 'Second', 'status' => 'responded'])->assertOk();
        $foreign = $this->withSession(['session_version' => 0])->actingAs($other)->postJson('/proposals/import-submitted', ['upwork_proposal_id' => '103', 'title' => 'Other', 'cover_letter' => 'Text'])->assertCreated()->json('id');
        $this->withSession(['session_version' => 0])->actingAs($user)->postJson('/proposals/refresh-views', ['ids' => ['101', '102', '103', '999']])->assertOk()->assertJsonPath('updated', 1)->assertJsonPath('matched', 2)->assertJsonPath('unmatched', 2);
        $this->assertDatabaseHas('proposals', ['id' => $first, 'status' => 'viewed']);
        $this->assertDatabaseHas('proposals', ['id' => $advanced, 'status' => 'responded']);
        $this->assertDatabaseHas('proposals', ['id' => $foreign, 'status' => 'submitted']);
        $this->assertDatabaseHas('proposal_history', ['proposal_id' => $first, 'from_status' => 'submitted', 'to_status' => 'viewed']);
        $this->postJson('/proposals/refresh-views', ['ids' => ['101']])->assertOk()->assertJsonPath('updated', 0);
    }

    public function test_view_refresh_requires_authentication_permission_and_valid_ids(): void
    {
        $this->postJson('/proposals/refresh-views', ['ids' => []])->assertUnauthorized();
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $member = User::factory()->create(['organization_id' => $org]);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/proposals/refresh-views', ['ids' => ['101']])->assertForbidden();
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/proposals/refresh-views', ['ids' => ['not-an-id']])->assertUnprocessable()->assertJsonValidationErrors(['ids.0']);
    }

    public function test_view_refresh_matches_older_records_only_with_unique_title_and_date(): void
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
        $user = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($user);
        $first = $this->postJson('/proposals', ['title' => 'Website design', 'proposal_date' => '2026-11-19'])->assertCreated()->json('id');
        $this->patchJson('/proposals/'.$first, ['title' => 'Website design', 'status' => 'submitted'])->assertOk();
        foreach ([1, 2] as $unused) {
            $id = $this->postJson('/proposals', ['title' => 'Duplicate title', 'proposal_date' => '2026-11-19'])->assertCreated()->json('id');
            $this->patchJson('/proposals/'.$id, ['title' => 'Duplicate title', 'status' => 'submitted'])->assertOk();
        }
        $this->postJson('/proposals/refresh-views', ['ids' => ['101', '102'], 'matches' => [
            ['id' => '101', 'title' => 'website design', 'proposal_date' => '2026-11-19'],
            ['id' => '102', 'title' => 'Duplicate title', 'proposal_date' => '2026-11-19'],
        ]])->assertOk()->assertJsonPath('updated', 1)->assertJsonPath('unmatched', 1);
        $this->assertDatabaseHas('proposals', ['id' => $first, 'status' => 'viewed', 'upwork_proposal_id' => '101']);
        $this->assertSame(2, DB::table('proposals')->where('title', 'Duplicate title')->where('status', 'submitted')->count());
    }
}
