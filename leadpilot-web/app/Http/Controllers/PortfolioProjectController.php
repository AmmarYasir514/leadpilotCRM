<?php

namespace App\Http\Controllers;

use App\Authorization\PermissionResolver;
use Illuminate\Database\Query\Builder;
use Illuminate\Http\JsonResponse;
use Illuminate\Http\Request;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;
use Illuminate\Validation\ValidationException;
use OpenSpout\Reader\XLSX\Reader;
use Smalot\PdfParser\Parser;
use Symfony\Component\HttpFoundation\StreamedResponse;

class PortfolioProjectController extends Controller
{
    private function authorizePortfolio(Request $request): void
    {
        $user = $request->user();
        abort_unless($user->organization_id && app(PermissionResolver::class)->scopes($user, 'ai_sales_agent', 'create', $user->organization_id), 403);
    }

    private function projects(Request $request): Builder
    {
        return DB::table('portfolio_projects')->where('organization_id', $request->user()->organization_id)->where('user_id', $request->user()->id);
    }

    private function validated(Request $request): array
    {
        return $request->validate([
            'name' => ['required', 'string', 'max:255'], 'summary' => ['nullable', 'string', 'max:10000'],
            'skills' => ['nullable', 'string', 'max:3000'], 'links' => ['nullable', 'array', 'max:10'],
            'links.*' => ['required', 'string', 'url:http,https', 'max:2048'],
            'pdf' => ['nullable', 'file', 'mimes:pdf', 'extensions:pdf', 'max:5120'], 'remove_pdf' => ['sometimes', 'boolean'],
        ]);
    }

    private function readPdf(UploadedFile $file): string
    {
        try {
            $pdf = (new Parser)->parseFile($file->getRealPath());
            if (count($pdf->getPages()) > 15) {
                throw ValidationException::withMessages(['pdf' => 'Please upload a PDF with 15 pages or fewer.']);
            }
            $text = trim($pdf->getText());
        } catch (ValidationException $exception) {
            throw $exception;
        } catch (\Throwable $exception) {
            throw ValidationException::withMessages(['pdf' => 'Could not read this PDF. Check that it is a valid, unlocked PDF.']);
        }
        if ($text === '') {
            throw ValidationException::withMessages(['pdf' => 'No readable text was found. Please upload a text-based PDF.']);
        }
        if (mb_strlen($text) > 30000 || strlen($text) > 60000) {
            throw ValidationException::withMessages(['pdf' => 'This PDF contains too much text. Please use a shorter portfolio document.']);
        }

        return $text;
    }

    private function present(object $project): array
    {
        return ['id' => $project->id, 'name' => $project->name, 'summary' => $project->summary, 'skills' => $project->skills,
            'links' => json_decode($project->links ?: '[]', true), 'has_pdf' => (bool) $project->pdf_path,
            'pdf_text' => $project->pdf_text, 'updated_at' => $project->updated_at];
    }

    public function previewImport(Request $request): JsonResponse
    {
        $this->authorizePortfolio($request);
        $request->validate(['file' => ['required', 'file', 'max:5120', 'extensions:csv,xlsx']]);
        $file = $request->file('file');
        $extension = strtolower($file->getClientOriginalExtension());
        $rows = [];
        try {
            if ($extension === 'xlsx') {
                $zip = new \ZipArchive;
                if ($zip->open($file->getRealPath()) !== true) {
                    throw new \RuntimeException;
                }
                $total = 0;
                for ($i = 0; $i < $zip->numFiles; $i++) {
                    $total += $zip->statIndex($i)['size'];
                    if ($total > 30 * 1024 * 1024) {
                        $zip->close();
                        throw new \RuntimeException;
                    }
                }
                $zip->close();
                $reader = new Reader;
                $reader->open($file->getRealPath());
                foreach ($reader->getSheetIterator() as $sheet) {
                    foreach ($sheet->getRowIterator() as $row) {
                        $rows[] = $row->toArray();
                        if (count($rows) > 501) {
                            throw new \RuntimeException;
                        }
                    }
                    break;
                }
                $reader->close();
            } else {
                $handle = fopen($file->getRealPath(), 'rb');
                while (($row = fgetcsv($handle, 0, ',', '"', '\\')) !== false) {
                    $rows[] = $row;
                    if (count($rows) > 501) {
                        throw new \RuntimeException;
                    }
                }
                fclose($handle);
            }
            foreach ($rows as &$row) {
                if (count($row) > 50) {
                    throw new \RuntimeException;
                }
                $row = array_map(function ($cell) {
                    if (! is_scalar($cell) && $cell !== null) {
                        throw new \RuntimeException;
                    }
                    $value = trim((string) $cell);
                    if (! mb_check_encoding($value, 'UTF-8') || mb_strlen($value) > 10000) {
                        throw new \RuntimeException;
                    }

                    return $value;
                }, $row);
            }
            unset($row);
        } catch (\Throwable $exception) {
            throw ValidationException::withMessages(['file' => 'Could not read this file. Use a valid UTF-8 CSV or XLSX with at most 500 rows and 50 columns.']);
        }
        if (count($rows) < 2) {
            throw ValidationException::withMessages(['file' => 'Add a header row and at least one project row.']);
        }
        $headers = array_shift($rows);
        $headers[0] = preg_replace('/^\xEF\xBB\xBF/', '', $headers[0]);

        return response()->json(['headers' => $headers, 'rows' => $rows]);
    }

