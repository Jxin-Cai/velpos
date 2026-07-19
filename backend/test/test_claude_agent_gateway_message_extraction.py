from claude_agent_sdk.types import ResultMessage

from infr.client.claude_agent_gateway import ClaudeAgentGateway


def test_extracts_sdk_result_message_as_terminal_result() -> None:
    message = ResultMessage(
        subtype="success",
        duration_ms=10,
        duration_api_ms=8,
        is_error=False,
        num_turns=1,
        session_id="sdk-session",
        result="Done",
        usage={"input_tokens": 3, "output_tokens": 2},
    )

    extracted = ClaudeAgentGateway._extract_message_info(message)

    assert extracted is not None
    assert extracted["message_type"] == "result"
    assert extracted["content"]["text"] == "Done"
    assert extracted["content"]["is_error"] is False


def test_extracts_mapping_result_message_as_terminal_result() -> None:
    extracted = ClaudeAgentGateway._extract_message_info(
        {
            "type": "result",
            "result": "Done",
            "usage": {"input_tokens": 4, "output_tokens": 1},
        }
    )

    assert extracted is not None
    assert extracted["message_type"] == "result"
    assert extracted["content"]["text"] == "Done"
