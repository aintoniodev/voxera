"""Acceptance runtime: expands JSON IR into executions and dispatches steps.

Implements the runtime contract from the Acceptance Pipeline Specification
(acceptance-generator.md): load IR, expand scenarios into executions (one per
example row, or one with an empty example object), prepend background steps,
resolve placeholders, route steps to project step handlers, and fail on
unsupported steps, missing values, invalid conversions, or failed assertions.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

PLACEHOLDER = re.compile(r"<([A-Za-z0-9_]+)>")


class AcceptanceError(Exception):
    """Base class for acceptance-test failures."""


class UnsupportedStepError(AcceptanceError):
    """The step text matches no registered handler."""


class MissingValueError(AcceptanceError):
    """A placeholder referenced by a step is absent from the example object."""


class InvalidValueError(AcceptanceError):
    """An example value is malformed or semantically invalid."""


class AssertionFailure(AcceptanceError):
    """A step assertion failed."""


def load_ir(path: str | Path) -> dict:
    """Load and validate a parser-produced JSON IR file."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidValueError(f"cannot read feature IR: {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("name"), str):
        raise InvalidValueError(f"invalid feature IR: missing string 'name' in {path}")
    if not isinstance(data.get("scenarios"), list):
        raise InvalidValueError(f"invalid feature IR: missing 'scenarios' list in {path}")
    return data


@dataclass
class Execution:
    """One scenario execution: a scenario plus one example row."""

    scenario_index: int
    example_index: int  # one-based, per APS naming
    name: str  # "<scenario name>/example_<n>"
    example: dict[str, str]
    steps: list[dict] = field(default_factory=list)


def _execution_steps(feature: dict, scenario: dict) -> list[dict]:
    """Steps for one scenario: background steps (if any) then scenario steps."""
    background = feature.get("background") or []
    return [dict(step) for step in background] + [dict(step) for step in scenario["steps"]]


def expand(feature: dict) -> list[Execution]:
    """Expand a feature IR into one execution per example row.

    Scenarios without examples execute once with an empty example object.
    Background steps are prepended to every execution.
    """
    executions: list[Execution] = []
    for scenario_index, scenario in enumerate(feature["scenarios"]):
        examples = scenario.get("examples") or []
        rows: list[dict] = examples if examples else [{}]
        for example_index, example in enumerate(rows, start=1):
            executions.append(
                Execution(
                    scenario_index=scenario_index,
                    example_index=example_index,
                    name=f"{scenario['name']}/example_{example_index}",
                    example=example,
                    steps=_execution_steps(feature, scenario),
                )
            )
    return executions


def expand_text(text: str, example: dict[str, str]) -> str:
    """Replace ``<placeholder>`` tokens with values from ``example``.

    Raises :class:`MissingValueError` when a placeholder has no example value.
    """

    def _repl(match: re.Match) -> str:
        name = match.group(1)
        if name not in example:
            raise MissingValueError(
                f"example value for placeholder '{name}' is missing"
            )
        return example[name]

    return PLACEHOLDER.sub(_repl, text)


class StepRegistry:
    """Registry of project step handlers.

    Two handler kinds are supported:

    - regex handlers (default): the pattern captures placeholder names; the
      runtime fetches each captured name from the current example object and
      passes ``{name: value}`` as ``params``. One handler covers every step
      shape that varies only by example values.
    - literal handlers: exact text matching on the example-expanded step text
      (the APS portable minimum), e.g. ``"the result is <result>"``.
    """

    def __init__(self, world_factory: Callable[[Execution], dict] | None = None) -> None:
        self._handlers: list[tuple[re.Pattern, Callable, str]] = []
        self._literals: list[tuple[str, Callable]] = []
        self._world_factory = world_factory

    def register(self, pattern: str) -> Callable:
        """Decorator: register a regex handler for ``pattern``."""

        def _decorator(fn: Callable) -> Callable:
            self._handlers.append((re.compile(pattern), fn, "regex"))
            return fn

        return _decorator

    def register_literal(self, text: str) -> Callable:
        """Decorator: register an exact-text handler (APS portable minimum)."""

        def _decorator(fn: Callable) -> Callable:
            self._literals.append((text, fn))
            return fn

        return _decorator

    def _params_for_match(self, match: re.Match, example: dict[str, str]) -> dict[str, str]:
        """Map captured placeholder names to example values."""
        params: dict[str, str] = {}
        for name in match.groups():
            if name not in example:
                raise MissingValueError(
                    f"example value for placeholder '{name}' is missing"
                )
            params[name] = example[name]
        return params

    def match(
        self, text: str, example: dict[str, str]
    ) -> tuple[Callable, dict[str, str]] | None:
        """Find the handler for ``text``.

        Returns ``(handler, params)`` where ``params`` maps captured
        placeholder names to example values, or ``None`` when no handler
        matches. Raises :class:`MissingValueError` when a captured placeholder
        has no example value.
        """
        for pattern, fn, _kind in self._handlers:
            match = pattern.fullmatch(text)
            if match:
                return fn, self._params_for_match(match, example)
        expanded = expand_text(text, example)
        for literal, fn in self._literals:
            if literal == expanded:
                return fn, {}
        return None

    def make_world(self, execution: Execution) -> dict:
        """Create a fresh world/state object for one scenario execution."""
        if self._world_factory is not None:
            return self._world_factory(execution)
        return {"execution": execution.name}


Handler = Callable[..., Any]


@dataclass
class ExecutionResult:
    """Outcome of one scenario execution."""

    name: str
    ok: bool
    failure: str | None = None
    duration_ms: int = 0


def run_execution(
    feature: dict,
    execution: Execution,
    registry: StepRegistry,
    world: dict | None = None,
) -> ExecutionResult:
    """Execute one scenario execution; never raises, reports failures."""
    started = time.perf_counter()
    try:
        if world is None:
            world = registry.make_world(execution)
        for step in execution.steps:
            dispatch_step(step, execution.example, registry, world)
        return ExecutionResult(
            execution.name, True, duration_ms=_elapsed_ms(started)
        )
    except AcceptanceError as exc:
        return ExecutionResult(
            execution.name, False, str(exc), duration_ms=_elapsed_ms(started)
        )
    except Exception as exc:  # unexpected: still a test failure, with diagnostics
        return ExecutionResult(
            execution.name,
            False,
            f"unexpected error: {type(exc).__name__}: {exc}",
            duration_ms=_elapsed_ms(started),
        )


def dispatch_step(
    step: dict, example: dict[str, str], registry: StepRegistry, world: dict
) -> None:
    """Route one step to its handler, failing unsupported or malformed steps."""
    text = step.get("text", "")
    matched = registry.match(text, example)
    if matched is None:
        raise UnsupportedStepError(
            f"unsupported step: {step.get('keyword', '')} {text}"
        )
    handler, params = matched
    handler(text, params, example, world)


def run_execution_by_index(
    feature: dict,
    scenario_index: int,
    example_index: int,
    registry: StepRegistry,
) -> ExecutionResult:
    """Run the scenario execution identified by its scenario/example indexes."""
    for execution in expand(feature):
        if (
            execution.scenario_index == scenario_index
            and execution.example_index == example_index
        ):
            return run_execution(feature, execution, registry)
    return ExecutionResult(
        f"scenario_{scenario_index + 1}/example_{example_index}",
        False,
        f"no execution for scenario index {scenario_index}, example index {example_index}",
    )


def run_all(feature: dict, registry: StepRegistry) -> list[ExecutionResult]:
    """Run every scenario execution represented by the IR, in order."""
    return [run_execution(feature, execution, registry) for execution in expand(feature)]


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
