"""
GHOST Query Expansion — Multi-language keyword extraction and search expansion.

Improves memory search recall by:
  1. Extracting meaningful keywords from conversational queries
  2. Removing stopwords across multiple languages (EN, ES, PT, AR, ZH, JA, KO)
  3. Generating stemming variants for English terms
  4. Handling CJK text (character n-grams for Chinese, particle stripping for Korean)
  5. Optional LLM-powered expansion for richer related-term discovery
"""

import re
import unicodedata
from typing import Callable, Optional

# ═══════════════════════════════════════════════════════════════════════
#  STOPWORDS — multi-language
# ═══════════════════════════════════════════════════════════════════════

_STOPWORDS_EN = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had", "having",
    "i", "me", "my", "myself", "you", "your", "yourself", "we", "our",
    "they", "their", "them", "he", "she", "it", "its", "his", "her",
    "this", "that", "these", "those", "what", "which", "who", "whom",
    "how", "when", "where", "why", "can", "could", "will", "would",
    "shall", "should", "may", "might", "must",
    "of", "in", "on", "at", "to", "for", "with", "by", "from", "about",
    "and", "or", "not", "no", "but", "if", "so", "as", "up", "out",
    "just", "also", "than", "then", "too", "very", "really", "quite",
    "don", "t", "s", "re", "ve", "ll", "d", "m", "ain",
    "there", "here", "some", "any", "all", "each", "every", "both",
    "few", "more", "most", "other", "into", "through", "during",
    "before", "after", "above", "below", "between", "under", "again",
    "once", "further", "same", "own", "such", "only", "over",
    "get", "got", "getting", "go", "going", "went", "gone",
    "make", "made", "know", "knew", "known", "think", "thought",
    "tell", "told", "find", "found", "give", "gave", "take", "took",
    "come", "came", "see", "saw", "look", "want", "need", "use", "try",
    "thing", "something", "anything", "everything", "nothing",
    "remember", "recall", "mentioned", "talked", "said", "asked",
})

_STOPWORDS_ES = frozenset({
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "en", "con", "por", "para", "que", "es", "son",
    "y", "o", "pero", "como", "más", "muy", "no", "se", "su",
    "al", "lo", "le", "les", "me", "te", "nos",
})

_STOPWORDS_PT = frozenset({
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "com", "por", "para", "que", "é", "são", "e", "ou", "mas",
    "como", "mais", "muito", "não", "se", "seu", "sua",
})

_STOPWORDS_AR = frozenset({
    "في", "من", "على", "إلى", "عن", "مع", "هو", "هي",
    "هذا", "هذه", "ذلك", "تلك", "التي", "الذي", "ما", "كيف",
    "أن", "لا", "نعم", "و", "أو", "ثم", "لكن", "إذا",
    "كان", "كانت", "هل", "قد", "لم", "لن", "حتى",
})

_ALL_STOPWORDS = _STOPWORDS_EN | _STOPWORDS_ES | _STOPWORDS_PT | _STOPWORDS_AR

# Korean particles to strip from ends of words
_KO_PARTICLES = re.compile(
    r'(은|는|이|가|을|를|에|에서|으로|로|와|과|의|도|만|까지|부터|라고|하고)$'
)

_CJK_RANGE = re.compile(
    r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff'
    r'\U00020000-\U0002a6df\U0002a700-\U0002b73f]'
)

_HANGUL_RANGE = re.compile(r'[\uac00-\ud7af]')

_CONVERSATIONAL_PREFIXES = re.compile(
    r'^(what\s+(?:was|is|are|were)\s+(?:that|the)\s+(?:thing|stuff|part)\s+about\s*)'
    r'|(^(?:do\s+you\s+)?remember\s+(?:when|that|the)\s*)'
    r'|(^(?:tell|show)\s+me\s+(?:about|what)\s*)'
    r'|(^(?:find|search\s+for|look\s+(?:up|for))\s*)',
    re.IGNORECASE,
)

# Simple English suffix stemming rules
_STEM_RULES = [
    (re.compile(r'ies$'), 'y'),
    (re.compile(r'(s|x|z|ch|sh)es$'), r'\1'),
    (re.compile(r'([^s])s$'), r'\1'),
    (re.compile(r'ied$'), 'y'),
    (re.compile(r'(ed|ing)$'), ''),
    (re.compile(r'ation$'), 'ate'),
    (re.compile(r'ness$'), ''),
    (re.compile(r'ment$'), ''),
    (re.compile(r'able$'), ''),
    (re.compile(r'ible$'), ''),
    (re.compile(r'ful$'), ''),
    (re.compile(r'less$'), ''),
    (re.compile(r'ously$'), 'ous'),
    (re.compile(r'ively$'), 'ive'),
    (re.compile(r'ly$'), ''),
]


