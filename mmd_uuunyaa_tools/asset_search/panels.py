# -*- coding: utf-8 -*-
# Copyright 2021 UuuNyaa <UuuNyaa@gmail.com>
# This file is part of MMD UuuNyaa Tools.

import functools
import time
from enum import Enum
from typing import List, Set, Union

import bpy
import bpy.utils.previews
from mmd_uuunyaa_tools.asset_search.assets import ASSETS, AssetDescription
from mmd_uuunyaa_tools.asset_search.cache import CONTENT_CACHE, Content, Task
from mmd_uuunyaa_tools.utilities import label_multiline, to_human_friendly_text, to_int32


class AssetState(Enum):
    INITIALIZED = 0
    DOWNLOADING = 1
    CACHED = 2
    EXTRACTED = 3
    FAILED = 4
    UNKNOWN = -1


class Utilities:
    @staticmethod
    def is_importable(asset: AssetDescription) -> bool:
        return (
            ASSETS.is_extracted(asset.id)
            or
            CONTENT_CACHE.try_get_content(asset.download_url) is not None
        )

    @staticmethod
    def get_asset_state(asset: AssetDescription) -> (AssetState, Union[Content, None], Union[Task, None]):
        if ASSETS.is_extracted(asset.id):
            return (AssetState.EXTRACTED, None, None)

        content = CONTENT_CACHE.try_get_content(asset.download_url)
        if content is not None:
            if content.state is Content.State.CACHED:
                return (AssetState.CACHED, content, None)

            if content.state is Content.State.FAILED:
                return (AssetState.FAILED, content, None)

        else:
            task = CONTENT_CACHE.try_get_task(asset.download_url)
            if task is None:
                return (AssetState.INITIALIZED, None, None)

            elif task.state in {Task.State.QUEUING, Task.State.RUNNING}:
                return (AssetState.DOWNLOADING, None, task)

        return (AssetState.UNKNOWN, None, None)

    @staticmethod
    def resolve_path(asset: AssetDescription) -> str:
        return ASSETS.resolve_path(asset.id)


