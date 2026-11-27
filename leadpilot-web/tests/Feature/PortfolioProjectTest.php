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

    private function pdfFromPages(string $filename, array $pageTexts): UploadedFile
    {
        return UploadedFile::fake()->createWithContent($filename, $this->buildSimplePdf($pageTexts));
    }

    private function buildSimplePdf(array $pageTexts): string
    {
        if ($pageTexts === []) {
            $pageTexts = [''];
        }

        $pageCount = count($pageTexts);
        $pageIds = range(3, 2 + $pageCount);
        $contentIds = range(3 + $pageCount, 2 + (2 * $pageCount));
        $fontId = 3 + (2 * $pageCount);
        $objects = [];
        $objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
        $kids = implode(' ', array_map(fn ($id) => $id.' 0 R', $pageIds));
        $objects[2] = '<< /Type /Pages /Kids ['.$kids.'] /Count '.$pageCount.' >>';

        foreach ($pageTexts as $index => $text) {
            $pageId = $pageIds[$index];
            $contentId = $contentIds[$index];
            $objects[$pageId] = '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents '.$contentId.' 0 R /Resources << /Font << /F1 '.$fontId.' 0 R >> >> >>';
            $stream = $this->pageContentStream((string) $text);
            $objects[$contentId] = '<< /Length '.strlen($stream)." >>\nstream\n".$stream."\nendstream";
        }

        $objects[$fontId] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>';
        $out = "%PDF-1.4\n";
        $offsets = [0];
        $maxId = max(array_keys($objects));
        for ($id = 1; $id <= $maxId; $id++) {
            $offsets[$id] = strlen($out);
            $out .= $id." 0 obj\n".$objects[$id]."\nendobj\n";
        }
        $xref = strlen($out);
        $out .= "xref\n0 ".($maxId + 1)."\n0000000000 65535 f \n";
        for ($id = 1; $id <= $maxId; $id++) {
            $out .= sprintf("%010d 00000 n \n", $offsets[$id]);
        }

        return $out.'trailer << /Root 1 0 R /Size '.($maxId + 1)." >>\nstartxref\n".$xref."\n%%EOF\n";
    }

    private function pageContentStream(string $text): string
    {
        $ops = "BT /F1 11 Tf 36 750 Td\n";
        $chunks = $text === '' ? [''] : str_split($text, 80);
        foreach ($chunks as $index => $chunk) {
            $safe = str_replace(['\\', '(', ')'], ['\\\\', '\\(', '\\)'], $chunk);
            if ($index > 0) {
                $ops .= "0 -12 Td\n";
            }
            $ops .= '('.$safe.") Tj\n";
        }

        return $ops.'ET';
    }

    private function imageOnlyPdf(): UploadedFile
    {
        // Minimal image-only PDF (1x1 grayscale XObject, no text operators) so this
        // does not depend on the PHP GD extension that Dompdf needs to embed images.
        $image = "<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\nX\nendstream";
        $pageStream = "q 100 0 0 100 100 600 cm /Im1 Do Q";
        $objects = [
            1 => '<< /Type /Catalog /Pages 2 0 R >>',
            2 => '<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
            3 => '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /XObject << /Im1 4 0 R >> >> /Contents 5 0 R >>',
            4 => $image,
            5 => '<< /Length '.strlen($pageStream)." >>\nstream\n".$pageStream."\nendstream",
        ];
        $out = "%PDF-1.4\n";
        $offsets = [0];
        for ($id = 1; $id <= 5; $id++) {
            $offsets[$id] = strlen($out);
            $out .= $id." 0 obj\n".$objects[$id]."\nendobj\n";
        }
        $xref = strlen($out);
        $out .= "xref\n0 6\n0000000000 65535 f \n";
        for ($id = 1; $id <= 5; $id++) {
            $out .= sprintf("%010d 00000 n \n", $offsets[$id]);
        }

        return UploadedFile::fake()->createWithContent('scanned.pdf', $out."trailer << /Root 1 0 R /Size 6 >>\nstartxref\n".$xref."\n%%EOF\n");
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
        $row = DB::table('portfolio_projects')->where('id', $id)->first();
        $path = $row->pdf_path;
        $this->assertStringContainsString('Built a React website', (string) $row->pdf_text);
        $this->assertStringStartsWith('portfolio/'.$org.'/'.$owner->id.'/', $path);
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
        $this->assertNull(DB::table('portfolio_projects')->where('id', $id)->value('pdf_text'));
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
        $this->assertStringContainsString('Built a React website', (string) DB::table('portfolio_projects')->where('id', $id)->value('pdf_text'));
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

    public function test_replacing_a_pdf_updates_text_and_deletes_the_old_file(): void
    {
        Storage::fake('local');
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $id = $this->postJson('/portfolio-projects', ['name' => 'Case study', 'summary' => 'First summary', 'pdf' => $this->samplePdf()])->assertCreated()->json('id');
        $original = DB::table('portfolio_projects')->where('id', $id)->first();
        Storage::disk('local')->assertExists($original->pdf_path);
        $this->postJson('/portfolio-projects/'.$id, ['name' => 'Case study updated', 'summary' => 'First summary', 'pdf' => $this->pdfFromPages('replacement.pdf', ['Replacement case study for Acme'])])->assertOk()->assertJsonPath('name', 'Case study updated')->assertJsonPath('has_pdf', true)->assertJsonPath('pdf_text', 'Replacement case study for Acme');
        $updated = DB::table('portfolio_projects')->where('id', $id)->first();
        $this->assertSame('Replacement case study for Acme', $updated->pdf_text);
        $this->assertStringStartsWith('portfolio/'.$org.'/'.$owner->id.'/', $updated->pdf_path);
        $this->assertNotSame($original->pdf_path, $updated->pdf_path);
        Storage::disk('local')->assertMissing($original->pdf_path);
        Storage::disk('local')->assertExists($updated->pdf_path);
        $this->postJson('/portfolio-projects/'.$id, ['name' => 'Case study kept', 'summary' => 'Edited summary only'])->assertOk()->assertJsonPath('has_pdf', true);
        $kept = DB::table('portfolio_projects')->where('id', $id)->first();
        $this->assertSame($updated->pdf_path, $kept->pdf_path);
        $this->assertSame('Replacement case study for Acme', $kept->pdf_text);
    }

    public function test_pdf_upload_limits_and_unreadable_pdfs_are_rejected(): void
    {
        Storage::fake('local');
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);

        $this->postJson('/portfolio-projects', ['name' => 'Notes', 'pdf' => UploadedFile::fake()->createWithContent('notes.txt', 'just a text file')])->assertUnprocessable()->assertJsonValidationErrors(['pdf']);
        $this->postJson('/portfolio-projects', ['name' => 'Photo', 'pdf' => UploadedFile::fake()->createWithContent('photo.jpg', "\xFF\xD8\xFF\xD9")])->assertUnprocessable()->assertJsonValidationErrors(['pdf']);

        $oversized = UploadedFile::fake()->createWithContent('too-big.pdf', "%PDF-1.4\n".str_repeat('A', 5121 * 1024));
        $this->postJson('/portfolio-projects', ['name' => 'Huge file', 'pdf' => $oversized])->assertUnprocessable()->assertJsonValidationErrors(['pdf']);

        $fifteen = $this->pdfFromPages('fifteen.pdf', array_map(fn ($n) => 'Fifteen page document page '.$n, range(1, 15)));
        $this->postJson('/portfolio-projects', ['name' => 'Fifteen pages', 'pdf' => $fifteen])->assertCreated()->assertJsonPath('has_pdf', true);
        $this->assertStringContainsString('Fifteen page document page 1', (string) DB::table('portfolio_projects')->where('name', 'Fifteen pages')->value('pdf_text'));
        $this->assertStringContainsString('Fifteen page document page 15', (string) DB::table('portfolio_projects')->where('name', 'Fifteen pages')->value('pdf_text'));

        $sixteen = $this->pdfFromPages('sixteen.pdf', array_map(fn ($n) => 'Sixteen page document page '.$n, range(1, 16)));
        $this->postJson('/portfolio-projects', ['name' => 'Sixteen pages', 'pdf' => $sixteen])->assertUnprocessable()->assertJsonValidationErrors(['pdf'])->assertJsonPath('errors.pdf.0', 'Please upload a PDF with 15 pages or fewer.');

        $withinLimit = $this->pdfFromPages('limit-ok.pdf', [str_repeat('Within limit text. ', 1500)]);
        $this->postJson('/portfolio-projects', ['name' => 'At limit', 'pdf' => $withinLimit])->assertCreated();
        $this->assertLessThanOrEqual(30000, mb_strlen((string) DB::table('portfolio_projects')->where('name', 'At limit')->value('pdf_text')));

        $tooLong = $this->pdfFromPages('too-long.pdf', [str_repeat('X', 30001)]);
        $this->postJson('/portfolio-projects', ['name' => 'Too much text', 'pdf' => $tooLong])->assertUnprocessable()->assertJsonValidationErrors(['pdf'])->assertJsonPath('errors.pdf.0', 'This PDF contains too much text. Please use a shorter portfolio document.');

        $this->postJson('/portfolio-projects', ['name' => 'Empty text', 'pdf' => $this->pdfFromPages('empty.pdf', [''])])->assertUnprocessable()->assertJsonValidationErrors(['pdf'])->assertJsonPath('errors.pdf.0', 'No readable text was found. Please upload a text-based PDF.');
        $this->postJson('/portfolio-projects', ['name' => 'Scanned', 'pdf' => $this->imageOnlyPdf()])->assertUnprocessable()->assertJsonValidationErrors(['pdf'])->assertJsonPath('errors.pdf.0', 'No readable text was found. Please upload a text-based PDF.');
        $this->postJson('/portfolio-projects', ['name' => 'Corrupt', 'pdf' => UploadedFile::fake()->createWithContent('corrupt.pdf', "%PDF-1.4\nthis is not a valid pdf structure\n")])
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['pdf'])
            ->assertJsonPath('errors.pdf.0', 'Could not read this PDF. Check that it is a valid, unlocked PDF.');

        $this->assertSame(2, DB::table('portfolio_projects')->count());
    }

    public function test_multiple_pdf_projects_are_capped_at_five_and_one_hundred_thousand_characters(): void
    {
        Storage::fake('local');
        Http::preventStrayRequests();
        Http::fake(['api.openai.com/v1/chat/completions' => Http::response(['choices' => [['message' => ['content' => 'Draft']]]], 200)]);
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();

        $ids = [];
        foreach (range(1, 6) as $n) {
            $ids[] = $this->postJson('/portfolio-projects', [
                'name' => 'PDF Project '.$n,
                'summary' => 'Summary '.$n,
                'pdf' => $this->pdfFromPages('project-'.$n.'.pdf', ['Unique extracted text for project '.$n]),
            ])->assertCreated()->assertJsonPath('has_pdf', true)->json('id');
        }

        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'project_ids' => $ids])->assertUnprocessable()->assertJsonValidationErrors(['project_ids']);
        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'project_ids' => array_slice($ids, 0, 5)])->assertOk();
        Http::assertSent(function ($request) {
            $content = $request['messages'][1]['content'];

            return str_contains($content, 'Unique extracted text for project 1')
                && str_contains($content, 'Unique extracted text for project 5')
                && ! str_contains($content, 'Unique extracted text for project 6');
        });

        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'instructions' => 'Please mention PDF Project 6'])->assertOk();
        Http::assertSent(fn ($request) => str_contains($request['messages'][1]['content'], 'Unique extracted text for project 6'));

        foreach (array_slice($ids, 0, 4) as $id) {
            DB::table('portfolio_projects')->where('id', $id)->update(['pdf_text' => str_repeat('Large portfolio excerpt. ', 1400)]);
        }
        $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'project_ids' => array_slice($ids, 0, 4)])
            ->assertUnprocessable()
            ->assertJsonValidationErrors(['project_ids'])
            ->assertJsonPath('errors.project_ids.0', 'The selected projects contain too much text. Select fewer projects.');
    }

    public function test_account_privacy_hides_pdf_text_and_files_from_other_users(): void
    {
        Storage::fake('local');
        Http::preventStrayRequests();
        Http::fake(['api.openai.com/v1/chat/completions' => Http::response(['choices' => [['message' => ['content' => 'Draft']]]], 200)]);
        $org = $this->organization();
        $owner = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $colleague = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $outsider = User::factory()->create(['organization_id' => $this->organization(), 'is_super_admin' => true]);
        $this->withSession(['session_version' => 0])->actingAs($owner);
        $id = $this->postJson('/portfolio-projects', ['name' => 'Private PDF', 'pdf' => $this->pdfFromPages('private.pdf', ['Secret extracted portfolio text'])])->assertCreated()->json('id');
        $this->assertSame('Secret extracted portfolio text', DB::table('portfolio_projects')->where('id', $id)->value('pdf_text'));

        foreach ([$colleague, $outsider] as $other) {
            $this->withSession(['session_version' => 0])->actingAs($other);
            $this->getJson('/portfolio-projects')->assertOk()->assertExactJson([])->assertJsonMissing(['pdf_text' => 'Secret extracted portfolio text']);
            $this->get('/portfolio-projects/'.$id.'/pdf')->assertNotFound();
            $this->putJson('/ai-writer/settings', ['api_key' => 'sk-test_abcdefghijklmnopqrstuv', 'model' => 'gpt-4o-mini'])->assertOk();
            $this->postJson('/ai-writer/generate', ['job' => 'Build a shop', 'knowledge_mode' => 'portfolio', 'project_ids' => [$id]])->assertUnprocessable()->assertJsonValidationErrors(['project_ids']);
        }
    }
}
