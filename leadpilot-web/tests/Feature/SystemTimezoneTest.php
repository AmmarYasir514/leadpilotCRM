<?php

namespace Tests\Feature;

use App\Models\User;
use App\Support\SystemTimezone;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Tests\TestCase;

class SystemTimezoneTest extends TestCase
{
    use RefreshDatabase;

    protected function tearDown(): void
    {
        SystemTimezone::setForTesting(null);
        parent::tearDown();
    }

    public function test_windows_zone_ids_map_to_iana_names(): void
    {
        $this->assertSame('Asia/Karachi', SystemTimezone::fromWindowsId('Pakistan Standard Time'));
        $this->assertSame('America/New_York', SystemTimezone::fromWindowsId('Eastern Standard Time'));
        $this->assertSame('Europe/London', SystemTimezone::fromWindowsId(" GMT Standard Time\r\n"));
        $this->assertNull(SystemTimezone::fromWindowsId('Not A Real Zone'));
        $this->assertNull(SystemTimezone::fromWindowsId(''));
    }

    public function test_linux_and_mac_zone_detection(): void
    {
        $this->assertSame('Europe/Berlin', SystemTimezone::fromUnix("Europe/Berlin\n", null));
        $this->assertSame('Asia/Tokyo', SystemTimezone::fromUnix(null, '/usr/share/zoneinfo/Asia/Tokyo'));
        $this->assertSame('America/Chicago', SystemTimezone::fromUnix('garbage', '/var/db/timezone/zoneinfo/America/Chicago'));
        $this->assertNull(SystemTimezone::fromUnix(null, null));
    }

    public function test_fallback_order_is_override_then_detected_then_app_zone_then_utc(): void
    {
        $this->assertSame('Asia/Dubai', SystemTimezone::resolveFrom('Asia/Dubai', fn () => $this->fail('Detection must not run when an override is set.'), 'UTC'));
        $this->assertSame('Asia/Tokyo', SystemTimezone::resolveFrom('Not/AZone', fn () => 'Asia/Tokyo', 'UTC'));
        $this->assertSame('Europe/Paris', SystemTimezone::resolveFrom(null, fn () => null, 'Europe/Paris'));
        $this->assertSame('UTC', SystemTimezone::resolveFrom('', fn () => 'bad zone', 'also bad'));
    }

    public function test_env_override_is_used_and_cached_for_the_process(): void
    {
        config(['app.leadpilot_timezone' => 'America/Chicago']);
        SystemTimezone::setForTesting(null);
        $this->assertSame('America/Chicago', SystemTimezone::get());
        config(['app.leadpilot_timezone' => 'Asia/Dubai']);
        $this->assertSame('America/Chicago', SystemTimezone::get());
    }

    public function test_detection_on_this_computer_returns_a_valid_zone_or_nothing(): void
    {
        $zone = SystemTimezone::detect();
        $this->assertTrue($zone === null || SystemTimezone::valid($zone), 'Detected zone must be a valid IANA name: '.var_export($zone, true));
    }

    public function test_scheduler_reads_lead_dates_in_the_system_zone(): void
    {
        $this->travelTo(Carbon::parse('2026-01-01 12:00:00', 'UTC'));
        $org = DB::table('organizations')->insertGetId(['name' => 'Zones', 'created_at' => now(), 'updated_at' => now()]);
        $admin = User::factory()->create(['organization_id' => $org, 'is_super_admin' => true]);
        $lead = fn (string $name) => DB::table('leads')->insertGetId(['organization_id' => $org, 'created_by' => $admin->id, 'assigned_to' => $admin->id, 'name' => $name, 'status' => 'new', 'lead_date' => '2026-01-05', 'created_at' => now(), 'updated_at' => now()]);

        SystemTimezone::setForTesting('Europe/London');
        $london = $lead('London');
        $this->artisan('leadpilot:follow-ups')->assertSuccessful();
        SystemTimezone::setForTesting('America/New_York');
        $newYork = $lead('New York');
        $this->artisan('leadpilot:follow-ups')->assertSuccessful();

        $this->assertSame('2026-01-05 00:00:00', DB::table('follow_up_cycles')->where('lead_id', $london)->value('anchor_at'));
        $this->assertSame('2026-01-05 05:00:00', DB::table('follow_up_cycles')->where('lead_id', $newYork)->value('anchor_at'));
    }
}
