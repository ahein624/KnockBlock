#!/usr/bin/env python3
"""Generate dependency-free STL meshes for the KnockBlock case.

The OpenSCAD file remains the editable source of truth. This generator makes
axis-aligned, watertight meshes at 0.25 mm XY / 0.5 mm Z resolution so the
parts can also be assembled and sliced directly in Bambu Studio.
"""

from __future__ import annotations

import argparse
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


XY_STEP = 0.25
Z_STEP = 0.5

PANEL_WIDTH = 160.0
PANEL_HEIGHT = 80.0
PANEL_DEPTH = 14.7
PANEL_POCKET = 161.0

DIFFUSER_WIDTH = 164.0
DIFFUSER_THICKNESS = 2.0
DIFFUSER_CLEARANCE = 0.4
DIFFUSER_CORNER_CLIP = 8.0
DIFFUSER_GAP = 10.0
VIEW_OPENING = 159.5

CASE_WIDTH = 180.0
CORNER_RADIUS = 7.0
BEZEL_DEPTH = 4.0
CRADLE_DEPTH = 16.0
ELECTRONICS_DEPTH = 32.0
WALL = 3.0

FACE_SCREW_RADIUS = 1.7
FACE_COUNTERSINK_RADIUS = 3.2
INSERT_HOLE_RADIUS = 2.1
FACE_SCREW_OFFSET = 82.0
CLIP_INSERT_RADIUS = 2.1


def in_square(x: float, y: float, size: float) -> bool:
    half = size / 2.0
    return abs(x) < half and abs(y) < half


def in_rounded_square(x: float, y: float, size: float, radius: float) -> bool:
    half = size / 2.0
    ax, ay = abs(x), abs(y)
    if ax >= half or ay >= half:
        return False
    dx = max(ax - (half - radius), 0.0)
    dy = max(ay - (half - radius), 0.0)
    return dx * dx + dy * dy < radius * radius


def in_chamfered_square(x: float, y: float, size: float, chamfer: float) -> bool:
    half = size / 2.0
    ax, ay = abs(x), abs(y)
    return ax < half and ay < half and ax + ay < 2.0 * half - chamfer


def in_circle(x: float, y: float, cx: float, cy: float, radius: float) -> bool:
    return (x - cx) ** 2 + (y - cy) ** 2 < radius * radius


def in_any_face_hole(x: float, y: float, radius: float) -> bool:
    return any(
        in_circle(x, y, sx * FACE_SCREW_OFFSET, sy * FACE_SCREW_OFFSET, radius)
        for sx in (-1, 1)
        for sy in (-1, 1)
    )


def bezel_solid(x: float, y: float, z: float) -> bool:
    if not in_rounded_square(x, y, CASE_WIDTH, CORNER_RADIUS):
        return False
    if in_square(x, y, VIEW_OPENING):
        return False
    pocket_start = BEZEL_DEPTH - DIFFUSER_THICKNESS - DIFFUSER_CLEARANCE
    if z >= pocket_start and in_chamfered_square(
        x,
        y,
        DIFFUSER_WIDTH + DIFFUSER_CLEARANCE,
        DIFFUSER_CORNER_CLIP,
    ):
        return False
    screw_radius = FACE_SCREW_RADIUS
    if z < 2.1:
        screw_radius = FACE_COUNTERSINK_RADIUS + (
            FACE_SCREW_RADIUS - FACE_COUNTERSINK_RADIUS
        ) * (z / 2.1)
    return not in_any_face_hole(x, y, screw_radius)


def spacer_solid(x: float, y: float, z: float) -> bool:
    if not in_rounded_square(x, y, CASE_WIDTH, CORNER_RADIUS):
        return False
    if in_square(x, y, VIEW_OPENING):
        return False
    if 1.5 <= z < DIFFUSER_GAP - 1.5 and in_chamfered_square(
        x, y, DIFFUSER_WIDTH + 2.0, 6.0
    ):
        return False
    return not in_any_face_hole(x, y, FACE_SCREW_RADIUS)


