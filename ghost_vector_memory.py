"""
ghost_vector_memory.py - Semantic memory with vector embeddings

Enables intelligent memory retrieval using semantic similarity.
Finds related memories even when using different words or phrasing.
"""

import os
import json
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class MemoryEntry:
    """A memory with semantic embedding."""
    id: str
    content: str
    summary: str
    embedding: List[float]
    metadata: Dict[str, Any]
    created_at: str
    memory_type: str
    tags: List[str]
    source: str


class SimpleEmbedding:
    """
    Simple embedding using sentence statistics.
    Not as good as OpenAI embeddings but works offline and is fast.
    """
    
    def __init__(self):
        # Simple vocabulary for basic semantic matching
        self.stopwords = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 
                         'be', 'been', 'being', 'have', 'has', 'had', 
                         'do', 'does', 'did', 'will', 'would', 'could',
                         'should', 'may', 'might', 'must', 'shall', 'can',
                         'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                         'for', 'on', 'with', 'at', 'by', 'from', 'as',
                         'into', 'through', 'during', 'before', 'after',
                         'above', 'below', 'between', 'under', 'and', 'but',
                         'or', 'yet', 'so', 'if', 'because', 'although',
                         'though', 'while', 'where', 'when', 'that', 'which',
                         'who', 'whom', 'whose', 'what', 'this', 'these',
                         'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they',
                         'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his',
                         'its', 'our', 'their', 'mine', 'yours', 'hers', 'ours',
                         'theirs', 'myself', 'yourself', 'himself', 'herself',
                         'itself', 'ourselves', 'yourselves', 'themselves'}
    
    def embed(self, text: str) -> List[float]:
        """
        Create a simple embedding from text.
        Uses word frequency + n-grams for basic semantic capture.
        """
        # Normalize
        text = text.lower()
        
        # Extract words
        words = []
        current = []
        for char in text:
            if char.isalnum():
                current.append(char)
            else:
                if current:
                    word = ''.join(current)
                    if word not in self.stopwords and len(word) > 2:
                        words.append(word)
                    current = []
        if current:
            word = ''.join(current)
            if word not in self.stopwords and len(word) > 2:
                words.append(word)
        
        # Create bigrams
        bigrams = []
        for i in range(len(words) - 1):
            bigrams.append(f"{words[i]}_{words[i+1]}")
        
        # Build feature vector (simple bag of words + bigrams)
        all_features = words + bigrams
        
        # Create a hash-based embedding (deterministic)
        embedding = [0.0] * 128
        for feature in all_features:
            # Hash feature to get index
            h = hashlib.md5(feature.encode()).hexdigest()
            idx = int(h[:8], 16) % 128
            # Weight by frequency
            weight = all_features.count(feature) / len(all_features) if all_features else 0
            embedding[idx] += weight
        
        # Normalize
        magnitude = sum(x**2 for x in embedding) ** 0.5
        if magnitude > 0:
            embedding = [x / magnitude for x in embedding]
        
        return embedding


