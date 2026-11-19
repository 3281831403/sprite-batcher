"""精灵批处理的核心接口。

精灵统一使用内联四字段字典::

    {"texture": <hashable>, "z": <finite float>,
     "blend": "opaque" | "alpha", "verts": <positive int>}

约定：

* ``verts`` 是顶点数，也是图集页面积占用的计量单位（1 顶点 = 1 面积单位），
  以保持精灵的四字段接口不变。
* 所有浮点比较（z、面积累计）统一使用 ``EPS = 1e-6`` 容差。
* 非法输入、非法上限、单精灵超过 ``max_vertices`` 时抛出 ``BatchError``，
  不得静默丢弃精灵或返回半成品。
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

# 浮点比较容差。
EPS = 1e-6

# merge_compatible 使用的默认硬件顶点上限。
MAX_VERTICES = 4096

_VALID_BLENDS = ("opaque", "alpha")


class BatchError(Exception):
    """批处理输入非法、上限非法或存在无法装入批次的精灵。"""


def _validate_sprite(sprite: object, index: object = "?") -> Mapping[str, object]:
    """校验单个精灵的四字段结构，非法时抛 ``BatchError``。"""
    if not isinstance(sprite, Mapping):
        raise BatchError(f"精灵 {index} 不是映射: {sprite!r}")
    missing = {"texture", "z", "blend", "verts"} - set(sprite)
    if missing:
        raise BatchError(f"精灵 {index} 缺少字段: {sorted(missing)}")

    texture = sprite["texture"]
    try:
        hash(texture)
    except TypeError:
        raise BatchError(f"精灵 {index} 的 texture 不可哈希: {texture!r}") from None

    z = sprite["z"]
    if (
        isinstance(z, bool)
        or not isinstance(z, (int, float))
        or not math.isfinite(z)
    ):
        raise BatchError(f"精灵 {index} 的 z 必须是有限浮点数: {z!r}")

    blend = sprite["blend"]
    if blend not in _VALID_BLENDS:
        raise BatchError(f"精灵 {index} 的 blend 非法: {blend!r}")

    verts = sprite["verts"]
    if isinstance(verts, bool) or not isinstance(verts, int) or verts <= 0:
        raise BatchError(f"精灵 {index} 的 verts 必须是正整数: {verts!r}")

    return sprite


def _validate_sprites(
    sprites: Sequence[Mapping[str, object]],
) -> Sequence[Mapping[str, object]]:
    if isinstance(sprites, (str, bytes)) or not isinstance(sprites, Sequence):
        raise BatchError(f"sprites 必须是序列: {type(sprites).__name__}")
    for index, sprite in enumerate(sprites):
        _validate_sprite(sprite, index)
    return sprites


def _validate_max_vertices(max_vertices: int) -> int:
    if (
        isinstance(max_vertices, bool)
        or not isinstance(max_vertices, int)
        or max_vertices <= 0
    ):
        raise BatchError(f"max_vertices 必须是正整数: {max_vertices!r}")
    return max_vertices


def build_batches(
    sprites: Sequence[Mapping[str, object]], max_vertices: int
) -> list[list[int]]:
    """按纹理与混合模式分组，并把每组切成不超过顶点上限的批次。

    * ``sprites`` 为精灵序列，返回值中的整数是精灵在 ``sprites`` 中的下标。
    * ``max_vertices`` 必须是正整数；每个批次满足
      ``sum(sprite["verts"] for sprite in batch) <= max_vertices``。
    * 分组键为 ``(texture, blend)``，分组顺序取该键首次出现的顺序；组内保持
      输入顺序。空输入返回 ``[]``。
    * ``max_vertices <= 0``、精灵字段非法，或单个精灵的 ``verts`` 已超过
      ``max_vertices`` 时抛 ``BatchError``，不得静默丢弃。
    * 浮点比较使用 ``1e-6`` 容差。
    """
    _validate_max_vertices(max_vertices)
    _validate_sprites(sprites)

    # 先整体校验单精灵上限，任何超限都直接报错，不产出半成品。
    for index, sprite in enumerate(sprites):
        if sprite["verts"] > max_vertices:
            raise BatchError(
                f"精灵 {index} 的 verts={sprite['verts']} 超过上限 {max_vertices}"
            )

    groups: dict[tuple, list[int]] = {}
    for index, sprite in enumerate(sprites):
        key = (sprite["texture"], sprite["blend"])
        groups.setdefault(key, []).append(index)

    batches: list[list[int]] = []
    for indices in groups.values():
        current: list[int] = []
        current_verts = 0
        for index in indices:
            verts = sprites[index]["verts"]
            if current and current_verts + verts > max_vertices + EPS:
                batches.append(current)
                current = []
                current_verts = 0
            current.append(index)
            current_verts += verts
        if current:
            batches.append(current)
    return batches


def sort_key(sprite: Mapping[str, object]) -> tuple:
    """返回稳定排序键：不透明按 z 升序，透明按 z 降序。

    不透明精灵返回 ``(0, z)``，透明精灵返回 ``(1, -z)``，因此
    ``sorted(sprites, key=sort_key)`` 会先画不透明层、再画透明层。相同 z 的
    精灵必须得到相同的 key，依靠 Python 稳定排序保留输入相对顺序；不得在
    key 中加入 id、下标等 tie-breaker。z 必须是有限 float，blend 非法时抛
    ``BatchError``。浮点比较使用 ``1e-6`` 容差。
    """
    _validate_sprite(sprite)
    z = float(sprite["z"])
    if sprite["blend"] == "opaque":
        return (0, z)
    return (1, -z)


def assign_pages(
    sprites: Sequence[Mapping[str, object]], page_capacity: float
) -> dict:
    """按面积把精灵装入图集页。

    返回 ``{"pages": {page_id: [sprite_idx, ...]}, "overflow": [...]}``：

    * ``page_capacity`` 是每页面积上限，面积单位与 ``verts`` 相同（1 顶点 =
      1 面积单位）；精灵按输入顺序装入当前页，放不下时从 0 开始新开一页。
    * ``page_id`` 从 0 连续递增；每个精灵至多出现一次，页内保持输入顺序。
    * 单个精灵的面积超过容量时放入 ``overflow``，不抛异常，也不影响其他精灵
      的分页。``overflow`` 按输入顺序保存下标。
    * ``page_capacity <= 0`` 或精灵非法时抛 ``BatchError``；累计面积及浮点
      比较使用 ``1e-6`` 容差。
    """
    if (
        isinstance(page_capacity, bool)
        or not isinstance(page_capacity, (int, float))
        or not math.isfinite(page_capacity)
        or page_capacity <= 0
    ):
        raise BatchError(f"page_capacity 必须是正数: {page_capacity!r}")
    _validate_sprites(sprites)

    pages: dict[int, list[int]] = {}
    overflow: list[int] = []
    page_id = 0
    used = 0.0
    current: list[int] = []

    for index, sprite in enumerate(sprites):
        area = float(sprite["verts"])
        if area > page_capacity + EPS:
            overflow.append(index)
            continue
        if current and used + area > page_capacity + EPS:
            pages[page_id] = current
            page_id += 1
            current = []
            used = 0.0
        current.append(index)
        used += area

    if current:
        pages[page_id] = current

    return {"pages": pages, "overflow": overflow}


def merge_compatible(a: Mapping[str, object], b: Mapping[str, object]) -> bool:
    """判断两个精灵（或同形批描述）是否可以合并。

    当且仅当 ``texture`` 相同、``blend`` 相同，且两者 ``verts`` 之和不超过
    ``MAX_VERTICES`` 时返回 ``True``，否则返回 ``False``。三个条件缺一不可。
    本函数不修改输入；z 不参与合并判断。输入非法时抛 ``BatchError``，浮点
    比较使用 ``1e-6`` 容差。
    """
    _validate_sprite(a, "a")
    _validate_sprite(b, "b")
    if a["texture"] != b["texture"]:
        return False
    if a["blend"] != b["blend"]:
        return False
    return a["verts"] + b["verts"] <= MAX_VERTICES + EPS


def interleave_alpha(groups: Sequence[Mapping[str, object]]) -> list[int]:
    """把交错的有序组稳定重排成一条绘制序列。

    ``groups`` 是若干 ``{"blend": "opaque" | "alpha", "indices": [int, ...]}``
    组。返回扁平 ``list[int]``：先按组的输入顺序连接所有 opaque 组，再按组的
    输入顺序连接所有 alpha 组。每个组内部、以及同 blend 组之间的相对顺序
    必须保持不变，从而透明与非透明交错输入时不会出现穿插。空 ``groups``
    返回 ``[]``；blend 非法或组结构非法时抛 ``BatchError``。
    """
    if isinstance(groups, (str, bytes)) or not isinstance(groups, Sequence):
        raise BatchError(f"groups 必须是序列: {type(groups).__name__}")

    opaque: list[int] = []
    alpha: list[int] = []
    for position, group in enumerate(groups):
        if not isinstance(group, Mapping) or "blend" not in group or "indices" not in group:
            raise BatchError(f"组 {position} 结构非法: {group!r}")
        blend = group["blend"]
        if blend not in _VALID_BLENDS:
            raise BatchError(f"组 {position} 的 blend 非法: {blend!r}")
        indices = group["indices"]
        if isinstance(indices, (str, bytes)) or not isinstance(indices, Sequence):
            raise BatchError(f"组 {position} 的 indices 必须是序列: {indices!r}")
        for item in indices:
            if isinstance(item, bool) or not isinstance(item, int):
                raise BatchError(f"组 {position} 的索引必须是整数: {item!r}")
        target = opaque if blend == "opaque" else alpha
        target.extend(indices)
    return opaque + alpha


def estimate_draws(batches: Sequence[Sequence[int]]) -> int:
    """返回 draw call 数：每个非空批次计一次，空批次不计。"""
    if isinstance(batches, (str, bytes)) or not isinstance(batches, Sequence):
        raise BatchError(f"batches 必须是序列: {type(batches).__name__}")
    return sum(1 for batch in batches if batch)


def split_overflow(
    sprites: Sequence[Mapping[str, object]], max_vertices: int
) -> dict:
    """按顶点上限切批，并对单个超限精灵显式报错。

    返回 ``{"batches": [[sprite_idx, ...], ...], "overflow": []}``；切批语义
    与 :func:`build_batches` 相同。任何单个精灵的 ``verts > max_vertices``
    时立即抛 ``BatchError``，绝不静默丢弃或塞进 ``overflow``。``max_vertices``
    非正或精灵非法同样抛 ``BatchError``。
    """
    batches = build_batches(sprites, max_vertices)
    return {"batches": batches, "overflow": []}


def batch_frames(
    frames: Sequence[Sequence[Mapping[str, object]]], max_vertices: int
) -> dict:
    """对多帧精灵批量切批；任一帧非法时整体失败，不返回半成品。

    返回::

        {
            "frames": [
                {"batches": [[frame_local_idx, ...], ...], "draws": <int>},
                ...
            ],
            "draws": <所有帧 draw call 总数>,
        }

    每个帧的 ``batches`` 与 :func:`build_batches` 一致，下标是帧内下标；
    ``draws`` 只统计非空批次。必须先校验全部帧、全部精灵和 ``max_vertices``，
    再生成结果；任一阵列不是序列、精灵非法、单精灵超限或上限非法时抛
    ``BatchError``，不产生部分输出。空 ``frames`` 返回
    ``{"frames": [], "draws": 0}``；浮点比较使用 ``1e-6`` 容差。
    """
    _validate_max_vertices(max_vertices)
    if isinstance(frames, (str, bytes)) or not isinstance(frames, Sequence):
        raise BatchError(f"frames 必须是序列: {type(frames).__name__}")

    # 第一阶段：完整校验所有帧，任何非法都直接抛错，不产生部分输出。
    for frame_index, frame in enumerate(frames):
        if isinstance(frame, (str, bytes)) or not isinstance(frame, Sequence):
            raise BatchError(f"帧 {frame_index} 不是序列: {frame!r}")
        _validate_sprites(frame)
        for sprite_index, sprite in enumerate(frame):
            if sprite["verts"] > max_vertices:
                raise BatchError(
                    f"帧 {frame_index} 精灵 {sprite_index} 的 "
                    f"verts={sprite['verts']} 超过上限 {max_vertices}"
                )

    # 第二阶段：全部合法后才生成结果。
    results = []
    total_draws = 0
    for frame in frames:
        batches = build_batches(frame, max_vertices)
        draws = estimate_draws(batches)
        results.append({"batches": batches, "draws": draws})
        total_draws += draws
    return {"frames": results, "draws": total_draws}
