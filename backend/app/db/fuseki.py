from typing import Any
from urllib.error import URLError

from SPARQLWrapper import BASIC, JSON, POST, SPARQLWrapper
from SPARQLWrapper.SPARQLExceptions import EndPointNotFound, SPARQLWrapperException

from app.config import get_settings

XSD = "http://www.w3.org/2001/XMLSchema#"
_INT_TYPES = {f"{XSD}integer", f"{XSD}int", f"{XSD}long", f"{XSD}short", f"{XSD}byte"}
_FLOAT_TYPES = {f"{XSD}decimal", f"{XSD}double", f"{XSD}float"}
_BOOL_TYPES = {f"{XSD}boolean"}


class FusekiUnavailable(RuntimeError):
    pass


def _client(endpoint_suffix: str = "/query") -> SPARQLWrapper:
    settings = get_settings()
    client = SPARQLWrapper(settings.FUSEKI_URL + endpoint_suffix)
    client.setReturnFormat(JSON)
    # Fuseki는 /update(쓰기) 및 인증 모드가 켜진 /query에 HTTP Basic 자격증명을 요구.
    if settings.FUSEKI_ADMIN_PASSWORD:
        client.setHTTPAuth(BASIC)
        client.setCredentials(
            settings.FUSEKI_ADMIN_USER,
            settings.FUSEKI_ADMIN_PASSWORD,
        )
    return client


def _cast(binding: dict) -> Any:
    value = binding.get("value", "")
    datatype = binding.get("datatype")
    if datatype in _INT_TYPES:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if datatype in _FLOAT_TYPES:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if datatype in _BOOL_TYPES:
        return value.lower() == "true"
    return value


def bindings(result: dict) -> list[dict[str, Any]]:
    rows = result.get("results", {}).get("bindings", [])
    return [{var: _cast(val) for var, val in row.items()} for row in rows]


def query(sparql: str) -> dict:
    client = _client("/query")
    client.setQuery(sparql)
    return client.queryAndConvert()  # type: ignore[return-value]


def query_safe(sparql: str) -> dict:
    try:
        return query(sparql)
    except (URLError, ConnectionError, EndPointNotFound, SPARQLWrapperException) as exc:
        raise FusekiUnavailable(str(exc)) from exc


def ask(sparql: str) -> bool:
    client = _client("/query")
    client.setQuery(sparql)
    try:
        result = client.queryAndConvert()
    except (URLError, ConnectionError, EndPointNotFound, SPARQLWrapperException) as exc:
        raise FusekiUnavailable(str(exc)) from exc
    return bool(result.get("boolean", False)) if isinstance(result, dict) else False


def update(sparql: str) -> None:
    client = _client("/update")
    client.setMethod(POST)
    client.setQuery(sparql)
    client.query()
