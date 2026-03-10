"""JSON Schema Validator - validates JSON against schemas and generates schemas from samples."""

import json


def register(api):
    """Entry point called by ToolManager with a ToolAPI instance."""

    def validate_json(data, schema, **kwargs):
        """Validate JSON data against a JSON Schema.
        
        Args:
            data: The JSON data to validate (dict, list, or JSON string)
            schema: The JSON Schema to validate against (dict or JSON string)
        
        Returns:
            JSON string with {valid: bool, errors: [...]}
        """
        try:
            import jsonschema
            from jsonschema import Draft7Validator
        except ImportError:
            return json.dumps({
                "valid": False,
                "errors": ["jsonschema package not installed. Install with: pip install jsonschema"]
            })
        
        # Parse inputs if they're strings
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except json.JSONDecodeError as e:
                return json.dumps({
                    "valid": False,
                    "errors": [f"Invalid JSON data: {e}"]
                })
        
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except json.JSONDecodeError as e:
                return json.dumps({
                    "valid": False,
                    "errors": [f"Invalid JSON schema: {e}"]
                })
        
        # Validate
        try:
            validator = Draft7Validator(schema)
            errors = list(validator.iter_errors(data))
            
            if errors:
                error_list = []
                for err in errors:
                    error_list.append({
                        "message": err.message,
                        "path": list(err.path) if err.path else [],
                        "schema_path": list(err.schema_path) if err.schema_path else []
                    })
                return json.dumps({
                    "valid": False,
                    "errors": error_list
                })
            
            return json.dumps({
                "valid": True,
                "errors": []
            })
            
        except Exception as e:
            return json.dumps({
                "valid": False,
                "errors": [f"Validation error: {str(e)}"]
            })

    def generate_schema(sample_json, **kwargs):
        """Generate a basic JSON Schema from a sample JSON object.
        
        Args:
            sample_json: A sample JSON object (dict, list, or JSON string)
        
        Returns:
            JSON string with the generated schema
        """
        # Parse input if it's a string
        if isinstance(sample_json, str):
            try:
                sample_json = json.loads(sample_json)
            except json.JSONDecodeError as e:
                return json.dumps({
                    "error": f"Invalid JSON: {e}"
                })
        
        def infer_type(value):
            """Infer JSON Schema type from a Python value."""
            if value is None:
                return {"type": "null"}
            elif isinstance(value, bool):
                return {"type": "boolean"}
            elif isinstance(value, int):
                return {"type": "integer"}
            elif isinstance(value, float):
                return {"type": "number"}
            elif isinstance(value, str):
                return {"type": "string"}
            elif isinstance(value, list):
                if value:
                    # Infer type from first item
                    item_schema = infer_type(value[0])
                    return {
                        "type": "array",
                        "items": item_schema
                    }
                else:
                    return {"type": "array"}
            elif isinstance(value, dict):
                properties = {}
                required = []
                for k, v in value.items():
                    properties[k] = infer_type(v)
                    required.append(k)
                return {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            else:
                return {}
        
        schema = infer_type(sample_json)
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        
        api.log("Generated JSON Schema from sample data")
        return json.dumps(schema, indent=2)

    api.register_tool({
        "name": "validate_json",
        "description": "Validate JSON data against a JSON Schema. Returns {valid: bool, errors: [...]} with detailed validation errors. Accepts JSON strings, objects, or arrays.",
        "parameters": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "The JSON data to validate (as a JSON string)"
                },
                "schema": {
                    "type": "string",
                    "description": "The JSON Schema to validate against (as a JSON string)"
                }
            },
            "required": ["data", "schema"]
        },
        "execute": validate_json
    })

    api.register_tool({
        "name": "generate_schema",
        "description": "Generate a basic JSON Schema from a sample JSON object. Infers types from the sample data.",
        "parameters": {
            "type": "object",
            "properties": {
                "sample_json": {
                    "type": "string",
                    "description": "A sample JSON object to generate schema from (as a JSON string)"
                }
            },
            "required": ["sample_json"]
        },
        "execute": generate_schema
    })