"""Mathematical templates in the portrait frame; geometry is computed before it is drawn."""
from __future__ import annotations

import copy
import numpy as np
from manim import Arrow, Circle, Dot, VGroup, VMobject, UpdateFromAlphaFunc

from animation_agent.visuals.base import Template, Step, colour, mark_background, text
from animation_agent.visuals.math_support import slope_samples, clipped_line, plane_polygon, project_3d, surface_mesh, vector_label
from animation_agent.visuals.specs import (
    SLOPE_FIELD, GEOMETRY_CONSTRUCTION, SCENE_3D, est_width,
)


def wire(points, col="BLUE", width=2):
    return mark_background(VMobject(stroke_color=colour(col), stroke_width=width).set_points_as_corners(points))


class ComputedDiagram(Template):
    """Rebuild from validated mathematical state, also when replaying carried segments."""
    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self.st = self.spec.init_state(params)
        self.picture = None

    def _refresh(self):
        new = self._picture()
        if self.picture is None:
            self.picture = new
            return self.add(new)
        anims, self.picture = self.morph(self.picture, new)
        return anims

    def create(self):
        yield Step(self._refresh())

    def move(self, a):
        self.area = a.area
        yield Step(self._refresh())

    def _change(self, op, a):
        state = copy.deepcopy(self.st)
        problem = self.spec.actions[op].check(state, a)
        if problem:
            raise ValueError(problem)
        self.st = state
        yield Step(self._refresh())


class SlopeField(ComputedDiagram):
    spec = SLOPE_FIELD

    def _picture(self):
        box = self.bounds
        xr, yr = self.st["x_range"], self.st["y_range"]
        number = lambda v: str(float(v)).removesuffix(".0")
        y_labels = [text(number(v),30) for v in yr]
        x_labels = [text(number(v),30) for v in xr]
        left = box.left + max(max(t.width for t in y_labels)+0.12, x_labels[0].width/2+0.05)
        right = box.right - max(0.15, x_labels[1].width/2+0.05)
        bottom, top = box.bottom + 1.0, box.top - 0.65
        sx, sy = (right-left)/(xr[1]-xr[0]), (top-bottom)/(yr[1]-yr[0])
        def pos(x, y):
            return np.array([left+(x-xr[0])*sx, bottom+(y-yr[0])*sy, 0])
        heading = "dy/dx = " + self.st["fn"]
        if est_width(heading) > box.width - 0.15:
            heading = "Slope field"
        out = VGroup(text(heading, 30).move_to([box.center[0], box.top-0.2, 0]))
        out.add(wire([pos(xr[0],yr[1]), pos(xr[0],yr[0]), pos(xr[1],yr[0])], "GREY"))
        if xr[0] < 0 < xr[1]:
            out.add(wire([pos(0,yr[0]), pos(0,yr[1])], "GREY", 1))
        if yr[0] < 0 < yr[1]:
            out.add(wire([pos(xr[0],0), pos(xr[1],0)], "GREY", 1))
        for x,label in zip(xr,x_labels):
            out.add(label.move_to([pos(x,0)[0],bottom-0.23,0]))
        for y,label in zip(yr,y_labels):
            out.add(label.move_to([left-0.08-label.width/2,pos(0,y)[1],0]))
        out.add(text("x",30).move_to([(left+right)/2,bottom-0.23,0]),
                text("y",30).move_to([left-0.23,(top+bottom)/2,0]))
        half = 0.33 * min((right-left), (top-bottom)) / self.st["density"]
        for x,y,m in slope_samples(self.st["fn"], xr, yr, self.st["density"]):
            # Convert dy/dx into screen units before normalizing, even on unequal scales.
            angle = np.arctan2(m * sy, sx)
            d = half * np.array([np.cos(angle),np.sin(angle),0])
            out.add(wire([pos(x,y)-d, pos(x,y)+d], "BLUE", 2))
        for solution in self.st["solutions"]:
            out.add(wire([pos(x,y) for x,y in solution["points"]],solution["colour"],4))
            out.add(mark_background(Dot(pos(*solution["initial"]),radius=0.05,color=colour(solution["colour"]))))
        footer = "Solutions: approximate" if self.st["solutions"] else "Undefined slopes omitted"
        out.add(text(footer,30).move_to([box.center[0],box.bottom+0.2,0]))
        return out

    def solution(self, a):
        yield from self._change("solution", a)

    def clear(self, a):
        yield from self._change("clear", a)