class VectorMemoryStore:
    """SQLite-backed vector memory store."""
    
    def __init__(self, db_path: Optional[str] = None):
        _default = str(Path.home() / ".ghost" / "vector_memory.db")
        self.db_path = str(db_path) if db_path else _default
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.embedder = SimpleEmbedding()
        self._init_db()
    
    def _init_db(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    summary TEXT,
                    embedding TEXT,  -- JSON array
                    metadata TEXT,  -- JSON
                    created_at TEXT,
                    memory_type TEXT,
                    tags TEXT,  -- JSON array
                    source TEXT
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_type 
                ON memories(memory_type)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_memories_created 
                ON memories(created_at)
            """)
            
            conn.commit()
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        dot = sum(x*y for x, y in zip(a, b))
        mag_a = sum(x**2 for x in a) ** 0.5
        mag_b = sum(x**2 for x in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
    
    def save(self, entry: MemoryEntry) -> str:
        """Save a memory entry."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memories 
                (id, content, summary, embedding, metadata, created_at, memory_type, tags, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.id,
                entry.content,
                entry.summary,
                json.dumps(entry.embedding),
                json.dumps(entry.metadata),
                entry.created_at,
                entry.memory_type,
                json.dumps(entry.tags),
                entry.source
            ))
            conn.commit()
        return entry.id
    
    def search(self, query: str, top_k: int = 5, 
               memory_type: Optional[str] = None,
               tags: Optional[List[str]] = None) -> List[Tuple[MemoryEntry, float]]:
        """
        Search memories by semantic similarity.
        Returns list of (memory, similarity_score) tuples sorted by relevance.
        """
        query_embedding = self.embedder.embed(query)
        
        with sqlite3.connect(self.db_path) as conn:
            # Build query
            sql = "SELECT * FROM memories WHERE 1=1"
            params = []
            
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
        
        # Score all memories by similarity
        results = []
        for row in rows:
            entry = MemoryEntry(
                id=row[0],
                content=row[1],
                summary=row[2],
                embedding=json.loads(row[3]) if row[3] else [],
                metadata=json.loads(row[4]) if row[4] else {},
                created_at=row[5],
                memory_type=row[6],
                tags=json.loads(row[7]) if row[7] else [],
                source=row[8]
            )
            
            # Filter by tags if specified
            if tags and not any(t in entry.tags for t in tags):
                continue
            
            # Calculate similarity
            similarity = self._cosine_similarity(query_embedding, entry.embedding)
            
            if similarity > 0.1:  # Minimum relevance threshold
                results.append((entry, similarity))
        
        # Sort by similarity (descending)
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results[:top_k]
    
    def get_by_id(self, memory_id: str) -> Optional[MemoryEntry]:
        """Get a specific memory by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT * FROM memories WHERE id = ?", (memory_id,)
            )
            row = cursor.fetchone()
            
            if row:
                return MemoryEntry(
                    id=row[0],
                    content=row[1],
                    summary=row[2],
                    embedding=json.loads(row[3]) if row[3] else [],
                    metadata=json.loads(row[4]) if row[4] else {},
                    created_at=row[5],
                    memory_type=row[6],
                    tags=json.loads(row[7]) if row[7] else [],
                    source=row[8]
                )
            return None
    
    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "DELETE FROM memories WHERE id = ?", (memory_id,)
            )
            conn.commit()
            return cursor.rowcount > 0
    
    def list_all(self, memory_type: Optional[str] = None,
                 limit: int = 100) -> List[MemoryEntry]:
        """List all memories, optionally filtered by type."""
        with sqlite3.connect(self.db_path) as conn:
            if memory_type:
                cursor = conn.execute(
                    "SELECT * FROM memories WHERE memory_type = ? ORDER BY created_at DESC LIMIT ?",
                    (memory_type, limit)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                    (limit,)
                )
            
            rows = cursor.fetchall()
            
            return [
                MemoryEntry(
                    id=row[0],
                    content=row[1],
                    summary=row[2],
                    embedding=json.loads(row[3]) if row[3] else [],
                    metadata=json.loads(row[4]) if row[4] else {},
                    created_at=row[5],
                    memory_type=row[6],
                    tags=json.loads(row[7]) if row[7] else [],
                    source=row[8]
                )
                for row in rows
            ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the memory store."""
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
            
            type_counts = {}
            cursor = conn.execute(
                "SELECT memory_type, COUNT(*) FROM memories GROUP BY memory_type"
            )
            for row in cursor:
                type_counts[row[0]] = row[1]
            
            return {
                "total_memories": total,
                "by_type": type_counts,
                "db_path": self.db_path
            }


# Global store instance
_store: Optional[VectorMemoryStore] = None


def get_store() -> VectorMemoryStore:
    """Get or create global vector memory store."""
    global _store
    if _store is None:
        _store = VectorMemoryStore()
    return _store


def make_semantic_memory_save():
    """Create the semantic_memory_save tool."""
    
    def execute(content: str, summary: str = "", memory_type: str = "note",
                tags: List[str] = None, source: str = "user", metadata: Dict = None):
        """
        Save a memory with semantic embedding for intelligent retrieval.
        
        Args:
            content: The full content to remember
            summary: Brief summary for quick reference
            memory_type: Type of memory (note, fact, preference, code, etc.)
            tags: List of tags for categorization
            source: Where this memory came from
            metadata: Additional structured data
            
        Returns:
            Dict with memory_id and confirmation
        """
        store = get_store()
        
        # Generate ID
        memory_id = hashlib.sha256(
            f"{content}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]
        
        # Generate embedding
        embedder = SimpleEmbedding()
        embedding = embedder.embed(content)
        
        # Create entry
        entry = MemoryEntry(
            id=memory_id,
            content=content,
            summary=summary or content[:200],
            embedding=embedding,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
            memory_type=memory_type,
            tags=tags or [],
            source=source
        )
        
        # Save
        store.save(entry)
        
        return {
            "memory_id": memory_id,
            "saved": True,
            "type": memory_type,
            "embedding_dimensions": len(embedding),
            "message": f"Memory saved with ID: {memory_id}"
        }
    
    return {
        "name": "semantic_memory_save",
        "description": "Save a memory with semantic embedding for intelligent, concept-based retrieval later.",
        "parameters": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Full content to remember"},
                "summary": {"type": "string", "description": "Brief summary for quick reference"},
                "memory_type": {"type": "string", "default": "note", "description": "Type: note, fact, preference, code, insight, etc."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags for categorization"},
                "source": {"type": "string", "default": "user", "description": "Source of the memory"},
                "metadata": {"type": "object", "description": "Additional structured data"}
            },
            "required": ["content"]
        },
        "execute": execute
    }


