# sprite-batcher

## 题面

同屏精灵一多，draw call 飙到几千、透明还画错层：只按纹理分批，混合模式不同也合，透明物体被当不透明画；分批不看顶点上限，单批超过硬件上限；排序只按纹理 id，透明物体互相遮挡错误；同 z 时排序不稳定，两次结果不同；图集分页按精灵数而不是面积，页溢出才报错；合并条件漏掉混合模式，等效批被拆开；交错透明时相对顺序被打乱，出现穿插；estimate_draws 把空批也计入，统计虚高；单精灵超上限被静默丢弃，画面缺件；批量处理遇非法精灵只跳过，输出里留下半批。render/batcher.py 是核心，tests/test_batcher.py 15个红。要修的是：按契约补齐 render/batcher.py 的 8 个实现，修掉上述 10 类缺陷，让 tests/test_batcher.py 的 15 个测试全部转绿。

## 运行

在仓库根目录执行 `python -m pytest tests -q`。

初始桩状态应恰好得到 `15 failed`，且没有 collection / import / syntax error；15 个测试全部会调用未实现的桩并以 `NotImplementedError` 失败。

## 字段表

| 字段 | 取值 |
| --- | --- |
| 所属领域 | 游戏、图形与多媒体 |
| 子方向 | 图形渲染 |
| 任务类型 | Bugfix |
| 语言/框架 | Python 3, pytest |
| 环境可复现等级 | 无外部依赖 |

## 约束

`tests/test_batcher.py` 不可修改；判分以该文件中的 15 个测试为准。只实现 `render/batcher.py`，使用标准库，离线运行，不使用随机数。
