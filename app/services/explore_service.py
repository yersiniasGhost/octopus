"""
ExploreService - Agentic Natural Language MongoDB Query Interface

Uses Claude's tool use capability with an agentic loop to allow iterative
exploration, error correction, and multi-step reasoning.
"""

import json
from typing import Any
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

# Maximum iterations to prevent infinite loops
MAX_ITERATIONS = 50

# System prompt for the agent
SYSTEM_PROMPT = """You are a MongoDB data exploration assistant for an energy efficiency campaign system.
You have access to tools to explore the database. Use them to answer user questions thoroughly.

## Available Databases
- **campaign_data**: Read-only archive of raw campaign data (deprecated — use empower_development)
- **empower_development**: Primary database with all unified campaign, participant, and county data

## Key Patterns
- County collections are named: {County}CountyDemographic, {County}CountyResidential, {County}ElectricalDB, {County}ThermalLoads
- Example: FranklinCountyDemographic, CuyahogaCountyResidential
- The `customer_name` field format varies: "FIRSTNAME LASTNAME", "LASTNAME, FIRSTNAME", "LASTNAME FIRSTNAME"

## Workflow
1. If unsure about collection names, use list_collections first
2. If unsure about document structure, use get_document_sample first
3. Use count_documents to get totals
4. Use find_documents or sample_documents to retrieve actual data
5. Use run_aggregation for complex queries (grouping, statistics)

## Important
- Campaign collections: campaigns, participants, exposures, applications
- Always verify collection names exist before querying
- If a query returns no results, consider trying alternative approaches
- Provide clear, helpful summaries of what you found

When you have gathered enough information to answer the user's question, provide your final response.
Do NOT call tools after you have the answer - just respond with your findings."""

# Tool definitions for Claude
TOOLS = [
    {
        "name": "list_collections",
        "description": "List all collections in a database. Use this first if unsure about collection names.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name: 'campaign_data' or 'empower_development'",
                    "enum": ["campaign_data", "empower_development"]
                },
                "filter_pattern": {
                    "type": "string",
                    "description": "Optional: filter collection names containing this string (case-insensitive)"
                }
            },
            "required": ["database"]
        }
    },
    {
        "name": "get_document_sample",
        "description": "Get a sample document from a collection to understand its schema/structure.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["campaign_data", "empower_development"]
                },
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                }
            },
            "required": ["database", "collection"]
        }
    },
    {
        "name": "count_documents",
        "description": "Count documents in a collection, optionally with a filter.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["campaign_data", "empower_development"]
                },
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                },
                "filter": {
                    "type": "object",
                    "description": "Optional MongoDB filter query"
                }
            },
            "required": ["database", "collection"]
        }
    },
    {
        "name": "find_documents",
        "description": "Find documents matching a filter. Returns up to `limit` documents.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["campaign_data", "empower_development"]
                },
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                },
                "filter": {
                    "type": "object",
                    "description": "MongoDB filter query. Use $regex for pattern matching."
                },
                "projection": {
                    "type": "object",
                    "description": "Optional: fields to include (1) or exclude (0)"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max documents to return (default: 20, max: 100)",
                    "default": 20
                },
                "sort": {
                    "type": "object",
                    "description": "Optional: sort specification, e.g., {\"field\": 1} for ascending"
                }
            },
            "required": ["database", "collection"]
        }
    },
    {
        "name": "sample_documents",
        "description": "Get random sample of documents from a collection.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["campaign_data", "empower_development"]
                },
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                },
                "count": {
                    "type": "integer",
                    "description": "Number of random documents (default: 10, max: 100)",
                    "default": 10
                },
                "projection": {
                    "type": "object",
                    "description": "Optional: fields to include (1) or exclude (0)"
                }
            },
            "required": ["database", "collection"]
        }
    },
    {
        "name": "run_aggregation",
        "description": "Run a MongoDB aggregation pipeline for complex queries (grouping, statistics, joins).",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "enum": ["campaign_data", "empower_development"]
                },
                "collection": {
                    "type": "string",
                    "description": "Collection name"
                },
                "pipeline": {
                    "type": "array",
                    "description": "MongoDB aggregation pipeline stages",
                    "items": {"type": "object"}
                }
            },
            "required": ["database", "collection", "pipeline"]
        }
    },
    {
        "name": "search_by_name",
        "description": "Search for a person by name across demographic collections. Handles name format variations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Person's name to search for (any format)"
                },
                "county": {
                    "type": "string",
                    "description": "Optional: specific county to search (e.g., 'Franklin', 'Cuyahoga')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results (default: 20)",
                    "default": 20
                }
            },
            "required": ["name"]
        }
    }
]


