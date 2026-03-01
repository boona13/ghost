"""
ghost_data_extract.py - Intelligent data extraction from unstructured text

Extracts structured information like emails, phones, dates, prices, tables,
and custom entities from any text source.
"""

import re
import json
from typing import Optional, Dict, Any, List, Tuple, Pattern
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ExtractionRule:
    """A rule for extracting data."""
    name: str
    pattern: str
    extractor: callable
    confidence: float = 1.0


class DataExtractor:
    """Extract structured data from unstructured text."""
    
    # Common extraction patterns
    PATTERNS = {
        "email": re.compile(
            r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
            re.IGNORECASE
        ),
        "phone": re.compile(
            r'(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})',
            re.IGNORECASE
        ),
        "url": re.compile(
            r'https?://(?:[-\w.])+(?:[:\d]+)?(?:/(?:[\w/_.()])*(?:\?(?:[\w&=%.()])*)?(?:#(?:[\w.()])*)?)?',
            re.IGNORECASE
        ),
        "ip_address": re.compile(
            r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b'
        ),
        "date_iso": re.compile(
            r'\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?'
        ),
        "date_us": re.compile(
            r'\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12]\d|3[01])[/-](?:19|20)?\d{2}\b'
        ),
        "price": re.compile(
            r'(?:[$€£¥]\s*)?\d{1,3}(?:,\d{3})*(?:\.\d{2})?(?:\s*(?:USD|EUR|GBP|JPY))?',
            re.IGNORECASE
        ),
        "percentage": re.compile(
            r'\d{1,3}(?:\.\d+)?\s*%'
        ),
        "credit_card": re.compile(
            r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
        ),
        "ssn": re.compile(
            r'\b\d{3}-\d{2}-\d{4}\b'
        ),
        "hashtag": re.compile(
            r'#\w+',
            re.IGNORECASE
        ),
        "mention": re.compile(
            r'@\w+',
            re.IGNORECASE
        ),
        "uuid": re.compile(
            r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
            re.IGNORECASE
        ),
        "api_key": re.compile(
            r'\b(?:sk-|pk-|Bearer\s+)[a-zA-Z0-9_-]{20,}\b',
            re.IGNORECASE
        ),
    }
    
    def __init__(self):
        self.custom_patterns = {}
    
    def extract_all(self, text: str, types: List[str] = None) -> Dict[str, List[str]]:
        """
        Extract all supported data types from text.
        
        Args:
            text: Source text
            types: List of types to extract (None = all)
            
        Returns:
            Dict mapping type names to lists of extracted values
        """
        results = {}
        types_to_extract = types or list(self.PATTERNS.keys())
        
        for data_type in types_to_extract:
            if data_type in self.PATTERNS:
                pattern = self.PATTERNS[data_type]
                matches = pattern.findall(text)
                
                # Handle tuple results (groups)
                if matches and isinstance(matches[0], tuple):
                    matches = [''.join(m) for m in matches]
                
                # Deduplicate while preserving order
                seen = set()
                unique = []
                for m in matches:
                    if m not in seen:
                        seen.add(m)
                        unique.append(m)
                
                if unique:
                    results[data_type] = unique
        
        return results
    
    def extract_emails(self, text: str) -> List[Dict[str, Any]]:
        """Extract emails with validation and context."""
        matches = self.PATTERNS["email"].finditer(text)
        results = []
        
        for match in matches:
            email = match.group()
            line_num = text[:match.start()].count('\n') + 1
            
            # Get surrounding context
            start = max(0, match.start() - 50)
            end = min(len(text), match.end() + 50)
            context = text[start:end]
            
            results.append({
                "value": email,
                "line": line_num,
                "context": context,
                "domain": email.split('@')[1] if '@' in email else None,
                "confidence": 1.0
            })
        
        return results
    
    def extract_phones(self, text: str) -> List[Dict[str, Any]]:
        """Extract phone numbers with formatting."""
        matches = self.PATTERNS["phone"].finditer(text)
        results = []
        
        for match in matches:
            phone = match.group()
            line_num = text[:match.start()].count('\n') + 1
            
            # Normalize to standard format
            digits = re.sub(r'\D', '', phone)
            if len(digits) == 10:
                normalized = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits[0] == '1':
                normalized = f"+1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            else:
                normalized = phone
            
            results.append({
                "value": phone,
                "normalized": normalized,
                "digits_only": digits,
                "line": line_num,
                "confidence": 0.9 if len(digits) >= 10 else 0.5
            })
        
        return results
    
    def extract_prices(self, text: str) -> List[Dict[str, Any]]:
        """Extract prices with currency detection."""
        matches = self.PATTERNS["price"].finditer(text)
        results = []
        
        currency_map = {
            '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY',
            'USD': 'USD', 'EUR': 'EUR', 'GBP': 'GBP', 'JPY': 'JPY'
        }
        
        for match in matches:
            price_str = match.group()
            line_num = text[:match.start()].count('\n') + 1
            
            # Detect currency
            currency = None
            for symbol, code in currency_map.items():
                if symbol in price_str:
                    currency = code
                    break
            
            # Extract numeric value
            numeric = re.sub(r'[^\d.]', '', price_str)
            try:
                value = float(numeric) if numeric else 0
            except (ValueError, TypeError):
                value = 0
            
            results.append({
                "original": price_str,
                "value": value,
                "currency": currency or "unknown",
                "line": line_num
            })
        
        return results
    
    def extract_table(self, text: str, delimiter: str = None) -> Optional[Dict[str, Any]]:
        """
        Extract a table from text (markdown, CSV, or space-aligned).
        
        Args:
            text: Text containing table
            delimiter: Explicit delimiter (auto-detected if None)
            
        Returns:
            Dict with headers and rows
        """
        lines = text.strip().split('\n')
        
        # Try markdown table
        if '|' in text:
            return self._extract_markdown_table(lines)
        
        # Try CSV
        if ',' in text or delimiter == ',':
            return self._extract_csv_table(lines, delimiter or ',')
        
        # Try space/tab aligned
        return self._extract_aligned_table(lines)
    
    def _extract_markdown_table(self, lines: List[str]) -> Optional[Dict]:
        """Extract markdown format table."""
        # Find table lines
        table_lines = []
        for line in lines:
            if '|' in line:
                table_lines.append(line)
        
        if len(table_lines) < 2:
            return None
        
        # Parse header
        header_line = table_lines[0]
        headers = [h.strip() for h in header_line.split('|') if h.strip()]
        
        # Skip separator line if present
        data_start = 1
        if len(table_lines) > 1 and '---' in table_lines[1]:
            data_start = 2
        
        # Parse data rows
        rows = []
        for line in table_lines[data_start:]:
            cells = [c.strip() for c in line.split('|') if c.strip() or c == '']
            # Pad to match header length
            while len(cells) < len(headers):
                cells.append('')
            rows.append(dict(zip(headers, cells[:len(headers)])))
        
        return {
            "format": "markdown",
            "headers": headers,
            "rows": rows,
            "row_count": len(rows)
        }
    
    def _extract_csv_table(self, lines: List[str], delimiter: str) -> Optional[Dict]:
        """Extract CSV format table."""
        if not lines:
            return None
        
        import csv
        from io import StringIO
        
        try:
            reader = csv.DictReader(StringIO('\n'.join(lines)), delimiter=delimiter)
            rows = list(reader)
            headers = reader.fieldnames or []
            
            return {
                "format": "csv",
                "headers": headers,
                "rows": rows,
                "row_count": len(rows)
            }
        except Exception:
            return None
    
    def _extract_aligned_table(self, lines: List[str]) -> Optional[Dict]:
        """Extract space/tab aligned table."""
        if len(lines) < 2:
            return None
        
        # Simple approach: split on multiple spaces or tabs
        rows = []
        for line in lines:
            # Split on 2+ spaces or tabs
            cells = re.split(r'\s{2,}|\t', line.strip())
            cells = [c.strip() for c in cells if c.strip()]
            if cells:
                rows.append(cells)
        
        if not rows:
            return None
        
        # Assume first row is headers
        headers = rows[0]
        data_rows = []
        for row in rows[1:]:
            while len(row) < len(headers):
                row.append('')
            data_rows.append(dict(zip(headers, row[:len(headers)])))
        
        return {
            "format": "aligned",
            "headers": headers,
            "rows": data_rows,
            "row_count": len(data_rows)
        }
    
    def add_custom_pattern(self, name: str, pattern: str, flags: int = 0):
        """Add a custom extraction pattern."""
        try:
            compiled = re.compile(pattern, flags)
            self.custom_patterns[name] = compiled
            return True
        except re.error as e:
            return {"error": f"Invalid regex: {str(e)}"}
    
    def extract_with_custom(self, text: str, pattern_name: str) -> List[str]:
        """Extract using a custom pattern."""
        if pattern_name not in self.custom_patterns:
            return []
        
        pattern = self.custom_patterns[pattern_name]
        matches = pattern.findall(text)
        
        # Handle tuple results
        if matches and isinstance(matches[0], tuple):
            matches = [''.join(m) for m in matches]
        
        return list(set(matches))