class GeometryConstruction(ComputedDiagram):
    spec = GEOMETRY_CONSTRUCTION
    palette = ["BLUE", "GOLD", "TEAL", "PINK", "GREEN", "ORANGE", "PURPLE", "WHITE"]

    def _picture(self):
        box, extent = self.bounds, self.st["extent"]
        side = min(box.width-0.35, box.height-1.65)
        center = box.center + [0,0.1,0]
        scale = side/(2*extent)
        def pos(p):
            return center + [p[0]*scale,p[1]*scale,0]
        out = VGroup(text("Geometric construction",30).move_to([box.center[0],box.top-0.2,0]))
        for i,(name,shape) in enumerate(self.st["shapes"].items()):
            col = self.palette[i]
            if shape["kind"] == "circle":
                out.add(mark_background(Circle(radius=shape["radius"]*scale,color=colour(col),stroke_width=2).move_to(pos(shape["center"]))))
            else:
                ends = ((shape["p"],shape["q"]) if shape["kind"] == "segment" else clipped_line(shape["p"],shape["q"],extent))
                if ends is not None:
                    out.add(wire([pos(ends[0]),pos(ends[1])],col,2))
            # Short colored legend keeps construction names off crossings and point labels.
            label = name if not name.startswith("triangle") else "△"
            out.add(text(label,30,colour(col)).move_to([box.left+0.3+i*0.45,box.bottom+0.6,0]))
        for name,p in self.st["points"].items():
            out.add(mark_background(Dot(pos(p),radius=0.04,color=colour("WHITE"))),
                    text(name,30).move_to(pos(p)+[0,0.2,0]))
        out.add(text("No intersection" if self.st["result"] == "No intersection" else "Equal scale",30)
                .move_to([box.center[0],box.bottom+0.15,0]))
        return out

    def line(self, a):
        yield from self._change("line", a)

    def segment(self, a):
        yield from self._change("segment", a)

    def circle(self, a):
        yield from self._change("circle", a)

    def triangle(self, a):
        yield from self._change("triangle", a)

    def midpoint(self, a):
        yield from self._change("midpoint", a)

    def bisector(self, a):
        yield from self._change("bisector", a)

    def perpendicular(self, a):
        yield from self._change("perpendicular", a)

    def angle_bisector(self, a):
        yield from self._change("angle_bisector", a)

    def intersect(self, a):
        yield from self._change("intersect", a)


