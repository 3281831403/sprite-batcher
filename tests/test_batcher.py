"""sprite-batcher 的 15 个红灯测试。

测试只依赖公开接口和标准库；精灵一律以内联四字段字典给出。
"""

import pytest

from render.batcher import (
    MAX_VERTICES,
    BatchError,
    assign_pages,
    batch_frames,
    build_batches,
    estimate_draws,
    interleave_alpha,
    merge_compatible,
    sort_key,
    split_overflow,
)


def test_build_batches_separates_texture_and_blend():
    sprites = [
        {"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "alpha", "verts": 4},
        {"texture": "hero", "z": 2.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 3.0, "blend": "alpha", "verts": 4},
    ]

    batches = build_batches(sprites, max_vertices=64)

    assert len(batches) == 2
    assert all(
        len({sprites[index]["blend"] for index in batch}) == 1 for batch in batches
    )


def test_build_batches_respects_vertex_limit():
    sprites = [
        {"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 2.0, "blend": "opaque", "verts": 4},
    ]

    batches = build_batches(sprites, max_vertices=8)

    assert len(batches) == 2
    assert all(
        sum(sprites[index]["verts"] for index in batch) <= 8 for batch in batches
    )
    assert sorted(index for batch in batches for index in batch) == [0, 1, 2]


def test_sort_key_orders_opaque_then_alpha_back_to_front():
    sprites = [
        {"texture": "hero", "z": 5.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 2.0, "blend": "alpha", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 8.0, "blend": "alpha", "verts": 4},
        {"texture": "hero", "z": 4.0, "blend": "alpha", "verts": 4},
    ]

    ordered = sorted(sprites, key=sort_key)

    assert [sprite["z"] for sprite in ordered] == [1.0, 5.0, 8.0, 4.0, 2.0]
    assert [sprite["blend"] for sprite in ordered] == [
        "opaque",
        "opaque",
        "alpha",
        "alpha",
        "alpha",
    ]


def test_sort_key_is_stable_for_equal_z():
    first = {"texture": "z", "z": 1.0, "blend": "opaque", "verts": 4}
    second = {"texture": "a", "z": 1.0, "blend": "opaque", "verts": 4}
    third = {"texture": "y", "z": 1.0, "blend": "alpha", "verts": 4}
    fourth = {"texture": "b", "z": 1.0, "blend": "alpha", "verts": 4}

    ordered_once = sorted([first, second, third, fourth], key=sort_key)
    ordered_twice = sorted([first, second, third, fourth], key=sort_key)

    assert ordered_once == [first, second, third, fourth]
    assert ordered_twice == ordered_once


def test_assign_pages_uses_area_not_sprite_count():
    sprites = [
        {"texture": "atlas", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "atlas", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "atlas", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "atlas", "z": 0.0, "blend": "opaque", "verts": 20},
    ]

    result = assign_pages(sprites, page_capacity=8)

    assert list(result["pages"].values()) == [[0, 1], [2]]
    assert result["overflow"] == [3]


def test_merge_compatible_requires_same_blend_texture_and_limit():
    opaque_a = {"texture": "atlas", "z": 0.0, "blend": "opaque", "verts": 4}
    opaque_b = {"texture": "atlas", "z": 2.0, "blend": "opaque", "verts": 4}
    alpha_a = {"texture": "atlas", "z": 1.0, "blend": "alpha", "verts": 4}
    near_limit = {
        "texture": "atlas",
        "z": 3.0,
        "blend": "opaque",
        "verts": MAX_VERTICES - 2,
    }

    assert merge_compatible(opaque_a, opaque_b) is True
    assert merge_compatible(opaque_a, alpha_a) is False
    assert merge_compatible(near_limit, opaque_a) is False


def test_interleave_alpha_preserves_relative_order():
    groups = [
        {"blend": "opaque", "indices": [0, 3]},
        {"blend": "alpha", "indices": [1, 4]},
        {"blend": "opaque", "indices": [2]},
        {"blend": "alpha", "indices": [5]},
    ]

    assert interleave_alpha(groups) == [0, 3, 2, 1, 4, 5]


def test_estimate_draws_ignores_empty_batches():
    batches = [[0, 1], [], [2], []]

    assert estimate_draws(batches) == 2


def test_split_overflow_raises_on_single_oversized_sprite():
    sprites = [
        {"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "opaque", "verts": 32},
        {"texture": "hero", "z": 2.0, "blend": "opaque", "verts": 4},
    ]

    with pytest.raises(BatchError):
        split_overflow(sprites, max_vertices=16)


def test_batch_frames_rolls_back_when_any_frame_invalid():
    frames = [
        [{"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4}],
        [{"texture": "hero", "z": 1.0, "blend": "opaque"}],
    ]

    with pytest.raises(BatchError):
        batch_frames(frames, max_vertices=16)


def test_empty_input_returns_empty_batches():
    assert build_batches([], max_vertices=16) == []


def test_zero_max_vertices_raises_batch_error():
    sprites = [{"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4}]

    with pytest.raises(BatchError):
        build_batches(sprites, max_vertices=0)


def test_build_batches_is_deterministic_for_same_input():
    sprites = [
        {"texture": "hero", "z": 3.0, "blend": "alpha", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "opaque", "verts": 4},
        {"texture": "tile", "z": 2.0, "blend": "opaque", "verts": 4},
    ]

    first = build_batches(sprites, max_vertices=8)
    second = build_batches(sprites, max_vertices=8)

    assert first == second


def test_single_texture_and_blend_fits_one_batch():
    sprites = [
        {"texture": "hero", "z": 0.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 1.0, "blend": "opaque", "verts": 4},
        {"texture": "hero", "z": 2.0, "blend": "opaque", "verts": 4},
    ]

    assert build_batches(sprites, max_vertices=12) == [[0, 1, 2]]


def test_estimate_draws_equals_batch_count():
    batches = [[0, 1], [2]]

    assert estimate_draws(batches) == len(batches)
