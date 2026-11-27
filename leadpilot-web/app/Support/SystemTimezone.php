<?php

namespace App\Support;

use DateTimeZone;
use IntlTimeZone;
use Throwable;

/**
 * The time zone of the computer LeadPilot runs on, worked out once per process.
 * Order: LEADPILOT_TIMEZONE override, then the detected system zone, then config('app.timezone'), then UTC.
 * Detection never passes user input to a command: it only runs fixed commands with no shell.
 */
class SystemTimezone
{
    /** Common Windows time zone IDs and their IANA names, used when the intl extension is not installed. */
    private const WINDOWS_TO_IANA = [
        'Dateline Standard Time' => 'Etc/GMT+12', 'UTC-11' => 'Etc/GMT+11', 'Hawaiian Standard Time' => 'Pacific/Honolulu',
        'Alaskan Standard Time' => 'America/Anchorage', 'Pacific Standard Time' => 'America/Los_Angeles', 'Pacific Standard Time (Mexico)' => 'America/Tijuana',
        'US Mountain Standard Time' => 'America/Phoenix', 'Mountain Standard Time' => 'America/Denver', 'Central America Standard Time' => 'America/Guatemala',
        'Central Standard Time' => 'America/Chicago', 'Central Standard Time (Mexico)' => 'America/Mexico_City', 'Canada Central Standard Time' => 'America/Regina',
        'SA Pacific Standard Time' => 'America/Bogota', 'Eastern Standard Time' => 'America/New_York', 'US Eastern Standard Time' => 'America/Indianapolis',
        'Atlantic Standard Time' => 'America/Halifax', 'SA Western Standard Time' => 'America/La_Paz', 'Newfoundland Standard Time' => 'America/St_Johns',
        'E. South America Standard Time' => 'America/Sao_Paulo', 'Argentina Standard Time' => 'America/Buenos_Aires', 'SA Eastern Standard Time' => 'America/Cayenne',
        'UTC-02' => 'Etc/GMT+2', 'Azores Standard Time' => 'Atlantic/Azores', 'Cape Verde Standard Time' => 'Atlantic/Cape_Verde',
        'UTC' => 'UTC', 'Coordinated Universal Time' => 'UTC', 'GMT Standard Time' => 'Europe/London', 'Greenwich Standard Time' => 'Atlantic/Reykjavik',
        'Morocco Standard Time' => 'Africa/Casablanca', 'W. Europe Standard Time' => 'Europe/Berlin', 'Central Europe Standard Time' => 'Europe/Budapest',
        'Romance Standard Time' => 'Europe/Paris', 'Central European Standard Time' => 'Europe/Warsaw', 'W. Central Africa Standard Time' => 'Africa/Lagos',
        'GTB Standard Time' => 'Europe/Bucharest', 'FLE Standard Time' => 'Europe/Kiev', 'Egypt Standard Time' => 'Africa/Cairo',
        'South Africa Standard Time' => 'Africa/Johannesburg', 'Israel Standard Time' => 'Asia/Jerusalem', 'Turkey Standard Time' => 'Europe/Istanbul',
        'Jordan Standard Time' => 'Asia/Amman', 'Arabic Standard Time' => 'Asia/Baghdad', 'Arab Standard Time' => 'Asia/Riyadh',
        'E. Africa Standard Time' => 'Africa/Nairobi', 'Russian Standard Time' => 'Europe/Moscow', 'Iran Standard Time' => 'Asia/Tehran',
        'Arabian Standard Time' => 'Asia/Dubai', 'Azerbaijan Standard Time' => 'Asia/Baku', 'Afghanistan Standard Time' => 'Asia/Kabul',
        'West Asia Standard Time' => 'Asia/Tashkent', 'Pakistan Standard Time' => 'Asia/Karachi', 'India Standard Time' => 'Asia/Kolkata',
        'Sri Lanka Standard Time' => 'Asia/Colombo', 'Nepal Standard Time' => 'Asia/Katmandu', 'Central Asia Standard Time' => 'Asia/Almaty',
        'Bangladesh Standard Time' => 'Asia/Dhaka', 'Myanmar Standard Time' => 'Asia/Rangoon', 'SE Asia Standard Time' => 'Asia/Bangkok',
        'China Standard Time' => 'Asia/Shanghai', 'Singapore Standard Time' => 'Asia/Singapore', 'Taipei Standard Time' => 'Asia/Taipei',
        'W. Australia Standard Time' => 'Australia/Perth', 'Tokyo Standard Time' => 'Asia/Tokyo', 'Korea Standard Time' => 'Asia/Seoul',
        'Cen. Australia Standard Time' => 'Australia/Adelaide', 'AUS Central Standard Time' => 'Australia/Darwin', 'E. Australia Standard Time' => 'Australia/Brisbane',
        'AUS Eastern Standard Time' => 'Australia/Sydney', 'Tasmania Standard Time' => 'Australia/Hobart', 'West Pacific Standard Time' => 'Pacific/Port_Moresby',
        'New Zealand Standard Time' => 'Pacific/Auckland', 'Fiji Standard Time' => 'Pacific/Fiji', 'Tonga Standard Time' => 'Pacific/Tongatapu',
    ];

