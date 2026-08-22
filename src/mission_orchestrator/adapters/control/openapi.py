from __future__ import annotations


def openapi_document() -> dict[str, object]:
    read_response = {
        "200": {
            "description": "Successful response",
            "content": {"application/json": {"schema": {"type": "object"}}},
        },
        "401": {"$ref": "#/components/responses/Unauthorized"},
    }
    command_response = read_response | {
        "400": {"$ref": "#/components/responses/InvalidRequest"},
        "409": {"$ref": "#/components/responses/Conflict"},
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "HARNESS Mission Control API",
            "version": "1.0.0",
            "description": "Local control contract used by Graph Lab.",
        },
        "servers": [{"url": "/api/v1"}],
        "tags": [
            {"name": "System", "description": "Worker discovery"},
            {"name": "Mission", "description": "Mission state and actions"},
            {"name": "Documents", "description": "Versioned mission documents"},
            {"name": "Design", "description": "Editable design map"},
            {"name": "Conversation", "description": "Interactive conversation"},
            {"name": "Contracts", "description": "Pinned task contracts and execution leases"},
        ],
        "security": [{"bearerAuth": []}],
        "paths": {
            "/health": {"get": _read_operation("Worker health", "health", "System", security=[])},
            "/openapi.json": {
                "get": _read_operation("OpenAPI contract", "openApiContract", "System", security=[])
            },
            "/capabilities": {
                "get": _read_operation("Worker capabilities", "workerCapabilities", "System")
            },
            "/snapshot": {"get": _read_operation("Mission snapshot", "missionSnapshot", "Mission")},
            "/operation": {"get": _read_operation("Current operation", "currentOperation", "Mission")},
            "/events": {"get": _read_operation("Mission events", "missionEvents", "Mission")},
            "/messages": {
                "get": _read_operation("Conversation transcript", "conversationMessages", "Conversation")
            },
            "/contracts/tasks": {
                "get": _read_operation("List contract tasks", "contractTasks", "Contracts")
            },
            "/contracts/tasks/{task_id}": {
                "get": _read_operation(
                    "Read pinned task contract",
                    "contractTask",
                    "Contracts",
                    parameters=[_path_parameter("task_id")],
                )
            },
            "/contracts/executions": {
                "post": _write_operation(
                    "Begin contract execution",
                    "beginContractExecution",
                    "Contracts",
                    command_response,
                )
            },
            "/contracts/executions/{execution_id}/{action}": {
                "post": _write_operation(
                    "Read or patch contract files, run checks, validate, complete, block, or amend execution",
                    "updateContractExecution",
                    "Contracts",
                    command_response,
                    parameters=[_path_parameter("execution_id"), _path_parameter("action")],
                )
            },
            "/design": {"get": _read_operation("Design snapshot", "designSnapshot", "Design")},
            "/design/operations": {
                "post": _write_operation("Apply design operations", "applyDesignOperations", "Design", command_response)
            },
            "/documents/{logical_id}": {
                "get": _read_operation(
                    "Read document version",
                    "readDocument",
                    "Documents",
                    parameters=[_path_parameter("logical_id")],
                ),
                "put": _write_operation(
                    "Save document version",
                    "saveDocument",
                    "Documents",
                    command_response,
                    parameters=[_path_parameter("logical_id")],
                ),
            },
            "/actions/{action}": {
                "post": _write_operation(
                    "Run mission action",
                    "runMissionAction",
                    "Mission",
                    command_response,
                    parameters=[_path_parameter("action")],
                    accepted=True,
                )
            },
            "/commands": {
                "post": _write_operation("Submit interaction command", "submitCommand", "Conversation", command_response)
            },
        },
        "components": {
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
            },
            "schemas": {
                "Error": {
                    "type": "object",
                    "required": ["code", "message", "details"],
                    "properties": {
                        "code": {"type": "string", "example": "invalid_request"},
                        "message": {"type": "string", "example": "request is invalid"},
                        "details": {"type": "object", "additionalProperties": True},
                        "current_revision": {"type": "integer", "example": 3},
                    },
                }
            },
            "responses": {
                "Unauthorized": _error_response("Bearer token is missing or invalid"),
                "InvalidRequest": _error_response("The request body or parameters are invalid"),
                "Conflict": _error_response("The requested revision or state is stale"),
            },
        },
    }


def _read_operation(
    summary: str,
    operation_id: str,
    tag: str,
    *,
    security: list[dict[str, list[str]]] | None = None,
    parameters: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    operation: dict[str, object] = {
        "tags": [tag],
        "summary": summary,
        "operationId": operation_id,
        "responses": {
            "200": {
                "description": "Successful response",
                "content": {"application/json": {"schema": {"type": "object"}}},
            },
            "401": {"$ref": "#/components/responses/Unauthorized"},
        },
    }
    if security is not None:
        operation["security"] = security
    if parameters:
        operation["parameters"] = parameters
    return operation


def _write_operation(
    summary: str,
    operation_id: str,
    tag: str,
    responses: dict[str, object],
    *,
    parameters: list[dict[str, object]] | None = None,
    accepted: bool = False,
) -> dict[str, object]:
    selected_responses = dict(responses)
    if accepted:
        selected_responses["202"] = selected_responses.pop("200")
    operation: dict[str, object] = {
        "tags": [tag],
        "summary": summary,
        "operationId": operation_id,
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {"type": "object"}}},
        },
        "responses": selected_responses,
    }
    if parameters:
        operation["parameters"] = parameters
    return operation


def _path_parameter(name: str) -> dict[str, object]:
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": "string"},
        "example": "mission%2Fidea" if name == "logical_id" else "research",
    }


def _error_response(description: str) -> dict[str, object]:
    return {
        "description": description,
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Error"}}
        },
    }
