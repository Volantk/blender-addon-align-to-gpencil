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
    "name": "Align Selection To Gpencil Stroke",
    "description": "Aligns selection to a grease pencil stroke. Hold SHIFT and double-click LEFT MOUSE to execute.",
    "author": "Bjørnar Frøyse",
    "version": (1, 0, 8),
    "blender": (2, 7, 0),
    "location": "Tool Shelf",
    "warning": "",  # used for warning icon and text in addons panel
    "wiki_url": "",
    "tracker_url": "",
    "category": "Mesh"}


import bpy
from bpy_extras import view3d_utils
import bmesh
import mathutils
from bpy.props import FloatProperty, BoolProperty
import math


# Preferences for the addon (Displayed "inside" the addon in user preferences)
class AlignSelectionToGpencilAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    clear_strokes = bpy.props.BoolProperty(
            name = "Clear Strokes On Execute",
            description = "Clear grease pencil strokes after executing",
            default = False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "clear_strokes")
        if(self.clear_strokes):
            layout.label(text="Be warned: This will currently make the influence slider stop working", icon="ERROR")


class AlignUVsToGpencil(bpy.types.Operator):
    """Aligns UV selection to gpencil stroke"""
    bl_idname = "bear.uv_align_to_gpencil"
    bl_label = "Align UV Verts to Gpencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence = FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        align_uvs(context, self.influence)
        return {'FINISHED'}


def align_uvs(context, influence):
    uvGP = bpy.context.area.spaces[0].grease_pencil

    ok = False
    if(uvGP is not None):
        if(len(uvGP.layers)>0):
            if(len(uvGP.layers[-1].active_frame.strokes) > 0):
                ok = True
    if(ok == False):
        return

    gp = uvGP.layers[-1].active_frame
    obj = bpy.context.edit_object
    me = obj.data
    bm = bmesh.from_edit_mesh(me)

    uv_layer = bm.loops.layers.uv.verify()
    bm.faces.layers.tex.verify()

    selected_uv_verts = []
    for f in bm.faces:
        for l in f.loops:
            l_uv = l[uv_layer]
            if l_uv.select:
                selected_uv_verts.append(l_uv)

    selected_uv_verts_positions = []
    for vert in selected_uv_verts:
        selected_uv_verts_positions.append(vert.uv)

    gpencil_points = [point.co for point in gp.strokes[-1].points]

    for i, v in enumerate(selected_uv_verts):
        nearest_point = get_nearest_interpolated_point_on_stroke(selected_uv_verts_positions[i], gpencil_points, context)
        v.uv = v.uv.lerp(nearest_point, influence)

    bmesh.update_edit_mesh(me, True)

    if context.user_preferences.addons[__name__].preferences.clear_strokes:
       gp.strokes.remove(gp.strokes[-1])


class AlignSelectionToGPencil(bpy.types.Operator):
    """Aligns selection to gpencil stroke"""
    bl_idname = "bear.align_to_gpencil"
    bl_label = "Align Verts to Gpencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence = FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):

        # TODO: Make it able to project the selected vertices onto a surface (for retopo).
        # TODO: Option to lock axis?
        # TODO: More flexible "projection"? Currently only vertical & horizontal.
        #       Works in most cases, but can easily break.
        # TODO: Make it work with the mesh.use_mirror_x setting.
        # TODO: Proportional editing
        # TODO: Support for bones (pose mode)

        # Object mode
        if bpy.context.mode == 'OBJECT':
            align_objects(context, self.influence)
            return {'FINISHED'}

        # Edit mode (vertices)
        if bpy.context.active_object.type == 'MESH' and bpy.context.active_object.data.is_editmode:
            align_vertices(context, self.influence)
            return {'FINISHED'}

        # Curves
        if bpy.context.active_object.type == 'CURVE' and bpy.context.active_object.data.is_editmode:
            align_curves(context, self.influence)
            return {'FINISHED'}

        # Bone edit mode
        if bpy.context.active_object.type == 'ARMATURE' and bpy.context.active_object.data.is_editmode:
            align_bones_editmode(context, self.influence)
            return {'FINISHED'}

        print("No valid cases found. Try again with another selection!")
        return{'FINISHED'}

    @classmethod
    def poll(cls, context):
        return check_if_any_gp_exists(context)

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
        newcoord_for_head = obj.matrix_world.inverted() * region_to_location(nearest_point_for_head, obj.matrix_world * bone.head)
        bone.head = bone.head.lerp(newcoord_for_head, influence)

        nearest_point_for_tail = get_nearest_interpolated_point_on_stroke(bone_tails_2d[i], stroke, context)
        newcoord_for_tail = obj.matrix_world.inverted() * region_to_location(nearest_point_for_tail, obj.matrix_world * bone.tail)
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
        newcoord = obj.matrix_world.inverted() * region_to_location(nearest_point, obj.matrix_world * v.co)
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
            newcoord = obj.matrix_world.inverted() * region_to_location(nearest_point, obj.matrix_world * p.co)
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

        stroke = gpencil_to_screenpos(context)

        for i, p in enumerate(selected_bezier_points):
            nearest_point = get_nearest_interpolated_point_on_stroke(bezier_points_world_2d[i], stroke, context)
            newcoord = obj.matrix_world.inverted() * region_to_location(nearest_point, obj.matrix_world * p.co)
            if p.handle_left_type == 'FREE' or p.handle_left_type == 'ALIGNED' or p.handle_right_type == 'FREE' or p.handle_right_type == 'ALIGNED':
                print("Supported handle modes: 'VECTOR', 'AUTO'. Please convert. Sorry!")
                return{'CANCELLED'}

            p.co = p.co.lerp(newcoord.to_4d(), influence)
            p.handle_left = obj.matrix_world.inverted() * region_to_location(get_nearest_interpolated_point_on_stroke(p.handle_left, stroke, context), obj.matrix_world * p.handle_left) 
            p.handle_right = obj.matrix_world.inverted() * region_to_location(get_nearest_interpolated_point_on_stroke(p.handle_right, stroke, context), obj.matrix_world * p.handle_right) 


