# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

bl_info = {
    "name": "Align Selection To Annotation Stroke",
    "description": "Aligns selection to last annotation grease pencil stroke. Default hotkey is [ALT + double-click RIGHT MOUSE].",
    "author": "Bjørnar Frøyse",
    "version": (1, 2, 3),
    "blender": (2, 80, 0),
    "location": "Shortcut Only",
    "category": "Mesh"
}

import bpy
from bpy_extras import view3d_utils
import bmesh
import mathutils
from bpy.props import FloatProperty, BoolProperty
from bpy.types import Operator
import math

# TODO: Implement surface snap/projection (for retopo).
# TODO: Option to lock axis?
# TODO: More flexible "projection"? Currently only vertical & horizontal. Works in most cases, but can easily be a bit wonky.
# TODO: Make it work with the mesh.use_mirror_x setting.
# TODO: Proportional editing
# TODO: Support for bones (pose mode)

# Preferences for the addon (Displayed "inside" the addon in user preferences)
class PREFS_bear_align_to_gpencil(bpy.types.AddonPreferences):
    bl_idname = __name__

    clear_strokes: BoolProperty(
            name = "Clear Strokes On Execute",
            description = "Clear grease pencil strokes after executing",
            default = False)

    use_default_shortcut: BoolProperty(
            name = "Use Default Shortcut",
            description = "Use default shortcut: mouse double-click + modifier",
            default = True)

    mouse_click : bpy.props.EnumProperty(
        name="Mouse button", description="Double click on right/left/middle mouse button in combination with a modifier to trigger alignement",
        default='RIGHTMOUSE',
        items=(
            ('RIGHTMOUSE', 'double Right click', 'Use double click on Right mouse button', 'MOUSE_RMB', 0),
            ('LEFTMOUSE', 'double Left click', 'Use double click on Left mouse button', 'MOUSE_LMB', 1),
            ('MIDDLEMOUSE', 'double Mid click', 'Use double click on Mid mouse button', 'MOUSE_MMB', 2),
            ))
    
    use_shift: BoolProperty(
            name = "combine with shift",
            description = "add shift combined with double click to trigger alignement",
            default = False)

    use_alt: BoolProperty(
            name = "combine with alt",
            description = "add alt combined with double click to trigger alignement (default)",
            default = True)

    use_ctrl: BoolProperty(
            name = "combine with ctrl",
            description = "add ctrl combined with double click to trigger alignement",
            default = False)

    def draw(self, context):

        self.layout.prop(self, "clear_strokes")
        if(self.clear_strokes):
            self.layout.label(text="'clear strokes' option will currently make the influence slider stop working", icon="ERROR")

        self.layout.prop(self, "use_default_shortcut", text='Bind shortcuts')

        if(self.use_default_shortcut):
            self.row = self.layout.row()
            self.row.label(text="After changes, use the Bind/Rebind button")#icon=""
            self.row.operator("prefs.bear_rebind_shortcut", text='Bind/Rebind shortcuts', icon='FILE_REFRESH')#EVENT_SPACEKEY
            self.layout.prop(self, "mouse_click",text='')
            self.layout.prop(self, "use_alt", text='+ Alt')
            self.layout.prop(self, "use_shift", text='+ Shift')
            self.layout.prop(self, "use_ctrl", text='+ Ctrl')
            self.layout.label(text="Choose at least one modifier to combine with the double click (default: Alt)", icon="INFO")

        else:
            self.layout.label(text="No hotkey has been set automatically. Following operators needs to be set manually:", icon="ERROR")
            self.layout.label(text="mesh.bear_align_selection_to_gpencil")
            self.layout.label(text="object.bear_align_selection_to_gpencil")
            self.layout.label(text="uv.bear_align_selection_to_gpencil")
            self.layout.label(text="armature.bear_align_selection_to_gpencil")
            self.layout.label(text="curve.bear_align_selection_to_gpencil")

        if self.use_default_shortcut:
            bind_keymap()
        else:
            unbind_keymap()

class PREFS_OT_rebind(Operator):
    """Rebind shortchuts for align to gp annotation"""
    bl_idname = "prefs.bear_rebind_shortcut"
    bl_label = "Rebind bear shortcut"
    bl_options = {'REGISTER', 'INTERNAL'}#internal mask it from search bar

    def execute(self, context):
        unbind_keymap()
        bind_keymap()
        return{'FINISHED'}

class OBJECT_OT_bear_align_to_gpencil(Operator):
    """Aligns selected objects to grease pencil stroke"""
    bl_idname = "object.bear_align_selection_to_gpencil"
    bl_label = "Align objects to Grease Pencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence: FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        # Object mode
        if bpy.context.mode == 'OBJECT':
            align_objects(context, self.influence)
            return {'FINISHED'}

        print("No valid cases found. Try again with another selection!")
        return{'FINISHED'}

