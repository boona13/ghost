"""Text Statistics Analyzer - Pure Python text analysis tool.

Analyzes text and returns: word count, character count, sentence count,
average word length, reading time estimate, and top N most frequent words.
"""

import json
import re
from collections import Counter


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def text_stats(text: str, top_n: int = 10, **kwargs):
        """Analyze text and return statistics.
        
        Args:
            text: The text to analyze
            top_n: Number of most frequent words to return (default: 10)
        """
        if not text or not isinstance(text, str):
            return json.dumps({
                "error": "Invalid input: text must be a non-empty string"
            })
        
        # Validate top_n to prevent negative values
        if not isinstance(top_n, int) or top_n < 0:
            return json.dumps({
                "error": "Invalid input: top_n must be a non-negative integer"
            })
        
        # Basic counts
        char_count = len(text)
        char_count_no_spaces = len(text.replace(" ", "").replace("\n", "").replace("\t", ""))
        
        # Word analysis
        words = re.findall(r"\b\w+\b", text.lower())
        word_count = len(words)
        avg_word_length = sum(len(w) for w in words) / word_count if word_count > 0 else 0
        
        # Sentence count (split by .!? followed by space or end)
        sentences = re.split(r'[.!?]+', text)
        sentence_count = len([s for s in sentences if s.strip()]) if sentences else 0
        
        # Reading time estimate (average 200 words per minute)
        reading_time_minutes = word_count / 200.0 if word_count > 0 else 0
        
        # Top N frequent words (exclude common stop words)
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them'}
        filtered_words = [w for w in words if w not in stop_words and len(w) > 2]
        word_freq = Counter(filtered_words).most_common(top_n) if filtered_words else []
        
        result = {
            "word_count": word_count,
            "character_count": char_count,
            "character_count_no_spaces": char_count_no_spaces,
            "sentence_count": sentence_count,
            "average_word_length": round(avg_word_length, 2),
            "reading_time_minutes": round(reading_time_minutes, 2),
            "top_words": [{"word": w, "count": c} for w, c in word_freq]
        }
        
        api.log(f"Analyzed text: {word_count} words, {sentence_count} sentences")
        return json.dumps(result, indent=2)

    api.register_tool({
        "name": "text_stats",
        "description": "Analyze text and return statistics: word count, character count, sentence count, average word length, reading time estimate, and top N most frequent words.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "The text to analyze"
                },
                "top_n": {
                    "type": "integer",
                    "description": "Number of most frequent words to return (default: 10)",
                    "default": 10
                }
            },
            "required": ["text"]
        },
        "execute": text_stats
    })
