"""Numerical invariants and actual rendering for the bounded advanced-math templates."""
import copy
import json
import os

import numpy as np
import pytest
from pydantic import ValidationError

from animation_agent.visuals.math_support import (
    formula_xy, slope_samples, solution_curve, line_intersections, plane_polygon, project_3d, surface_mesh,
)
from animation_agent.visuals.specs import (
    REGISTRY, GeometryParams, SlopeFieldParams, Scene3DParams, geometry_op, scene3d_op,
    GeoLineArgs, GeoCircleArgs, GeoIntersectionArgs, GeoPerpendicularArgs, GeoAngleArgs, GeoTriangleArgs,
    Vector3DArgs, Cross3DArgs, Plane3DArgs, Surface3DArgs,
)
from animation_agent.visuals.calls import check_segment, describe_segment
from script_generation_agent.picture_plan import PicturePlan, SYSTEM


def test_xy_formula_computes_broadcast_arrays_and_domain_gaps():
    x = np.array([1.,2.,3.])
    np.testing.assert_allclose(formula_xy("x^2 + sin(y) - pi")(x, np.pi/2), x*x+1-np.pi)
    assert not formula_xy("1/(x-0.13)").continuous_between([0,0], [1,0])
    assert not formula_xy("1/(x-0.13)**2").continuous_between([0,0], [1,0])
    assert not formula_xy("(x-0.13)**(-2)").continuous_between([0,0], [1,0])
    assert not formula_xy("tan(x)").continuous_between([1,0], [2,0])
    assert not formula_xy("sqrt(x)").continuous_between([-1,0], [1,0])
    assert formula_xy("x+y").continuous_between([-1,0], [1,0])


@pytest.mark.parametrize("source", ["__import__('os')", "x.real", "x[0]", "[x for x in y]", "sin", "sin(x,y)", "foo(x)", "True", "1e309", "x"*97, "(x+"*35 + "y" + ")"*35])
def test_formula_language_rejects_code_and_unbounded_inputs(source):
    with pytest.raises(ValueError):
        formula_xy(source)


def test_field_omits_undefined_slopes_and_keeps_steep_ones():
    samples = slope_samples("1/y", [-1,1], [-1,1], 5)
    assert len(samples) == 20 and all(y != 0 for x,y,m in samples)
    assert all(np.isfinite(m) for x,y,m in samples)
    assert slope_samples("1000000", [-1,1], [-1,1], 5)[0][2] == 1e6


@pytest.mark.parametrize("fn,initial,exact", [
    ("y", [0,1], lambda x: np.exp(x)),
    ("x-y", [0,1], lambda x: x-1+2*np.exp(-x)),
    ("0", [0,1], lambda x: np.ones_like(x)),
])
def test_adaptive_solutions_agree_with_known_solutions(fn, initial, exact):
    pts = np.array(solution_curve(fn, initial, [-1,1], [-10,10]))
    assert pts[0,0] == pytest.approx(-1) and pts[-1,0] == pytest.approx(1)
    assert np.all(np.diff(pts[:,0]) > 0)
    np.testing.assert_allclose(pts[:,1],exact(pts[:,0]),rtol=1e-5,atol=1e-6)
    assert any(np.allclose(p,initial) for p in pts)


def test_solution_stops_at_pole_and_frame_and_rejects_undefined_initial():
    pts = np.array(solution_curve("1/(x-0.13)", [0,0], [-1,1], [-2,2]))
    assert np.max(pts[:,0]) < 0.13
    assert np.max(np.abs(pts[:,1])) <= 2
    with pytest.raises(ValueError, match="defined"):
        solution_curve("1/y",[0,0],[-1,1],[-1,1])
    with pytest.raises(ValidationError):
        SlopeFieldParams(fn="x", x_range=[1,1])
    with pytest.raises(ValidationError):
        SlopeFieldParams(fn="sqrt(-1)")


def line(p,q,kind="line"):
    return {"kind":kind,"p":p,"q":q}


def circle(center,radius):
    return {"kind":"circle","center":center,"radius":radius}