def in_clip_insert(x: float, y: float) -> bool:
    edge = (CASE_WIDTH + PANEL_POCKET) / 4.0
    for p in (-55.0, 0.0, 55.0):
        if in_circle(x, y, p, edge, CLIP_INSERT_RADIUS):
            return True
        if in_circle(x, y, p, -edge, CLIP_INSERT_RADIUS):
            return True
        if in_circle(x, y, edge, p, CLIP_INSERT_RADIUS):
            return True
        if in_circle(x, y, -edge, p, CLIP_INSERT_RADIUS):
            return True
    return False


def cradle_solid(x: float, y: float, z: float) -> bool:
    if not in_rounded_square(x, y, CASE_WIDTH, CORNER_RADIUS):
        return False
    if in_square(x, y, PANEL_POCKET):
        return False
    if in_any_face_hole(x, y, FACE_SCREW_RADIUS):
        return False
    return not (z >= CRADLE_DEPTH - 6.0 and in_clip_insert(x, y))


def in_side_vent(x: float, y: float, z: float) -> bool:
    if not (10.0 <= z < 22.0):
        return False
    near_top_or_bottom = y > CASE_WIDTH / 2.0 - WALL or y < -CASE_WIDTH / 2.0 + WALL
    if not near_top_or_bottom:
        return False
    return any(abs(x - center) < 8.0 for center in (-60.0, -30.0, 0.0, 30.0, 60.0))


def in_rear_cut(x: float, y: float) -> bool:
    for center in (-55.0, 55.0):
        if in_circle(x, y, center, 48.0, 4.25):
            return True
        if abs(x - center) < 2.0 and 48.0 <= y < 60.0:
            return True
    for cx in (-54.0, -36.0, -18.0, 0.0, 18.0, 36.0, 54.0):
        for cy in (-36.0, -18.0, 0.0, 18.0, 36.0):
            if abs(x - cx) < 6.0 and abs(y - cy) < 2.0:
                return True
    return False


def back_shell_solid(x: float, y: float, z: float) -> bool:
    outer = in_rounded_square(x, y, CASE_WIDTH, CORNER_RADIUS)
    if not outer:
        return False
    inner = in_rounded_square(x, y, CASE_WIDTH - 2.0 * WALL, CORNER_RADIUS - WALL)
    shell = not (z < ELECTRONICS_DEPTH - WALL and inner)
    boss = any(
        in_circle(x, y, sx * FACE_SCREW_OFFSET, sy * FACE_SCREW_OFFSET, 4.5)
        for sx in (-1, 1)
        for sy in (-1, 1)
    )
    solid = shell or boss
    if not solid:
        return False
    if z < 7.0 and in_any_face_hole(x, y, INSERT_HOLE_RADIUS):
        return False
    if abs(x) < 10.0 and y < -CASE_WIDTH / 2.0 + WALL and 5.0 <= z < 15.0:
        return False
    if in_side_vent(x, y, z):
        return False
    if z >= ELECTRONICS_DEPTH - WALL and in_rear_cut(x, y):
        return False
    return True


def clip_solid(x: float, y: float, z: float) -> bool:
    # A compact capsule-shaped swivel clip. The foam pad takes up the nominal
    # 1.3 mm between a 14.7 mm panel and the 16 mm cradle.
    body = (
        in_circle(x, y, -5.0, 0.0, 5.0)
        or in_circle(x, y, 11.0, 0.0, 4.0)
        or (-5.0 <= x < 11.0 and abs(y) < 4.0)
    )
    return body and not in_circle(x, y, -5.0, 0.0, FACE_SCREW_RADIUS)


def diffuser_solid(x: float, y: float, z: float) -> bool:
    return in_chamfered_square(
        x, y, DIFFUSER_WIDTH, DIFFUSER_CORNER_CLIP
    )


def coupon_solid(x: float, y: float, z: float) -> bool:
    # Origin is the coupon's lower-left corner for easy slot dimensions.
    if not (0.0 <= x < 70.0 and 0.0 <= y < 30.0):
        return False
    panel_slot = 5.0 <= x < 33.0 and 4.0 <= y < 4.0 + PANEL_DEPTH + 0.8 and z >= 4.0
    diffuser_slot = (
        40.0 <= x < 65.0
        and 4.0 <= y < 4.0 + DIFFUSER_THICKNESS + DIFFUSER_CLEARANCE
        and z >= 4.0
    )
    return not (panel_slot or diffuser_slot)


