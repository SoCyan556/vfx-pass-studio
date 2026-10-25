"""Original compatibility bridge; requires the user's separately installed Beeble add-on."""
bl_info = {'name': 'Local VFX Pass Import', 'author': 'VFX Pass Studio', 'version': (0, 1, 0),
           'blender': (4, 2, 0), 'location': 'File > Import > Local VFX Passes',
           'description': 'Import local video passes using the existing Beeble shot controls', 'category': 'Import-Export'}

import json
import math
import os
from pathlib import Path
import uuid
import zipfile

import bpy
from bpy_extras.io_utils import ImportHelper
from bpy.props import StringProperty, BoolProperty


def unpack(filepath):
    path = Path(filepath)
    if path.name == 'Camera.json':
        return path.parent
    if path.suffix.lower() != '.zip':
        raise ValueError('Choose the exported ZIP or the Camera.json inside its .beeble folder.')
    destination = Path(bpy.utils.user_resource('DATAFILES')) / 'LocalVFX' / uuid.uuid4().hex
    destination.mkdir(parents=True)
    with zipfile.ZipFile(path) as archive:
        for item in archive.infolist():
            target = (destination / item.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('ZIP contains a path outside its export folder.')
            if item.file_size > 2 * 1024 ** 3:
                raise ValueError('ZIP contains an unexpectedly large individual file.')
        archive.extractall(destination)
    cameras = list(destination.rglob('Camera.json'))
    if len(cameras) != 1:
        raise ValueError('ZIP must contain exactly one shot with Camera.json.')
    return cameras[0].parent


def validate(root):
    if (root / 'INCOMPLETE.txt').exists():
        raise ValueError('This export is incomplete. Finish generating it before importing.')
    data = json.loads((root / 'Camera.json').read_text(encoding='utf-8'))
    count = data['frame_count']
    if not isinstance(count, int) or count < 1 or len(data['frames']) != count:
        raise ValueError('Invalid shot frame count.')
    for folder in ('source', 'alpha', 'normal', 'basecolor', 'roughness', 'metallic', 'specular', 'depth'):
        ext = 'exr' if folder == 'depth' else 'png'
        if any(not (root / folder / f'{i:06d}.{ext}').is_file() for i in range(count)):
            raise ValueError(f'Missing frames in {folder}.')
    return data


def import_package(context, root, use_settings=True):
    if not hasattr(context.scene, 'beeble_imported_shots'):
        raise RuntimeError('Enable your Beeble add-on first. This bridge uses its existing materials and controls.')
    data = validate(root)
    scene = context.scene
    previous_count = len(scene.beeble_imported_shots)
    keys = ('beeble_temp_use_imported_fps', 'beeble_temp_use_imported_resolution')
    saved = {key: scene.get(key) for key in keys}
    try:
        for key in keys:
            scene[key] = use_settings
        result = bpy.ops.beeble.import_shot('EXEC_DEFAULT', shot_path=str(root))
    finally:
        for key in keys:
            if saved[key] is None:
                if key in scene:
                    del scene[key]
            else:
                scene[key] = saved[key]
    if result != {'FINISHED'} or len(scene.beeble_imported_shots) != previous_count + 1:
        raise RuntimeError('Beeble did not finish importing the shot. See its console log.')
    shot = scene.beeble_imported_shots[-1]
    if use_settings:
        fps = data['frame_rate']
        scene.render.fps = round(fps)
        scene.render.fps_base = round(fps) / fps
        scene.render.resolution_x, scene.render.resolution_y = data['resolution']
        shot.resolution_x, shot.resolution_y = data['resolution']
    # Zero-numbered filenames require the original add-on's -1 offset.
    # Preserve that convention while normalizing the start and duration.
    for node in shot.attributes.material.node_tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image and node.image.source == 'SEQUENCE':
            node.image_user.frame_start = scene.frame_start
            node.image_user.frame_offset = -1
            node.image_user.frame_duration = data['frame_count']
            node.image_user.use_auto_refresh = True
    scene.frame_set(scene.frame_start)
    return shot


class LOCALVFX_OT_import(bpy.types.Operator, ImportHelper):
    bl_idname = 'local_vfx.import_shot'
    bl_label = 'Import Local VFX Passes'
    bl_options = {'REGISTER', 'UNDO'}
    filter_glob: StringProperty(default='*.zip;Camera.json', options={'HIDDEN'})
    use_settings: BoolProperty(name='Use clip FPS and resolution', default=True)

    def execute(self, context):
        try:
            shot = import_package(context, unpack(self.filepath), self.use_settings)
            self.report({'INFO'}, f'Imported {shot.file_name}. Adjust it in the Beeble sidebar.')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def menu(self, context):
    self.layout.operator(LOCALVFX_OT_import.bl_idname, text='Local VFX Passes (.zip / Camera.json)')


def register():
    bpy.utils.register_class(LOCALVFX_OT_import)
    bpy.types.TOPBAR_MT_file_import.append(menu)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu)
    bpy.utils.unregister_class(LOCALVFX_OT_import)
