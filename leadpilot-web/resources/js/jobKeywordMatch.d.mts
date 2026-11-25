export type KeywordMatch = {
    keyword: string;
    exact: boolean;
    partial: boolean;
    descriptionMatch: boolean;
    fraction: number;
    highlightWords: string[];
};

export type KeywordMatchResult = {
    matches: KeywordMatch[];
    fraction: number | null;
    highlightWords: string[];
};

export function keywordMatches(title: string, description: string, input: string): KeywordMatchResult;

export function titleParts(title: string, highlightWords: string[]): {text: string; matched: boolean}[];
