"""SQLite Database Explorer - explore and query SQLite databases safely.

Provides read-only exploration of SQLite databases: schema inspection,
safe querying (SELECT only), and database statistics.
"""

import json
import os
import sqlite3
from pathlib import Path


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def db_schema(path: str, **kwargs):
        """Get complete schema information for a SQLite database.
        
        Args:
            path: Path to the SQLite database file
        """
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            return json.dumps({"error": f"Database file not found: {path}"})
        
        try:
            conn = sqlite3.connect(f"file:{path_obj}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
            tables = cursor.fetchall()
            
            result = {"database": str(path_obj), "tables": []}
            
            for table_row in tables:
                table_name = table_row["name"]
                
                # Get column info
                cursor.execute(f'PRAGMA table_info("{table_name}")')
                columns = cursor.fetchall()
                
                # Get foreign keys
                cursor.execute(f'PRAGMA foreign_key_list("{table_name}")')
                foreign_keys = cursor.fetchall()
                fk_map = {fk["from"]: fk["table"] + "." + fk["to"] for fk in foreign_keys}
                
                # Get row count
                cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
                row_count = cursor.fetchone()[0]
                
                table_info = {
                    "name": table_name,
                    "row_count": row_count,
                    "columns": [
                        {
                            "name": col["name"],
                            "type": col["type"],
                            "nullable": not col["notnull"],
                            "primary_key": bool(col["pk"]),
                            "foreign_key": fk_map.get(col["name"], None)
                        }
                        for col in columns
                    ]
                }
                result["tables"].append(table_info)
            
            conn.close()
            api.log(f"Retrieved schema for {len(result['tables'])} tables from {path_obj.name}")
            return json.dumps(result, indent=2)
            
        except sqlite3.Error as e:
            return json.dumps({"error": f"SQLite error: {str(e)}"})

    api.register_tool({
        "name": "db_schema",
        "description": "Get complete schema information for a SQLite database: all tables with columns, types, primary keys, foreign keys, and row counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the SQLite database file"}
            },
            "required": ["path"]
        },
        "execute": db_schema
    })

    def db_query(path: str, sql: str, params: list = None, limit: int = 100, **kwargs):
        """Execute a read-only SELECT query against a SQLite database.
        
        Args:
            path: Path to the SQLite database file
            sql: SQL query (SELECT only - INSERT/UPDATE/DELETE/DROP/ALTER/CREATE are rejected)
            params: Optional list of query parameters
            limit: Maximum rows to return (default: 100)
        """
        if params is None:
            params = []
        
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            return json.dumps({"error": f"Database file not found: {path}"})
        
        # SECURITY: Only allow SELECT statements
        sql_stripped = sql.strip()
        first_word = sql_stripped.split()[0].upper() if sql_stripped else ""
        if first_word != "SELECT":
            return json.dumps({
                "error": "Only SELECT queries are allowed. INSERT, UPDATE, DELETE, DROP, ALTER, and CREATE are prohibited."
            })
        
        try:
            conn = sqlite3.connect(f"file:{path_obj}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Add LIMIT if not present
            sql_upper = sql_stripped.upper()
            if "LIMIT" not in sql_upper:
                sql_stripped = f"{sql_stripped} LIMIT {limit}"
            
            cursor.execute(sql_stripped, params)
            rows = cursor.fetchall()
            
            # Convert to list of dicts
            results = [dict(row) for row in rows]
            
            conn.close()
            api.log(f"Executed SELECT query on {path_obj.name}, returned {len(results)} rows")
            return json.dumps({
                "row_count": len(results),
                "rows": results
            }, indent=2, default=str)
            
        except sqlite3.Error as e:
            return json.dumps({"error": f"SQLite error: {str(e)}"})

    api.register_tool({
        "name": "db_query",
        "description": "Execute a read-only SELECT query against a SQLite database. Returns results as list of dicts. Only SELECT statements allowed - all modifying queries are rejected for security.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the SQLite database file"},
                "sql": {"type": "string", "description": "SQL query (SELECT only)"},
                "params": {"type": "array", "description": "Optional query parameters", "default": []},
                "limit": {"type": "integer", "description": "Maximum rows to return", "default": 100}
            },
            "required": ["path", "sql"]
        },
        "execute": db_query
    })

    def db_stats(path: str, **kwargs):
        """Get database statistics: file size, table count, total rows, index count.
        
        Args:
            path: Path to the SQLite database file
        """
        path_obj = Path(path).expanduser().resolve()
        if not path_obj.exists():
            return json.dumps({"error": f"Database file not found: {path}"})
        
        try:
            conn = sqlite3.connect(f"file:{path_obj}?mode=ro", uri=True)
            cursor = conn.cursor()
            
            # File size
            file_size = path_obj.stat().st_size
            
            # Table count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]
            
            # Index count
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index'")
            index_count = cursor.fetchone()[0]
            
            # Total rows across all tables
            total_rows = 0
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            for row in cursor.fetchall():
                try:
                    cursor.execute(f'SELECT COUNT(*) FROM "{row[0]}"')
                    total_rows += cursor.fetchone()[0]
                except sqlite3.Error:
                    pass
            
            conn.close()
            
            result = {
                "database": str(path_obj),
                "file_size_bytes": file_size,
                "file_size_human": f"{file_size / 1024:.1f} KB" if file_size < 1024*1024 else f"{file_size / (1024*1024):.2f} MB",
                "table_count": table_count,
                "index_count": index_count,
                "total_rows": total_rows
            }
            
            api.log(f"Retrieved stats for {path_obj.name}: {table_count} tables, {total_rows} rows")
            return json.dumps(result, indent=2)
            
        except sqlite3.Error as e:
            return json.dumps({"error": f"SQLite error: {str(e)}"})

    api.register_tool({
        "name": "db_stats",
        "description": "Get database statistics: file size, table count, total rows, and index count for a SQLite database.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the SQLite database file"}
            },
            "required": ["path"]
        },
        "execute": db_stats
    })