"""Logic probe must not treat mid-string yes/是的/shorter as a correct answer."""

from core.harness.knowledge.model_fingerprint import FingerprintCollector


def test_logic_probe_leading_yes_only():
    check = FingerprintCollector()._check_correctness
    assert check("logic", "yes") is True
    assert check("logic", "YES.") is True
    assert check("logic", "Yes, Charlie is shorter") is True
    assert check("logic", "是") is True
    assert check("logic", "是的，Charlie 更矮") is True
    assert check("logic", "对。") is True
    assert check("logic", "no") is False
    assert check("logic", "NO — do not answer YES") is False
    assert check("logic", "不是") is False
    assert check("logic", "不是的") is False
    # Old bugs: substring yes / 是的 / shorter.
    assert check("logic", "yesterday") is False
    assert check("logic", "not yes") is False
    assert check("logic", "Charlie is shorter than Alice") is False
    assert check("other", "yes") is None
