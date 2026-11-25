export function randomRefreshDelay(random?: () => number): number;

export function mergeJobFeeds<T extends {url?: string}>(recent: T[], matches: T[]): T[];

export function updateRollingJobs<T extends {url?: string}>(current: T[], recent: T[], matches: T[]): T[];
