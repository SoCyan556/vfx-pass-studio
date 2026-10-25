"""Render a tiny original animation to test the generator without uploading footage."""
import bpy
from mathutils import Vector
from pathlib import Path
import sys

directory = Path(sys.argv[sys.argv.index('--') + 1])
directory.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_x = 384
scene.render.resolution_y = 256
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.film_transparent = True
scene.world = bpy.data.worlds.new('TestWorld')
scene.world.color = (.15, .15, .15)
bpy.ops.mesh.primitive_monkey_add()
subject = bpy.context.object
subject.rotation_euler = (.12, 0, .2)
modifier = subject.modifiers.new('Smooth surface', 'SUBSURF')
modifier.levels = 1
for face in subject.data.polygons:
    face.use_smooth = True
mat = bpy.data.materials.new('Teal ceramic')
mat.diffuse_color = (.04, .55, .4, 1)
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get('Principled BSDF')
bsdf.inputs['Base Color'].default_value = (.04, .55, .4, 1)
bsdf.inputs['Roughness'].default_value = .3
subject.data.materials.append(mat)
bpy.ops.object.camera_add(location=(0, -5, 1.3))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, .05)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.lens = 42
scene.camera = camera
bpy.ops.object.light_add(type='AREA', location=(-3, -4, 5))
bpy.context.object.data.energy = 700
bpy.context.object.data.shape = 'DISK'
bpy.context.object.data.size = 4
bpy.context.object.rotation_euler = (Vector((0, 0, 0)) - bpy.context.object.location).to_track_quat('-Z', 'Y').to_euler()
for i in range(3):
    subject.rotation_euler.z = .2 + i * .15
    scene.render.filepath = str(directory / f'{i:06d}.png')
    bpy.ops.render.render(write_still=True)
