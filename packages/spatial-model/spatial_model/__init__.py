"""M2 空间计算纯函数库（D-029）：距离/最近排序/连通性——场景无关，无 IO。"""

from .geometry import connected_components, distance_2d, sort_nearest

__all__ = ["connected_components", "distance_2d", "sort_nearest"]
