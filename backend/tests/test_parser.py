from app.services.md_parser import parse_markdown, split_example


def test_parses_standard_table_with_title():
    md = """# 测试词书

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| abandon | /əˈbændən/ | v. 放弃 | He abandoned it. 他放弃了。 |
| benefit | /ˈbenɪfɪt/ | n. 好处 | |
"""
    name, words, skipped = parse_markdown(md)
    assert name == "测试词书"
    assert skipped == 0
    assert [w["spelling"] for w in words] == ["abandon", "benefit"]
    assert words[0]["example_en"] == "He abandoned it."
    assert words[0]["example_cn"] == "他放弃了。"
    assert words[1]["example_en"] is None
    assert [w["seq"] for w in words] == [0, 1]


def test_rows_containing_header_words_are_not_dropped():
    """回归：例句/释义里出现 word、meaning 等词时不能整行被当表头丢掉。"""
    md = """# Test

| 单词 | 音标 | 释义 | 例句 |
|---|---|---|---|
| vocabulary | /v/ | n. 词汇 | What does this word mean? 这个词是什么意思？ |
| term | /t/ | n. 术语；word 的另一种说法 | |
| phonetics | /f/ | n. meaning of speech sounds | |
"""
    _, words, _ = parse_markdown(md)
    assert [w["spelling"] for w in words] == ["vocabulary", "term", "phonetics"]
    assert words[0]["example_en"] == "What does this word mean?"
    assert words[0]["example_cn"] == "这个词是什么意思？"


def test_table_without_separator_drops_only_obvious_header():
    md = """| 单词 | 音标 | 释义 | 例句 |
| apple | /a/ | n. 苹果 | |
"""
    _, words, _ = parse_markdown(md)
    assert [w["spelling"] for w in words] == ["apple"]


def test_multiple_tables_are_merged():
    md = """# Book

| 单词 | 音标 | 释义 |
|---|---|---|
| one | /1/ | num. 一 |

some prose

| 单词 | 音标 | 释义 |
|---|---|---|
| two | /2/ | num. 二 |
"""
    _, words, _ = parse_markdown(md)
    assert [w["spelling"] for w in words] == ["one", "two"]


def test_duplicate_and_invalid_rows_are_counted():
    md = """# Book

| 单词 | 音标 | 释义 |
|---|---|---|
| apple | /a/ | n. 苹果 |
| Apple | /a/ | n. 苹果 |
|  | /x/ | 缺单词 |
| broken | /b/ |
"""
    _, words, skipped = parse_markdown(md)
    assert [w["spelling"] for w in words] == ["apple"]
    assert skipped == 3


def test_split_example():
    assert split_example("He left. 他离开了。") == ("He left.", "他离开了。")
    assert split_example("只有中文") == ("", "只有中文")
    assert split_example("English only") == ("English only", "")
    assert split_example("") == ("", "")
