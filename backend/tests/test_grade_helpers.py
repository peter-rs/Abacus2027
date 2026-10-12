import grade


def test_normalize_newlines():
    assert grade.normalize_newlines("a\r\nb\rc\n") == "a\nb\nc\n"
    assert grade.normalize_newlines(None) == ""


def test_normalize_for_compare_ignores_whitespace_case_and_blank_lines():
    assert grade.normalize_for_compare("Hello World\n\n  foo bar \r\n") == ["helloworld", "foobar"]


def test_check_passed():
    assert grade.check_passed("Hello World\n", "hello   world") is True
    assert grade.check_passed("1 2 3", "1 2 4") is False


def test_build_short_diff_only_changed_lines():
    out = grade.build_short_diff("a\nb\nc\n", "a\nX\nc\n")
    assert out.splitlines() == ["--- actual", "+++ expected", "@@ -1,3 +1,3 @@", "-b", "+X"]
    assert grade.build_short_diff("same\n", "same\n") == ""


def test_build_long_diff_includes_every_line():
    out = grade.build_long_diff("a\nb\n", "a\n")
    assert out.splitlines() == ["--- actual", "+++ expected", "@@ -1,2 +1,1 @@", "-a", "+a", "-b"]


def test_normalize_testcase_items():
    items = grade.normalize_testcase_items({"10": "j", "2": "b", "x": "z"})
    assert [key for key, _ in items] == ["2", "10", "x"]
    assert grade.normalize_testcase_items(["p", "q"]) == [("0", "p"), ("1", "q")]
    assert grade.normalize_testcase_items("junk") == []


def test_parse_entry_class_and_additional_files():
    assert grade.parse_entry_class_and_additional_files(["n", "d", "in", "out", ["f.txt"]]) == ("", ["f.txt"])
    assert grade.parse_entry_class_and_additional_files(
        ["n", "d", "in", "out", False, {"entry_class": " Main ", "files": ["a.java"]}]
    ) == ("Main", ["a.java"])
    assert grade.parse_entry_class_and_additional_files(
        ["n", "d", "in", "out", False, ["a.java"], "Main"]
    ) == ("Main", ["a.java"])
    assert grade.parse_entry_class_and_additional_files("not a list") == ("", [])


def test_parse_project_additional_payload():
    assert grade.parse_project_additional_payload("") == ("", [])
    assert grade.parse_project_additional_payload("/abs/one.txt") == ("", ["/abs/one.txt"])
    assert grade.parse_project_additional_payload('["/a.txt", "", "/b.txt"]') == ("", ["/a.txt", "/b.txt"])
    assert grade.parse_project_additional_payload('{"base_dir": "/base", "files": "/c.txt"}') == (
        "/base",
        ["/c.txt"],
    )
    assert grade.parse_project_additional_payload("{not json") == ("", [])
