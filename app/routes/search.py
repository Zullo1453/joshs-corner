"""Local read-only search transport. POST keeps terms out of access-log URLs."""
from flask import Blueprint, jsonify, request

from ..search import MAX_QUERY_LENGTH, UniversalSearchService

search_bp = Blueprint("search", __name__, url_prefix="/search")


@search_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@search_bp.post("")
def query():
    if request.content_length and request.content_length > 4096:
        return jsonify(error="Search request is too long."), 413
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) != {"query"}:
        return jsonify(error="Provide a search query."), 400
    value = payload["query"]
    if not isinstance(value, str) or len(value) > MAX_QUERY_LENGTH:
        return jsonify(error="Search must be 200 characters or fewer."), 400
    results, unavailable = UniversalSearchService().search(value)
    return jsonify(results=[result.public() for result in results], unavailable=unavailable, limit=40)
