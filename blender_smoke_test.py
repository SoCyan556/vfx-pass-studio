"""Run with a separate factory-startup Blender; never touches the user's open scene."""
import importlib.util
import json
from pathlib import Path
import sys
import bpy
import numpy as np

reference, package, output = sys.argv[sys.argv.index('--') + 1:]
spec = importlib.util.spec_from_file_location('beeble_reference', Path(reference) / '__init__.py',
                                             submodule_search_locations=[reference])
module = importlib.util.module_from_spec(spec)
sys.modules['beeble_reference'] = module
spec.loader.exec_module(module)
module.register()
# The supplied add-on calls this method on its modifier dictionary. A headless import
# test must exercise the actual code, including detecting upstream errors.
sys.path.insert(0, str(Path(__file__).parent))
from vfx_blender_bridge import import_package, unpack
bpy.context.scene.account_settings.workspace_path = str(Path(output).parent / 'beeble-workspace')
root = unpack(package) if Path(package).suffix.lower() == '.zip' else Path(package)
package = str(root)
shot = import_package(bpy.context, root)
assert shot.attributes.footage is not None
assert shot.attributes.camera is not None
assert shot.attributes.material is not None
nodes = shot.attributes.material.node_tree.nodes
images = {node.label: node.image.filepath for node in nodes if node.type == 'TEX_IMAGE' and node.image}
required = {'INPUT_VIDEO', 'INPUT_NORMAL', 'INPUT_BASECOLOR', 'INPUT_ALPHA', 'INPUT_ROUGHNESS', 'INPUT_REFLECTIVITY', 'INPUT_METALLIC'}
assert required <= set(images), images
assert all(Path(images[key]).is_file() for key in required)
assert shot.attributes.footage.get('use_depth') is not None
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT'
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
scene.render.film_transparent = True
shot.attributes.material['render_to_original'] = 1.0
for frame in (0, 1, bpy.context.scene.frame_end):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    scene.render.filepath = str(Path(output).parent / f'import-render-{frame:02d}.png')
    bpy.ops.render.render(write_still=True)
    rendered_image = bpy.data.images.load(scene.render.filepath, check_existing=False)
    rendered_alpha = np.array(rendered_image.pixels[:]).reshape(-1, 4)[:, 3]
    errors = []
    for candidate in range(3):
        reference_image = bpy.data.images.load(str(Path(package) / 'alpha' / f'{candidate:06d}.png'), check_existing=False)
        reference_alpha = np.array(reference_image.pixels[:]).reshape(-1, 4)[:, 0]
        errors.append(float(np.mean(np.abs(rendered_alpha - reference_alpha))))
        bpy.data.images.remove(reference_image)
    bpy.data.images.remove(rendered_image)
    assert np.argmin(errors) == frame, ('Sequence timing mismatch', frame, errors)
    assert errors[frame] < .02, ('Unexpected silhouette distortion', frame, errors)
    for node in nodes:
        if node.type == 'TEX_IMAGE' and node.image and node.image.source == 'SEQUENCE':
            assert node.image_user.frame_offset == -1
footage = shot.attributes.footage
for key in ('keying', 'alpha_erosion', 'render_to_original', 'basecolor_to_original'):
    assert key in shot.attributes.material, key
assert '2d_to_3d' in footage
shot.normal_strength = 1.25
shot.use_depth = False
assert footage['use_depth'] == False
shot.use_depth = True
shot.subdivision_level = 2
assert footage['use_depth'] == True
assert footage.modifiers['PlaneSubdivision_IMAGE'].levels == 2
print('SMOKE_IMPORT_OK=' + json.dumps({'images': images, 'frames': bpy.context.scene.frame_end + 1,
       'fps': bpy.context.scene.render.fps / bpy.context.scene.render.fps_base,
       'resolution': [bpy.context.scene.render.resolution_x, bpy.context.scene.render.resolution_y]}))
bpy.ops.wm.save_as_mainfile(filepath=output)
