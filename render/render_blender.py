"""Product-style Cycles renders of the exported STLs: light-grey studio sweep, same camera direction.

    blender --background --python render/render_blender.py -- [--names a,b,c] [--samples 128]
                                                              [--res 1600x1200] [--preview]

Reads exports/<name>.stl, writes the full-size master renders/_work/<name>.png (<name>_preview.png
with --preview). render/overview.py turns the masters into the web-size JPEGs that are committed.
The scene is scaled to each part's bounding radius, so lights, sweep and framing look the same
whether the part is a 10 mm clip or a 130 mm plate.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EXP = os.path.join(ROOT, "exports")
REN = os.path.join(ROOT, "renders", "_work")       # masters, not committed
ARGV = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
MM = 0.001

# camera direction from the part centre: front-left, about 28 deg above the bed
VIEW = Vector((-0.62, -1.0, 0.62)).normalized()
LENS_MM = 70.0
PLA = (0.020, 0.185, 0.290)        # linear RGB, a teal-blue PLA
LAYER_MM = 0.2
LIGHT = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--light=")), "1.0"))


def arg(name, default=None):
    for a in ARGV:
        if a.startswith(f"--{name}="):
            return a.split("=", 1)[1]
    return default


def principled(name, color, rough):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    return m, m.node_tree, b


def pla_material():
    m, nt, b = principled("PLA", PLA, 0.42)
    for key, val in (("Specular IOR Level", 0.45), ("Coat Weight", 0.05)):
        if key in b.inputs:
            b.inputs[key].default_value = val
    # printed layer lines: bands along Z every LAYER_MM
    tc = nt.nodes.new("ShaderNodeTexCoord")
    wv = nt.nodes.new("ShaderNodeTexWave")
    wv.wave_type = "BANDS"
    wv.bands_direction = "Z"
    wv.inputs["Scale"].default_value = 2 * math.pi / (20.0 * LAYER_MM * MM)
    wv.inputs["Distortion"].default_value = 0.0
    nt.links.new(tc.outputs["Object"], wv.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.10
    bp.inputs["Distance"].default_value = 0.00004
    nt.links.new(wv.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def sweep(R, coll):
    """Seamless studio sweep: floor, cove, back wall (behind the part, +Y)."""
    import bmesh
    m, _, _ = principled("Sweep", (0.80, 0.80, 0.80), 0.9)
    w, y_c, r, top = 40 * R, 4.0 * R, 5.0 * R, 20 * R
    prof = [(-30 * R, 0.0)] + [(y_c + r * math.sin(math.pi / 2 * i / 32), r - r * math.cos(math.pi / 2 * i / 32))
                               for i in range(33)] + [(y_c + r, top)]
    me = bpy.data.meshes.new("Sweep")
    bm = bmesh.new()
    rows = [[bm.verts.new((x, y, z)) for y, z in prof] for x in (-w, w)]
    for i in range(len(prof) - 1):
        bm.faces.new([rows[0][i], rows[1][i], rows[1][i + 1], rows[0][i + 1]])
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("Sweep", me)
    me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = True
    coll.objects.link(ob)


def area(name, loc, target, size, power, coll):
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = size
    ld.energy = power
    ob = bpy.data.objects.new(name, ld)
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = (target - loc).to_track_quat("-Z", "Y").to_euler()


def setup_render(sc, samples, res, preview):
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception as e:                      # CPU fallback, same image
        print("GPU unavailable, rendering on CPU:", e)
    sc.cycles.samples = samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.01
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 40 if preview else 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.image_settings.color_mode = "RGB"
    sc.render.film_transparent = False
    for vt, look in (("AgX", "AgX - Medium High Contrast"), ("AgX", None), ("Filmic", None)):
        try:
            sc.view_settings.view_transform = vt
            if look:
                sc.view_settings.look = look
            break
        except TypeError:
            continue
    sc.view_settings.exposure = -0.2


def render_one(name, samples, res, preview):
    bpy.ops.wm.read_homefile(use_empty=True)
    sc = bpy.context.scene
    coll = bpy.data.collections.new("Studio")
    sc.collection.children.link(coll)
    before = set(bpy.data.objects)
    bpy.ops.wm.stl_import(filepath=os.path.join(EXP, f"{name}.stl"), global_scale=MM, forward_axis="Y", up_axis="Z")
    ob = [o for o in bpy.data.objects if o not in before][0]
    ob.data.materials.clear()
    ob.data.materials.append(pla_material())
    try:
        with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]):
            bpy.ops.object.shade_auto_smooth(angle=math.radians(30))
    except Exception:
        pass
    # bounding sphere of the part (metres)
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    C = (lo + hi) / 2
    R = (hi - lo).length / 2
    sweep(R, coll)
    k = R * R * LIGHT                           # power scales with distance squared: same exposure at any size
    area("Key", C + Vector((-3.2 * R, -3.6 * R, 4.2 * R)), C, (3.2 * R, 2.4 * R), 330 * k, coll)
    area("Fill", C + Vector((4.2 * R, -2.4 * R, 2.2 * R)), C, (4 * R, 4 * R), 70 * k, coll)
    area("Rim", C + Vector((1.0 * R, 3.6 * R, 3.6 * R)), C, (2.6 * R, 2.6 * R), 120 * k, coll)
    area("Top", C + Vector((0, -0.4 * R, 6.0 * R)), C, (6 * R, 6 * R), 110 * k, coll)
    world = bpy.data.worlds.new("World")
    sc.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.82, 0.82, 0.83, 1)
    bg.inputs["Strength"].default_value = 0.15
    cd = bpy.data.cameras.new("Cam")
    cam = bpy.data.objects.new("Cam", cd)
    sc.collection.objects.link(cam)
    sc.camera = cam
    cd.lens = LENS_MM
    cd.sensor_fit = "VERTICAL"
    cd.sensor_height = 24.0
    fov = 2 * math.atan(cd.sensor_height / 2 / cd.lens)
    dist = 1.12 * R / math.sin(fov / 2)
    cd.clip_start, cd.clip_end = dist / 50, dist * 50
    cam.location = C + VIEW * dist
    cam.rotation_euler = (C - cam.location).to_track_quat("-Z", "Y").to_euler()
    setup_render(sc, samples, res, preview)
    os.makedirs(REN, exist_ok=True)
    out = os.path.join(REN, f"{name}{'_preview' if preview else ''}.png")
    sc.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print(f"wrote {out}", flush=True)


def main():
    names = arg("names")
    names = names.split(",") if names else sorted(f[:-4] for f in os.listdir(EXP) if f.endswith(".stl"))
    samples = int(arg("samples", "128"))
    w, h = (int(v) for v in arg("res", "1600x1200").split("x"))
    preview = "--preview" in ARGV
    for n in names:
        render_one(n, samples, (w, h), preview)


main()