class UV_OT_bear_align_to_gpencil(Operator):
    """Aligns UV selection to gpencil stroke"""
    """Aligns selection to grease pencil stroke"""
    bl_idname = "uv.bear_align_selection_to_gpencil"
    bl_label = "Align UV vertices to Grease Pencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence: FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        align_uvs(context, self.influence)
        return {'FINISHED'}


class MESH_OT_bear_align_to_gpencil(Operator):
    """Aligns selection to grease pencil stroke"""
    bl_idname = "mesh.bear_align_selection_to_gpencil"
    bl_label = "Align Verts to Grease Pencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence: FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        # Edit mode (vertices)
        if bpy.context.active_object.type == 'MESH' and bpy.context.active_object.data.is_editmode:
            align_vertices(context, self.influence)
            return {'FINISHED'}

        print("No valid cases found. Try again with another selection!")
        return{'FINISHED'}

class CURVE_OT_bear_align_to_gpencil(Operator):
    """Aligns selection to grease pencil stroke"""
    bl_idname = "curve.bear_align_selection_to_gpencil"
    bl_label = "Align curve points to Grease Pencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence: FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        # Curves
        if bpy.context.active_object.type == 'CURVE' and bpy.context.active_object.data.is_editmode:
            align_curves(context, self.influence)
            return {'FINISHED'}

        print("No valid cases found. Try again with another selection!")
        return{'FINISHED'}

class ARMATURE_OT_bear_align_to_gpencil(Operator):
    """Aligns selection to grease pencil stroke"""
    bl_idname = "armature.bear_align_selection_to_gpencil"
    bl_label = "Align armature (edit) bones points to Grease Pencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence: FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        # Bone edit mode
        if bpy.context.active_object.type == 'ARMATURE' and bpy.context.active_object.data.is_editmode:
            align_bones_editmode(context, self.influence)
            return {'FINISHED'}

        print("No valid cases found. Try again with another selection!")
        return{'FINISHED'}

    # @classmethod
    # def poll(cls, context):
    #     return check_if_any_gp_exists(context)

def align_bones_editmode(context, influence):
    obj = bpy.context.edit_object
    bo = obj.data.edit_bones

    selected_bones = [bone for bone in bo if bone.select]

    bone_heads_3d = [bone.head for bone in selected_bones]
    bone_heads_2d = vectors_to_screenpos(context, bone_heads_3d, obj.matrix_world)

    bone_tails_3d = [bone.tail for bone in selected_bones]
    bone_tails_2d = vectors_to_screenpos(context, bone_tails_3d, obj.matrix_world)

    stroke = gpencil_to_screenpos(context)
    
    for i, bone in enumerate(selected_bones):
        nearest_point_for_head = get_nearest_interpolated_point_on_stroke(bone_heads_2d[i], stroke, context)
        newcoord_for_head = obj.matrix_world.inverted() @ region_to_location(nearest_point_for_head, obj.matrix_world @ bone.head)
        bone.head = bone.head.lerp(newcoord_for_head, influence)

        nearest_point_for_tail = get_nearest_interpolated_point_on_stroke(bone_tails_2d[i], stroke, context)
        newcoord_for_tail = obj.matrix_world.inverted() @ region_to_location(nearest_point_for_tail, obj.matrix_world @ bone.tail)
        bone.tail = bone.tail.lerp(newcoord_for_tail, influence)


def align_vertices(context, influence):
    # Object currently in edit mode.
    obj = bpy.context.edit_object
    # Object's mesh datablock.
    me = obj.data
    # Convert mesh data to bmesh.
    bm = bmesh.from_edit_mesh(me)

    # Get all selected vertices (in their local space).
    selected_verts = [v for v in bm.verts if v.select]

    verts_local_3d = [v.co for v in selected_verts]

    # Convert selected vertices' positions to 2D screen space.
    # IMPORTANT: Multiply vertex coordinates with the world matrix to get their WORLD position, not local position.
    verts_world_2d = vectors_to_screenpos(context, verts_local_3d, obj.matrix_world)

    stroke = gpencil_to_screenpos(context)

    # For each vert, look up or to the side and find the nearest interpolated gpencil point for this vertex.
    for i, v in enumerate(selected_verts):
        nearest_point = get_nearest_interpolated_point_on_stroke(verts_world_2d[i], stroke, context)
        # Get new vertex coordinate by converting from 2D screen space to 3D world space. Must multiply depth coordinate
        # with world matrix and then final result by INVERTED world matrix to get a correct final value.
        newcoord = obj.matrix_world.inverted() @ region_to_location(nearest_point, obj.matrix_world @ v.co)
        # Apply the final position using an influence slider.
        v.co = v.co.lerp(newcoord, influence)

    # Recalculate mesh normals (so lighting looks right).
    for edge in bm.edges:
        edge.normal_update()

    # Push bmesh changes back to the actual mesh datablock.
    bmesh.update_edit_mesh(me, True)


