from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from decision_agent.shared.providers.ollama import (
    OllamaProvider,
    _extract_json_envelopes,
    _to_ollama_messages,
    _to_ollama_tools,
)
from decision_agent.shared.providers.registry import OLLAMA_MODEL_ALIASES, get_provider


class TestMessageTranslation(unittest.TestCase):
    def test_string_user_message_passes_through(self) -> None:
        out = _to_ollama_messages("sys", [{"role": "user", "content": "hi"}])
        self.assertEqual(out[0], {"role": "system", "content": "sys"})
        self.assertEqual(out[1], {"role": "user", "content": "hi"})

    def test_assistant_tool_use_block_becomes_tool_calls(self) -> None:
        msgs = [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "calling tool"},
                    {"type": "tool_use", "id": "x", "name": "read_file", "input": {"path": "a.txt"}},
                ],
            }
        ]
        out = _to_ollama_messages("sys", msgs)
        self.assertEqual(out[1]["role"], "assistant")
        self.assertEqual(out[1]["content"], "calling tool")
        self.assertEqual(
            out[1]["tool_calls"],
            [{"function": {"name": "read_file", "arguments": {"path": "a.txt"}}}],
        )

    def test_user_tool_result_becomes_tool_role_message(self) -> None:
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "x", "content": "OK: file content"},
                ],
            }
        ]
        out = _to_ollama_messages("sys", msgs)
        self.assertEqual(out[1], {"role": "tool", "content": "OK: file content"})


class TestToolTranslation(unittest.TestCase):
    def test_tool_translation_uses_function_envelope(self) -> None:
        tools = [{"name": "read_file", "description": "Read a file", "input_schema": {"type": "object"}}]
        out = _to_ollama_tools(tools)
        self.assertEqual(out[0]["type"], "function")
        self.assertEqual(out[0]["function"]["name"], "read_file")
        self.assertEqual(out[0]["function"]["parameters"], {"type": "object"})


class TestEnvelopeFallback(unittest.TestCase):
    def test_extracts_valid_envelope(self) -> None:
        text = 'I will call the tool: {"tool": "read_file", "input": {"path": "a.txt"}}'
        calls = _extract_json_envelopes(text, {"read_file"})
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["function"]["name"], "read_file")
        self.assertEqual(calls[0]["function"]["arguments"], {"path": "a.txt"})

    def test_ignores_envelope_with_unknown_tool(self) -> None:
        text = '{"tool": "delete_database", "input": {}}'
        self.assertEqual(_extract_json_envelopes(text, {"read_file"}), [])

    def test_handles_no_envelopes(self) -> None:
        self.assertEqual(_extract_json_envelopes("just text, no JSON", {"read_file"}), [])


class TestProviderHTTPMocked(unittest.TestCase):
    def test_complete_with_tools_returns_tool_use_when_model_responds_with_tool_calls(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b-instruct", host="http://test")
        mock_response = {
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "read_file", "arguments": {"path": "a.txt"}}}
                ],
            }
        }
        with patch.object(OllamaProvider, "_post", return_value=mock_response):
            result = provider.complete_with_tools(
                system="sys",
                messages=[{"role": "user", "content": "do it"}],
                tools=[{"name": "read_file", "description": "", "input_schema": {"type": "object"}}],
            )
        self.assertEqual(result["stop_reason"], "tool_use")
        self.assertEqual(result["tool_uses"][0]["name"], "read_file")
        self.assertEqual(result["tool_uses"][0]["input"], {"path": "a.txt"})

    def test_complete_with_tools_envelope_fallback(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b-instruct", host="http://test")
        mock_response = {
            "message": {
                "role": "assistant",
                "content": '{"tool": "read_file", "input": {"path": "a.txt"}}',
            }
        }
        with patch.object(OllamaProvider, "_post", return_value=mock_response):
            result = provider.complete_with_tools(
                system="sys",
                messages=[{"role": "user", "content": "do it"}],
                tools=[{"name": "read_file", "description": "", "input_schema": {"type": "object"}}],
            )
        self.assertEqual(result["stop_reason"], "tool_use")
        self.assertEqual(result["tool_uses"][0]["name"], "read_file")

    def test_complete_with_tools_text_response(self) -> None:
        provider = OllamaProvider(model="qwen2.5:7b-instruct", host="http://test")
        mock_response = {"message": {"role": "assistant", "content": '{"summary": "done"}'}}
        with patch.object(OllamaProvider, "_post", return_value=mock_response):
            result = provider.complete_with_tools(
                system="sys",
                messages=[{"role": "user", "content": "do it"}],
                tools=[{"name": "read_file", "description": "", "input_schema": {"type": "object"}}],
            )
        self.assertEqual(result["stop_reason"], "end_turn")
        self.assertIn("done", result["content"])


class TestRegistry(unittest.TestCase):
    def test_get_provider_with_anthropic_alias_returns_ollama(self) -> None:
        # Override path: explicit override beats env
        provider = get_provider("ollama/qwen2.5")
        self.assertEqual(provider.name, f"ollama/{OLLAMA_MODEL_ALIASES['ollama/qwen2.5']}")

    def test_get_provider_with_llama_alias(self) -> None:
        provider = get_provider("ollama/llama3.1")
        self.assertEqual(provider.name, f"ollama/{OLLAMA_MODEL_ALIASES['ollama/llama3.1']}")

    def test_get_provider_with_custom_tag(self) -> None:
        provider = get_provider("ollama/mistral:7b")
        self.assertEqual(provider.name, "ollama/mistral:7b")


class TestBenchmarkProvidersEnvFilter(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get("BENCHMARK_PROVIDERS")

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop("BENCHMARK_PROVIDERS", None)
        else:
            os.environ["BENCHMARK_PROVIDERS"] = self._saved

    def test_unset_env_keeps_all_conditions(self) -> None:
        os.environ.pop("BENCHMARK_PROVIDERS", None)
        from decision_agent.modules.evaluation.runner import _active_conditions
        keys = set(_active_conditions().keys())
        self.assertEqual(keys, {"A0", "A0_inf", "A", "C", "F", "G_qwen", "G_llama"})

    def test_anthropic_only_drops_ollama_conditions(self) -> None:
        os.environ["BENCHMARK_PROVIDERS"] = "anthropic"
        from decision_agent.modules.evaluation.runner import _active_conditions
        keys = set(_active_conditions().keys())
        self.assertEqual(keys, {"A0", "A0_inf", "A", "C", "F"})

    def test_qwen_only_drops_anthropic_and_llama(self) -> None:
        os.environ["BENCHMARK_PROVIDERS"] = "ollama/qwen2.5"
        from decision_agent.modules.evaluation.runner import _active_conditions
        keys = set(_active_conditions().keys())
        self.assertEqual(keys, {"A", "G_qwen"})

    def test_multi_value_works(self) -> None:
        os.environ["BENCHMARK_PROVIDERS"] = "anthropic, ollama/qwen2.5"
        from decision_agent.modules.evaluation.runner import _active_conditions
        keys = set(_active_conditions().keys())
        self.assertEqual(keys, {"A0", "A0_inf", "A", "C", "F", "G_qwen"})

    def test_unknown_provider_keeps_only_baseline_a(self) -> None:
        # A's provider is None (uses default), so it's always kept. Filtering
        # to a provider no condition declares yields {A} alone.
        os.environ["BENCHMARK_PROVIDERS"] = "nonexistent"
        from decision_agent.modules.evaluation.runner import _active_conditions
        keys = set(_active_conditions().keys())
        self.assertEqual(keys, {"A"})


if __name__ == "__main__":
    unittest.main()