def align_objects(context, influence):
    selected_objs = bpy.context.selected_objects

    stroke = gpencil_to_screenpos(context)

    for i, obj in enumerate(selected_objs):
        obj_loc_2d = vectors_to_screenpos(context, obj.location, obj.matrix_world * obj.matrix_world.inverted())
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
    gp = 0

    sceneGP = bpy.context.scene.grease_pencil
    objectGP = bpy.context.active_object.grease_pencil

    if(check_if_scene_gp_exists(context)):
        gp = sceneGP.layers[-1].active_frame
    elif(check_if_object_gp_exists(context)):
        gp = objectGP.layers[-1].active_frame

    if(gp == 0):
        points_2d = [(0,0), (0,10)]
    else:
        points_2d = [location_to_region(point.co) for point in gp.strokes[-1].points if (len(gp.strokes) > 0)]
        if context.user_preferences.addons[__name__].preferences.clear_strokes:
            gp.strokes.remove(gp.strokes[-1])

    
    return points_2d

def check_if_any_gp_exists(context):
    if(check_if_object_gp_exists(context)):
        return True
    elif(check_if_scene_gp_exists(context)):
        return True
    else:
        return False


def check_if_object_gp_exists(context):
    objectGP = bpy.context.active_object.grease_pencil

    if(objectGP is not None):
        if(len(objectGP.layers)>0):
            if(len(objectGP.layers[-1].active_frame.strokes) > 0):
                return True

    return False


def check_if_scene_gp_exists(context):
    sceneGP = bpy.context.scene.grease_pencil

    if(sceneGP is not None):
        if(len(sceneGP.layers)>0):
            if(len(sceneGP.layers[-1].active_frame.strokes) > 0):
                return True

    return False

def vectors_to_screenpos(context, list_of_vectors, matrix):
    if type(list_of_vectors) is mathutils.Vector:
        return location_to_region(matrix * list_of_vectors)
    else:
        return [location_to_region(matrix * vector) for vector in list_of_vectors]


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


class AlignSelectionToGpencilBUTTON(bpy.types.Panel):
    bl_category = "Tools"
    bl_label = "Gpencil Align"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"

    def draw(self, context):
        layout = self.layout
        layout.operator("bear.align_to_gpencil")

class AlignUVsToGpencilBUTTON(bpy.types.Panel):
    bl_category = "Tools"
    bl_label = "Gpencil Align"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = "TOOLS"

    def draw(self, context):
        layout = self.layout
        layout.operator("bear.uv_align_to_gpencil")


classes = [AlignSelectionToGpencilAddonPrefs, AlignSelectionToGPencil, AlignSelectionToGpencilBUTTON, AlignUVsToGpencil, AlignUVsToGpencilBUTTON]
addon_keymaps = []

def register():
    for c in classes:
        bpy.utils.register_class(c)

    km = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new("bear.align_to_gpencil", 'LEFTMOUSE', 'DOUBLE_CLICK', False, True)
    addon_keymaps.append((km, kmi))

    km = bpy.context.window_manager.keyconfigs.addon.keymaps.new(name='UV Editor', space_type='IMAGE_EDITOR')
    kmi = km.keymap_items.new("bear.uv_align_to_gpencil", 'LEFTMOUSE', 'DOUBLE_CLICK', False, True)
    addon_keymaps.append((km, kmi))


def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    for c in reversed(classes):
        bpy.utils.unregister_class(c)


if __name__ == "__main__":
    register()