    public function import(Request $request): JsonResponse
    {
        $this->authorizePortfolio($request);
        $data = $request->validate([
            'projects' => ['required', 'array', 'min:1', 'max:500'],
            'projects.*.name' => ['required', 'string', 'max:255'],
            'projects.*.summary' => ['nullable', 'string', 'max:10000'],
            'projects.*.skills' => ['nullable', 'string', 'max:3000'],
            'projects.*.links' => ['nullable', 'array', 'max:10'],
            'projects.*.links.*' => ['required', 'string', 'url:http,https', 'max:2048'],
        ]);
        $existing = $this->projects($request)->pluck('name')->map(fn ($name) => mb_strtolower(trim($name)))->all();
        $added = 0;
        $skipped = [];
        DB::transaction(function () use ($data, $request, &$existing, &$added, &$skipped) {
            foreach ($data['projects'] as $project) {
                $name = trim($project['name']);
                if ($name === '') {
                    throw ValidationException::withMessages(['projects' => 'Project names cannot be blank.']);
                }
                $key = mb_strtolower($name);
                if (in_array($key, $existing, true)) {
                    $skipped[] = $name;

                    continue;
                }
                DB::table('portfolio_projects')->insert(['organization_id' => $request->user()->organization_id, 'user_id' => $request->user()->id,
                    'name' => $name, 'summary' => $project['summary'] ?? null, 'skills' => $project['skills'] ?? null,
                    'links' => json_encode($project['links'] ?? [], JSON_THROW_ON_ERROR), 'created_at' => now(), 'updated_at' => now()]);
                $existing[] = $key;
                $added++;
            }
        });

        return response()->json(['added' => $added, 'skipped' => $skipped]);
    }

    public function index(Request $request): JsonResponse
    {
        $this->authorizePortfolio($request);
        if ($request->boolean('brief')) {
            return response()->json($this->projects($request)->orderBy('name')->get(['id', 'name']));
        }

        return response()->json($this->projects($request)->orderBy('name')->get()->map(fn ($project) => $this->present($project)));
    }

    public function store(Request $request): JsonResponse
    {
        $this->authorizePortfolio($request);
        $data = $this->validated($request);
        if (strlen(json_encode($data['links'] ?? [], JSON_THROW_ON_ERROR)) > 50000) {
            throw ValidationException::withMessages(['links' => 'The portfolio links are too long.']);
        }
        $file = $data['pdf'] ?? null;
        $text = $file ? $this->readPdf($file) : null;
        $path = $file?->store('portfolio/'.$request->user()->organization_id.'/'.$request->user()->id, 'local');
        if ($file && ! $path) {
            abort(500, 'Could not store the PDF.');
        }
        try {
            $id = DB::table('portfolio_projects')->insertGetId(['organization_id' => $request->user()->organization_id, 'user_id' => $request->user()->id,
                'name' => trim($data['name']), 'summary' => $data['summary'] ?? null, 'skills' => $data['skills'] ?? null,
                'links' => json_encode($data['links'] ?? [], JSON_THROW_ON_ERROR), 'pdf_path' => $path, 'pdf_text' => $text, 'created_at' => now(), 'updated_at' => now()]);
        } catch (\Throwable $exception) {
            if ($path) {
                Storage::disk('local')->delete($path);
            }
            throw $exception;
        }

        return response()->json($this->present($this->projects($request)->where('id', $id)->first()), 201);
    }

    public function update(Request $request, int $id): JsonResponse
    {
        $this->authorizePortfolio($request);
        $project = $this->projects($request)->where('id', $id)->first();
        abort_unless($project, 404);
        $data = $this->validated($request);
        if (strlen(json_encode($data['links'] ?? [], JSON_THROW_ON_ERROR)) > 50000) {
            throw ValidationException::withMessages(['links' => 'The portfolio links are too long.']);
        }
        $file = $data['pdf'] ?? null;
        $text = $file ? $this->readPdf($file) : (($data['remove_pdf'] ?? false) ? null : $project->pdf_text);
        $path = $file ? $file->store('portfolio/'.$request->user()->organization_id.'/'.$request->user()->id, 'local') : (($data['remove_pdf'] ?? false) ? null : $project->pdf_path);
        if ($file && ! $path) {
            abort(500, 'Could not store the PDF.');
        }
        try {
            $this->projects($request)->where('id', $id)->update(['name' => trim($data['name']), 'summary' => $data['summary'] ?? null, 'skills' => $data['skills'] ?? null,
                'links' => json_encode($data['links'] ?? [], JSON_THROW_ON_ERROR), 'pdf_path' => $path, 'pdf_text' => $text, 'updated_at' => now()]);
        } catch (\Throwable $exception) {
            if ($file && $path) {
                Storage::disk('local')->delete($path);
            }
            throw $exception;
        }
        if ($project->pdf_path && $project->pdf_path !== $path) {
            Storage::disk('local')->delete($project->pdf_path);
        }

        return response()->json($this->present($this->projects($request)->where('id', $id)->first()));
    }

    public function destroy(Request $request, int $id): JsonResponse
    {
        $this->authorizePortfolio($request);
        $project = $this->projects($request)->where('id', $id)->first();
        abort_unless($project, 404);
        if ($project->pdf_path && Storage::disk('local')->exists($project->pdf_path) && ! Storage::disk('local')->delete($project->pdf_path)) {
            abort(500, 'Could not delete the project PDF.');
        }
        $this->projects($request)->where('id', $id)->delete();

        return response()->json(['message' => 'Project deleted.']);
    }

    public function pdf(Request $request, int $id): StreamedResponse
    {
        $this->authorizePortfolio($request);
        $project = $this->projects($request)->where('id', $id)->first();
        abort_unless($project && $project->pdf_path && Storage::disk('local')->exists($project->pdf_path), 404);

        return Storage::disk('local')->download($project->pdf_path, 'portfolio.pdf', ['Cache-Control' => 'private, no-store']);
    }
}
