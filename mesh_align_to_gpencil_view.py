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
    "description": "Aligns selected vertices to the last drawn gpencil stroke. Only horizontal or vertical alignment for now.",
    "author": "Bjørnar Frøyse",
    "version": (1, 0, 1),
    "blender": (2, 7, 0),
    "location": "Tool Shelf",
    "warning": "",  # used for warning icon and text in addons panel
    "wiki_url": "",
    "tracker_url": "",
    "category": "Mesh"}


import bpy
from bpy_extras import view3d_utils
import bmesh
from bpy.props import FloatProperty, BoolProperty


# Preferences for the addon (Displayed "inside" the addon in user preferences)
class AlignVertsToGpencilAddonPrefs(bpy.types.AddonPreferences):
    bl_idname = __name__
    clear_strokes = bpy.props.BoolProperty(
            name = "Clear Strokes On Execute",
            description = "Clear grease pencil strokes after executing.",
            default = False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "clear_strokes")
        if(self.clear_strokes):
            layout.label(text="Clearing strokes will make the influence slider stop working!", icon="ERROR")


class AlignVertsToGpencil(bpy.types.Operator):
    """Aligns selection to gpencil stroke"""
    bl_idname = "mesh.align_verts_to_gpencil"
    bl_label = "Align Verts to Gpencil"
    bl_options = {'REGISTER', 'UNDO'}

    influence = FloatProperty(
            name="Influence",
            description="Influence",
            min=0.0, max=1.0,
            default=1.0,
            )

    def execute(self, context):
        # Last drawn gpencil stroke.
        gps = bpy.data.grease_pencil[-1].layers[-1].active_frame
        # Object currently in edit mode.
        obj = bpy.context.edit_object
        # Object's mesh datablock.
        me = obj.data
        # Convert mesh data to bmesh.
        bm = bmesh.from_edit_mesh(me)

        # Get all selected vertices (in their local space).
        verts_local_3d = [v for v in bm.verts if v.select]

        # Convert selected vertices' positions to 2D screen space.
        # IMPORTANT: Multiply vertex coordinates with the world matrix to get their WORLD position, not local position. 
        verts_world_2d = [location_to_region(obj.matrix_world * v.co) for v in verts_local_3d]

        # Convert gpencil points to 2D screen space
        points_2d = [location_to_region(point.co) for point in gps.strokes[-1].points if (len(gps.strokes) > 0)]

        # For each vert, look up or to the side and find the nearest interpolated gpencil point for this vertex.
        for i, v in enumerate(verts_local_3d):
            nearest_point = get_nearest_interpolated_point_on_stroke(verts_world_2d[i], points_2d, context)
            # Get new vertex coordinate by converting from 2D screen space to 3D world space. Must multiply depth coordinate
            # with world matrix and then final result by INVERTED world matrix to get a correct final value.
            newcoord = obj.matrix_world.inverted() * region_to_location(nearest_point, obj.matrix_world * v.co)
            # Apply the final position using an influence slider.
            v.co = v.co.lerp(newcoord, self.influence)

        # Recalculate mesh normals (so lighting looks right).
        for edge in bm.edges:
            edge.normal_update()

        # Push bmesh changes back to the actual mesh datablock.
        bmesh.update_edit_mesh(me, True)

        # If option ticked in settings, clear gpencil stroke after finishing up.
        if context.user_preferences.addons[__name__].preferences.clear_strokes:
            gps.clear()

        # All done!
        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        if len(bpy.data.grease_pencil[-1].layers) is 0:
            return False
        elif bpy.data.grease_pencil[-1].layers[-1].active_frame is None:
            return False
        elif len(bpy.data.grease_pencil[-1].layers[-1].active_frame.strokes) is 0:
            return False
        else:
            return True


def get_nearest_interpolated_point_on_stroke(vertex_2d, points_2d, context):
    # TODO: Make it able to project the selected vertices onto a surface (for retopo).
    # TODO: Option to lock axis?
    # TODO: More flexible "projection"? Currently only vertical & horizontal.
    #       Works in most cases, but can easily break.
    # TODO: Make it work with the mesh.use_mirror_x setting.

    # Define variables used for the two different axes (horizontal or vertical).
    # Doing it like this in order to use the same code for both axes.
    if is_vertical(points_2d, vertex_2d):
        a = 1
        b = 0
    if not is_vertical(points_2d, vertex_2d):
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

            # Define min and max ranges to calculate the interpolated point from
            hrange = (point_upper[b], point_lower[b])
            vrange = (point_upper[a], point_lower[a])
            coord_interpolated = map_range(vrange, hrange, vertex_2d[a])

            # Push the interpolated coord to the correct axis
            if a == 1:
                nearest_point = (coord_interpolated, vertex_2d[1])
            if a == 0:
                nearest_point = (vertex_2d[0], coord_interpolated)

    return nearest_point


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
def is_vertical(list_of_vec2, vertex):
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
        a2 += 0.001
    return  b1 + ((value - a1) * (b2 - b1) / (a2 - a1))


import bpy_extras


# Utility functions for converting between 2D and 3D coordinates
def location_to_region(worldcoords):
    return bpy_extras.view3d_utils.location_3d_to_region_2d(bpy.context.region, bpy.context.space_data.region_3d, worldcoords)


def region_to_location(viewcoords, depthcoords):
    return bpy_extras.view3d_utils.region_2d_to_location_3d(bpy.context.region, bpy.context.space_data.region_3d, viewcoords, depthcoords)


class AlignVertsToGpencilBUTTON(bpy.types.Panel):
    bl_category = "Tools"
    bl_label = "Gpencil Align"
    bl_space_type = "VIEW_3D"
    bl_region_type = "TOOLS"
    bl_context = "mesh_edit"

    def draw(self, context):
        layout = self.layout
        layout.operator("mesh.align_verts_to_gpencil")


def register():
    bpy.utils.register_class(AlignVertsToGpencilAddonPrefs)
    bpy.utils.register_class(AlignVertsToGpencil)
    bpy.utils.register_class(AlignVertsToGpencilBUTTON)


def unregister():
    bpy.utils.unregister_class(AlignVertsToGpencilAddonPrefs)
    bpy.utils.unregister_class(AlignVertsToGpencil)
    bpy.utils.unregister_class(AlignVertsToGpencilBUTTON)

if __name__ == "__main__":
    register()
