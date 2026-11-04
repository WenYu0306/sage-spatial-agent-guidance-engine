"""M2 纯函数库测试（D-029 重定位后的真实消费者契约）。"""

from spatial_model import connected_components, distance_2d, sort_nearest


def test_distance_2d():
    assert distance_2d((0, 0), (3, 4)) == 5.0


def test_sort_nearest_no_position_keeps_order():
    items = [{"id": 1, "floor_id": 2, "x": 1, "y": 1}, {"id": 2, "floor_id": 2, "x": 2, "y": 2}]
    assert sort_nearest(items, None) == items


def test_sort_nearest_same_floor_first():
    items = [
        {"id": 1, "floor_id": 3, "x": 610, "y": 410},   # 跨层但平面近
        {"id": 2, "floor_id": 2, "x": 900, "y": 400},   # 同层但平面远
    ]
    out = sort_nearest(items, (600, 400), here_floor=2, cross_floor_penalty=1e9)
    assert out[0]["id"] == 2, "同层优先"
    # 惩罚可调：跨层不被隐藏
    out2 = sort_nearest(items, (600, 400), here_floor=2, cross_floor_penalty=1.0)
    assert out2[0]["id"] == 1


def test_connected_components_detects_islands():
    nodes = [(1, 0, 0), (2, 1, 0), (3, 9, 9)]
    edges = [(1, 2)]
    comps = connected_components(nodes, edges)
    sizes = sorted(len(c) for c in comps)
    assert sizes == [1, 2], "孤立节点自成一份量（孤岛检测）"