@dataclass(frozen=True)
class Part:
    name: str
    bounds: tuple[float, float, float, float]
    depth: float
    solid: Callable[[float, float, float], bool]


PARTS = {
    "bezel": Part("bezel", (-90.0, 90.0, -90.0, 90.0), BEZEL_DEPTH, bezel_solid),
    "spacer": Part("spacer", (-90.0, 90.0, -90.0, 90.0), DIFFUSER_GAP, spacer_solid),
    "cradle": Part("cradle", (-90.0, 90.0, -90.0, 90.0), CRADLE_DEPTH, cradle_solid),
    "back_shell": Part(
        "back_shell", (-90.0, 90.0, -90.0, 90.0), ELECTRONICS_DEPTH, back_shell_solid
    ),
    "diffuser": Part(
        "diffuser", (-82.0, 82.0, -82.0, 82.0), DIFFUSER_THICKNESS, diffuser_solid
    ),
    "retainer_clip": Part("retainer_clip", (-11.0, 16.0, -6.0, 6.0), 3.0, clip_solid),
    "fit_coupon": Part("fit_coupon", (0.0, 70.0, 0.0, 30.0), 22.0, coupon_solid),
}


def write_triangle(handle, normal, a, b, c) -> None:
    handle.write(struct.pack("<12fH", *(normal + a + b + c), 0))


def write_quad(handle, normal, a, b, c, d) -> int:
    write_triangle(handle, normal, a, b, c)
    write_triangle(handle, normal, a, c, d)
    return 2


def greedy_rectangles(mask: bytearray, width: int, height: int):
    """Yield maximal same-facing rectangles from a 2D face mask."""
    for row in range(height):
        column = 0
        while column < width:
            index = row * width + column
            value = mask[index]
            if not value:
                column += 1
                continue

            run_width = 1
            while column + run_width < width and mask[index + run_width] == value:
                run_width += 1

            run_height = 1
            while row + run_height < height:
                next_index = (row + run_height) * width + column
                if any(mask[next_index + offset] != value for offset in range(run_width)):
                    break
                run_height += 1

            for clear_row in range(row, row + run_height):
                clear_index = clear_row * width + column
                mask[clear_index : clear_index + run_width] = b"\0" * run_width

            yield column, row, run_width, run_height, value
            column += run_width


def build_layers(part: Part):
    xmin, xmax, ymin, ymax = part.bounds
    nx = round((xmax - xmin) / XY_STEP)
    ny = round((ymax - ymin) / XY_STEP)
    nz = round(part.depth / Z_STEP)
    layers = []
    cache: dict[bytes, tuple[bytearray, list[int]]] = {}

    for k in range(nz):
        z = (k + 0.5) * Z_STEP
        raw = bytearray(nx * ny)
        active = []
        for j in range(ny):
            y = ymin + (j + 0.5) * XY_STEP
            offset = j * nx
            for i in range(nx):
                x = xmin + (i + 0.5) * XY_STEP
                if part.solid(x, y, z):
                    raw[offset + i] = 1
                    active.append(offset + i)
        signature = bytes(raw)
        cached = cache.get(signature)
        if cached is None:
            cached = (raw, active)
            cache[signature] = cached
        layers.append(cached)
    return xmin, ymin, nx, ny, nz, layers