def align_curves(context, influence):

    print("Aligning curves...\n")
    # Object currently in edit mode.
    obj = bpy.context.edit_object

    splines = bpy.context.active_object.data.splines

    spline_is_bezier = False

    if len(splines[0].bezier_points) > 0:
        spline_is_bezier = True

    # For each vert, look up or to the side and find the nearest interpolated gpencil point for this vertex.
    if not spline_is_bezier:
        selected_points = []
        for spline in splines:
            for point in spline.points:
               if point.select:
                   selected_points.append(point)

        points_local_3d = [p.co for p in selected_points]
        points_world_2d = vectors_to_screenpos(context, points_local_3d, obj.matrix_world)

        stroke = gpencil_to_screenpos(context)

        for i, p in enumerate(selected_points):
            nearest_point = get_nearest_interpolated_point_on_stroke(points_world_2d[i], stroke, context)
            # Get new vertex coordinate by converting from 2D screen space to 3D world space. Must multiply depth coordinate
            # with world matrix and then final result by INVERTED world matrix to get a correct final value.
            newcoord = obj.matrix_world.inverted() @ region_to_location(nearest_point, obj.matrix_world @ p.co)
            # Apply the final position using an influence slider.

            newcoord = newcoord.to_4d()
            p.co = p.co.lerp(newcoord, influence)

    if spline_is_bezier:
        selected_bezier_points = []
        for spline in splines:
            for point in spline.bezier_points:
               if point.select_control_point:
                   selected_bezier_points.append(point)

        bezier_points_local_3d = [p.co for p in selected_bezier_points]
        bezier_points_world_2d = vectors_to_screenpos(context, bezier_points_local_3d, obj.matrix_world)

        for i, p in enumerate(selected_bezier_points):
            if p.handle_left_type == 'FREE' or p.handle_left_type == 'ALIGNED' or p.handle_right_type == 'FREE' or p.handle_right_type == 'ALIGNED':
                print("Supported handle modes: 'VECTOR', 'AUTO'. Please convert. Sorry!")
                return{'CANCELLED'}

        stroke = gpencil_to_screenpos(context)

        for i, p in enumerate(selected_bezier_points):
            nearest_point = get_nearest_interpolated_point_on_stroke(bezier_points_world_2d[i], stroke, context)
            newcoord = obj.matrix_world.inverted() @ region_to_location(nearest_point, obj.matrix_world @ p.co)

            p.co = p.co.lerp(newcoord.to_4d(), influence)
            p.handle_left = obj.matrix_world.inverted() @ region_to_location(get_nearest_interpolated_point_on_stroke(p.handle_left, stroke, context), obj.matrix_world @ p.handle_left) 
            p.handle_right = obj.matrix_world.inverted() @ region_to_location(get_nearest_interpolated_point_on_stroke(p.handle_right, stroke, context), obj.matrix_world @ p.handle_right) 


def align_objects(context, influence):
    selected_objs = bpy.context.selected_objects

    stroke = gpencil_to_screenpos(context)

    for i, obj in enumerate(selected_objs):
        obj_loc_2d = vectors_to_screenpos(context, obj.location, obj.matrix_world @ obj.matrix_world.inverted())
        nearest_point = get_nearest_interpolated_point_on_stroke(obj_loc_2d, stroke, context)

        newcoord = region_to_location(nearest_point, obj.location)
        obj.location = obj.location.lerp(newcoord, influence)