class Scene3D(ComputedDiagram):
    spec = SCENE_3D
    durations = {"view": 2.0}

    def __init__(self, scene, params, uses=None):
        super().__init__(scene, params, uses)
        self._mesh_key, self._mesh = None, []

    def _picture(self):
        box, extent = self.bounds, self.st["extent"]
        # Room below for one label per vector; no other text, so the picture gets the rest of the frame.
        below = 0.35*len(self.st["vectors"]) + 0.2 if self.st["vectors"] else 0.0
        # A sphere around everything drawn keeps every projection inside the same frame at every angle (0.9: axis
        # labels). Fitting it to what is drawn, not to the whole cube, makes the picture larger.
        radius = min(box.width-0.65, box.height-below-0.9)/2
        center = box.center + [0, below/2, 0]
        scale = radius/self._reach()
        def pos(points):
            xy = project_3d(points,self.st["azimuth"],self.st["elevation"])*scale
            return np.concatenate([xy,np.zeros((*xy.shape[:-1],1))],axis=-1)+center
        out = VGroup()
        label_positions = []
        for i, label in enumerate("xyz"):
            lo,hi = np.zeros(3),np.zeros(3)
            lo[i],hi[i] = -extent,extent
            out.add(wire([pos(lo),pos(hi)],"GREY",1.5))
            tip = pos(hi)
            delta = tip-center
            delta /= np.linalg.norm(delta)
            label_pos = tip + 0.2*delta
            while any(np.linalg.norm(label_pos - old) < 0.38 for old in label_positions):
                label_pos = label_pos + [0.38, 0, 0]
            label_positions.append(label_pos)
            out.add(text(label,30).move_to(label_pos))
        sheet = self.st["sheet"]
        if sheet:
            if sheet["kind"] == "plane":
                vertices = plane_polygon(sheet["normal"],sheet["offset"],extent)
                out.add(wire(pos([*vertices,vertices[0]]),sheet["colour"],3))
                mid = np.mean(vertices,axis=0)
                # Cross-bracing distinguishes a bounded plane patch from an arbitrary polygon.
                for vertex in vertices:
                    out.add(wire(pos([vertex,mid]),sheet["colour"],1))
            else:
                self._surface()
                # One VMobject with separate subpaths: avoid thousands of scene objects per frame.
                mesh = VMobject(stroke_color=colour(sheet["colour"]),stroke_width=1.2)
                for start,end in self._mesh:
                    mesh.start_new_path(pos(start))
                    mesh.add_line_to(pos(end))
                out.add(mark_background(mesh))
        for i,(name,v) in enumerate(self.st["vectors"].items()):
            end = pos(v["value"])
            if np.linalg.norm(end-center) > 0.02:
                out.add(mark_background(Arrow(center,end,buff=0,color=colour(v["colour"]),stroke_width=4,max_tip_length_to_length_ratio=0.2)))
            else:
                out.add(mark_background(Dot(center,radius=0.05,color=colour(v["colour"]))))
            out.add(text(vector_label(name, v["value"]),30,colour(v["colour"]))
                    .move_to([box.center[0],box.bottom+0.2+(len(self.st["vectors"])-1-i)*0.35,0]))
        return out

    def _surface(self):
        key = (self.st["sheet"]["fn"], self.st["extent"])
        if key != self._mesh_key:
            self._mesh_key, self._mesh = key, surface_mesh(*key)
        return self._mesh

    def _reach(self) -> float:
        """The farthest drawn point from the origin: the axes reach the extent; a surface, plane or vector may reach
        farther (at most the cube's corner)."""
        extent, sheet = self.st["extent"], self.st["sheet"]
        points = [np.asarray(v["value"], dtype=float) for v in self.st["vectors"].values()]
        if sheet and sheet["kind"] == "plane":
            points += [np.asarray(p, dtype=float) for p in plane_polygon(sheet["normal"], sheet["offset"], extent)]
        elif sheet:
            points += [np.asarray(p, dtype=float) for edge in self._surface() for p in edge]
        return max([float(extent), *(float(np.linalg.norm(p)) for p in points)])

    def vector(self, a):
        yield from self._change("vector", a)

    def cross(self, a):
        yield from self._change("cross", a)

    def plane(self, a):
        yield from self._change("plane", a)

    def surface(self, a):
        yield from self._change("surface", a)

    def clear(self, a):
        yield from self._change("clear", a)

    def view(self, a):
        start_a,start_e = self.st["azimuth"],self.st["elevation"]
        def update(mob,alpha):
            self.st.update(azimuth=start_a+(a.azimuth-start_a)*alpha,
                           elevation=start_e+(a.elevation-start_e)*alpha)
            mob.become(self._picture())
        yield Step([UpdateFromAlphaFunc(self.picture,update)])
        self.st.update(azimuth=a.azimuth,elevation=a.elevation)
