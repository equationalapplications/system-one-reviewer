def test_halves_round_up(jr):
    assert jr.sev_level(0.5) == 1
    assert jr.sev_level(1.5) == 2
    assert jr.sev_level(2.5) == 3          # banker's rounding said 2

def test_clamping_and_none(jr):
    assert jr.sev_level(-1) == 0
    assert jr.sev_level(None) == 0
    assert jr.sev_level(9) == 3
    assert jr.sev_level(2.6) == 3