def get_nearest_interpolated_point_on_stroke(vertex_2d, points_2d, context):
    # Define variables used for the two different axes (horizontal or vertical).
    # Doing it like this in order to use the same code for both axes.
    if is_vertical(vertex_2d, points_2d):
        a = 1
        b = 0
    if not is_vertical(vertex_2d, points_2d):
        a = 0
        b = 1

    # Variable for nearest point. Set to 9999 in order to guarantee a closer match.
    nearest_distance = 9999.0
    nearest_point = (0, 0)
    point_upper = 0.0
    point_lower = 0.0
    coord_interpolated = 0

    # I have a feeling this is not the best way to do this, but anyway;
    # This bit of code finds (in 2D) the point (on a line) closest to another point.

    # Works by finding the closest in one direction, then the other, then
    # calculating the interpolated position between these two outer points.
    for i, gpoint_2d in enumerate(points_2d):
        # Variables used to find points relative to the current point (i),
        # clamped to avoid out of range errors.
        previous_point = clamp(0, len(points_2d)-1, i - 1)
        next_point = clamp(0, len(points_2d)-1, i + 1)

        # Gets the absolute (non-negative) distance from the
        # current vertex to the current grease pencil point.
        distance = abs(vertex_2d[a] - gpoint_2d[a])

        # If the current gpencil point is the closest so far, calculate
        # everything and push the values to the variables defined earlier.
        if (distance < nearest_distance):
            nearest_distance = distance
            # If the nearest gpoint is ABOVE the current vertex,
            # find the nearest point BELOW as well.
            # TODO: Make this more readable/elegant? It works, so no need, but still.
            if (gpoint_2d[a] >= vertex_2d[a]):
                point_upper = gpoint_2d
                point_lower = points_2d[previous_point]

                # If the lower point is actually above the vertex,
                # we picked the wrong point and need to correct.
                if (point_lower[a] > point_upper[a]) or (point_upper == point_lower):
                    point_lower = points_2d[next_point]
            else:
                # The opposite of the previous lines
                point_lower = gpoint_2d
                point_upper = points_2d[previous_point]
                if (point_upper[a] <= point_lower[a]) or (point_upper == point_lower):
                    point_upper = points_2d[next_point]

            # Define min and max ranges to calculate the interpolated po<int from
            hrange = (point_upper[b], point_lower[b])
            vrange = (point_upper[a], point_lower[a])
            coord_interpolated = map_range(vrange, hrange, vertex_2d[a])

            # Push the interpolated coord to the correct axis
            if a == 1:
                nearest_point = (coord_interpolated, vertex_2d[1])
            if a == 0:
                nearest_point = (vertex_2d[0], coord_interpolated)

    return nearest_point


def get_closest_segment(vertex_2d, points_2d, context):
    if is_vertical(vertex_2d, points_2d):
        a = 1
        b = 0
    if not is_vertical(vertex_2d, points_2d):
        a = 0
        b = 1
    nearest_distance = 9999.0
    nearest_point = (0, 0)
    point_upper = 0.0
    point_lower = 0.0
    coord_interpolated = 0
    for i, gpoint_2d in enumerate(points_2d):
        previous_point = clamp(0, len(points_2d)-1, i - 1)
        next_point = clamp(0, len(points_2d)-1, i + 1)

        distance = abs(vertex_2d[a] - gpoint_2d[a])

        if (distance < nearest_distance):
            nearest_distance = distance
            if (gpoint_2d[a] >= vertex_2d[a]):
                point_upper = gpoint_2d
                point_lower = points_2d[previous_point]
                if (point_lower[a] > point_upper[a]) or (point_upper == point_lower):
                    point_lower = points_2d[next_point]
            else:
                point_lower = gpoint_2d
                point_upper = points_2d[previous_point]
                if (point_upper[a] <= point_lower[a]) or (point_upper == point_lower):
                    point_upper = points_2d[next_point]

    segment = (point_upper, point_lower)
    return segment


def gpencil_to_screenpos(context):
    gp = None

    sceneGP = bpy.context.scene.grease_pencil

    if(check_if_scene_gp_exists(context)):
        gp = sceneGP.layers[-1].active_frame

    if(gp == None):
        points_2d = [(0,0), (0,10)]
    else:
        points_2d = [location_to_region(point.co) for point in gp.strokes[-1].points if (len(gp.strokes) > 0)]
        if bpy.context.preferences.addons[__name__].preferences.clear_strokes:
            gp.strokes.remove(gp.strokes[-1])

    
    return points_2d


def check_if_any_gp_exists(context):
    return check_if_scene_gp_exists(context)


def check_if_scene_gp_exists(context):
    gps = bpy.context.scene.grease_pencil

    if(gps is not None):
        if(len(gps.layers)>0):
            if(len(gps.layers[-1].active_frame.strokes) > 0):
                return True

    return False

def vectors_to_screenpos(context, list_of_vectors, matrix):
    if type(list_of_vectors) is mathutils.Vector:
        return location_to_region(matrix @ list_of_vectors)
    else:
        return [location_to_region(matrix @ vector) for vector in list_of_vectors]


# Generic clamp function
def clamp(a, b, v):
    if (v <= a):
        return a
    elif (v >= b):
        return b
    else:
        return v