def make_smart_extract():
    """Create the smart_extract tool."""
    
    def execute(text: str, extract_types: List[str] = None):
        """
        Automatically extract structured data from text.
        
        Args:
            text: Source text to analyze
            extract_types: Types to extract (email, phone, url, price, date, etc.)
                          Default: all types
                          
        Returns:
            Dict with extracted data organized by type
        """
        extractor = DataExtractor()
        
        # Default to all types if not specified
        if not extract_types:
            extract_types = list(extractor.PATTERNS.keys())
        
        results = extractor.extract_all(text, extract_types)
        
        # Add metadata
        return {
            "extracted_data": results,
            "types_found": list(results.keys()),
            "total_extractions": sum(len(v) for v in results.values()),
            "input_length": len(text),
            "summary": _generate_extraction_summary(results)
        }
    
    def _generate_extraction_summary(results: Dict) -> str:
        """Generate human-readable summary."""
        parts = []
        for data_type, values in results.items():
            if values:
                parts.append(f"{len(values)} {data_type}(s)")
        
        if parts:
            return f"Found: {', '.join(parts)}"
        return "No structured data found"
    
    return {
        "name": "smart_extract",
        "description": "Automatically extract emails, phones, URLs, prices, dates, and other structured data from any text.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to extract data from"},
                "extract_types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Types to extract: email, phone, url, price, date, ip_address, hashtag, mention, etc."
                }
            },
            "required": ["text"]
        },
        "execute": execute
    }


