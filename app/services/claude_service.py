"""
ClaudeService - Python Script Execution for MongoDB Exploration

Allows Claude to write and execute Python scripts for flexible data exploration.
Uses restricted execution with safeguards for security.
"""

import json
import sys
import io
import traceback
import threading
from typing import Any
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pymongo import MongoClient
from bson import ObjectId
from src.utils.envvars import EnvVars
from src.utils.log_manager import LogManager

logger = LogManager().get_logger(__name__)

# Maximum iterations and execution limits
MAX_ITERATIONS = 15
SCRIPT_TIMEOUT_SECONDS = 30
MAX_OUTPUT_SIZE = 100000  # 100KB max output

# System prompt for the Python-enabled agent
SYSTEM_PROMPT = """You are a MongoDB data exploration assistant with the ability to write and execute Python scripts.

## Available Databases (pre-connected as `db_campaign` and `db_empower`)
- **db_campaign**: Campaign, participant, and exposure data (empower_development database)
- **db_empower**: Same database — county-specific demographic, residential, and energy data (empower_development database)
- Note: Both point to empower_development after database unification.

## Pre-imported Libraries
- `pandas as pd` - DataFrames and data manipulation
- `json` - JSON handling
- `datetime` - Date/time operations
- `re` - Regular expressions
- `ObjectId` from bson - MongoDB ObjectId handling

## Key Collection Patterns
- County collections: {County}CountyDemographic, {County}CountyResidential, {County}ElectricalDB, {County}ThermalLoads
- Campaign collections: campaigns, participants, exposures, applications

## Writing Scripts
1. Use `db_campaign` or `db_empower` to access collections: `db_empower['FranklinCountyDemographic']`
2. Store your final result in a variable called `result` - this will be returned
3. For DataFrames, convert to dict: `result = df.to_dict('records')`
4. Print statements will be captured and shown to the user
5. Keep scripts focused and efficient

## Example Script
```python
# Find high energy burden customers in Franklin
cursor = db_empower['FranklinCountyDemographic'].find(
    {'energy_burden': {'$gt': 10}},
    {'customer_name': 1, 'energy_burden': 1, 'address': 1}
).limit(20)

df = pd.DataFrame(list(cursor))
print(f"Found {len(df)} high energy burden customers")
result = df.to_dict('records')
```

## Important
- Scripts timeout after 30 seconds
- Always use .limit() on queries to avoid huge result sets
- The `result` variable is what gets returned to the user
- If no `result` is set, captured print output will be shown instead"""

# Tool definition for Python execution
TOOLS = [
    {
        "name": "execute_python",
        "description": """Execute a Python script to query MongoDB and process data.
The script has access to:
- db_campaign: MongoDB database for campaign_data
- db_empower: MongoDB database for empower_development
- pandas (as pd), json, datetime, re, ObjectId
Set a variable called `result` with your final output (list of dicts for tables).""",
        "input_schema": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Python script to execute. Use db_campaign or db_empower to access collections."
                },
                "description": {
                    "type": "string",
                    "description": "Brief description of what this script does"
                }
            },
            "required": ["script", "description"]
        }
    },
    {
        "name": "list_collections",
        "description": "List all collections in a database to discover available data.",
        "input_schema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Database name",
                    "enum": ["campaign_data", "empower_development"]
                }
            },
            "required": ["database"]
        }
    },
    {
        "name": "get_sample_document",
        "description": "Get a sample document from a collection to understand its schema.",
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
    }
]


class ScriptTimeoutError(Exception):
    """Script execution timeout."""
    pass