class ExploreService:
    """Agentic service for natural language MongoDB exploration using Claude's tool use."""

    def __init__(self):
        self.env = EnvVars()
        self.mongo_uri = self.env.get_env('MONGO_URI', 'mongodb://localhost:27017')
        self.client = MongoClient(self.mongo_uri)
        self.databases = {
            'campaign_data': self.client['campaign_data'],
            'empower_development': self.client['empower_development']
        }

        # Claude API setup
        self.anthropic_api_key = self.env.get_env('ANTHROPIC_API_KEY', '')
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set - explore queries will fail")

    def _get_db(self, database: str):
        """Get database by name."""
        if database not in self.databases:
            raise ValueError(f"Unknown database: {database}. Use 'campaign_data' or 'empower_development'")
        return self.databases[database]

    def _serialize_doc(self, doc: dict) -> dict:
        """Convert MongoDB document to JSON-serializable format."""
        if doc is None:
            return None
        result = {}
        for key, value in doc.items():
            if isinstance(value, ObjectId):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, dict):
                result[key] = self._serialize_doc(value)
            elif isinstance(value, list):
                result[key] = [
                    self._serialize_doc(item) if isinstance(item, dict)
                    else str(item) if isinstance(item, ObjectId)
                    else item.isoformat() if isinstance(item, datetime)
                    else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    # ========== Tool Implementations ==========

    def _tool_list_collections(self, database: str, filter_pattern: str = None) -> dict:
        """List collections in a database."""
        try:
            db = self._get_db(database)
            collections = db.list_collection_names()

            if filter_pattern:
                pattern_lower = filter_pattern.lower()
                collections = [c for c in collections if pattern_lower in c.lower()]

            # Get document counts
            result = []
            for coll_name in sorted(collections):
                count = db[coll_name].estimated_document_count()
                result.append({"name": coll_name, "document_count": count})

            return {"success": True, "collections": result, "total": len(result)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_get_document_sample(self, database: str, collection: str) -> dict:
        """Get a sample document to understand schema."""
        try:
            db = self._get_db(database)
            doc = db[collection].find_one()
            if doc:
                serialized = self._serialize_doc(doc)
                # Also extract field names and types
                schema = {k: type(v).__name__ for k, v in doc.items()}
                return {"success": True, "sample": serialized, "schema": schema}
            return {"success": True, "sample": None, "message": "Collection is empty"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_count_documents(self, database: str, collection: str, filter: dict = None) -> dict:
        """Count documents in a collection."""
        try:
            db = self._get_db(database)
            filter_query = filter or {}
            count = db[collection].count_documents(filter_query)
            return {"success": True, "count": count, "collection": collection, "filter": filter_query}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_find_documents(self, database: str, collection: str, filter: dict = None,
                             projection: dict = None, limit: int = 20, sort: dict = None) -> dict:
        """Find documents matching a filter."""
        try:
            db = self._get_db(database)
            filter_query = filter or {}
            limit = min(limit or 20, 100)  # Cap at 100

            cursor = db[collection].find(filter_query, projection)
            if sort:
                cursor = cursor.sort(list(sort.items()))
            cursor = cursor.limit(limit)

            docs = [self._serialize_doc(doc) for doc in cursor]
            return {"success": True, "documents": docs, "count": len(docs), "collection": collection}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_sample_documents(self, database: str, collection: str, count: int = 10, projection: dict = None) -> dict:
        """Get random sample of documents."""
        try:
            db = self._get_db(database)
            count = min(count or 10, 100)  # Cap at 100

            pipeline = [{"$sample": {"size": count}}]
            if projection:
                pipeline.append({"$project": projection})

            docs = [self._serialize_doc(doc) for doc in db[collection].aggregate(pipeline)]
            return {"success": True, "documents": docs, "count": len(docs), "collection": collection}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_run_aggregation(self, database: str, collection: str, pipeline: list) -> dict:
        """Run an aggregation pipeline."""
        try:
            db = self._get_db(database)

            # Add a limit if not present to prevent huge results
            has_limit = any('$limit' in stage for stage in pipeline)
            if not has_limit:
                pipeline.append({"$limit": 100})

            results = [self._serialize_doc(doc) for doc in db[collection].aggregate(pipeline)]
            return {"success": True, "results": results, "count": len(results), "collection": collection}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_search_by_name(self, name: str, county: str = None, limit: int = 20) -> dict:
        """Search for a person by name across demographic collections."""
        try:
            # Parse name into parts
            name_parts = name.strip().upper().split()
            if not name_parts:
                return {"success": False, "error": "Empty name provided"}

            # Build regex patterns for different name formats
            if len(name_parts) >= 2:
                first = name_parts[0]
                last = name_parts[-1]
                # Match various formats: "FIRST LAST", "LAST FIRST", "LAST, FIRST"
                patterns = [
                    f".*{first}.*{last}.*",
                    f".*{last}.*{first}.*",
                ]
                regex_pattern = "|".join(patterns)
            else:
                regex_pattern = f".*{name_parts[0]}.*"

            db = self._get_db('empower_development')
            collections = db.list_collection_names()

            # Filter to demographic collections
            if county:
                county_title = county.strip().title()
                demographic_colls = [c for c in collections if f"{county_title}CountyDemographic" == c]
            else:
                demographic_colls = [c for c in collections if c.endswith('CountyDemographic')]

            all_results = []
            for coll_name in demographic_colls:
                cursor = db[coll_name].find(
                    {"customer_name": {"$regex": regex_pattern, "$options": "i"}},
                    {"customer_name": 1, "address": 1, "service_city": 1, "email": 1, "mobile": 1, "parcel_id": 1}
                ).limit(limit)

                for doc in cursor:
                    doc['_source_collection'] = coll_name
                    all_results.append(self._serialize_doc(doc))

                if len(all_results) >= limit:
                    break

            return {
                "success": True,
                "results": all_results[:limit],
                "count": len(all_results[:limit]),
                "searched_collections": demographic_colls
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool and return results."""
        tool_map = {
            "list_collections": self._tool_list_collections,
            "get_document_sample": self._tool_get_document_sample,
            "count_documents": self._tool_count_documents,
            "find_documents": self._tool_find_documents,
            "sample_documents": self._tool_sample_documents,
            "run_aggregation": self._tool_run_aggregation,
            "search_by_name": self._tool_search_by_name,
        }

        if tool_name not in tool_map:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        logger.info(f"Executing tool: {tool_name} with input: {json.dumps(tool_input)[:200]}")
        result = tool_map[tool_name](**tool_input)
        logger.info(f"Tool result: success={result.get('success')}")
        return result

    def explore(self, query: str) -> dict[str, Any]:
        """
        Main entry point for agentic exploration.

        Args:
            query: Natural language query from user

        Returns:
            Dictionary with reasoning steps, results, and final response
        """
        logger.info(f"Agentic explore query: {query}")

        if not self.anthropic_api_key:
            return {
                "success": False,
                "error": "ANTHROPIC_API_KEY not configured",
                "steps": [],
                "results": [],
                "summary": "Cannot process query - API key not configured."
            }

        import anthropic
        client = anthropic.Anthropic(api_key=self.anthropic_api_key)

        # Initialize conversation
        messages = [{"role": "user", "content": query}]
        steps = []  # Track reasoning steps for display
        all_results = []  # Collect all query results

        try:
            for iteration in range(MAX_ITERATIONS):
                logger.info(f"Agentic iteration {iteration + 1}/{MAX_ITERATIONS}")

                # Debug: Log the messages being sent to Claude
                logger.debug("=" * 60)
                logger.debug(f"CLAUDE API CALL - Iteration {iteration + 1}")
                logger.debug("=" * 60)
                logger.debug(f"System prompt length: {len(SYSTEM_PROMPT)} chars")
                logger.debug(f"Number of messages: {len(messages)}")
                for i, msg in enumerate(messages):
                    role = msg.get('role', 'unknown')
                    content = msg.get('content', '')
                    if isinstance(content, str):
                        content_preview = content[:500] + '...' if len(content) > 500 else content
                        logger.debug(f"Message {i} [{role}]: {content_preview}")
                    elif isinstance(content, list):
                        logger.debug(f"Message {i} [{role}]: {len(content)} content blocks")
                        for j, block in enumerate(content):
                            if hasattr(block, 'type'):
                                logger.debug(f"  Block {j}: type={block.type}")
                            elif isinstance(block, dict):
                                logger.debug(f"  Block {j}: {block.get('type', 'unknown')}")
                logger.debug("-" * 60)

                # Call Claude with tools
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages
                )

                # Debug: Log Claude's response
                logger.debug(f"CLAUDE RESPONSE - stop_reason: {response.stop_reason}")
                logger.debug(f"Response content blocks: {len(response.content)}")
                for i, block in enumerate(response.content):
                    if block.type == "text":
                        text_preview = block.text[:300] + '...' if len(block.text) > 300 else block.text
                        logger.debug(f"  Block {i} [text]: {text_preview}")
                    elif block.type == "tool_use":
                        logger.debug(f"  Block {i} [tool_use]: {block.name} - {json.dumps(block.input)[:200]}")
                logger.debug("=" * 60)

                # Process response content
                assistant_content = []
                tool_results_for_message = []

                for block in response.content:
                    if block.type == "text":
                        # Claude is providing text (thinking or final answer)
                        steps.append({
                            "type": "thinking",
                            "content": block.text,
                            "iteration": iteration + 1
                        })
                        assistant_content.append(block)

                    elif block.type == "tool_use":
                        # Claude wants to use a tool
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id

                        steps.append({
                            "type": "tool_call",
                            "tool": tool_name,
                            "input": tool_input,
                            "iteration": iteration + 1
                        })

                        # Execute the tool
                        tool_result = self._execute_tool(tool_name, tool_input)

                        # Store results that have data for display
                        if tool_result.get("success"):
                            result_entry = {
                                "tool": tool_name,
                                "collection": tool_input.get("collection", "N/A"),
                                "data": None
                            }
                            # Extract displayable data
                            if "documents" in tool_result:
                                result_entry["data"] = tool_result["documents"]
                                result_entry["count"] = tool_result.get("count", 0)
                            elif "results" in tool_result:
                                result_entry["data"] = tool_result["results"]
                                result_entry["count"] = tool_result.get("count", 0)
                            elif "collections" in tool_result:
                                result_entry["data"] = tool_result["collections"]
                                result_entry["count"] = tool_result.get("total", 0)
                                result_entry["collection"] = "system"
                            elif "sample" in tool_result and tool_result["sample"]:
                                result_entry["data"] = [tool_result["sample"]]
                                result_entry["count"] = 1
                            elif "count" in tool_result:
                                result_entry["data"] = [{"count": tool_result["count"]}]
                                result_entry["count"] = 1

                            if result_entry["data"]:
                                all_results.append(result_entry)

                        steps.append({
                            "type": "tool_result",
                            "tool": tool_name,
                            "success": tool_result.get("success", False),
                            "summary": self._summarize_tool_result(tool_result),
                            "iteration": iteration + 1
                        })

                        assistant_content.append(block)
                        tool_results_for_message.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(tool_result, default=str)
                        })

                # Add assistant message to conversation
                messages.append({"role": "assistant", "content": assistant_content})

                # If there were tool calls, add results and continue
                if tool_results_for_message:
                    messages.append({"role": "user", "content": tool_results_for_message})
                else:
                    # No tool calls - Claude has finished
                    break

                # Check stop reason
                if response.stop_reason == "end_turn":
                    break

            # Extract final response (last text block)
            final_response = ""
            for step in reversed(steps):
                if step["type"] == "thinking":
                    final_response = step["content"]
                    break

            return {
                "success": True,
                "steps": steps,
                "results": self._format_results_for_display(all_results),
                "summary": final_response,
                "metadata": {
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "iterations": len([s for s in steps if s["type"] == "tool_call"]),
                    "total_records": sum(r.get("count", 0) for r in all_results)
                }
            }

        except Exception as e:
            logger.error(f"Agentic explore error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "steps": steps,
                "results": [],
                "summary": f"An error occurred: {str(e)}"
            }

    def _summarize_tool_result(self, result: dict) -> str:
        """Create a brief summary of a tool result for display."""
        if not result.get("success"):
            return f"Error: {result.get('error', 'Unknown error')}"

        if "count" in result and "collection" in result:
            return f"{result['count']:,} documents in {result['collection']}"
        if "documents" in result:
            return f"Retrieved {len(result['documents'])} documents"
        if "results" in result:
            return f"Retrieved {len(result['results'])} results"
        if "collections" in result:
            return f"Found {len(result['collections'])} collections"
        if "sample" in result:
            return "Retrieved sample document"
        return "Success"

    def _format_results_for_display(self, all_results: list) -> list:
        """Format collected results for frontend display."""
        formatted = []
        for result in all_results:
            if result.get("data"):
                formatted.append({
                    "collection": result.get("collection", "Results"),
                    "description": f"From {result.get('tool', 'query')}",
                    "count": result.get("count", len(result["data"])),
                    "data": result["data"],
                    "success": True
                })
        return formatted

    def get_available_counties(self) -> list[str]:
        """Get list of available county collections."""
        db = self.databases['empower_development']
        collections = db.list_collection_names()
        counties = set()
        for name in collections:
            if name.endswith('CountyDemographic'):
                county = name.replace('CountyDemographic', '')
                counties.add(county)
        return sorted(list(counties))

    def get_collection_stats(self) -> dict:
        """Get basic stats about available collections."""
        stats = {"empower_development": {}}

        # Campaign data collections (now in empower_development)
        for coll_name in ['campaigns', 'participants', 'exposures', 'applications', 'applicants']:
            try:
                count = self.databases['empower_development'][coll_name].estimated_document_count()
                stats["empower_development"][coll_name] = count
            except Exception:
                stats["empower_development"][coll_name] = 0

        # County collections
        counties = self.get_available_counties()
        stats["empower_development"]["counties"] = counties
        stats["empower_development"]["county_count"] = len(counties)

        return stats
