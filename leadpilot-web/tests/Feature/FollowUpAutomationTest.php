<?php

namespace Tests\Feature;

use App\Models\User;
use App\Support\SystemTimezone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Notification;
use PDO;
use Tests\TestCase;

class FollowUpAutomationTest extends TestCase
{
    use RefreshDatabase;

    private array $tempFiles = [];

    private string $lockDir;

    protected function setUp(): void
    {
        parent::setUp();
        // Keep the run lock in a private temp folder so tests never share a lock with the real app.
        $this->lockDir = sys_get_temp_dir().DIRECTORY_SEPARATOR.'lp_test_locks_'.bin2hex(random_bytes(4));
        config(['cache.stores.file.path' => $this->lockDir, 'cache.stores.file.lock_path' => $this->lockDir]);
        Cache::forgetDriver('file');
        // Pin the local zone so these tests give the same answers on any computer.
        SystemTimezone::setForTesting('Asia/Karachi');
    }

    protected function tearDown(): void
    {
        foreach ($this->tempFiles as $file) {
            @unlink($file);
        }
        File::deleteDirectory($this->lockDir);
        SystemTimezone::setForTesting(null);
        parent::tearDown();
    }

    private function tempPath(): string
    {
        $base = tempnam(sys_get_temp_dir(), 'lp_fixture_');
        @unlink($base);
        $this->tempFiles[] = $base.'.db';

        return $base.'.db';
    }

