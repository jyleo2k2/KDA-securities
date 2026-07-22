import pytest

from backend.app.chat import tools
from backend.app.chat.tools import (
    CHAT_AGENT_TOOLS,
    ENGINE_AGENT_TOOLS,
    PENSION_TAX_AGENT_TOOLS,
)


def test_chat_agent_registers_every_read_only_engine_tool() -> None:
    assert tuple(tool.__name__ for tool in ENGINE_AGENT_TOOLS) == (
        "account_diagnostics_tool",
        "profile_assessment_tool",
        "allocation_example_tool",
        "account_aggregation_tool",
    )
    assert CHAT_AGENT_TOOLS == ENGINE_AGENT_TOOLS + PENSION_TAX_AGENT_TOOLS


@pytest.mark.parametrize(
    ("tool_name", "engine_name"),
    (
        ("account_diagnostics_tool", "evaluate_account_diagnostics"),
        ("profile_assessment_tool", "evaluate_profile"),
        ("allocation_example_tool", "build_allocation_example"),
        ("account_aggregation_tool", "aggregate_accounts"),
    ),
)
def test_engine_tools_delegate_without_transforming_inputs(
    monkeypatch: pytest.MonkeyPatch, tool_name: str, engine_name: str
) -> None:
    inputs = object()
    expected = object()
    monkeypatch.setattr(tools, engine_name, lambda received: expected)

    assert getattr(tools, tool_name)(inputs) is expected
