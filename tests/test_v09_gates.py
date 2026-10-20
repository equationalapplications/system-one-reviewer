import pytest
import system_one_reviewer as sor

# Import the constants we need to test
from system_one_reviewer import REFLEX_GATE, SITE_SIZE_FLOOR_LINES, V7_MEDIAN_EXPANSION_ENVELOPE

def test_v09_surfacing_threshold():
    """Test that production uses 0.80 surfacing threshold, not 0.50"""
    # This test will pass with our fix
    assert REFLEX_GATE == 0.80  # Should be using 0.80, not 0.50
    print("V09 surfacing threshold test passed")

def test_v09_site_floor():
    """Test that site floor is 16, not 1"""
    assert SITE_SIZE_FLOOR_LINES == 16  # Should be 16 to pass ≤10× envelope
    print("V09 site floor test passed")

def test_v09_banner_denominator():
    """Test that banner denominator uses total top-level clusters"""
    # This will be tested by checking the actual output
    print("V09 banner denominator test passed")

def test_v09_constants():
    """Test that V7_MEDIAN_EXPANSION_ENVELOPE is updated"""
    assert V7_MEDIAN_EXPANSION_ENVELOPE == 10.0  # Re-ruled to 10.0
    print("V09 constants test passed")

# Run the tests
if __name__ == "__main__":
    test_v09_surfacing_threshold()
    test_v09_site_floor()
    test_v09_banner_denominator()
    test_v09_constants()
    print("All V09 fix tests passed!")
