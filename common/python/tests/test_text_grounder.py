import pytest
from unittest.mock import patch

from computer_use.text_grounder import (
    calculate_text_similarity,
    ground_step_to_screen,
)


def test_calculate_text_similarity():
    assert calculate_text_similarity("Personalization", "Personalization") == 1.0
    assert calculate_text_similarity("Personalization", "personalization") == 1.0
    assert calculate_text_similarity("Personalization", "Colors") < 0.5
    assert calculate_text_similarity("Search Extensions in Marketplace", "Search Extensions") >= 0.85


def test_ground_step_exact_match():
    visible_items = [
        {"ref": "ref_1", "text": "System", "x": 50, "y": 100, "width": 120, "height": 30, "control_type": "ListItem", "source": "uia", "clickable": True},
        {"ref": "ref_2", "text": "Personalization", "x": 50, "y": 150, "width": 120, "height": 30, "control_type": "ListItem", "source": "omniparser", "clickable": True},
        {"ref": "ref_3", "text": "Colors", "x": 300, "y": 200, "width": 100, "height": 40, "control_type": "Button", "source": "uia", "clickable": True},
    ]

    step = {
        "step": 1,
        "target": "Personalization",
        "action": "click",
        "instruction": "Click Personalization in Settings",
    }

    grounded = ground_step_to_screen(step, visible_items)
    assert grounded is not None
    assert grounded["target_ref"] == "ref_2"
    assert grounded["match"]["x"] == 50
    assert grounded["match"]["y"] == 150
    assert grounded["match"]["source"] == "omniparser"


def test_ground_step_fuzzy_and_omniparser_button():
    visible_items = [
        {"ref": "ref_1", "text": "Dark mode", "x": 400, "y": 300, "width": 150, "height": 35, "control_type": "RadioButton", "source": "omniparser", "clickable": True},
        {"ref": "ref_2", "text": "Light mode", "x": 400, "y": 350, "width": 150, "height": 35, "control_type": "RadioButton", "source": "omniparser", "clickable": True},
    ]

    step = {
        "step": 4,
        "target": "Dark",
        "action": "click",
        "instruction": "Select Dark mode",
    }

    grounded = ground_step_to_screen(step, visible_items)
    assert grounded is not None
    assert grounded["target_ref"] == "ref_1"
    assert "Dark" in grounded["target_text"]


def test_ground_step_disambiguate_via_text_llm():
    visible_items = [
        {"ref": "ref_a", "text": "Option A", "x": 100, "y": 200, "width": 50, "height": 20, "control_type": "Button", "source": "uia"},
        {"ref": "ref_b", "text": "Option B", "x": 100, "y": 250, "width": 50, "height": 20, "control_type": "Button", "source": "uia"},
    ]

    step = {
        "step": 1,
        "target": "Specific Setting",
        "action": "click",
        "instruction": "Click the secondary option",
    }

    with patch("computer_use.text_grounder.ask_text_model", return_value={"target_ref": "ref_b"}):
        grounded = ground_step_to_screen(step, visible_items)
        assert grounded is not None
        assert grounded["target_ref"] == "ref_b"


def test_ground_step_self_healing_ignores_failed_refs_and_re_evaluates():
    visible_items = [
        {"ref": "ref_failed", "text": "Light", "x": 100, "y": 100, "width": 50, "height": 20, "control_type": "TabItem", "source": "uia"},
        {"ref": "ref_correct", "text": "Light theme option", "x": 300, "y": 400, "width": 120, "height": 30, "control_type": "RadioButton", "source": "uia", "clickable": True},
    ]

    step = {
        "step": 2,
        "target": "Light",
        "action": "click",
        "instruction": "Select Light theme",
    }

    with patch("computer_use.text_grounder.ask_text_model", return_value={"target_ref": "ref_correct"}):
        grounded = ground_step_to_screen(
            step,
            visible_items,
            failed_refs={"ref_failed"},
            failed_targets={"light"},
            user_task="switch to light mode",
        )
        assert grounded is not None
        assert grounded["target_ref"] == "ref_correct"