# Function for determining if a sequence of 2D
# coordinates form a vertical or horizontal line.
def is_vertical(vertex, list_of_vec2):
    if len(list_of_vec2) == 1:
        if abs(list_of_vec2[0][0] - vertex[0]) > abs(list_of_vec2[0][1] - vertex[1]):
            return True
        else:
            return False

    minval = list(map(min, *list_of_vec2))
    maxval = list(map(max, *list_of_vec2))

    if (maxval[0] - minval[0] > maxval[1] - minval[1]):
        return False
    if (maxval[0] - minval[0] < maxval[1] - minval[1]):
        return True
    

# Generic map range function.
# grabbed from here: www.rosettacode.org/wiki/Map_range
def map_range(fromrange, torange, value):
    (a1, a2), (b1, b2) = fromrange, torange
    # WORKAROUND: If torange start and end is equal, division by zero occurs.
    # A tiny amount is added to one of them to avoid a zero value here.
    if (a1 == a2):
        a2 += 0.0001
    return b1 + ((value - a1) * (b2 - b1) / (a2 - a1))

# Utility functions for converting between 2D and 3D coordinates
def location_to_region(worldcoords):
    out = view3d_utils.location_3d_to_region_2d(bpy.context.region, bpy.context.space_data.region_3d, worldcoords)
    return out


def region_to_location(viewcoords, depthcoords):
    return view3d_utils.region_2d_to_location_3d(bpy.context.region, bpy.context.space_data.region_3d, viewcoords, depthcoords)

classes = (OBJECT_OT_bear_align_to_gpencil,
    UV_OT_bear_align_to_gpencil,
    MESH_OT_bear_align_to_gpencil,
    CURVE_OT_bear_align_to_gpencil,
    ARMATURE_OT_bear_align_to_gpencil,
    PREFS_bear_align_to_gpencil,
    PREFS_OT_rebind)

addon_keymaps = []

def bind_keymap():
    pref = bpy.context.preferences.addons[__name__].preferences
    # If user doesn't want to create default hotkey, we shall not do so
    if not pref.use_default_shortcut:
        return

    # Check if hotkey has already been set, to avoid duplicates when auto creating hotkey
    try:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps["Mesh"]
    except Exception as e:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new("Mesh", space_type='EMPTY', region_type='WINDOW')
        pass

    if "mesh.bear_align_selection_to_gpencil" not in km.keymap_items:
        kmi = km.keymap_items.new(idname="mesh.bear_align_selection_to_gpencil", type=pref.mouse_click , value='DOUBLE_CLICK', any=False, alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift)
        addon_keymaps.append((km, kmi))

    try:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps["Object Mode"]
    except Exception as e:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new("Object Mode", space_type='EMPTY', region_type='WINDOW')
        pass

    if "object.bear_align_selection_to_gpencil" not in km.keymap_items:
        kmi = km.keymap_items.new(idname="object.bear_align_selection_to_gpencil", type=pref.mouse_click , value='DOUBLE_CLICK', any=False, alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift)
        addon_keymaps.append((km, kmi))

    try:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps["UV Editor"]
    except Exception as e:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new("UV Editor", space_type='EMPTY', region_type='WINDOW')
        pass

    if "uv.bear_align_selection_to_gpencil" not in km.keymap_items:
        kmi = km.keymap_items.new(idname="uv.bear_align_selection_to_gpencil", type=pref.mouse_click , value='DOUBLE_CLICK', any=False, alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift)
        addon_keymaps.append((km, kmi))

    try:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps["Armature"]
    except Exception as e:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new("Armature", space_type='EMPTY', region_type='WINDOW')
        pass

    if "armature.bear_align_selection_to_gpencil" not in km.keymap_items:
        kmi = km.keymap_items.new(idname="armature.bear_align_selection_to_gpencil", type=pref.mouse_click , value='DOUBLE_CLICK', any=False, alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift)
        addon_keymaps.append((km, kmi))

    try:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps["Curve"]
    except Exception as e:
        km = bpy.context.window_manager.keyconfigs.addon.keymaps.new("Curve", space_type='EMPTY', region_type='WINDOW')
        pass

    if "curve.bear_align_selection_to_gpencil" not in km.keymap_items:
        kmi = km.keymap_items.new(idname="curve.bear_align_selection_to_gpencil", type=pref.mouse_click , value='DOUBLE_CLICK', any=False, alt=pref.use_alt, ctrl=pref.use_ctrl, shift=pref.use_shift)
        addon_keymaps.append((km, kmi))


def unbind_keymap():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    bind_keymap()
 
 
def unregister():
    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)
    unbind_keymap()
       
        
if __name__ == "__main__":
    register()
