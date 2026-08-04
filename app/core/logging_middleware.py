import json
import time
from urllib.parse import parse_qsl, urlencode

SENSITIVE_HEADERS = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
    "x-auth-token",
}

SENSITIVE_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "token",
    "access_token",
    "refresh_token",
    "secret",
    "client_secret",
    "client_id",
    "api_key",
    "apikey",
    "api-key",
    "access_key",
    "private_key",
    "key",
    "authorization",
    "credentials",
    "credential",
}

SENSITIVE_SUBSTRINGS = ("token", "password", "secret", "credential")

MAX_BODY_BYTES = 100_000

BODY_LOGGABLE_PREFIXES = (
    "application/json",
    "text/",
    "application/xml",
    "application/x-www-form-urlencoded",
)

SKIP_BODY_PREFIXES = (
    "multipart/",
    "image/",
    "audio/",
    "video/",
    "application/pdf",
    "application/octet-stream",
    "application/zip",
    "application/x-zip-compressed",
)


def _is_sensitive_field(name: str) -> bool:
    lowered = name.lower()
    if lowered in SENSITIVE_FIELD_NAMES:
        return True
    return any(sub in lowered for sub in SENSITIVE_SUBSTRINGS)


def _redact_value(obj):
    if isinstance(obj, dict):
        return {
            k: ("***" if _is_sensitive_field(k) else _redact_value(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_value(item) for item in obj]
    return obj


def _is_body_loggable(content_type: str) -> bool:
    if not content_type:
        return False
    ct = content_type.lower()
    if any(ct.startswith(prefix) for prefix in SKIP_BODY_PREFIXES):
        return False
    return any(ct.startswith(prefix) for prefix in BODY_LOGGABLE_PREFIXES)


def _redact_body(body: bytes, content_type: str) -> str:
    if not body:
        return ""
    if len(body) > MAX_BODY_BYTES:
        return f"<body truncated: {len(body)} bytes>"
    text = body.decode("utf-8", errors="replace")
    ct = (content_type or "").lower()
    if "json" in ct:
        try:
            return json.dumps(_redact_value(json.loads(text)), ensure_ascii=False)
        except Exception:
            pass
    if "x-www-form-urlencoded" in ct:
        try:
            pairs = [
                (k, "***" if _is_sensitive_field(k) else v)
                for k, v in parse_qsl(text)
            ]
            return urlencode(pairs, safe="*")
        except Exception:
            pass
    return text


def _redact_headers(headers: dict) -> dict:
    return {
        k: ("***" if k in SENSITIVE_HEADERS or _is_sensitive_field(k) else v)
        for k, v in headers.items()
    }


def _redact_query(query_string: str) -> str:
    if not query_string:
        return ""
    try:
        pairs = [
            (k, "***" if _is_sensitive_field(k) else v)
            for k, v in parse_qsl(query_string)
        ]
        return urlencode(pairs, safe="*")
    except Exception:
        return query_string


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_start = time.perf_counter()
        request_body = bytearray()

        request_content_type = ""
        for name, value in scope.get("headers", []):
            if name == b"content-type":
                request_content_type = value.decode("latin-1").lower()
                break
        buffer_request_body = _is_body_loggable(request_content_type)

        async def receive_logging():
            message = await receive()
            if message["type"] == "http.request":
                if buffer_request_body and len(request_body) < MAX_BODY_BYTES:
                    request_body.extend(message.get("body", b""))
            return message

        status_code = 0
        response_headers = {}
        response_content_type = ""
        response_body = bytearray()

        async def send_logging(message):
            nonlocal status_code, response_headers, response_content_type
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_headers = {
                    k.decode("latin-1").lower(): v.decode("latin-1")
                    for k, v in message.get("headers", [])
                }
                response_content_type = response_headers.get("content-type", "")
            elif message["type"] == "http.response.body":
                if _is_body_loggable(response_content_type) and len(response_body) < MAX_BODY_BYTES:
                    response_body.extend(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive_logging, send_logging)
        except Exception:
            if status_code == 0:
                status_code = 500
            print(
                f"RequestLoggingMiddleware caught exception for {scope.get('method', '')} {scope.get('path', '')}",
                flush=True,
            )
            raise

        duration_ms = (time.perf_counter() - request_start) * 1000
        method = scope.get("method", "")
        path = scope.get("path", "")
        query_raw = scope.get("query_string", b"").decode("latin-1")
        query_redacted = _redact_query(query_raw)

        request_headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }

        client = scope.get("client")
        client_ip = client[0] if client else None

        log_parts = {
            "method": method,
            "path": path,
            "query": query_redacted,
            "client_ip": client_ip,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "request_headers": _redact_headers(request_headers),
            "request_body": _redact_body(bytes(request_body), request_content_type)
            if _is_body_loggable(request_content_type)
            else f"<not logged: content-type {request_content_type or 'unknown'}>",
            "response_headers": _redact_headers(response_headers),
            "response_body": _redact_body(bytes(response_body), response_content_type)
            if _is_body_loggable(response_content_type)
            else f"<not logged: content-type {response_content_type or 'unknown'}>",
        }

        url = path + (f"?{query_redacted}" if query_redacted else "")
        print(
            f"{method} {url} -> {status_code} in {duration_ms:.2f}ms",
            flush=True,
        )
        print(
            f"Request/Response details: {json.dumps(log_parts, ensure_ascii=False, default=str)}",
            flush=True,
        )