class AddAssetThumbnail(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.add_asset_thumbnail'
    bl_label = 'Add Asset Item'
    bl_options = {'INTERNAL'}

    asset_id: bpy.props.StringProperty()
    update_time: bpy.props.IntProperty()

    def execute(self, context):
        search_result = context.scene.mmd_uuunyaa_tools_asset_search.result
        if search_result.update_time != self.update_time:
            return {'FINISHED'}

        asset_item = search_result.asset_items.add()
        asset_item.id = self.asset_id
        return {'FINISHED'}


class AssetSearch(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.asset_search'
    bl_label = 'Search Asset'
    bl_options = {'INTERNAL'}

    def _on_thumbnail_fetched(self, context, region, update_time, asset, content):
        search_result = context.scene.mmd_uuunyaa_tools_asset_search.result
        if search_result.update_time != update_time:
            return

        asset_item = search_result.asset_items.add()
        asset_item.id = asset.id

        global PREVIEWS
        if asset.id not in PREVIEWS:
            PREVIEWS.load(asset.id, content.filepath, 'IMAGE')

        region.tag_redraw()

    def execute(self, context):
        max_search_result_count = 50

        query = context.scene.mmd_uuunyaa_tools_asset_search.query
        query_type = query.type
        query_text = query.text.lower()
        query_tags = query.tags
        query_is_cached = query.is_cached

        enabled_tag_names = {tag.name for tag in query_tags if tag.enabled}
        enabled_tag_count = len(enabled_tag_names)

        search_results: List[AssetDescription] = []
        search_results = [
            asset for asset in ASSETS.values() if (
                query_type == asset.type.name
                and enabled_tag_count == len(asset.tag_names & enabled_tag_names)
                and query_text in asset.keywords
                and (Utilities.is_importable(asset) if query_is_cached else True)
            )
        ]

        hit_count = len(search_results)
        update_time = to_int32(time.time_ns() >> 10)
        result = context.scene.mmd_uuunyaa_tools_asset_search.result
        result.count = min(max_search_result_count, hit_count)
        result.hit_count = hit_count
        result.asset_items.clear()
        result.update_time = update_time

        for asset in search_results[:max_search_result_count]:
            CONTENT_CACHE.async_get_content(
                asset.thumbnail_url,
                functools.partial(self._on_thumbnail_fetched, context, context.region, update_time, asset)
            )

        return {'FINISHED'}


class AssetDownload(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.asset_download'
    bl_label = 'Download Asset'
    bl_options = {'INTERNAL'}

    asset_id: bpy.props.StringProperty()

    def __on_fetched(self, context, asset, content):
        print(f'done: {asset.name}, {asset.id}, {content.state}, {content.id}')

    def execute(self, context):
        print(f'do: {self.bl_idname}, {self.asset_id}')
        asset = ASSETS[self.asset_id]
        CONTENT_CACHE.async_get_content(asset.download_url, functools.partial(self.__on_fetched, context, asset))
        return {'FINISHED'}


class AssetDownloadCancel(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.asset_download_cancel'
    bl_label = 'Download Cancel Asset'
    bl_options = {'INTERNAL'}

    asset_id: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return False

    def execute(self, context):
        print(f'do: {self.bl_idname}')
        return {'FINISHED'}


class AssetImport(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.asset_import'
    bl_label = 'Import Asset'
    bl_options = {'INTERNAL'}

    asset_id: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        print(f'do: {self.bl_idname}')

        asset = ASSETS[self.asset_id]
        content = CONTENT_CACHE.try_get_content(asset.download_url)
        ASSETS.execute_import_action(asset.id, content.filepath if content is not None else None)

        return {'FINISHED'}


class AssetDetailPopup(bpy.types.Operator):
    bl_idname = 'mmd_uuunyaa_tools.asset_detail_popup'
    bl_label = 'Popup Asset Detail'
    bl_options = {'INTERNAL'}

    asset_id: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        print(f'do: {self.bl_idname}')
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_popup(self, width=600)

    def draw(self, context):
        asset = ASSETS[self.asset_id]

        layout = self.layout

        def draw_titled_label(layout, title, text, split_factor=0.11):
            split = layout.split(factor=split_factor)
            split.alignment = 'RIGHT'
            split.label(text=title)
            label_multiline(split.column(align=True), text=text, width=int(600*(1-split_factor)))

        self.asset_name = asset.name

        col = layout.column(align=True)
        draw_titled_label(col, title='Name:', text=asset.name)
        draw_titled_label(col, title='Aliases:', text=', '.join([p for p in asset.aliases.values()]))
        draw_titled_label(col, title='Tags:', text=asset.tags_text())
        draw_titled_label(col, title='Updated at:', text=asset.updated_at.strftime('%Y-%m-%d %H:%M:%S %Z'))
        draw_titled_label(col, title='Note:', text=asset.note)

        (asset_state, content, task) = Utilities.get_asset_state(asset)

        if asset_state is AssetState.INITIALIZED:
            layout.operator(AssetDownload.bl_idname, text='Download', icon='TRIA_DOWN_BAR').asset_id = asset.id

        elif asset_state is AssetState.DOWNLOADING:
            draw_titled_label(layout, title='Cache:', text=f'Downloading {to_human_friendly_text(task.fetched_size)}B / {to_human_friendly_text(task.content_length)}B')
            layout.operator(AssetDownloadCancel.bl_idname, text='Cancel', icon='CANCEL').asset_id = asset.id

        elif asset_state is AssetState.CACHED:
            draw_titled_label(col, title='Cache:', text=f'{content.filepath}\n{to_human_friendly_text(content.length)}B   ({content.type})')
            layout.operator(AssetImport.bl_idname, text='Import', icon='IMPORT').asset_id = asset.id

        elif asset_state is AssetState.EXTRACTED:
            draw_titled_label(col, title='Path:', text=f'{Utilities.resolve_path(asset)}')
            layout.operator(AssetImport.bl_idname, text='Import', icon='IMPORT').asset_id = asset.id

        elif asset_state is AssetState.FAILED:
            layout.operator(AssetDownload.bl_idname, text='Retry', icon='FILE_REFRESH').asset_id = asset.id

        else:
            layout.operator(AssetDownload.bl_idname, text='Retry', icon='FILE_REFRESH').asset_id = asset.id


class AssetSearchQueryTags(bpy.types.UIList):
    bl_idname = 'UUUNYAA_UL_mmd_uuunyaa_tools_asset_search_query_tags'

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        layout.prop(item, 'enabled', text=item.name, index=index)


class AssetSearchPanel(bpy.types.Panel):
    bl_idname = 'UUUNYAA_PT_mmd_uuunyaa_tools_asset_search'
    bl_label = 'UuuNyaa Asset Search'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MMD'

    def draw(self, context):
        search = context.scene.mmd_uuunyaa_tools_asset_search
        query = search.query
        layout = self.layout

        layout.prop(query, 'type', text='Asset type')
        layout.prop(query, 'text', text='Query', icon='VIEWZOOM')
        if query.tags is not None:
            col = layout.column()
            row = col.row()
            row.label(text='Tags:')
            row = row.row()
            row.alignment = 'RIGHT'
            row.prop(query, 'is_cached', text='Cached')
            col.template_list(AssetSearchQueryTags.bl_idname, '', query, 'tags', query, 'tags_index', type='GRID', columns=3, rows=2)
            row = col.row()

        row = layout.row()
        row.alignment = 'RIGHT'
        row.label(text=f'{search.result.count} of {search.result.hit_count} results')

        asset_items = context.scene.mmd_uuunyaa_tools_asset_search.result.asset_items

        global PREVIEWS

        grid = layout.grid_flow(row_major=True)
        for asset_item in asset_items:
            asset = ASSETS[asset_item.id]
            (asset_state, _, _) = Utilities.get_asset_state(asset)

            if asset_state is AssetState.INITIALIZED:
                icon = 'NONE'
            elif asset_state is AssetState.DOWNLOADING:
                icon = 'SORTTIME'
            elif asset_state is AssetState.CACHED:
                icon = 'SOLO_OFF'
            elif asset_state is AssetState.EXTRACTED:
                icon = 'SOLO_ON'
            elif asset_state is AssetState.FAILED:
                icon = 'SORTTIME'
            else:
                icon = 'ERROR'

            box = grid.box().column(align=True)
            box.template_icon(PREVIEWS[asset.id].icon_id, scale=6.0)
            box.operator(AssetDetailPopup.bl_idname, text=asset.name, icon=icon).asset_id = asset.id

        if search.result.count > len(asset_items):
            row = layout.row()
            row.alignment = 'CENTER'
            row.label(text='Loading...')
            return

    @staticmethod
    def register():
        global PREVIEWS
        PREVIEWS = bpy.utils.previews.new()

    @staticmethod
    def unregister():
        global PREVIEWS
        if PREVIEWS is not None:
            bpy.utils.previews.remove(PREVIEWS)