def test_intersections_parallel_coincident_tangent_two_and_segment_bounds():
    assert line_intersections(line([0,0],[1,0]),line([0,1],[1,1])) == []
    with pytest.raises(ValueError,match="coincident"):
        line_intersections(line([0,0],[1,0]),line([2,0],[3,0]))
    assert line_intersections(line([-2,1],[2,1]),circle([0,0],1)) == [[0,1]]
    assert line_intersections(line([-2,0],[2,0]),circle([0,0],1)) == [[-1,0],[1,0]]
    assert line_intersections(line([0,0],[0.5,0],"segment"),circle([0,0],1)) == []
    assert line_intersections(line([0,0],[1,0],"segment"),line([2,0],[3,0],"segment")) == []
    assert line_intersections(line([0,0],[1,0],"segment"),line([1,0],[3,0],"segment")) == [[1,0]]
    assert line_intersections(circle([0,0],1),circle([2,0],1)) == [[1,0]]
    assert line_intersections(circle([0,0],1),circle([3,0],1)) == []
    assert line_intersections(circle([0,0],1),circle([0,0],2)) == []
    with pytest.raises(ValueError,match="coincident"):
        line_intersections(circle([0,0],1),circle([0,0],1))
    pts = np.array(line_intersections(circle([-1,0],2),circle([1,0],2)))
    np.testing.assert_allclose(pts,[[0,-np.sqrt(3)],[0,np.sqrt(3)]])


def geo_state():
    return REGISTRY["GeometryConstruction"].init_state(GeometryParams(points={"A":[-2,0],"B":[2,0],"C":[0,2]},extent=4))


def test_computed_midpoints_perpendiculars_and_bisectors():
    s=geo_state()
    assert geometry_op("midpoint",s,GeoLineArgs(name="M",a="A",b="B")) is None
    assert s["points"]["M"] == [0,0]
    geometry_op("line",s,GeoLineArgs(name="l",a="A",b="B"))
    geometry_op("bisector",s,GeoLineArgs(name="b",a="A",b="B"))
    assert s["shapes"]["b"]["p"] == [0,0]
    geometry_op("perpendicular",s,GeoPerpendicularArgs(name="p",line="l",through="C"))
    assert s["shapes"]["p"]["p"] == [0,2] and s["shapes"]["p"]["q"][0] == 0
    geometry_op("angle_bisector",s,GeoAngleArgs(name="a",a="A",vertex="C",b="B"))
    q = s["shapes"]["a"]["q"]
    assert q[0] == pytest.approx(0) and q[1] < 2


def test_construction_validation_is_transactional_and_all_intersections_are_named():
    s=geo_state()
    geometry_op("circle",s,GeoCircleArgs(name="c",center="A",radius=2))
    geometry_op("circle",s,GeoCircleArgs(name="d",center="B",radius=2))
    before=copy.deepcopy(s)
    assert "exactly" in geometry_op("intersect",s,GeoIntersectionArgs(first="c",second="d",names=["P","Q"]))
    assert s == before
    assert geometry_op("intersect",s,GeoIntersectionArgs(first="c",second="d",names=["P"])) is None
    assert s["points"]["P"] == [0,0]
    assert "new" in geometry_op("line",s,GeoLineArgs(name="A",a="A",b="B"))
    with pytest.raises(ValidationError):
        GeometryParams(points={"A":[float("nan"),0]})
    assert geometry_op("triangle",geo_state(),GeoTriangleArgs(a="A",b="B",c="C")) is None
    collinear = geo_state()
    collinear["points"]["C"] = [0,0]
    assert "collinear" in geometry_op("triangle",collinear,GeoTriangleArgs(a="A",b="B",c="C"))


@pytest.mark.parametrize("normal,offset", [([0,0,1],1),([1,0,0],0),([1,1,1],1),([0,2,0],6)])
def test_plane_clipping_keeps_vertices_on_plane_and_inside_cube(normal,offset):
    pts=np.array(plane_polygon(normal,offset,3))
    assert len(pts)>=3 and np.all(np.abs(pts)<=3+1e-9)
    np.testing.assert_allclose(pts @ normal,offset,atol=1e-9)


def test_plane_rejects_zero_normal_and_invisible_patch():
    for normal,offset in [([0,0,0],0),([0,0,1],4),([1,1,1],9)]:
        with pytest.raises(ValueError):
            plane_polygon(normal,offset,3)


