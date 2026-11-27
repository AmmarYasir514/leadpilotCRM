<?php

namespace Tests;

use Illuminate\Foundation\Application;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    private static bool $cacheCleanupRegistered = false;

    public function createApplication(): Application
    {
        $app = parent::createApplication();
        if ($app['config']->get('database.default') !== 'sqlite' || $app['config']->get('database.connections.sqlite.database') !== ':memory:' || $app['config']->get('database.connections.sqlite.url')) {
            throw new \RuntimeException('Tests require an isolated in-memory SQLite database.');
        }

        // Tests keep file cache data and locks in a temp folder, never in the real storage/framework/cache folders,
        // so a test run and a live scheduled run can never make each other skip.
        $cacheDir = sys_get_temp_dir().DIRECTORY_SEPARATOR.'lp_test_cache_'.getmypid();
        $app['config']->set('cache.stores.file.path', $cacheDir.DIRECTORY_SEPARATOR.'data');
        $app['config']->set('cache.stores.file.lock_path', $cacheDir.DIRECTORY_SEPARATOR.'locks');
        if (! self::$cacheCleanupRegistered) {
            self::$cacheCleanupRegistered = true;
            register_shutdown_function(static fn () => (new \Illuminate\Filesystem\Filesystem)->deleteDirectory($cacheDir));
        }

        return $app;
    }
}