def build_data_extract_tools():
    """Build data extraction tools for the ghost tool registry."""
    return [make_smart_extract(), make_extract_data(), make_extract_table()]


def make_extract_data():
    """Create the extract_data tool for specific patterns."""
    
    def execute(text: str, pattern: str, name: str = "match"):
        """
        Extract data using a custom regex pattern.
        
        Args:
            text: Source text
            pattern: Regex pattern to match
            name: Name for the extracted data type
            
        Returns:
            List of matches with context
        """
        try:
            compiled = re.compile(pattern, re.IGNORECASE | re.MULTILINE)
        except re.error as e:
            return {"error": f"Invalid regex pattern: {str(e)}"}
        
        matches = compiled.finditer(text)
        results = []
        
        for match in matches:
            line_num = text[:match.start()].count('\n') + 1
            
            # Get context (line containing match)
            lines = text.split('\n')
            context = lines[line_num - 1] if line_num <= len(lines) else ""
            
            results.append({
                "value": match.group(),
                "groups": match.groups(),
                "line": line_num,
                "context": context.strip(),
                "start": match.start(),
                "end": match.end()
            })
        
        return {
            "pattern": pattern,
            "data_type": name,
            "matches": results,
            "count": len(results)
        }
    
    return {
        "name": "extract_data",
        "description": "Extract data using a custom regex pattern with context and line numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to search"},
                "pattern": {"type": "string", "description": "Regex pattern to match"},
                "name": {"type": "string", "default": "match", "description": "Name for this data type"}
            },
            "required": ["text", "pattern"]
        },
        "execute": execute
    }


def make_extract_table():
    """Create the extract_table tool."""
    
    def execute(text: str, format_hint: str = "auto"):
        """
        Extract a table from text (markdown, CSV, or aligned columns).
        
        Args:
            text: Text containing table data
            format_hint: "markdown", "csv", "aligned", or "auto" (detect)
            
        Returns:
            Structured table with headers and rows
        """
        extractor = DataExtractor()
        
        # Override delimiter based on hint
        delimiter = None
        if format_hint == "csv":
            delimiter = ","
        elif format_hint == "tsv":
            delimiter = "\t"
        
        result = extractor.extract_table(text, delimiter)
        
        if result:
            return result
        else:
            return {
                "error": "Could not extract table from text",
                "hint": "Ensure table has consistent delimiters or alignment"
            }
    
    return {
        "name": "extract_table",
        "description": "Extract structured table data from markdown, CSV, or space-aligned text.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text containing table"},
                "format_hint": {
                    "type": "string",
                    "enum": ["auto", "markdown", "csv", "tsv", "aligned"],
                    "default": "auto",
                    "description": "Expected table format"
                }
            },
            "required": ["text"]
        },
        "execute": execute
    }