class ClaudeService:
    """Service for Claude-powered Python script execution against MongoDB."""

    def __init__(self):
        self.env = EnvVars()
        self.mongo_uri = self.env.get_env('MONGO_URI', 'mongodb://localhost:27017')
        self.client = MongoClient(self.mongo_uri)
        self.databases = {
            'campaign_data': self.client['campaign_data'],  # Archive (read-only)
            'empower_development': self.client['empower_development']
        }

        self.anthropic_api_key = self.env.get_env('ANTHROPIC_API_KEY', '')
        if not self.anthropic_api_key:
            logger.warning("ANTHROPIC_API_KEY not set - Claude queries will fail")

    def _serialize_value(self, value: Any) -> Any:
        """Recursively serialize MongoDB types to JSON-compatible types."""
        if isinstance(value, ObjectId):
            return str(value)
        elif isinstance(value, datetime):
            return value.isoformat()
        elif isinstance(value, dict):
            return {k: self._serialize_value(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [self._serialize_value(item) for item in value]
        else:
            return value

    def _create_safe_globals(self) -> dict:
        """Create a restricted globals dict for script execution."""
        import pandas as pd
        import re as re_module
        from datetime import datetime, timedelta, date

        safe_globals = {
            # Allowed built-ins
            '__builtins__': {
                'print': print,
                'len': len,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'set': set,
                'tuple': tuple,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'map': map,
                'filter': filter,
                'sorted': sorted,
                'reversed': reversed,
                'sum': sum,
                'min': min,
                'max': max,
                'abs': abs,
                'round': round,
                'any': any,
                'all': all,
                'isinstance': isinstance,
                'type': type,
                'getattr': getattr,
                'hasattr': hasattr,
                'None': None,
                'True': True,
                'False': False,
            },
            # Pre-imported libraries
            'pd': pd,
            'json': json,
            'datetime': datetime,
            'timedelta': timedelta,
            'date': date,
            're': re_module,
            'ObjectId': ObjectId,
            # Pre-connected databases
            'db_campaign': self.databases['empower_development'],
            'db_empower': self.databases['empower_development'],
        }

        return safe_globals

    def _execute_script(self, script: str, description: str) -> dict:
        """Execute a Python script in a restricted environment with thread-safe timeout."""
        logger.info(f"Executing script: {description}")
        logger.debug(f"Script content:\n{script}")

        safe_globals = self._create_safe_globals()
        safe_locals = {}

        # Container for results from the execution thread
        execution_result = {
            'result': None,
            'output': '',
            'error': None,
            'traceback': None
        }

        def run_script():
            """Execute script in a separate thread with stdout capture."""
            stdout_capture = io.StringIO()
            old_stdout = sys.stdout
            try:
                sys.stdout = stdout_capture
                exec(script, safe_globals, safe_locals)
                execution_result['result'] = safe_locals.get('result', None)
                execution_result['output'] = stdout_capture.getvalue()
            except Exception as e:
                execution_result['error'] = f"{type(e).__name__}: {str(e)}"
                execution_result['traceback'] = traceback.format_exc()
                execution_result['output'] = stdout_capture.getvalue()
            finally:
                sys.stdout = old_stdout

        try:
            # Use ThreadPoolExecutor for timeout support in any thread context
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(run_script)
                try:
                    future.result(timeout=SCRIPT_TIMEOUT_SECONDS)
                except FuturesTimeoutError:
                    logger.warning(f"Script timeout after {SCRIPT_TIMEOUT_SECONDS}s")
                    return {
                        "success": False,
                        "error": f"Script execution timed out after {SCRIPT_TIMEOUT_SECONDS} seconds",
                        "output": execution_result.get('output', ''),
                        "description": description
                    }

            # Check if script had an error
            if execution_result['error']:
                logger.error(f"Script execution error: {execution_result['error']}")
                return {
                    "success": False,
                    "error": execution_result['error'],
                    "traceback": execution_result['traceback'],
                    "output": execution_result['output'],
                    "description": description
                }

            # Get captured output
            output = execution_result['output']
            if len(output) > MAX_OUTPUT_SIZE:
                output = output[:MAX_OUTPUT_SIZE] + "\n... (output truncated)"

            # Get and serialize result
            result = execution_result['result']
            if result is not None:
                result = self._serialize_value(result)

            return {
                "success": True,
                "result": result,
                "output": output,
                "description": description
            }

        except Exception as e:
            logger.error(f"Script execution setup error: {e}", exc_info=True)
            return {
                "success": False,
                "error": f"{type(e).__name__}: {str(e)}",
                "traceback": traceback.format_exc(),
                "output": "",
                "description": description
            }

    def _tool_list_collections(self, database: str) -> dict:
        """List collections in a database."""
        try:
            db = self.databases.get(database)
            if not db:
                return {"success": False, "error": f"Unknown database: {database}"}

            collections = []
            for name in sorted(db.list_collection_names()):
                count = db[name].estimated_document_count()
                collections.append({"name": name, "document_count": count})

            return {"success": True, "collections": collections, "total": len(collections)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _tool_get_sample_document(self, database: str, collection: str) -> dict:
        """Get a sample document from a collection."""
        try:
            db = self.databases.get(database)
            if not db:
                return {"success": False, "error": f"Unknown database: {database}"}

            doc = db[collection].find_one()
            if doc:
                serialized = self._serialize_value(doc)
                schema = {k: type(v).__name__ for k, v in doc.items()}
                return {"success": True, "sample": serialized, "schema": schema}
            return {"success": True, "sample": None, "message": "Collection is empty"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _execute_tool(self, tool_name: str, tool_input: dict) -> dict:
        """Execute a tool and return results."""
        logger.info(f"Executing tool: {tool_name}")

        if tool_name == "execute_python":
            return self._execute_script(
                tool_input.get("script", ""),
                tool_input.get("description", "Script execution")
            )
        elif tool_name == "list_collections":
            return self._tool_list_collections(tool_input.get("database", ""))
        elif tool_name == "get_sample_document":
            return self._tool_get_sample_document(
                tool_input.get("database", ""),
                tool_input.get("collection", "")
            )
        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

    def explore(self, query: str) -> dict[str, Any]:
        """
        Main entry point for Python-powered exploration.

        Args:
            query: Natural language query from user

        Returns:
            Dictionary with reasoning steps, results, and final response
        """
        logger.info(f"Claude Python explore query: {query}")

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

        messages = [{"role": "user", "content": query}]
        steps = []
        all_results = []

        try:
            for iteration in range(MAX_ITERATIONS):
                logger.info(f"Claude iteration {iteration + 1}/{MAX_ITERATIONS}")

                # Debug logging
                logger.debug("=" * 60)
                logger.debug(f"CLAUDE API CALL - Iteration {iteration + 1}")
                logger.debug(f"Messages: {len(messages)}")
                logger.debug("=" * 60)

                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4096,
                    system=SYSTEM_PROMPT,
                    tools=TOOLS,
                    messages=messages
                )

                logger.debug(f"Response stop_reason: {response.stop_reason}")

                assistant_content = []
                tool_results_for_message = []

                for block in response.content:
                    if block.type == "text":
                        steps.append({
                            "type": "thinking",
                            "content": block.text,
                            "iteration": iteration + 1
                        })
                        assistant_content.append(block)

                    elif block.type == "tool_use":
                        tool_name = block.name
                        tool_input = block.input
                        tool_use_id = block.id

                        # For execute_python, show the script in steps
                        if tool_name == "execute_python":
                            steps.append({
                                "type": "script",
                                "description": tool_input.get("description", "Python script"),
                                "script": tool_input.get("script", ""),
                                "iteration": iteration + 1
                            })
                        else:
                            steps.append({
                                "type": "tool_call",
                                "tool": tool_name,
                                "input": tool_input,
                                "iteration": iteration + 1
                            })

                        # Execute the tool
                        tool_result = self._execute_tool(tool_name, tool_input)

                        # Store results for display
                        if tool_result.get("success"):
                            result_entry = {
                                "tool": tool_name,
                                "description": tool_input.get("description", tool_name),
                                "data": None
                            }

                            if tool_name == "execute_python":
                                if tool_result.get("result"):
                                    data = tool_result["result"]
                                    if isinstance(data, list):
                                        result_entry["data"] = data
                                        result_entry["count"] = len(data)
                                    elif isinstance(data, dict):
                                        result_entry["data"] = [data]
                                        result_entry["count"] = 1
                                    else:
                                        result_entry["data"] = [{"result": data}]
                                        result_entry["count"] = 1
                                result_entry["output"] = tool_result.get("output", "")
                            elif "collections" in tool_result:
                                result_entry["data"] = tool_result["collections"]
                                result_entry["count"] = tool_result.get("total", 0)
                                result_entry["collection"] = "system"
                            elif "sample" in tool_result and tool_result["sample"]:
                                result_entry["data"] = [tool_result["sample"]]
                                result_entry["count"] = 1

                            if result_entry["data"]:
                                all_results.append(result_entry)

                        # Record step result
                        steps.append({
                            "type": "script_result" if tool_name == "execute_python" else "tool_result",
                            "tool": tool_name,
                            "success": tool_result.get("success", False),
                            "summary": self._summarize_result(tool_result),
                            "output": tool_result.get("output", ""),
                            "error": tool_result.get("error", ""),
                            "iteration": iteration + 1
                        })

                        assistant_content.append(block)
                        tool_results_for_message.append({
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(tool_result, default=str)[:50000]  # Limit size
                        })

                messages.append({"role": "assistant", "content": assistant_content})

                if tool_results_for_message:
                    messages.append({"role": "user", "content": tool_results_for_message})
                else:
                    break

                if response.stop_reason == "end_turn":
                    break

            # Extract final response
            final_response = ""
            for step in reversed(steps):
                if step["type"] == "thinking":
                    final_response = step["content"]
                    break

            return {
                "success": True,
                "steps": steps,
                "results": self._format_results(all_results),
                "summary": final_response,
                "metadata": {
                    "query": query,
                    "timestamp": datetime.now().isoformat(),
                    "iterations": len([s for s in steps if s["type"] in ("script", "tool_call")]),
                    "total_records": sum(r.get("count", 0) for r in all_results),
                    "method": "python"
                }
            }

        except Exception as e:
            logger.error(f"Claude explore error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "steps": steps,
                "results": [],
                "summary": f"An error occurred: {str(e)}"
            }

    def _summarize_result(self, result: dict) -> str:
        """Create a brief summary of a tool result."""
        if not result.get("success"):
            return f"Error: {result.get('error', 'Unknown error')}"

        if "result" in result:
            data = result["result"]
            if isinstance(data, list):
                return f"Returned {len(data)} records"
            elif data is not None:
                return f"Returned result: {str(data)[:100]}"
            elif result.get("output"):
                return f"Script output captured"
            return "Script completed (no result)"

        if "collections" in result:
            return f"Found {len(result['collections'])} collections"
        if "sample" in result:
            return "Retrieved sample document"
        return "Success"

    def _format_results(self, all_results: list) -> list:
        """Format collected results for frontend display."""
        formatted = []
        for result in all_results:
            if result.get("data"):
                formatted.append({
                    "collection": result.get("description", result.get("collection", "Results")),
                    "description": f"From {result.get('tool', 'query')}",
                    "count": result.get("count", len(result["data"])),
                    "data": result["data"],
                    "output": result.get("output", ""),
                    "success": True
                })
        return formatted
