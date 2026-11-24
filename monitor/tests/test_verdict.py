from monitor.verdict import TickEvidence, evaluate


def clean(**overrides) -> TickEvidence:
    values = {
        "new_sentry_issues": 0,
        "sentry_error_level_issues": 0,
        "error_count": 10,
        "baseline_error_count": 10.0,
        "smoke_failures": 0,
        "unavailable_sources": [],
    }
    values.update(overrides)
    return TickEvidence(**values)


def test_missing_baseline_is_yellow():
    assert evaluate(clean(baseline_error_count=None), history=[]) == "YELLOW"


def test_unavailable_source_is_yellow_never_green():
    assert evaluate(clean(unavailable_sources=["sentry"]), history=[]) == "YELLOW"


def test_error_level_issue_is_red_on_second_consecutive_tick():
    ev = clean(new_sentry_issues=1, sentry_error_level_issues=1)
    assert evaluate(ev, history=["RED"]) == "RED"
    assert evaluate(ev, history=["GREEN"]) == "YELLOW"


def test_error_rate_above_three_times_baseline_for_two_ticks_is_red():
    assert evaluate(clean(error_count=31), history=["YELLOW"]) == "RED"


def test_zero_baseline_with_errors_is_yellow():
    assert (
        evaluate(clean(error_count=5, baseline_error_count=0.0), history=[]) == "YELLOW"
    )


def test_new_issue_or_smoke_failure_is_yellow():
    assert evaluate(clean(new_sentry_issues=1), history=["GREEN"]) == "YELLOW"
    assert evaluate(clean(smoke_failures=1), history=["GREEN"]) == "YELLOW"


def test_clean_tick_is_green():
    assert evaluate(clean(), history=["GREEN"]) == "GREEN"


def test_zero_baseline_with_zero_errors_is_green():
    assert (
        evaluate(clean(error_count=0, baseline_error_count=0.0), history=[]) == "GREEN"
    )