    private function workspace(): array
    {
        $org = DB::table('organizations')->insertGetId(['name' => 'Automation', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);

        return [$org, $admin];
    }

    private function lead(int $org, int $owner, array $extra = []): int
    {
        return DB::table('leads')->insertGetId(array_merge(['organization_id' => $org, 'created_by' => $owner, 'assigned_to' => $owner, 'name' => 'Client', 'status' => 'new', 'created_at' => now(), 'updated_at' => now()], $extra));
    }

    private function dueEvents(int $lead): int
    {
        return DB::table('follow_up_events')->where('lead_id', $lead)->where('action', 'due')->count();
    }

    public function test_scheduled_job_starts_cycles_and_logs_one_reminder_per_due_step_without_sending(): void
    {
        Http::fake();
        Mail::fake();
        Notification::fake();
        $this->travelTo(Carbon::parse('2026-01-01 12:00:00', 'UTC'));
        [$org, $admin] = $this->workspace();
        $lead = $this->lead($org, $admin->id);
        $closed = $this->lead($org, $admin->id, ['name' => 'Done', 'status' => 'lost']);

        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Started: 1')->assertSuccessful();
        $cycle = DB::table('follow_up_cycles')->where('lead_id', $lead)->first();
        $this->assertSame('[24,48,48,72,72]', $cycle->cadence);
        $this->assertSame('2026-01-02 12:00:00', $cycle->next_due_at);
        $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', $closed)->first());
        $this->assertSame(0, $this->dueEvents($lead));

        $this->travel(25)->hours();
        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Reminders logged: 1')->assertSuccessful();
        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Reminders logged: 0')->assertSuccessful();
        $this->assertSame(1, $this->dueEvents($lead));
        $this->assertStringContainsString('Follow-up 1 of 5 is due', DB::table('follow_up_events')->where('lead_id', $lead)->where('action', 'due')->value('note'));

        // Lengthening the timings after a reminder must not log a second reminder for the same step.
        $this->withSession(['session_version' => 0])->actingAs($admin)->putJson('/leads/'.$lead.'/follow-up-cycle', ['action' => 'configure', 'cadence' => [30, 48, 48, 72, 72]])->assertOk()->assertJsonPath('cycle.due_at', '2026-01-02T18:00:00+00:00');
        $this->travel(6)->hours();
        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Reminders logged: 0')->assertSuccessful();
        $this->assertSame(1, $this->dueEvents($lead));

        $this->putJson('/leads/'.$lead.'/follow-up-cycle', ['action' => 'sent'])->assertOk()->assertJsonPath('cycle.completed', 1)->assertJsonPath('cycle.due_at', '2026-01-04T19:00:00+00:00');
        $this->assertSame('2026-01-04 19:00:00', DB::table('follow_up_cycles')->where('lead_id', $lead)->value('next_due_at'));
        $this->travel(49)->hours();
        $this->artisan('leadpilot:follow-ups')->assertSuccessful();
        $this->assertSame(2, $this->dueEvents($lead));

        Http::assertNothingSent();
        Mail::assertNothingSent();
        Notification::assertNothingSent();
    }

    public function test_a_second_run_skips_cleanly_while_another_run_holds_the_lock(): void
    {
        [$org, $admin] = $this->workspace();
        $lead = $this->lead($org, $admin->id);
        $held = Cache::store('file')->lock('leadpilot:follow-ups', 600);
        $this->assertTrue($held->get());

        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Another follow-up run is already in progress, so this run was skipped.')->assertSuccessful();
        $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', $lead)->first());

        $held->release();
        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Started: 1')->assertSuccessful();
        $again = Cache::store('file')->lock('leadpilot:follow-ups', 600);
        $this->assertTrue($again->get(), 'The run must release its lock when it finishes.');
        $again->release();
    }

    public function test_a_lock_error_is_logged_and_fails_instead_of_skipping_silently(): void
    {
        Log::spy();
        [$org, $admin] = $this->workspace();
        $lead = $this->lead($org, $admin->id);
        File::ensureDirectoryExists($this->lockDir);
        $notAFolder = $this->lockDir.DIRECTORY_SEPARATOR.'locks-is-a-file';
        file_put_contents($notAFolder, 'not a folder');
        config(['cache.stores.file.lock_path' => $notAFolder]);
        Cache::forgetDriver('file');

        $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Follow-up run failed: the lock folder could not be used')->assertFailed();
        Log::shouldHaveReceived('error')->withArgs(fn ($message) => str_contains($message, 'could not use its lock'))->once();
        $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', $lead)->first());
    }

    public function test_auto_started_cycle_uses_lead_date_midnight_in_karachi_time(): void
    {
        $this->travelTo(Carbon::parse('2026-01-01 12:00:00', 'UTC'));
        [$org, $admin] = $this->workspace();
        $lead = $this->lead($org, $admin->id, ['lead_date' => '2026-01-05']);
        $this->artisan('leadpilot:follow-ups')->assertSuccessful();
        $cycle = DB::table('follow_up_cycles')->where('lead_id', $lead)->first();
        $this->assertSame('2026-01-04 19:00:00', $cycle->anchor_at);
        $this->assertSame('2026-01-05 19:00:00', $cycle->next_due_at);
    }

    public function test_meeting_booked_and_contract_started_pause_and_stage_change_or_reply_restarts(): void
    {
        $this->travelTo(Carbon::parse('2026-01-01 12:00:00', 'UTC'));
        [$org, $admin] = $this->workspace();
        $lead = $this->lead($org, $admin->id);
        $url = '/leads/'.$lead.'/follow-up-cycle';
        $this->withSession(['session_version' => 0])->actingAs($admin);
        $this->putJson($url, ['action' => 'start', 'cadence' => [24, 48]])->assertOk();

        foreach (['Contract started', 'Meeting booked'] as $paused) {
            $this->putJson($url, ['action' => 'stage', 'stage' => $paused])->assertOk()->assertJsonPath('cycle.due_at', null)->assertJsonPath('cycle.paused', true);
            $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', $lead)->value('next_due_at'));
            $this->getJson('/follow-up-cycles')->assertOk()->assertJsonCount(0, 'data');
            $this->putJson($url, ['action' => 'sent'])->assertUnprocessable();
            $this->travel(100)->hours();
            $this->artisan('leadpilot:follow-ups')->expectsOutputToContain('Paused: 1')->assertSuccessful();
            $this->assertSame(0, $this->dueEvents($lead));
        }

        // Moving out of a paused stage restarts the clock: follow-up 1 is due 24 hours later.
        $expected = now()->addHours(24)->toIso8601String();
        $this->putJson($url, ['action' => 'stage', 'stage' => 'Chat started'])->assertOk()->assertJsonPath('cycle.paused', false)->assertJsonPath('cycle.completed', 0)->assertJsonPath('cycle.due_at', $expected);
        $this->getJson('/follow-up-cycles')->assertOk()->assertJsonCount(1, 'data');

        // Choosing the same stage again does not restart the clock (desktop fu_change_stage returns early).
        $this->travel(2)->hours();
        $stageEvents = DB::table('follow_up_events')->where('lead_id', $lead)->where('action', 'stage')->count();
        $this->putJson($url, ['action' => 'stage', 'stage' => 'Chat started'])->assertOk()->assertJsonPath('cycle.due_at', $expected);
        $this->assertSame($stageEvents, DB::table('follow_up_events')->where('lead_id', $lead)->where('action', 'stage')->count());

        // A client reply restarts the cycle from step 1.
        $this->travel(23)->hours();
        $this->putJson($url, ['action' => 'sent'])->assertOk()->assertJsonPath('cycle.completed', 1);
        $this->travel(5)->hours();
        $this->putJson($url, ['action' => 'reply'])->assertOk()->assertJsonPath('cycle.completed', 0)->assertJsonPath('cycle.due_at', now()->addHours(24)->toIso8601String());
    }

    private function desktopFixture(): string
    {
        $path = $this->tempPath();
        $db = new PDO('sqlite:'.$path);
        $db->exec("CREATE TABLE leads(id INTEGER PRIMARY KEY AUTOINCREMENT, account TEXT NOT NULL, member TEXT NOT NULL, name TEXT NOT NULL, company TEXT, source TEXT DEFAULT 'Upwork', proposal_id INTEGER, lead_date TEXT, status TEXT DEFAULT 'Qualified', budget REAL DEFAULT 0, next_followup TEXT, last_contact TEXT, notes TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP, fu_count INTEGER DEFAULT 0, fu_anchor TEXT, chat_start TEXT, last_client_msg TEXT, last_preview TEXT, job_title TEXT, closed_reason TEXT, sales_stage TEXT, stage_at TEXT)");
        $db->exec('CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)');
        $db->exec("INSERT INTO settings VALUES('fu_cadence','24,48,48,72,72'),('openai_api_key','secret-should-not-import')");
        $insert = $db->prepare('INSERT INTO leads(id, account, member, name, company, lead_date, status, next_followup, created_at, fu_count, fu_anchor, job_title, sales_stage) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)');
        $insert->execute([7, 'Upwork', 'Ammar', 'Open Client', 'Northwind', '2026-11-11', 'Follow-up', '2026-11-19 00:49', '2026-11-14 16:41:29', 1, '2026-11-17 00:49', 'Shopify job', 'Chat started']);
        $insert->execute([11, 'Upwork', 'Ammar', 'Won Client', 'Brightpath', '2026-11-12', 'Won', null, '2026-11-14 16:41:29', 0, '2026-11-14 22:17', null, 'Contract started']);
        $insert->execute([16, 'Upwork', 'Ammar', 'Finished Client', null, '2026-11-08', 'Follow-up', null, '2026-11-14 16:41:29', 5, '2026-11-10 17:41', null, 'Proposal sent, awaiting response']);

        return $path;
    }

    public function test_desktop_import_keeps_cycle_state_and_is_idempotent(): void
    {
        [$org, $admin] = $this->workspace();
        $fixture = $this->desktopFixture();
        $before = hash_file('sha256', $fixture);

        $this->artisan('leadpilot:import-desktop', ['--path' => $fixture, '--owner' => $admin->email])
            ->expectsOutputToContain('Source leads: 3. Imported: 3. Skipped (already imported): 0. Duplicate source ids skipped: 0. Follow-up cycles created: 3. Due time mismatches: 0.')->assertSuccessful();
        $this->artisan('leadpilot:import-desktop', ['--path' => $fixture, '--owner' => (string) $admin->id])
            ->expectsOutputToContain('Source leads: 3. Imported: 0. Skipped (already imported): 3. Duplicate source ids skipped: 0. Follow-up cycles created: 0.')->assertSuccessful();

        $this->assertSame($before, hash_file('sha256', $fixture));
        $this->assertSame(3, DB::table('leads')->where('organization_id', $org)->count());
        $this->assertSame(3, DB::table('follow_up_cycles')->count());
        $open = DB::table('leads')->where('import_key', 'desktop:7')->first();
        $this->assertSame('follow-up', $open->status);
        $this->assertSame($admin->id, (int) $open->assigned_to);
        $this->assertSame('2026-11-11', $open->lead_date);
        $cycle = DB::table('follow_up_cycles')->where('lead_id', $open->id)->first();
        $this->assertSame(1, (int) $cycle->completed);
        $this->assertSame('2026-11-16 19:49:00', $cycle->anchor_at);
        $this->assertSame('2026-11-18 19:49:00', $cycle->next_due_at);
        $won = DB::table('leads')->where('import_key', 'desktop:11')->first();
        $this->assertSame('won', $won->status);
        $this->assertSame('Contract started', DB::table('follow_up_cycles')->where('lead_id', $won->id)->value('stage'));
        $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', $won->id)->value('next_due_at'));
        $this->assertNull(DB::table('follow_up_cycles')->where('lead_id', DB::table('leads')->where('import_key', 'desktop:16')->value('id'))->value('next_due_at'));
        $this->assertStringNotContainsString('secret', DB::table('leads')->pluck('notes')->implode(' '));
    }

    public function test_desktop_import_counts_duplicate_source_ids_separately(): void
    {
        [$org, $admin] = $this->workspace();
        $path = $this->tempPath();
        $db = new PDO('sqlite:'.$path);
        $db->exec('CREATE TABLE leads(id INTEGER, name TEXT NOT NULL, status TEXT)');
        $db->exec("INSERT INTO leads VALUES(1, 'First', 'Contacted'), (1, 'Copy of first', 'Contacted'), (2, 'Second', 'Lost')");
        $db = null;

        $this->artisan('leadpilot:import-desktop', ['--path' => $path, '--owner' => $admin->email])
            ->expectsOutputToContain('Source leads: 3. Imported: 2. Skipped (already imported): 0. Duplicate source ids skipped: 1.')->assertSuccessful();
        $this->artisan('leadpilot:import-desktop', ['--path' => $path, '--owner' => $admin->email])
            ->expectsOutputToContain('Source leads: 3. Imported: 0. Skipped (already imported): 2. Duplicate source ids skipped: 1.')->assertSuccessful();
        $this->assertSame(['First', 'Second'], DB::table('leads')->where('organization_id', $org)->orderBy('id')->pluck('name')->all());
    }

    public function test_desktop_import_rejects_files_that_are_not_desktop_databases(): void
    {
        [, $admin] = $this->workspace();
        $garbage = $this->tempPath();
        file_put_contents($garbage, str_repeat('not a database ', 200));
        $this->artisan('leadpilot:import-desktop', ['--path' => $garbage, '--owner' => $admin->email])
            ->expectsOutputToContain('Could not read this file as a LeadPilot desktop database')->assertFailed();

        $noLeads = $this->tempPath();
        $db = new PDO('sqlite:'.$noLeads);
        $db->exec('CREATE TABLE settings(k TEXT PRIMARY KEY, v TEXT)');
        $db = null;
        $this->artisan('leadpilot:import-desktop', ['--path' => $noLeads, '--owner' => $admin->email])
            ->expectsOutputToContain('This file has no leads table')->assertFailed();

        $this->assertSame(0, DB::table('leads')->count());
    }
}
