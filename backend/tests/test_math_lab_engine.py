from physis.math_lab_engine import calculate_lab


def run(mode, expression, **kwargs):
    return calculate_lab({"mode": mode, "expression": expression, **kwargs})


def row(result, label):
    return next(item for item in result["rows"] if item["label"] == label)


def test_function_reports_exact_roots_y_intercept_extrema_and_curve():
    result = run("function", "x^2-1", lo=-2, hi=2)

    assert result["status"] == "ok"
    assert row(result, "x절편")["value"] == "-1, 1"
    assert row(result, "y절편")["value"] == "-1"
    assert row(result, "극솟값")["value"] == "(0, -1)"
    assert result["curves"][0]["label"] == "f(x)"
    assert result["curves"][0]["segments"]


def test_function_substitutes_bounded_coefficients_before_sampling():
    result = run("function", "a*x^2+b*x+c", params={"a": 2, "b": -3, "c": 1})

    assert result["status"] == "ok"
    assert row(result, "수식")["value"] == "2*x**2 - 3*x + 1"
    assert row(result, "x절편")["value"] == "1/2, 1"


def test_function_reports_optional_curve_intersections():
    result = run("function", "x^2", other="x", lo=-2, hi=2)

    assert result["status"] == "ok"
    assert {curve["label"] for curve in result["curves"]} >= {"f(x)", "g(x)"}
    assert row(result, "교점")["value"] == "(0, 0), (1, 1)"


def test_function_splits_curve_at_a_pole_without_connecting_the_gap():
    result = run("function", "1/(x-0.25)", lo=-1, hi=1)

    assert result["status"] == "ok"
    assert len(result["curves"][0]["segments"]) == 2
    left, right = result["curves"][0]["segments"]
    assert left[-1][0] < 0.25 < right[0][0]
    assert row(result, "수직점근선")["value"] == "x = 1/4"


def test_piecewise_grammar_keeps_branches_as_separate_segments():
    result = run("function", "piecewise((x, x < 0), (-x, True))", lo=-2, hi=2)

    assert result["status"] == "ok"
    assert len(result["curves"][0]["segments"]) == 2
    assert "piecewise" in row(result, "수식")["value"].lower()


def test_piecewise_rejects_arbitrary_python_or_non_boolean_conditions():
    assert run("function", "piecewise((x, __import__('os')), (0, True))")["status"] == "invalid"
    assert run("function", "piecewise((x, x), (0, True))")["status"] == "invalid"
    assert run("function", "piecewise((0, 1/x < 0), (1, True))")["status"] == "invalid"


def test_tangent_is_opt_in_and_its_curve_uses_the_same_expression():
    result = run("derivative", "a*x^2", params={"a": 3}, point=2, lo=0, hi=4)

    assert result["status"] == "ok"
    assert row(result, "도함수")["value"] == "6*x"
    assert row(result, "접선")["value"] == "y = 12*x - 12"
    assert {curve["label"] for curve in result["curves"]} >= {"f(x)", "f′(x)", "접선", "할선"}


def test_derivative_returns_second_derivative_and_stationary_classification():
    result = run("derivative", "x^3-3*x", lo=-3, hi=3)

    assert result["status"] == "ok"
    assert row(result, "이계도함수")["value"] == "6*x"
    assert row(result, "극대")["value"] == "(-1, 2)"
    assert row(result, "극소")["value"] == "(1, -2)"
    assert row(result, "변곡점")["value"] == "(0, 0)"


def test_limit_distinguishes_sides_and_function_value_at_a_hole():
    result = run("limit", "(x^2-1)/(x-1)", point=1, lo=0, hi=2)

    assert result["status"] == "ok"
    assert row(result, "좌극한")["value"] == "2"
    assert row(result, "우극한")["value"] == "2"
    assert row(result, "함수값")["value"] == "정의되지 않음"
    assert result["guides"]["vertical"] == [1.0]
    samples = next(curve for curve in result["curves"] if curve["label"] == "좌극한 표본")
    assert all(len(segment) == 1 for segment in samples["segments"])


def test_limit_shows_opposite_infinite_one_sided_limits():
    result = run("limit", "1/x", point=0, lo=-1, hi=1)

    assert result["status"] == "ok"
    assert row(result, "좌극한")["value"] == "-oo"
    assert row(result, "우극한")["value"] == "oo"
    assert row(result, "양측 극한")["value"] == "존재하지 않음"


def test_derivative_rejects_tangent_at_a_point_outside_the_real_domain():
    result = run("derivative", "sqrt(x)", point=-1)

    assert result["status"] == "unverifiable"
    assert result["curves"] == []