def _simple_stem(word: str) -> str:
    """Apply simple suffix-stripping stemming. Returns stem if >= 3 chars."""
    if len(word) <= 3:
        return word
    for pattern, replacement in _STEM_RULES:
        stemmed = pattern.sub(replacement, word)
        if stemmed != word and len(stemmed) >= 3:
            return stemmed
    return word


def _is_cjk(char: str) -> bool:
    return bool(_CJK_RANGE.match(char))


def _is_hangul(char: str) -> bool:
    return bool(_HANGUL_RANGE.match(char))


def _extract_cjk_ngrams(text: str, n: int = 2) -> list[str]:
    """Extract character-level n-grams from CJK text for FTS matching."""
    cjk_chars = [c for c in text if _is_cjk(c)]
    if len(cjk_chars) <= n:
        return ["".join(cjk_chars)] if cjk_chars else []
    return ["".join(cjk_chars[i:i + n]) for i in range(len(cjk_chars) - n + 1)]


def _strip_korean_particles(word: str) -> str:
    """Strip common Korean grammatical particles from word endings."""
    return _KO_PARTICLES.sub('', word)


# ═══════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════════════

def extract_keywords(query: str) -> list[str]:
    """Extract meaningful keywords from a conversational search query.

    Handles:
      - Conversational prefix stripping ("what was that thing about X" -> X terms)
      - Multi-language stopword removal (EN, ES, PT, AR)
      - CJK character n-gram extraction
      - Korean particle stripping
      - Deduplication while preserving order
    """
    if not query or not query.strip():
        return []

    text = _CONVERSATIONAL_PREFIXES.sub('', query).strip()
    if not text:
        text = query

    keywords: list[str] = []
    seen: set[str] = set()

    cjk_ngrams = _extract_cjk_ngrams(text)
    for ng in cjk_ngrams:
        if ng not in seen:
            keywords.append(ng)
            seen.add(ng)

    hangul_words = []
    ascii_text = re.sub(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]', ' ', text)

    tokens = re.findall(r'[\w\u0600-\u06ff\uac00-\ud7af]+', ascii_text.lower())

    for tok in tokens:
        if _is_hangul(tok[0]) if tok else False:
            stripped = _strip_korean_particles(tok)
            if stripped and stripped not in seen:
                hangul_words.append(stripped)
                seen.add(stripped)
            continue

        if tok in _ALL_STOPWORDS or len(tok) <= 1:
            continue
        if tok not in seen:
            keywords.append(tok)
            seen.add(tok)

    keywords.extend(hangul_words)
    return keywords


def expand_query_for_fts(query: str) -> dict:
    """Expand a query for FTS5 search with stemming variants.

    Returns:
        {
            "original": the raw query,
            "keywords": extracted keyword list,
            "expanded": FTS5 OR expression with original terms + stems,
        }
    """
    keywords = extract_keywords(query)
    if not keywords:
        text = re.sub(r"[^\w\s]", " ", query)
        fallback = [w for w in text.lower().split() if len(w) > 1][:5]
        return {
            "original": query,
            "keywords": fallback,
            "expanded": " OR ".join(f'"{w}"' for w in fallback) if fallback else "",
        }

    all_terms: list[str] = []
    seen: set[str] = set()

    for kw in keywords:
        if kw not in seen:
            all_terms.append(kw)
            seen.add(kw)

        stem = _simple_stem(kw)
        if stem != kw and stem not in seen and len(stem) >= 3:
            all_terms.append(stem)
            seen.add(stem)

    expanded = " OR ".join(f'"{t}"' for t in all_terms)
    return {
        "original": query,
        "keywords": keywords,
        "expanded": expanded,
    }


async def expand_query_with_llm(
    query: str,
    llm_fn: Optional[Callable] = None,
) -> list[str]:
    """Optionally expand a query using an LLM for richer related terms.

    Args:
        query: The user's search query.
        llm_fn: Async callable(prompt: str) -> str. If None, falls back to
                keyword extraction only.

    Returns:
        List of expanded search terms (original keywords + LLM suggestions).
    """
    keywords = extract_keywords(query)

    if llm_fn is None:
        return keywords

    prompt = (
        f"Given this memory search query: \"{query}\"\n"
        f"Keywords extracted: {', '.join(keywords)}\n\n"
        "Suggest 3-5 additional search terms (single words or short phrases) "
        "that would help find relevant memories. Focus on synonyms, related "
        "concepts, and alternative phrasings. Return ONLY the terms, one per line."
    )

    try:
        response = await llm_fn(prompt)
        suggestions = [
            line.strip().strip('- ').strip('"').strip("'").lower()
            for line in response.strip().split('\n')
            if line.strip() and len(line.strip()) > 1
        ]
        suggestions = [s for s in suggestions if s not in _ALL_STOPWORDS][:5]

        seen = set(keywords)
        for s in suggestions:
            if s not in seen:
                keywords.append(s)
                seen.add(s)
    except Exception:
        pass

    return keywords
