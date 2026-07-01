from preflight import PreflightResult


def test_preflight_result_defaults():
    r = PreflightResult(passed=True)
    assert r.passed is True
    assert r.stage is None
    assert r.reason == ""
    assert r.detected_original_sender is None
