<?php

namespace Tests\Feature;

use App\Models\User;
use Dompdf\Dompdf;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;
use Tests\TestCase;

class PortfolioProjectTest extends TestCase
{
    use RefreshDatabase;

    private function organization(): int
    {
        return DB::table('organizations')->insertGetId(['name' => 'Example', 'created_at' => now(), 'updated_at' => now()]);
    }

    private function samplePdf(): UploadedFile
    {
        $pdf = new Dompdf;
        $pdf->loadHtml('<html><body><h1>Portfolio project</h1><p>Built a React website for a client.</p></body></html>');
        $pdf->render();

        return UploadedFile::fake()->createWithContent('portfolio.pdf', $pdf->output());
    }

    public function test_pdf_is_extracted_stored_privately_and_scoped_to_its_owner(): void
    {
        Storage::fake('local');
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $otherOrg = $this->organization();
        $outsider = User::factory()->create(['organization_id' => $otherOrg, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $id = $this->postJson('/portfolio-projects', ['name' => 'Acme site', 'skills' => 'React', 'links' => ['https://example.com/project'], 'pdf' => $this->samplePdf()])->assertCreated()->assertJsonPath('has_pdf', true)->json('id');
        $this->getJson('/portfolio-projects')->assertOk()->assertJsonFragment(['name' => 'Acme site'])->assertSee('React website');
        $this->getJson('/portfolio-projects?brief=1')->assertOk()->assertExactJson([['id' => $id, 'name' => 'Acme site']]);
        $path = DB::table('portfolio_projects')->where('id', $id)->value('pdf_path');
        Storage::disk('local')->assertExists($path);
        $this->get('/portfolio-projects/'.$id.'/pdf')->assertOk()->assertHeader('cache-control', 'no-store, private');
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/portfolio-projects')->assertOk()->assertExactJson([]);
        $this->get('/portfolio-projects/'.$id.'/pdf')->assertNotFound();
        $this->deleteJson('/portfolio-projects/'.$id)->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($outsider)->getJson('/portfolio-projects')->assertExactJson([]);
        $this->postJson('/portfolio-projects/'.$id, ['name' => 'Unauthorized change'])->assertNotFound();
        $this->withSession(['session_version' => 0])->actingAs($owner)->deleteJson('/portfolio-projects/'.$id)->assertOk();
        Storage::disk('local')->assertMissing($path);
    }

    public function test_invalid_pdf_and_unauthorized_access_are_rejected(): void
    {
        Storage::fake('local');
        $this->getJson('/portfolio-projects')->assertUnauthorized();
        $org = $this->organization();
        $member = User::factory()->create(['organization_id' => $org]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($member)->postJson('/portfolio-projects', ['name' => 'Project'])->assertForbidden();
        $this->withSession(['session_version' => 0])->actingAs($admin)->postJson('/portfolio-projects', ['name' => 'Project', 'pdf' => UploadedFile::fake()->createWithContent('bad.pdf', 'not a pdf')])->assertUnprocessable()->assertJsonValidationErrors(['pdf']);
        $this->assertDatabaseCount('portfolio_projects', 0);
    }

    public function test_project_edit_can_remove_the_pdf_and_rejects_invalid_links(): void
    {
        Storage::fake('local');
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $id = $this->postJson('/portfolio-projects', ['name' => 'Original', 'pdf' => $this->samplePdf()])->assertCreated()->json('id');
        $path = DB::table('portfolio_projects')->where('id', $id)->value('pdf_path');
        $this->postJson('/portfolio-projects/'.$id, ['name' => 'Renamed', 'links' => ['javascript:alert(1)']])->assertUnprocessable()->assertJsonValidationErrors(['links.0']);
        Storage::disk('local')->assertExists($path);
        $this->postJson('/portfolio-projects/'.$id, ['name' => 'Renamed', 'remove_pdf' => true])->assertOk()->assertJsonPath('name', 'Renamed')->assertJsonPath('has_pdf', false);
        Storage::disk('local')->assertMissing($path);
        $this->get('/portfolio-projects/'.$id.'/pdf')->assertNotFound();
    }

    public function test_selected_pdf_text_is_provided_to_ai_but_not_in_normal_mode(): void
    {
        Storage::fake('local');
        Http::preventStrayRequests();
        Http::fake(['api.openai.com/v1/chat/completions' => Http::response(['choices' => [['message' => ['content' => 'Draft']]]], 200)]);
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        $id = $this->postJson('/portfolio-projects', ['name' => 'Acme PDF', 'pdf' => $this->samplePdf()])->assertCreated()->json('id');
        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'project_ids' => [$id]])->assertOk();
        Http::assertSent(fn ($request) => str_contains($request['messages'][1]['content'], 'Built a React website'));
        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'none', 'project_ids' => [$id]])->assertOk();
        Http::assertSent(fn ($request) => ! str_contains($request['messages'][1]['content'], 'Built a React website'));
    }

    public function test_only_selected_or_named_owner_projects_are_sent_to_ai(): void
    {
        Http::preventStrayRequests();
        Http::fake(['api.openai.com/v1/chat/completions' => Http::response(['choices' => [['message' => ['content' => 'Draft']]]], 200)]);
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        $selected = $this->postJson('/portfolio-projects', ['name' => 'Acme site', 'summary' => 'Built checkout', 'links' => ['https://example.com/acme']])->assertCreated()->json('id');
        $this->postJson('/portfolio-projects', ['name' => 'Private project', 'summary' => 'Secret unrelated context'])->assertCreated();
        $this->postJson('/ai-writer/generate', ['job' => 'Build a store', 'knowledge_mode' => 'portfolio', 'project_ids' => [$selected]])->assertOk();
        Http::assertSent(fn ($request) => str_contains($request['messages'][1]['content'], 'Built checkout') && str_contains($request['messages'][1]['content'], 'https://example.com/acme') && ! str_contains($request['messages'][1]['content'], 'Secret unrelated context'));
        $this->postJson('/ai-writer/generate', ['job' => 'Build a store', 'knowledge_mode' => 'portfolio', 'instructions' => 'Mention Acme site'])->assertOk();
        $this->postJson('/ai-writer/generate', ['job' => 'Build a store', 'knowledge_mode' => 'portfolio'])->assertUnprocessable()->assertJsonValidationErrors(['project_ids']);
        $this->postJson('/ai-writer/generate', ['job' => 'Build a store', 'knowledge_mode' => 'none'])->assertOk();
        Http::assertSent(fn ($request) => ! str_contains($request['messages'][1]['content'], 'Built checkout'));
        $this->withSession(['session_version' => 0])->actingAs($other)->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
        $this->postJson('/ai-writer/generate', ['job' => 'Build a store', 'knowledge_mode' => 'portfolio', 'project_ids' => [$selected]])->assertUnprocessable()->assertJsonValidationErrors(['project_ids']);
    }

    public function test_spreadsheet_import_preview_and_commit_are_private_and_skip_duplicates(): void
    {
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->postJson('/portfolio-projects/import-preview')->assertUnauthorized();
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $csv = UploadedFile::fake()->createWithContent('portfolio.csv', "Project Name,Description,Skills,Link\nWebsite,Built a site,React,https://example.com\n");
        $this->postJson('/portfolio-projects/import-preview', ['file' => $csv])->assertOk()->assertJsonPath('headers.0', 'Project Name')->assertJsonPath('rows.0.1', 'Built a site');
        $projects = [['name' => 'Website', 'summary' => 'Built a site', 'skills' => 'React', 'links' => ['https://example.com']], ['name' => 'website']];
        $this->postJson('/portfolio-projects/import', ['projects' => $projects])->assertOk()->assertJsonPath('added', 1)->assertJsonPath('skipped.0', 'website');
        $this->postJson('/portfolio-projects/import', ['projects' => $projects])->assertOk()->assertJsonPath('added', 0);
        $this->postJson('/portfolio-projects/import', ['projects' => [['name' => 'Bad', 'links' => ['javascript:alert(1)']]]])->assertUnprocessable();
        $other = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($other)->getJson('/portfolio-projects')->assertExactJson([]);
    }

    public function test_xlsx_preview_reads_first_sheet(): void
    {
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $path = tempnam(sys_get_temp_dir(), 'xlsx');
        $writer = new Writer;
        $writer->openToFile($path);
        $writer->addRow(Row::fromValues(['Name', 'Description']));
        $writer->addRow(Row::fromValues(['Store', 'Online shop']));
        $writer->close();
        $file = new UploadedFile($path, 'projects.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', null, true);
        $this->withSession(['session_version' => 0])->actingAs($owner)->postJson('/portfolio-projects/import-preview', ['file' => $file])->assertOk()->assertJsonPath('rows.0.1', 'Online shop');
        unlink($path);
    }
}
