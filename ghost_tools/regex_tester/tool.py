import json
import re

# Flag mapping for all 6 supported flags
FLAG_MAP = {
    "ignore_case": re.IGNORECASE,
    "multiline": re.MULTILINE,
    "dotall": re.DOTALL,
    "verbose": re.VERBOSE,
    "ascii": re.ASCII,
    "locale": re.LOCALE,
}


def _parse_flags(flags_list):
    """Convert list of flag names to combined regex flags integer."""
    if not flags_list:
        return 0
    combined = 0
    for flag_name in flags_list:
        if flag_name in FLAG_MAP:
            combined |= FLAG_MAP[flag_name]
    return combined


def _generate_explanation(pattern):
    """Generate a human-readable explanation of the regex pattern."""
    explanations = []
    
    # Common pattern components
    if pattern.startswith("^"):
        explanations.append("matches the start of the string")
    if pattern.endswith("$"):
        explanations.append("matches the end of the string")
    
    # Character classes
    if "\\d" in pattern:
        explanations.append("\\d matches any digit (0-9)")
    if "\\w" in pattern:
        explanations.append("\\w matches any word character (letters, digits, underscore)")
    if "\\s" in pattern:
        explanations.append("\\s matches any whitespace character")
    if "." in pattern and "\\." not in pattern:
        explanations.append(". matches any character (except newline unless dotall flag is used)")
    
    # Quantifiers
    if "*" in pattern:
        explanations.append("* matches zero or more of the preceding element")
    if "+" in pattern:
        explanations.append("+ matches one or more of the preceding element")
    if "?" in pattern:
        explanations.append("? matches zero or one of the preceding element")
    if "{" in pattern and "}" in pattern:
        explanations.append("{n,m} matches between n and m occurrences")
    
    # Groups
    if "(" in pattern and ")" in pattern:
        explanations.append("() creates a capture group")
    if "(?:" in pattern:
        explanations.append("(?:) creates a non-capturing group")
    
    if explanations:
        return "This pattern: " + "; ".join(explanations) + "."
    return "This pattern matches text according to the specified regex rules."


def register(api):
    def regex_test(pattern: str, text: str, flags: list = None, **kwargs):
        """
        Test a regular expression pattern against input text.
        
        Args:
            pattern: The regex pattern to test
            text: The text to match against
            flags: List of flag names (ignore_case, multiline, dotall, verbose, ascii, locale)
        
        Returns:
            JSON with match results, capture groups, and pattern explanation
        """
        # Input validation
        if not pattern:
            return json.dumps({"error": "Missing required parameter: pattern"}, indent=2)
        if not text:
            return json.dumps({"error": "Missing required parameter: text"}, indent=2)
        
        # Parse flags
        flags_int = _parse_flags(flags or [])
        flags_used = flags or []
        
        try:
            # Compile the regex pattern
            compiled = re.compile(pattern, flags_int)
        except re.error as e:
            return json.dumps({"error": f"Invalid regex: {str(e)}"}, indent=2)
        
        # Find all matches
        matches = []
        for match in compiled.finditer(text):
            match_data = {
                "full_match": match.group(0),
                "position": [match.start(), match.end()],
                "groups": list(match.groups())
            }
            matches.append(match_data)
        
        # Build result
        result = {
            "pattern": pattern,
            "flags_used": flags_used,
            "match_count": len(matches),
            "matches": matches,
            "explanation": _generate_explanation(pattern)
        }
        
        api.log(f"Tested regex pattern: {pattern} - found {len(matches)} matches")
        return json.dumps(result, indent=2)
    
    api.register_tool({
        "name": "regex_test",
        "description": "Test a regular expression pattern against input text with match highlighting, capture group extraction, and pattern explanations. Supports flags: ignore_case, multiline, dotall, verbose, ascii, locale.",
        "parameters": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "The regular expression pattern to test"
                },
                "text": {
                    "type": "string",
                    "description": "The text to match the pattern against"
                },
                "flags": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["ignore_case", "multiline", "dotall", "verbose", "ascii", "locale"]
                    },
                    "description": "List of regex flags to apply",
                    "default": []
                }
            },
            "required": ["pattern", "text"]
        },
        "execute": regex_test
    })