def test_projection_is_linear_equal_unit_and_rotates():
    points=np.eye(3)
    projected=project_3d(points,35,25)
    # Orthonormal camera rows preserve length in the view plane.
    np.testing.assert_allclose(projected.T @ projected,np.eye(2),atol=1e-12)
    np.testing.assert_allclose(project_3d([1,2,3],35,25),np.array([1,2,3]) @ projected)
    assert not np.allclose(projected,project_3d(points,110,35))


def test_cross_product_and_bounds_are_computed_without_mutating_on_failure():
    s=REGISTRY["Scene3D"].init_state(Scene3DParams())
    scene3d_op("vector",s,Vector3DArgs(name="u",value=[2,0,0]))
    scene3d_op("vector",s,Vector3DArgs(name="v",value=[0,1,0]))
    assert scene3d_op("cross",s,Cross3DArgs(name="w",first="u",second="v")) is None
    assert s["vectors"]["w"]["value"] == [0,0,2]
    before=copy.deepcopy(s)
    assert scene3d_op("plane",s,Plane3DArgs(normal=[0,0,0]))
    assert s == before
    with pytest.raises(ValidationError):
        Vector3DArgs(name="a",value=[1,2])


def test_surface_mesh_does_not_bridge_poles_and_rejects_empty_surface():
    edges=surface_mesh("1/(x-0.13)",3,density=5)
    assert edges
    for a,b in edges:
        assert np.all(np.isfinite([a,b])) and np.max(np.abs([a,b])) <= 3
        assert (a[0]-0.13)*(b[0]-0.13)>0
    s=REGISTRY["Scene3D"].init_state(Scene3DParams())
    assert "no visible" in scene3d_op("surface",s,Surface3DArgs(fn="sqrt(-1)"))
    assert s["sheet"] is None


def test_new_families_are_selected_and_their_limits_are_in_the_classifier():
    for family,template in [("slope_field","SlopeField"),("geometry","GeometryConstruction"),("vectors_3d","Scene3D")]:
        p=PicturePlan(family=family,reason="test")
        assert not p.gap and p.main == template and template in p.templates
    assert "implicit/parametric surfaces" in SYSTEM and "not systems or implicit ODEs" in SYSTEM


RENDER_CASES = {
    "circles": [['g = GeometryConstruction(points={"A":[-1,0],"B":[1,0]}, extent=4)'],
                ['g.circle(name="c", center="A", radius=2)', 'g.circle(name="d", center="B", radius=2)'],
                ['g.intersect(first="c", second="d", names=["P","Q"])']],
    "tangent": [['g = GeometryConstruction(points={"A":[-1,0],"B":[1,0]}, extent=4)'],
                ['g.circle(name="c", center="A", radius=1)', 'g.circle(name="d", center="B", radius=1)'],
                ['g.intersect(first="c", second="d", names=["P"])']],
    "parallel": [['g = GeometryConstruction(points={"A":[-2,-1],"B":[2,-1],"C":[-2,1],"D":[2,1]}, extent=4)'],
                 ['g.line(name="l", a="A", b="B")','g.line(name="m", a="C", b="D")'],
                 ['g.intersect(first="l", second="m", names=[])']],
    "wide_axis_labels": [['f = SlopeField(fn="x-y", x_range=[-100,-90], y_range=[-99.5,-90.5], density=13)']],
    "singular_field": [['f = SlopeField(fn="1/y", x_range=[-2,2], y_range=[-2,2])'], ['f.solution(initial=[0,1])']],
    "triangle_bisector": [['g = GeometryConstruction(points={"A":[-2,0],"B":[2,0],"C":[0,2]}, extent=4)'],
                          ['g.triangle(a="A", b="B", c="C")'],
                          ['g.angle_bisector(name="b", a="A", vertex="C", b="B")']],
    "parallel_cross": [['s = Scene3D()'], ['s.vector(name="u", value=[1,0,0])', 's.vector(name="v", value=[2,0,0], colour="PINK")'],
                       ['s.cross(name="w", first="u", second="v")']],
    "axis_alignment": [['s = Scene3D()'], ['s.vector(name="u", value=[1.234,0,0])'], ['s.view(azimuth=180,elevation=45)']],
    "vertical_plane": [['s = Scene3D()'], ['s.plane(normal=[1,0,0])'], ['s.view(azimuth=-40,elevation=45)']],
    "singular_surface": [['s = Scene3D()'], ['s.surface(fn="1/(x-0.13)")'], ['s.view(azimuth=-40,elevation=35)']],
}


