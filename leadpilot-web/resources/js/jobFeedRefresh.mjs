export function randomRefreshDelay(random = Math.random) {
  return 180000 + Math.floor(random() * 420001);
}

function jobKey(job) {
  if (typeof job?.url !== 'string') return null;
  try {
    const url = new URL(job.url);
    if (url.hostname !== 'upwork.com' && !url.hostname.endsWith('.upwork.com')) return null;
    const id = url.pathname.match(/~0[0-9]{10,}/)?.[0];
    return id ? `id:${id}` : `url:${url.pathname.replace(/\/$/, '')}`;
  } catch { return null; }
}

export function mergeJobFeeds(recent, matches) {
  const seen = new Set();
  return [...recent, ...matches].filter(job => {
    const key = jobKey(job);
    if (key && seen.has(key)) return false;
    if (key) seen.add(key);
    return true;
  });
}

export function updateRollingJobs(current, recent, matches) {
  const incoming = mergeJobFeeds(recent, matches);
  const currentKeys = new Set(current.map(jobKey).filter(Boolean));
  const latestByKey = new Map(incoming.map(job => [jobKey(job), job]).filter(([key]) => key));
  const added = incoming.filter(job => { const key = jobKey(job); return !key || !currentKeys.has(key); });
  return [...added, ...current.map(job => latestByKey.get(jobKey(job)) || job)].slice(0, 100);
}
