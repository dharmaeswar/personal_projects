import pytest

from quality_platform import seed
from quality_platform.mcp import MCPClient, MCPServer


@pytest.fixture()
def client():
    server = MCPServer(seed.build_registry())
    return MCPClient(server)


def test_initialize_and_ping(client):
    info = client.initialize()
    assert info["serverInfo"]["name"] == "quality-mcp-server"
    assert client.server.handle(
        {"jsonrpc": "2.0", "id": 99, "method": "ping"})["result"] == {}


def test_list_tools_has_five(client):
    names = [t["name"] for t in client.list_tools()]
    assert names == ["search_data_products", "get_product_metadata",
                     "run_quality_check", "get_quality_metrics", "list_lineage"]


def test_search_tool(client):
    result = client.call_tool("search_data_products", {"query": "batch release"})
    assert result["products"][0]["product_id"] == "batch-release"


def test_metadata_tool(client):
    result = client.call_tool("get_product_metadata", {"product_id": "capa-tracker"})
    assert result["product"]["owner"] == "quality-assurance"
    assert result["product"]["access_level"] == "restricted"


def test_quality_check_tool_passes(client):
    result = client.call_tool("run_quality_check", {"product_id": "batch-release"})
    assert result["passed"] is True
    assert result["rows_checked"] == 12


def test_metrics_tool_quarters(client):
    result = client.call_tool("get_quality_metrics", {"quarter": "Q2"})
    assert result["metrics"]["mean_release_cycle_days"] == 20.0
    result = client.call_tool("get_quality_metrics", {"quarter": "Q3"})
    assert result["metrics"]["mean_release_cycle_days"] == 27.5
    assert result["deviations"]["by_category"]["documentation"] == 7


def test_lineage_tool(client):
    result = client.call_tool("list_lineage", {"product_id": "deviation-register"})
    assert result["lineage"][0]["transform"] == "classify_severity v2"


def test_unknown_tool_error(client):
    with pytest.raises(RuntimeError, match="unknown tool"):
        client.call_tool("nope", {})


def test_missing_argument_error(client):
    with pytest.raises(RuntimeError, match="missing required argument"):
        client.call_tool("get_product_metadata", {})


def test_wrong_type_argument_error(client):
    with pytest.raises(RuntimeError, match="must be a string"):
        client.call_tool("get_product_metadata", {"product_id": 7})


def test_unknown_product_error(client):
    with pytest.raises(RuntimeError, match="unknown product_id"):
        client.call_tool("get_product_metadata", {"product_id": "nope"})


def test_unknown_method_and_bad_version(client):
    resp = client.server.handle({"jsonrpc": "2.0", "id": 1, "method": "nope"})
    assert resp["error"]["code"] == -32601
    resp = client.server.handle({"jsonrpc": "1.0", "id": 1, "method": "ping"})
    assert resp["error"]["code"] == -32600
