"""reflex_class: path-only classification of test files (deterministic)."""

import pytest


@pytest.mark.parametrize("path,expected", [
    # the five field firings (issue #26)
    ("integrations/deepseek/src/index.ts", "code"),
    ("__tests__/drawerTermsGate.test.tsx", "test"),
    ("__tests__/acceptTermsScreen.test.tsx", "test"),
    ("tests/unit/memory-transfer.test.ts", "test"),
    ("packages/ct-wisdom-core/src/spawn.ts", "code"),
    # directory segments
    ("src/tests/helpers.ts", "test"),
    ("src/test/Foo.java", "test"),
    ("pkg/__mocks__/fs.js", "test"),
    ("spec/models/user_spec.rb", "test"),
    ("web/e2e/login.ts", "test"),
    # filename patterns
    ("src/foo.test.ts", "test"),
    ("src/foo.spec.js", "test"),
    ("pkg/test_utils.py", "test"),
    ("pkg/foo_test.go", "test"),
    ("src/foo_test.ts", "test"),
    ("conftest.py", "test"),
    ("pkg/conftest.py", "test"),
    # deliberately NOT test: product or infrastructure code
    ("src/testing/clock.ts", "code"),
    ("packages/test-utils/src/index.ts", "code"),
    ("packages/testutils/index.ts", "code"),
    ("src/fixtures/seed.ts", "code"),
    ("src/contest.py", "code"),
    ("src/latest.ts", "code"),
    # normalisation
    ("SRC\\Tests\\Foo.TS", "test"),
    ("Src/TESTS/foo.ts", "test"),
    # a FILE named like a directory is not a test directory
    ("src/test", "code"),
    ("", "code"),
    (None, "code"),
])
def test_reflex_class(jr, path, expected):
    assert jr.reflex_class(path) == expected
