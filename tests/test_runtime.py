"""Runtime contract tests: IR expansion, dispatch, and failure semantics."""

import pytest

from acceptance.runtime import (
    AssertionFailure,
    Execution,
    InvalidValueError,
    MissingValueError,
    StepRegistry,
    UnsupportedStepError,
    dispatch_step,
    expand,
    expand_text,
    load_ir,
    run_all,
    run_execution,
)

FEATURE = {
    "name": "probe",
    "background": [
        {"keyword": "Given", "text": "a configured project state", "parameters": []}
    ],
    "scenarios": [
        {
            "name": "plain",
            "steps": [{"keyword": "Then", "text": "the result is ok"}],
            "examples": [],
        },
        {
            "name": "outlined",
            "steps": [{"keyword": "When", "text": "run with <input>", "parameters": ["input"]}],
            "examples": [
                {"input": "a.wav", "result": "ok"},
                {"input": "b.wav", "result": "ok"},
            ],
        },
    ],
}


def make_registry():
    registry = StepRegistry()

    @registry.register(r"^the result is <([A-Za-z0-9_]+)>$")
    def result_handler(text, params, example, world):
        world["result"] = params

    @registry.register(r"^run with <([A-Za-z0-9_]+)>$")
    def run_handler(text, params, example, world):
        world["ran"] = params

    @registry.register_literal("a configured project state")
    def background_handler(text, params, example, world):
        world.setdefault("backgrounds", 0)
        world["backgrounds"] += 1

    @registry.register_literal("the result is ok")
    def ok_handler(text, params, example, world):
        world["result"] = "ok"

    return registry


class TestExpand:
    def test_scenario_without_examples_executes_once(self):
        executions = expand(FEATURE)
        names = [e.name for e in executions]
        assert names == ["plain/example_1", "outlined/example_1", "outlined/example_2"]

    def test_empty_example_object_for_plain_scenario(self):
        (plain,) = [e for e in expand(FEATURE) if e.scenario_index == 0]
        assert plain.example == {}

    def test_background_steps_prepended(self):
        (plain,) = [e for e in expand(FEATURE) if e.scenario_index == 0]
        assert plain.steps[0]["text"] == "a configured project state"
        assert plain.steps[-1]["text"] == "the result is ok"

    def test_background_is_optional(self):
        feature = {"name": "x", "scenarios": [{"name": "s", "steps": [], "examples": []}]}
        (execution,) = expand(feature)
        assert execution.steps == []


class TestExpandText:
    def test_placeholder_replaced_from_example(self):
        assert expand_text("go <place>", {"place": "home"}) == "go home"

    def test_missing_placeholder_raises(self):
        with pytest.raises(MissingValueError):
            expand_text("go <place>", {})

    def test_repeated_placeholder(self):
        assert expand_text("a <x> b <x>", {"x": "1"}) == "a 1 b 1"


class TestRegistry:
    def test_regex_handler_captures_placeholder_name(self):
        registry = make_registry()
        handler, params = registry.match("the result is <result>", {"result": "ok"})
        assert params == {"result": "ok"}
        assert handler.__name__ == "result_handler"

    def test_literal_handler_matches_expanded_text(self):
        registry = make_registry()
        handler, params = registry.match("a configured project state", {})
        assert handler.__name__ == "background_handler"
        assert params == {}

    def test_no_match_returns_none(self):
        registry = make_registry()
        assert registry.match("completely unknown step", {}) is None

    def test_missing_captured_value_raises(self):
        registry = make_registry()
        with pytest.raises(MissingValueError):
            registry.match("the result is <result>", {})

    def test_unrelated_step_does_not_match(self):
        registry = make_registry()
        assert registry.match("the result is fine", {}) is None


class TestExecution:
    def test_background_and_scenario_share_world(self):
        registry = make_registry()
        (plain,) = [e for e in expand(FEATURE) if e.scenario_index == 0]
        world = {"count": 0}
        result = run_execution(FEATURE, plain, registry, world)
        assert result.ok
        assert world["backgrounds"] == 1
        assert world["result"] == "ok"

    def test_fresh_world_per_execution(self):
        registry = make_registry()
        results = run_all(FEATURE, registry)
        assert all(r.ok for r in results)
        assert results[1].name == "outlined/example_1"
        assert results[2].name == "outlined/example_2"

    def test_unsupported_step_fails(self):
        feature = {
            "name": "x",
            "scenarios": [{"name": "s", "steps": [{"keyword": "Then", "text": "nonsense step"}], "examples": []}],
        }
        (execution,) = expand(feature)
        registry = make_registry()
        result = run_execution(feature, execution, registry)
        assert not result.ok
        assert "unsupported step" in result.failure

    def test_assertion_failure_reported(self):
        registry = StepRegistry()

        @registry.register(r"^must hold$")
        def fail_handler(text, params, example, world):
            raise AssertionFailure("nope")

        (execution,) = expand({"name": "x", "scenarios": [{"name": "s", "steps": [{"keyword": "Then", "text": "must hold"}], "examples": []}]})
        result = run_execution({"name": "x", "scenarios": [{"name": "s", "steps": [{"keyword": "Then", "text": "must hold"}], "examples": []}]}, execution, registry)
        assert not result.ok
        assert result.failure == "nope"

    def test_dispatch_unmatched_step_raises(self):
        registry = make_registry()
        with pytest.raises(UnsupportedStepError):
            dispatch_step({"keyword": "Then", "text": "unknown"}, {}, registry, {})


class TestLoadIr:
    def test_loads_valid_ir(self, tmp_path):
        path = tmp_path / "f.json"
        path.write_text('{"name": "n", "scenarios": []}', encoding="utf-8")
        assert load_ir(path)["name"] == "n"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(InvalidValueError):
            load_ir(tmp_path / "nope.json")

    def test_invalid_shape_raises(self, tmp_path):
        path = tmp_path / "f.json"
        path.write_text('{"name": 3}', encoding="utf-8")
        with pytest.raises(InvalidValueError):
            load_ir(path)