def build_vector_memory_tools(memory_db=None):
    """Build vector memory tools for the ghost tool registry."""
    return [make_semantic_memory_save(), make_semantic_memory_search(), make_hybrid_memory_search()]


def make_semantic_memory_search():
    """Create the semantic_memory_search tool."""
    
    def execute(query: str, top_k: int = 5, memory_type: str = None, tags: List[str] = None):
        """
        Search memories by semantic similarity.
        Finds conceptually related memories even with different words.
        
        Args:
            query: Natural language query describing what you're looking for
            top_k: Number of results to return
            memory_type: Filter by memory type
            tags: Filter by tags
            
        Returns:
            List of matching memories with similarity scores
        """
        store = get_store()
        results = store.search(query, top_k, memory_type, tags)
        
        return {
            "query": query,
            "results": [
                {
                    "id": entry.id,
                    "content": entry.content[:500] + "..." if len(entry.content) > 500 else entry.content,
                    "summary": entry.summary,
                    "type": entry.memory_type,
                    "tags": entry.tags,
                    "similarity_score": round(score, 3),
                    "created_at": entry.created_at
                }
                for entry, score in results
            ],
            "count": len(results)
        }
    
    return {
        "name": "semantic_memory_search",
        "description": "Search memories by meaning/semantics. Finds related memories even when phrased differently.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Natural language query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"},
                "memory_type": {"type": "string", "description": "Filter by memory type"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"}
            },
            "required": ["query"]
        },
        "execute": execute
    }


def make_hybrid_memory_search():
    """Create the hybrid_memory_search tool combining text + semantic."""
    
    def execute(query: str, top_k: int = 5):
        """
        Search using both text matching and semantic similarity.
        Best of both worlds: finds exact matches and conceptually similar content.
        
        Args:
            query: Search query
            top_k: Number of results
            
        Returns:
            Combined results with relevance scores
        """
        from ghost_memory import memory_search
        
        # Get semantic results
        store = get_store()
        semantic_results = store.search(query, top_k * 2)
        semantic_ids = {entry.id for entry, _ in semantic_results}
        
        # Get text results from existing memory system
        try:
            text_results = memory_search(query, limit=top_k * 2)
        except Exception:
            text_results = []
        
        # Combine and deduplicate
        seen = set()
        combined = []
        
        # Add semantic results first (weighted higher)
        for entry, score in semantic_results:
            if entry.id not in seen:
                seen.add(entry.id)
                combined.append({
                    "id": entry.id,
                    "content": entry.content[:500] + "..." if len(entry.content) > 500 else entry.content,
                    "summary": entry.summary,
                    "type": entry.memory_type,
                    "tags": entry.tags,
                    "relevance": round(score * 0.6 + 0.4, 3),  # Weighted boost
                    "match_type": "semantic",
                    "created_at": entry.created_at
                })
        
        # Add text results
        for mem in text_results:
            mem_id = mem.get("id", hashlib.sha256(mem.get("content", "").encode()).hexdigest()[:16])
            if mem_id not in seen:
                seen.add(mem_id)
                combined.append({
                    "id": mem_id,
                    "content": mem.get("content", "")[:500] + "..." if len(mem.get("content", "")) > 500 else mem.get("content", ""),
                    "summary": mem.get("summary", ""),
                    "type": mem.get("type", "unknown"),
                    "tags": mem.get("tags", []),
                    "relevance": 0.5,  # Base score for text matches
                    "match_type": "text",
                    "created_at": mem.get("created_at", "")
                })
        
        # Sort by relevance
        combined.sort(key=lambda x: x["relevance"], reverse=True)
        
        return {
            "query": query,
            "results": combined[:top_k],
            "semantic_matches": len(semantic_results),
            "text_matches": len(text_results),
            "count": len(combined[:top_k])
        }
    
    return {
        "name": "hybrid_memory_search",
        "description": "Search memories using both semantic similarity and text matching. Best comprehensive search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "top_k": {"type": "integer", "default": 5, "description": "Number of results"}
            },
            "required": ["query"]
        },
        "execute": execute
    }
