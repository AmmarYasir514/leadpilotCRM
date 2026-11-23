const words = s => (s.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
export function keywordMatches(title, description, input) {
  const targets = [...new Set((input || '').split(',').map(s => s.trim()).filter(Boolean))];
  const titleWords = words(title || ''), descriptionWords = words(description || '');
  const phrase = (haystack, needle) => needle.length > 0 && haystack.some((_, i) => needle.every((word, j) => haystack[i+j] === word));
  const matches = targets.map(keyword => {
    const terms = words(keyword);
    const exact = phrase(titleWords, terms);
    const matched = [...new Set(terms.filter(w => w.length >= 3 && titleWords.includes(w)))];
    const partial = !exact && terms.length > 1 && matched.length > 0;
    const descriptionMatch = phrase(descriptionWords, terms);
    const fraction = exact || descriptionMatch ? 1 : partial ? matched.length / new Set(terms).size : 0;
    return {keyword, exact, partial, descriptionMatch, fraction, highlightWords: exact ? terms : partial ? matched : []};
  });
  return {matches, fraction: targets.length ? matches.reduce((a,m)=>a+m.fraction,0)/targets.length : null, highlightWords: [...new Set(matches.flatMap(m=>m.highlightWords))]};
}
export function titleParts(title, highlightWords) {
  const highlight = new Set(highlightWords);
  return (title || '').split(/([\p{L}\p{N}]+)/gu).filter(Boolean).map(text=>({text, matched:highlight.has(text.toLocaleLowerCase())}));
}
