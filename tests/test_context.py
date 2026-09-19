"""Tests for context builder, smart truncation, sliding window history, and decision parsing."""

from orchestrator.context import (
    build_reasoning_prompt,
    parse_reasoner_decision,
    smart_truncate,
)
from orchestrator.state import TaskState, IterationRecord
from executors.base import ExecutorResult


def test_smart_truncate():
    # Below limit
    assert smart_truncate("Hello world", 20) == "Hello world"

    # Paragraph boundary truncation
    para_text = "Paragraph 1 is here.\n\nParagraph 2 is here.\n\nParagraph 3 is very long and should get cut off."
    truncated = smart_truncate(para_text, 50)
    assert "[... truncated ...]" in truncated
    assert "Paragraph 1 is here.\n\nParagraph 2 is here." in truncated
    assert "Paragraph 3" not in truncated

    # Line boundary truncation
    line_text = "Line 1\nLine 2\nLine 3\nLine 4 is very long and exceeds boundary"
    truncated_line = smart_truncate(line_text, 25)
    assert "[... truncated ...]" in truncated_line
    assert "Line 1\nLine 2" in truncated_line


def test_sliding_window_history():
    state = TaskState(
        task_id="test-task",
        project_name="medicoder",
        project_path="/tmp/medicoder",
        goal="Test sliding window",
    )

    # Add 5 iterations
    for i in range(1, 6):
        rec = IterationRecord(
            iteration_number=i,
            reasoner_used="claude",
            lead_decision={
                "action": "DELEGATE",
                "analysis": f"Analysis for step {i} that needs tracking.",
            },
            executor_used="python",
            instruction=f"echo step {i}",
            execution_result=ExecutorResult(
                success=True,
                executor_name="python",
                output=f"step {i} output details",
                exit_code=0,
            ),
        )
        state.iterations.append(rec)

    knowledge = {"name": "medicoder"}
    prompt = build_reasoning_prompt(state, knowledge, ["python"], history_window=2)

    # Old iterations (1, 2, 3) should be compressed one-liners
    assert "[Iteration 1] Action: DELEGATE | Executor: python | Status: Success" in prompt
    assert "[Iteration 2] Action: DELEGATE | Executor: python | Status: Success" in prompt
    assert "[Iteration 3] Action: DELEGATE | Executor: python | Status: Success" in prompt

    # Recent iterations (4, 5) should have full details
    assert "--- Iteration 4 ---" in prompt
    assert "--- Iteration 5 ---" in prompt
    assert "Output: step 4 output details" in prompt
    assert "Output: step 5 output details" in prompt


def test_parse_reasoner_decision_json_markdown():
    # Direct JSON
    dec1 = parse_reasoner_decision('{"action": "COMPLETE", "analysis": "Done"}')
    assert dec1["action"] == "COMPLETE"
    assert dec1["analysis"] == "Done"

    # Markdown wrapped ```json ... ```
    md_text = """Here is my plan:
```json
{
  "action": "DELEGATE",
  "executor": "agy",
  "instruction": "Fix bug"
}
```
Hope this helps!"""
    dec2 = parse_reasoner_decision(md_text)
    assert dec2["action"] == "DELEGATE"
    assert dec2["executor"] == "agy"
    assert dec2["instruction"] == "Fix bug"

    # Fallback unparseable text
    unparseable = "Sorry, I cannot produce JSON."
    dec3 = parse_reasoner_decision(unparseable)
    assert dec3["action"] == "ABORT"
    assert dec3["raw_text"] == unparseable


def test_split_prompt_and_delegation_header():
    from orchestrator.context import (
        build_delegation_context_header,
        build_system_prompt,
        build_user_prompt,
    )

    knowledge = {
        "name": "sample_proj",
        "conventions": "Use snake_case for all methods.",
        "safety": "Never touch production db.",
    }
    state = TaskState(
        task_id="task-42",
        project_name="sample_proj",
        project_path="/tmp/sample",
        goal="Refactor authentication",
    )

    sys_prompt = build_system_prompt(knowledge, ["claude", "agy"])
    assert "You are the Lead Reasoning Agent in `Polyphony`" in sys_prompt
    assert "Use snake_case for all methods." in sys_prompt
    assert "Never touch production db." in sys_prompt
    assert "sample_proj" in sys_prompt

    user_prompt = build_user_prompt(state)
    assert "Task ID: task-42" in user_prompt
    assert "Objective / Goal: Refactor authentication" in user_prompt

    delegation_hdr = build_delegation_context_header(knowledge)
    assert "[Project Context: sample_proj]" in delegation_hdr
    assert "Use snake_case for all methods." in delegation_hdr
    assert "Never touch production db." in delegation_hdr
