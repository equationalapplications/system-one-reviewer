"""Python ast_context line numbering.

ast line numbers count "\\n" only, but str.splitlines() also splits on form
feed, U+2028 and friends, so every symbol after one of those read the wrong
source line (same class as the TS fix in test_ts_enrichment.py).
"""


def test_form_feed_does_not_shift_signature_or_window(jr):
    src = "import os\n\x0c\nclass A:\n    def m(self):\n        return 1\n"
    table = jr._file_symbol_table(src)
    assert table == {"A": "class A:"}
    assert jr._symbol_context_window(src, 5) == [
        "    def m(self):", "        return 1"]


def test_u2028_in_string_does_not_shift_signature_or_window(jr):
    src = 's = "a\u2028b"\n\ndef f():\n    return 1\n\ndef g():\n    return 2\n'
    table = jr._file_symbol_table(src)
    assert table == {"f": "def f():", "g": "def g():"}
    assert jr._symbol_context_window(src, 7) == ["def g():", "    return 2"]


def test_crlf_lines_are_stripped(jr):
    src = "def f():\r\n    return 1\r\n"
    assert jr._file_symbol_table(src) == {"f": "def f():"}
    assert jr._symbol_context_window(src, 2) == ["def f():", "    return 1"]
