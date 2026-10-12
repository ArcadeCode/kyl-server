from flask import Response, jsonify, request


def error_response(
    code: str, message: str, status: int, headers: dict[str, str] | None = None
) -> Response:
    """Uniform JSON error: {"error": <code>, "message": <human readable>}."""
    response = jsonify({"error": code, "message": message})
    response.status_code = status
    if headers:
        response.headers.update(headers)
    return response


def get_json_strings(*fields: str) -> dict[str, str] | None:
    """
    Read the JSON body and return the requested fields, or None if the body is
    not a JSON object or if any requested field is missing / not a string.
    """
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None
    values: dict[str, str] = {}
    for field in fields:
        value = data.get(field)
        if not isinstance(value, str):
            return None
        values[field] = value
    return values