@pytest.mark.parametrize("name",RENDER_CASES)
def test_edge_case_calls_pass_and_descriptions_match(name):
    assert check_segment(RENDER_CASES[name]) == []
    said=describe_segment(RENDER_CASES[name])
    if name == "parallel":
        assert "No intersection" in said[-1]
    elif name == "singular_field":
        assert "approximate" in said[-1]


@pytest.mark.skipif(not os.environ.get("SYLLABYTE_RENDER_TESTS"),reason="set SYLLABYTE_RENDER_TESTS=1 to render")
@pytest.mark.parametrize("name",RENDER_CASES)
def test_edge_cases_render_without_layout_findings(name,tmp_path):
    from animation_agent.layout import BEATS_FILE
    from animation_agent.renderer import _try_render
    from animation_agent.visuals.scene_code import build_spec_scene
    from test_visual_templates import segment
    beats=RENDER_CASES[name]
    code=build_spec_scene(segment(*beats),"Seg0")
    durations=[2.5]*len(beats)
    (tmp_path/BEATS_FILE).write_text(json.dumps(durations))
    ok,error,_,layout=_try_render(tmp_path,code,"Seg0","low",len(durations),sum(durations),check_formulas=False,frame="dialogue")
    assert ok,error
    assert layout.findings == [],layout.findings


def test_full_frame_prompt_normalization_and_carried_state():
    from animation_agent.visuals.normalize import lay_out
    from animation_agent.visuals.calls import check_script, describe_script
    from script_generation_agent.prompts import picture_brief
    for family, template in [("geometry", "GeometryConstruction"), ("slope_field", "SlopeField"), ("vectors_3d", "Scene3D")]:
        assert "Never put another template beside" in picture_brief(family, [template])
    # Tuple coordinates may be copied from the template's defaults; normalization keeps them usable.
    segments = [[['f = SlopeField(fn="y", x_range=(-1,1), y_range=(-3,3))']],
                [['f.solution(initial=(0,1))'], ['f.clear()']]]
    normalized = lay_out(segments)
    assert check_script(normalized) == []
    assert "approximate" in describe_script(normalized)[1][0]
    carried = [['s = Scene3D()'], ['s.vector(name="u", value=[1,0,0])']], [['s.vector(name="v", value=[0,1,0])'], ['s.cross(name="w", first="u", second="v")']]
    assert check_script(list(carried)) == []
    assert "[0.0, 0.0, 1.0]" in describe_script(list(carried))[1][-1]


def test_rounded_vector_labels_are_marked_approximate():
    from animation_agent.visuals.math_support import vector_label
    assert vector_label("u", [1.234,0,0]) == "u≈(1.23,0,0)"
    assert vector_label("v", [2,0,1]) == "v=(2,0,1)"


def test_unreadable_coordinate_ranges_and_tiny_circles_are_rejected():
    with pytest.raises(ValidationError, match="labels are too long"):
        SlopeFieldParams(fn="y", x_range=[-0.123456789, 0.123456789])
    assert "too small" in geometry_op("circle", geo_state(), GeoCircleArgs(name="c", center="A", radius=1e-10))


def test_parallel_cross_product_is_a_visible_zero_and_is_not_dropped_by_normalization():
    from animation_agent.visuals.normalize import normalize_script
    from animation_agent.visuals.calls import describe_script
    fixed = normalize_script([RENDER_CASES["parallel_cross"]])
    assert fixed.left == [] and fixed.log == []
    assert "Vector w = [0.0, 0.0, 0.0]" in describe_script(fixed.segments)[0][-1]


def test_intersection_can_reuse_a_known_endpoint_without_moving_it():
    s=REGISTRY["GeometryConstruction"].init_state(GeometryParams(points={"A":[0,0],"B":[1,0]},extent=4))
    geometry_op("line",s,GeoLineArgs(name="l",a="A",b="B"))
    geometry_op("circle",s,GeoCircleArgs(name="c",center="A",radius=1))
    before=copy.deepcopy(s)
    assert "original position" in geometry_op("intersect",s,GeoIntersectionArgs(first="l",second="c",names=["B","P"]))
    assert s == before
    assert geometry_op("intersect",s,GeoIntersectionArgs(first="l",second="c",names=["P","B"])) is None
    assert s["points"]["P"] == [-1,0] and s["points"]["B"] == [1,0]