def test_definite_integral_separates_exact_value_and_numerical_estimates():
    result = run("integral", "x^2", lower=0, upper=1, divisions=20)

    assert result["status"] == "ok"
    assert row(result, "정적분")["value"] == "1/3"
    assert row(result, "사다리꼴 근사")["kind"] == "numeric"
    assert row(result, "Simpson 근사")["kind"] == "numeric"
    assert abs(float(row(result, "Simpson 근사")["value"]) - 1 / 3) < 1e-10
    assert float(row(result, "Simpson 오차")["value"]) < 1e-10
    assert {curve["label"] for curve in result["curves"]} >= {"f(x)", "리만 합", "누적 적분"}


def test_integral_refuses_an_interval_crossing_a_real_domain_hole():
    result = run("integral", "1/x", lower=-1, upper=1)

    assert result["status"] == "unverifiable"
    assert "정의" in result["detail"] or "구간" in result["detail"]


def test_indefinite_integral_verifies_antiderivative_and_keeps_overlay():
    result = run("integral", "2*x")

    assert result["status"] == "ok"
    assert row(result, "부정적분")["value"] == "x**2"
    assert result["curves"]


def test_indefinite_log_primitive_is_real_and_keeps_original_holes():
    result = run("integral", "1/x", lo=-2, hi=2)

    assert result["status"] == "ok"
    assert row(result, "부정적분")["value"] == "log(Abs(x))"
    primitive = next(curve for curve in result["curves"] if curve["label"] == "F(x)")
    assert len(primitive["segments"]) == 2


def test_tan_domain_and_sampling_do_not_cross_its_pole():
    result = run("function", "tan(x)", lo=1, hi=2)

    assert result["status"] == "ok"
    assert len(result["curves"][0]["segments"]) == 2
    assert row(result, "수직점근선")["value"] == "x = pi/2"


def test_piecewise_cusp_is_not_reported_as_differentiable_at_its_boundary():
    result = run("derivative", "piecewise((x^2, x < 0), (x^2, True))", point=0)

    assert result["status"] == "ok"
    assert row(result, "접점의 도함수")["value"] == "0"
    cusp = run("derivative", "piecewise((x, x < 0), (-x, True))", point=0)
    assert cusp["status"] == "unverifiable"
    jump = run("derivative", "piecewise((0, x < 0), (1, True))", point=0)
    assert jump["status"] == "unverifiable"


def test_derivative_curve_splits_at_the_nondifferentiable_abs_root():
    result = run("derivative", "abs(x)", lo=-2, hi=2)

    assert result["status"] == "ok"
    derivative = next(curve for curve in result["curves"] if curve["label"] == "f′(x)")
    assert len(derivative["segments"]) == 2
    assert all(point[0] != 0 for segment in derivative["segments"] for point in segment)


def test_real_domain_controls_one_sided_sqrt_and_log_limits():
    root = run("limit", "sqrt(x)", point=0)
    assert root["status"] == "ok"
    assert row(root, "좌극한")["value"] == "실수 정의역에서 접근 불가"
    assert row(root, "우극한")["value"] == "0"
    assert row(root, "연속성")["value"] == "정의역 끝점에서 상대 연속"

    logarithm = run("limit", "log(x)", point=0)
    assert logarithm["status"] == "ok"
    assert row(logarithm, "좌극한")["value"] == "실수 정의역에서 접근 불가"
    assert row(logarithm, "우극한")["value"] == "-oo"


def test_function_evaluates_requested_point_and_emptyset_means_no_roots():
    result = run("function", "x^2+1", point=2)

    assert result["status"] == "ok"
    assert row(result, "f(2)")["value"] == "5"
    assert row(result, "x절편")["value"] == "없음"


def test_symmetry_respects_the_original_domain_not_only_simplified_values():
    result = run("function", "(x-1)/(x-1)")

    assert result["status"] == "ok"
    assert row(result, "수식")["value"] == "1"
    assert row(result, "대칭성")["value"] == "해당 없음"


def test_tan_with_multiple_poles_splits_at_every_finite_viewport_pole():
    result = run("function", "tan(2*x)", lo=0, hi=3)

    assert result["status"] == "ok"
    assert len(result["curves"][0]["segments"]) == 3
    assert row(result, "수직점근선")["value"] == "x = pi/4, x = 3*pi/4"


def test_bad_modes_unknown_symbols_and_invalid_bounds_are_rejected():
    assert calculate_lab({"mode": "vector", "expression": "x"})["status"] == "invalid"
    assert run("function", "q*x") ["status"] == "invalid"
    assert run("function", "x", lo=2, hi=-2)["status"] == "invalid"
    assert run("function", "x", params={"z": 2})["status"] == "invalid"
