import test from 'node:test';
import assert from 'node:assert/strict';
import {keywordMatches,titleParts} from '../resources/js/jobKeywordMatch.mjs';
test('title exact and partial matches share the existing keyword points',()=>{
 const r=keywordMatches('Shopify expert for a new store','','Shopify, Shopify development, WordPress');
 assert.deepEqual(r.matches.map(m=>[m.exact,m.partial,m.fraction]),[[true,false,1],[false,true,.5],[false,false,0]]);
 assert.equal(r.fraction,.5);
 assert.equal(titleParts('Shopify expert',r.highlightWords)[0].matched,true);
});
test('matches use whole words and description matches retain credit',()=>{
 assert.equal(keywordMatches('Shopify expert','','shop').fraction,0);
 assert.equal(keywordMatches('A job','Build a Shopify store','Shopify store').fraction,1);
 assert.equal(keywordMatches('A job','','').fraction,null);
});