def mesh_part(part: Part, destination: Path) -> tuple[int, tuple[float, float, float]]:
    xmin, ymin, nx, ny, nz, layers = build_layers(part)
    destination.parent.mkdir(parents=True, exist_ok=True)
    triangles = 0

    segments = []
    segment_start = 0
    for k in range(1, nz + 1):
        if k == nz or layers[k][0] is not layers[segment_start][0]:
            segments.append((segment_start, k, layers[segment_start][0]))
            segment_start = k

    with destination.open("wb") as handle:
        title = f"KnockBlock {part.name}".encode("ascii")[:80]
        handle.write(title.ljust(80, b"\0"))
        handle.write(struct.pack("<I", 0))

        # Horizontal faces at the base, top, and every Z-profile transition.
        empty = bytearray(nx * ny)
        boundaries = [(0, empty, segments[0][2])]
        for previous, current in zip(segments, segments[1:]):
            boundaries.append((previous[1], previous[2], current[2]))
        boundaries.append((nz, segments[-1][2], empty))

        for k, below, above in boundaries:
            face_mask = bytearray(nx * ny)
            for index in range(nx * ny):
                if below[index] and not above[index]:
                    face_mask[index] = 2  # +Z
                elif above[index] and not below[index]:
                    face_mask[index] = 1  # -Z
            z = k * Z_STEP
            for i, j, run_x, run_y, direction in greedy_rectangles(face_mask, nx, ny):
                x0 = xmin + i * XY_STEP
                x1 = xmin + (i + run_x) * XY_STEP
                y0 = ymin + j * XY_STEP
                y1 = ymin + (j + run_y) * XY_STEP
                if direction == 2:
                    triangles += write_quad(
                        handle, (0.0, 0.0, 1.0),
                        (x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z)
                    )
                else:
                    triangles += write_quad(
                        handle, (0.0, 0.0, -1.0),
                        (x0, y0, z), (x0, y1, z), (x1, y1, z), (x1, y0, z)
                    )

        # Each constant-profile Z segment needs its vertical boundary only once.
        for start, end, layer in segments:
            z0, z1 = start * Z_STEP, end * Z_STEP

            for i in range(nx + 1):
                face_line = bytearray(ny)
                for j in range(ny):
                    left = i > 0 and layer[j * nx + i - 1]
                    right = i < nx and layer[j * nx + i]
                    if left and not right:
                        face_line[j] = 2  # +X
                    elif right and not left:
                        face_line[j] = 1  # -X
                j = 0
                while j < ny:
                    direction = face_line[j]
                    if not direction:
                        j += 1
                        continue
                    end_j = j + 1
                    while end_j < ny and face_line[end_j] == direction:
                        end_j += 1
                    x = xmin + i * XY_STEP
                    y0, y1 = ymin + j * XY_STEP, ymin + end_j * XY_STEP
                    if direction == 2:
                        triangles += write_quad(
                            handle, (1.0, 0.0, 0.0),
                            (x, y0, z0), (x, y1, z0), (x, y1, z1), (x, y0, z1)
                        )
                    else:
                        triangles += write_quad(
                            handle, (-1.0, 0.0, 0.0),
                            (x, y0, z0), (x, y0, z1), (x, y1, z1), (x, y1, z0)
                        )
                    j = end_j

            for j in range(ny + 1):
                face_line = bytearray(nx)
                for i in range(nx):
                    front = j > 0 and layer[(j - 1) * nx + i]
                    back = j < ny and layer[j * nx + i]
                    if front and not back:
                        face_line[i] = 2  # +Y
                    elif back and not front:
                        face_line[i] = 1  # -Y
                i = 0
                while i < nx:
                    direction = face_line[i]
                    if not direction:
                        i += 1
                        continue
                    end_i = i + 1
                    while end_i < nx and face_line[end_i] == direction:
                        end_i += 1
                    y = ymin + j * XY_STEP
                    x0, x1 = xmin + i * XY_STEP, xmin + end_i * XY_STEP
                    if direction == 2:
                        triangles += write_quad(
                            handle, (0.0, 1.0, 0.0),
                            (x0, y, z0), (x0, y, z1), (x1, y, z1), (x1, y, z0)
                        )
                    else:
                        triangles += write_quad(
                            handle, (0.0, -1.0, 0.0),
                            (x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)
                        )
                    i = end_i

        handle.seek(80)
        handle.write(struct.pack("<I", triangles))

    return triangles, (
        part.bounds[1] - part.bounds[0],
        part.bounds[3] - part.bounds[2],
        part.depth,
    )


def selected_parts(names: Iterable[str]) -> list[Part]:
    result = []
    for name in names:
        if name == "all":
            return list(PARTS.values())
        result.append(PARTS[name])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("parts", nargs="*", choices=["all", *PARTS], default=["all"])
    parser.add_argument("--output", type=Path, default=Path(__file__).with_name("stl"))
    args = parser.parse_args()

    for part in selected_parts(args.parts):
        output = args.output / f"knockblock_{part.name}.stl"
        triangles, size = mesh_part(part, output)
        print(
            f"{output}: {triangles:,} triangles; "
            f"{size[0]:g} × {size[1]:g} × {size[2]:g} mm"
        )


if __name__ == "__main__":
    main()
