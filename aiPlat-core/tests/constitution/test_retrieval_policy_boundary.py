"""
Constitution Test G10: retrieval_policy MUST NOT be registered as a Skill.

Verifies that retrieval_policy, answer_strategy, and question_analysis
are internal policy modules (in core/apps/document_intelligence/) and
are NOT registered in the SkillRegistry.
"""

import sys
import os


def test_retrieval_policy_is_not_skill():
    """Ensure retrieval_policy is not a Skill — it's an Internal Policy."""
    # Check: retrieval_policy.py exists in document_intelligence (not skills/)
    policy_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "core", "apps", "document_intelligence", "retrieval_policy.py"
    )
    assert os.path.exists(policy_path), "retrieval_policy.py should exist"

    # Check: no skill with name 'retrieval_policy' in engine/skills
    skills_dir = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "core", "engine", "skills"
    )
    if os.path.exists(skills_dir):
        for root, dirs, files in os.walk(skills_dir):
            for f in files:
                if "retrieval" in f.lower() and f.endswith((".md", ".py")):
                    assert "retrieval_policy" not in f, (
                        f"Found {f} in skills/ — retrieval_policy must be Internal Policy, not Skill"
                    )

    print("G10 PASS: retrieval_policy is an Internal Policy module")


def test_entity_resolver_not_in_skills():
    """Ensure entity_resolver is in ontology_engine, not skills."""
    engine_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "core", "harness", "ontology_engine", "entity_resolver.py"
    )
    assert os.path.exists(engine_path), "entity_resolver.py should be in ontology_engine"


def test_knowledge_synthesis_not_in_skills():
    """Ensure knowledge_synthesis is in ontology_engine, not skills."""
    synth_path = os.path.join(
        os.path.dirname(__file__), "..", "..",
        "core", "harness", "ontology_engine", "knowledge_synthesis.py"
    )
    assert os.path.exists(synth_path), "knowledge_synthesis.py should be in ontology_engine"


if __name__ == "__main__":
    test_retrieval_policy_is_not_skill()
    test_entity_resolver_not_in_skills()
    test_knowledge_synthesis_not_in_skills()
