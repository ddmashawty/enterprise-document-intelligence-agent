from doc_agent.kaoyan.normalize import (
    CollegeName,
    CountValue,
    Subject,
    build_school_aliases,
    fill_same_as_above,
    find_schools,
    is_408,
    normalize_program_code,
    parse_college,
    parse_count,
    parse_subject,
    parse_subject_lines,
    parse_total_tm,
    parse_year,
    resolve_same,
    resolve_school,
    split_source_urls,
    split_subjects,
)


def test_parse_total_tm_scnu_catalog_cell() -> None:
    assert parse_total_tm("48(17)") == (48, 17)
    assert parse_total_tm("50（4）") == (50, 4)
    assert parse_total_tm(" 20 ") == (20, None)
    assert parse_total_tm("") == (None, None)
    assert parse_total_tm("若干") == (None, None)


def test_parse_count_exact_upper_bound_and_pool() -> None:
    assert parse_count("55") == CountValue(55, False, None, "55")
    ub = parse_count("≤41")
    assert (ub.value, ub.is_upper_bound, ub.pool_scope) == (41, True, None)
    pool = parse_count("（0812合计≤19）")
    assert (pool.value, pool.is_upper_bound, pool.pool_scope) == (19, True, "0812")
    assert parse_count("(0812合计<=19)").pool_scope == "0812"
    assert parse_count("").is_empty
    assert parse_count("未知").is_empty


def test_same_as_above() -> None:
    assert resolve_same("同上", "101思想政治理论") == "101思想政治理论"
    assert resolve_same("204英语（二）", "201英语（一）") == "204英语（二）"
    rows = [["085404", "101思想政治理论", "408"], ["085405", "同上", "同上"], ["085410", "同上", "302"]]
    filled = fill_same_as_above(rows, columns=[1, 2])
    assert filled[1] == ["085405", "101思想政治理论", "408"]
    assert filled[2] == ["085410", "101思想政治理论", "302"]
    assert fill_same_as_above([["a"], ["同上"]], columns=[5])[1] == ["同上"]


def test_split_subjects_circled_and_spaced() -> None:
    circled = split_subjects("①101思想政治理论②204英语（二）③302数学（二）④408计算机学科专业基础")
    assert [s.code for s in circled] == ["101", "204", "302", "408"]
    assert circled[1] == Subject("204", "英语（二）")
    spaced = split_subjects("101思想政治理论 201英语（一） 301数学（一） 408计算机学科专业基础")
    assert [s.code for s in spaced] == ["101", "201", "301", "408"]
    lines = split_subjects("101 思想政治理论\n204 英语（二）\n302 数学（二）\n884 信号与系统")
    assert [s.code for s in lines] == ["101", "204", "302", "884"]
    assert lines[3].name == "信号与系统"
    assert split_subjects("") == []


def test_parse_subject_and_408_variants() -> None:
    assert parse_subject("④408计算机学科专业基础") == Subject("408", "计算机学科专业基础")
    assert parse_subject("未知（目录不可达）") is None
    assert is_408(split_subjects("①101思想政治理论②201英语（一）③301数学（一）④408计算机学科专业基础"))
    assert not is_408(split_subjects("①101思想政治理论②204英语（二）③302数学（二）④884信号与系统"))


def test_normalize_program_code_merges_line_breaks() -> None:
    assert normalize_program_code("0854\n04") == "085404"
    assert normalize_program_code(" 0812z3 ") == "0812Z3"
    assert normalize_program_code("140500") == "140500"
    assert normalize_program_code("0812") is None
    assert normalize_program_code("") is None


def test_parse_subject_lines_variants() -> None:
    four = parse_subject_lines("政治50/外语50/业务课一60/业务课二60")
    assert (four.politics, four.foreign_lang, four.subject1, four.subject2) == (50, 50, 60, 60)
    bare = parse_subject_lines("30/30/48/48")
    assert (bare.politics, bare.subject2) == (30, 48)
    school = parse_subject_lines("政治50/外语50/业务课70（学校基本线）")
    assert (school.politics, school.foreign_lang, school.subject1, school.subject2) == (50, 50, 70, 70)
    assert school.note == "学校基本线"
    empty = parse_subject_lines("")
    assert empty.politics is None


def test_parse_college_and_year() -> None:
    assert parse_college("041人工智能学院（佛山南海）") == CollegeName("041", "人工智能学院", "佛山南海")
    assert parse_college("670计算机学院").code == "670"
    no_code = parse_college("计算机科学与工程学院")
    assert (no_code.code, no_code.name, no_code.campus) == (None, "计算机科学与工程学院", None)
    assert parse_year("2027（推免目录）/2026（复试）") == 2027
    assert parse_year("") is None


def test_split_source_urls_drops_bracket_notes() -> None:
    text = (
        "https://yz.scut.edu.cn/2025/1009/c30381a604485/page.htm（目录系统 https://yanzhao.scut.edu.cn/x 未取得）"
        " ; https://www2.scut.edu.cn/cs/2026/0325/c45223a621366/page.htm"
    )
    assert split_source_urls(text) == [
        "https://yz.scut.edu.cn/2025/1009/c30381a604485/page.htm",
        "https://www2.scut.edu.cn/cs/2026/0325/c45223a621366/page.htm",
    ]
    assert split_source_urls("") == []


def test_school_alias_resolution() -> None:
    aliases = build_school_aliases([{"id": "sysu", "name": "中山大学"}])
    assert resolve_school("中大", aliases) == "sysu"
    assert resolve_school("华南理工", aliases) == "scut"
    assert resolve_school("SCNU", aliases) == "scnu"
    assert resolve_school("北大", aliases) is None
    assert find_schools("对比中山大学、华工和暨大的085404") == ["sysu", "scut", "jnu"]
    assert find_schools("华南师范大学计算机学院") == ["scnu"]
    assert find_schools("jnu-010 与 SCUTS") == ["jnu"]