    private static ?string $cached = null;

    /** The zone to use for calendar days and local times, cached for this process. */
    public static function get(): string
    {
        return self::$cached ??= self::resolveFrom(config('app.leadpilot_timezone'), static fn (): ?string => self::detect(), config('app.timezone'));
    }

    /** Tests use this to pin a zone (pass null to clear the cache). */
    public static function setForTesting(?string $zone): void
    {
        self::$cached = $zone;
    }

    /** Pick the first valid zone: override, then detected (only worked out if needed), then the app zone, then UTC. */
    public static function resolveFrom(?string $override, callable $detect, ?string $appZone): string
    {
        if (self::valid($override)) {
            return trim($override);
        }
        $detected = $detect();
        if (self::valid($detected)) {
            return trim($detected);
        }

        return self::valid($appZone) ? trim($appZone) : 'UTC';
    }

    /** Ask the operating system for its zone. Returns null when it cannot be worked out. */
    public static function detect(): ?string
    {
        $tz = getenv('TZ');
        if (is_string($tz) && self::valid(ltrim($tz, ':'))) {
            return ltrim($tz, ':');
        }
        if (PHP_OS_FAMILY === 'Windows') {
            $id = self::run(['tzutil', '/g']);
            if ($id === null) {
                $reg = self::run(['reg', 'query', 'HKLM\\SYSTEM\\CurrentControlSet\\Control\\TimeZoneInformation', '/v', 'TimeZoneKeyName']);
                $id = ($reg !== null && preg_match('/TimeZoneKeyName\s+REG_SZ\s+(.+)$/m', $reg, $m)) ? trim($m[1]) : null;
            }

            return $id !== null ? self::fromWindowsId($id) : null;
        }
        $etc = is_readable('/etc/timezone') ? (string) @file_get_contents('/etc/timezone') : null;
        $link = is_link('/etc/localtime') ? (string) @readlink('/etc/localtime') : null;

        return self::fromUnix($etc, $link);
    }

    public static function fromWindowsId(string $id): ?string
    {
        $id = trim($id);
        if ($id === '') {
            return null;
        }
        if (class_exists(IntlTimeZone::class)) {
            $iana = IntlTimeZone::getIDForWindowsID($id);
            if (is_string($iana) && self::valid($iana)) {
                return $iana;
            }
        }
        $iana = self::WINDOWS_TO_IANA[$id] ?? null;

        return self::valid($iana) ? $iana : null;
    }

    public static function fromUnix(?string $etcTimezone, ?string $localtimeLink): ?string
    {
        $zone = trim((string) $etcTimezone);
        if (self::valid($zone)) {
            return $zone;
        }
        if ($localtimeLink && preg_match('#zoneinfo/(.+)$#', $localtimeLink, $m) && self::valid($m[1])) {
            return $m[1];
        }

        return null;
    }

    public static function valid(?string $zone): bool
    {
        if (! is_string($zone) || trim($zone) === '') {
            return false;
        }
        try {
            new DateTimeZone(trim($zone));

            return ! preg_match('/^[+-]\d/', trim($zone));
        } catch (Throwable) {
            return false;
        }
    }

    /** Run a fixed command without a shell and return its output, or null on any problem. */
    private static function run(array $command): ?string
    {
        try {
            $process = @proc_open($command, [1 => ['pipe', 'w'], 2 => ['pipe', 'w']], $pipes, null, null, ['bypass_shell' => true]);
            if (! is_resource($process)) {
                return null;
            }
            $output = stream_get_contents($pipes[1]);
            fclose($pipes[1]);
            fclose($pipes[2]);
            $code = proc_close($process);

            return ($code === 0 && is_string($output) && trim($output) !== '') ? trim($output) : null;
        } catch (Throwable) {
            return null;
        }
    }
}
