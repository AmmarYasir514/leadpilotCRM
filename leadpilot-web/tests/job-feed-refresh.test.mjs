import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeJobFeeds, randomRefreshDelay} from '../resources/js/jobFeedRefresh.mjs';

test('refresh interval stays between three and ten minutes', () => {
  assert.equal(randomRefreshDelay(() => 0), 180000);
  assert.equal(randomRefreshDelay(() => 0.999999999), 600000);
});
test('merges both feeds by Upwork job identity without conflating unknown jobs', () => {
  const recent = [{title:'Recent',url:'https://www.upwork.com/jobs/~0123456789012345?x=1'}, {title:'Unknown'}];
  const matches = [{title:'Same job',url:'https://www.upwork.com/nx/jobs/details/~0123456789012345'}, {title:'Unknown'}, {title:'Different',url:'https://www.upwork.com/jobs/~0987654321098765'}];
  assert.deepEqual(mergeJobFeeds(recent,matches).map(j=>j.title), ['Recent','Unknown','Unknown','Different']);
});
import {updateRollingJobs} from '../resources/js/jobFeedRefresh.mjs';
test('rolling feed adds new jobs above existing, updates known jobs, and caps at one hundred',()=>{
 const job=(n)=>({url:`https://www.upwork.com/jobs/~0${String(n).padStart(12,'0')}`, title:`Job ${n}`});
 const existing=Array.from({length:100},(_,n)=>job(n));
 const updated=updateRollingJobs(existing,[job(100),{...job(1),title:'Updated job'}],[job(100)]);
 assert.equal(updated.length,100);assert.equal(updated[0].title,'Job 100');assert.equal(updated[2].title,'Updated job');assert.ok(!updated.some(j=>j.title==='Job 99'));
});
