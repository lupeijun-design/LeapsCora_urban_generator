# Urban Ground-Floor Robot Service Scene Schema / 城市公共空间机器人服务场景数据标准（JSON)
**Version / 版本:** 0.1.0  
**Format / 格式:** Markdown specification for the step-grouped JSON scene schema / 按步骤分组的 JSON 场景 schema 的 Markdown 说明文档

---

## 1. Purpose / 目的

This schema defines a lightweight, machine-readable scene description for:  
本 schema 定义了一套轻量级、机器可读的场景描述格式，用于：

- urban ground-floor public space generation / 城市首层公共空间生成
- first-floor robot-service environments / 首层机器人服务环境
- Blender-based fast preview / 基于 Blender 的快速预览
- future export to USD / Isaac Sim / 后续导出到 USD / Isaac Sim

It is **not** intended to replace BIM, CityGML, or detailed mesh formats.  
它**不是**用来替代 BIM、CityGML 或精细网格格式的。

It is a **logical scene schema** focused on:  
它本质上是一个**逻辑场景 schema**，重点描述：

- topology / 拓扑
- spatial generation / 空间生成
- functional zoning / 功能分区
- semantic labeling / 语义标注
- lightweight rendering bindings / 轻量渲染绑定

---

## 2. Design Principles / 设计原则

1. **Topology first / 拓扑优先**  
   Streets, frontages, nodes, and circulation are defined before detailed geometry.  
   先定义街道、沿街界面、节点和流线，再细化几何。

2. **Layered parametric generation / 分层参数化生成**  
   The scene is structured as a sequence of generation steps.  
   场景按照一系列生成步骤组织。

3. **Step-grouped outputs / 按步骤分组输出**  
   The `generated` layer is split by step so that importers can selectively show intermediate results.  
   `generated` 层按步骤拆分，便于导入器按阶段显示中间结果。

4. **Backend-independent core / 后端无关核心层**  
   JSON is the source scene description. Blender and USD are downstream render/export backends.  
   JSON 是源场景描述，Blender 和 USD 是下游渲染/导出后端。

---

## 3. Top-Level Structure / 顶层结构

```json
{
  "schema_version": "0.1.0",
  "scene_info": {},
  "global_settings": {},
  "inputs": {},
  "generated": {
    "step_1_network": {},
    "step_2_massing": {},
    "step_3_key_nodes": {},
    "step_4_topology": {},
    "step_5_spaces": {},
    "step_6_functionalization": {}
  },
  "semantics": {},
  "render_bindings": {},
  "export_hints": {}
}
```

---

## 4. Top-Level Fields / 顶层字段

### `schema_version`
Schema version string / schema 版本字符串。

**Type / 类型:** `string`

Example / 示例:
```json
"schema_version": "0.1.0"
```

---

### `scene_info` / 场景信息
Scene metadata / 场景元信息。

**Type / 类型:** `object`

Recommended fields / 推荐字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `scene_id` | string | Unique scene identifier / 场景唯一 ID |
| `scene_name` | string | Human-readable scene name / 场景名称 |
| `description` | string | Optional description / 可选描述 |
| `author` | string | Scene author / 作者 |
| `created_at` | string | ISO-like timestamp / 时间戳 |
| `coordinate_system` | string | Usually `local_xy_up_z` / 通常为本地坐标系 |
| `unit` | string | Usually `meter` / 通常为米 |

Example / 示例:
```json
"scene_info": {
  "scene_id": "sample_full_001",
  "scene_name": "Full schema test scene",
  "coordinate_system": "local_xy_up_z",
  "unit": "meter"
}
```

---

### `global_settings` / 全局设置
Global defaults used by generation and backend import / 生成和后端导入使用的全局默认参数。

**Type / 类型:** `object`

Typical fields / 常见字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `default_road_width_by_class` | object | Width defaults per road class / 不同道路等级的默认宽度 |
| `default_population_activity` | object | Pedestrian Activity Levels per road class / 不同道路等级的人流活力等级 |
| `default_corner_radius_by_pair` | object | Corner radii per road-class pair / 不同道路组合的转角半径 |
| `default_solver_grid` | number | Default grid size for massing / 体量求解默认网格 |
| `default_transit_influence_width` | number | Transit frontage influence width / 公交地铁影响带宽度 |
| `default_clear_path_width` | number | Default clear pedestrian width / 默认净通行宽度 |
| `default_threshold_depth` | number | Default threshold depth / 默认阈值空间深度 |
| `default_indoor_corridor_width` | number | Default main indoor corridor width / 默认室内主走廊宽度 |
| `default_secondary_corridor_width` | number | Default secondary corridor width / 默认次级走廊宽度 |



---

### `inputs` / 输入层
Original or preprocessed inputs / 原始输入或预处理输入。

**Type / 类型:** `object`

Contains / 包含：

- `roads` / 道路
- `intersections` / 交叉口
- `transit_nodes` / 公交地铁节点
- `planning_controls` / 规划控制条件

---

### `generated` / 生成层
The generated spatial result, grouped by step / 按生成步骤分组的空间结果。

**Type / 类型:** `object`

Contains / 包含：

- `step_1_network` / 第一步：路网层结果
- `step_2_massing` / 第二步：体量层结果
- `step_3_key_nodes` / 第三步：关键节点结果
- `step_4_topology` / 第四步：步行拓扑结果
- `step_5_spaces` / 第五步：步行空间结果
- `step_6_functionalization` / 第六步：功能区与局部规则结果

This is the core scene result for debugging and preview.  
这是用于调试和预览的核心场景结果。

---

### `semantics` / 语义层
Semantic labels for spaces, nodes, and elements / 空间、节点和对象的语义标签。

**Type / 类型:** `object`

Contains / 包含：

- `space_labels` / 空间标签
- `node_labels` / 节点标签
- `element_labels` / 对象标签
- `restricted_areas` / 受限区域

---

### `render_bindings` / 渲染绑定层
Lightweight rendering and asset class bindings / 轻量渲染类别和资产类别绑定。

**Type / 类型:** `object`

Contains / 包含：

- `material_classes` / 材质类别
- `asset_classes` / 资产类别
- `style_tags` / 风格标签

These fields are intentionally lightweight and backend-neutral.  
这些字段有意保持轻量，并尽量与后端无关。

---

### `export_hints` / 导出提示
Hints for Blender / USD / other downstream tools / 给 Blender、USD 等后端的导出提示。

**Type / 类型:** `object`

Contains exporter-specific options such as:  
包含导出器相关选项，例如：

- collection grouping / 集合分组
- simple extrusion / 简单拉伸
- semantic export / 语义导出
- instancing hints / 实例化提示

---

## 5. Coordinate and Geometry Conventions / 坐标与几何约定

### Coordinate system / 坐标系
Use / 使用：

- `x, y` = horizontal plane / 水平平面坐标 
- `z` = vertical axis in backend rendering / 后端渲染中的竖直方向
- y轴正方向为北方

### Units / 单位
Use meters unless otherwise noted / 除非特别说明，否则统一使用米。

### Geometry encoding / 几何编码
All polygons and polylines are 2D in JSON / JSON 中所有折线和多边形都使用二维坐标：

- point / 点: `[x, y]`
- polyline / 折线: `[[x1, y1], [x2, y2], ...]`
- polygon / 多边形: `[[x1, y1], [x2, y2], ..., [x1, y1]]`

Polygons should be closed / 多边形应闭合。

---

## 6. `inputs` Layer / 输入层

## 6.1 `roads` / 道路

Represents input road centerlines / 表示输入道路中心线。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Road ID / 道路 ID |
| `name` | string | Optional road name / 可选道路名称 |
| `road_class` | string | `expressway`, `arterial`, `secondary`, `local`,`Tree-lined avenue`,`residential` / 快速、主干、次干、支路、林荫景观路、居住区内部路 |
| `custom_width` | number/null | Explicit override width / 用户指定宽度 |
| `centerline` | polyline2D | Road centerline / 道路中心线 |
| `attributes` | object | Additional user-defined attributes / 其他用户自定义属性 |

Example / 示例:
```json
{
  "id": "road_001",
  "name": "Main Street",
  "road_class": "arterial",
  "custom_width": null,
  "centerline": [[0, 0], [160, 0]],
  "attributes": {
    "pedestrian_priority": 0.95,
    "vehicle_priority": 0.7
  }
}
```

---

## 6.2 `intersections` / 交叉口

Road intersection points / 道路交叉点。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Intersection ID / 交叉口 ID |
| `road_ids` | array<string> | Connected roads / 相交道路 |
| `position` | point2D | Intersection point / 交叉口位置 |

---

## 6.3 `transit_nodes` / 公交地铁节点

Transit access nodes / 公交与地铁接入节点。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Transit node ID / 交通节点 ID |
| `type` | string | `metro` or `bus` / 地铁或公交 |
| count_line | number | count of lines / 线路数量 |
| number_line | array<string> | line / 线路 |
| `position` | point2D | Location / 位置 |
| `served_frontage_ids` | array<string> | Optional associated frontage IDs / 关联沿街界面 ID |



---

## 6.4 `planning_controls` / 规划控制条件

Planning and regulatory controls / 规划与控制指标。

**Type / 类型:** `object`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `parcel_id` | string | Parcel identifier / 地块 ID |
| `land_use` | string | `B1`, `B2`, `R` / 商业、办公、居住 |
| `setbacks` | object | Setback per frontage type / 不同沿街界面的退界 |
| `building_density_max` | number | Maximum building density / 最大建筑密度 |
| `far_max` | number | Maximum FAR / 最大容积率 |
| `height_max` | number | Height limit / 建筑高度上限 |
| `special_requirements` | object | Optional flags / 特殊要求，如连廊、地下商业预留 |

---

## 7. `generated.step_1_network` / 第一步：路网结果层

This layer stores the road-derived and block-derived spatial structure.  
这一层存储由道路推导出的街区空间结构。

### Contents / 包含
- `block_boundaries` / 地块边界
- `frontage_segments` / 沿街界面分段
- `corners` / 转角
- `transit_influence_zones` / 公交地铁影响区

---

## 7.1 `block_boundaries` / 地块边界

Closed block polygons / 闭合街区多边形。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Block ID / 地块 ID |
| `polygon` | polygon2D | Closed boundary polygon / 闭合边界多边形 |

---

## 7.2 `frontage_segments` / 沿街界面分段

Typed street-facing boundary segments / 带类型的沿街边界段。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Frontage ID / 沿街界面 ID |
| `block_id` | string | Parent block / 所属地块 |
| `polyline` | polyline2D | Boundary segment geometry / 边界段几何 |
| `frontage_type` | string | `primary_frontage`, `secondary_frontage`, `back_frontage` / 主街、次街、背街界面 |
| `adjacent_road_id` | string | Related road / 相邻道路 |
| `length` | number | Segment length / 长度 |
| `orientation` | number | Optional orientation angle / 朝向角 |
| `transit_influenced` | boolean | Whether under transit influence / 是否受公交地铁影响 |
| `served_transit_node_ids` | array<string> | Related transit nodes / 关联交通节点 |

---

## 7.3 `corners` / 转角

Classified block corners / 分类后的街区转角。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Corner ID / 转角 ID |
| `block_id` | string | Parent block / 所属地块 |
| `position` | point2D | Corner position / 转角位置 |
| `corner_type` | string | `transit_corner`, `open_plaza_corner`, `normal_corner` / 交通枢纽角、开放广场角、普通转角 |
| `radius` | number | Corner radius / 转角半径 |
| `adjacent_frontage_ids` | array<string> | Connected frontages / 相邻沿街界面 |

---

## 7.4 `transit_influence_zones` / 公交地铁影响区

Transit frontage influence bands or polygons / 公交地铁对沿街界面的影响带或影响区。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Zone ID / 影响区 ID |
| `transit_node_id` | string | Related transit node / 关联交通节点 |
| `geometry_type` | string | Usually `polygon` / 一般为多边形 |
| `polygon` | polygon2D | Influence geometry / 影响区几何 |
| `width` | number | Influence width / 影响宽度 |
| `priority_boost` | number | Relative bonus for generation / 生成优先级加权 |
| `associated_frontage_ids` | array<string> | Related frontages / 关联沿街界面 |

---

## 8. `generated.step_2_massing` / 第二步：体量层

Stores buildable zones and abstracted building massing.  
存储可建区和抽象建筑体量。

### Contents / 包含
- `buildable_zones` / 可建区
- `building_masses` / 建筑体量
- `atriums` / 中庭
- `cores` / 交通核
- `podium_retail_bands` / 底商带
- `reserved_open_spaces` / 预留开放空间

---

## 8.1 `buildable_zones` / 可建区

Setback-filtered buildable areas / 扣除退界后的可建范围。

**Type / 类型:** `array<object>`

Same structure as `polygonFeature` / 结构与普通 polygon feature 一致。

---

## 8.2 `building_masses` / 建筑体量

Abstract building volumes / 抽象建筑体量。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Building ID / 建筑 ID |
| `building_type` | string | `mall`, `office`, `residential`, `mixed_use` / 商场、办公、住宅、混合功能 |
| `footprint` | polygon2D | Footprint polygon / 建筑轮廓 |
| `height` | number | Height in meters / 高度 |
| `levels_above_ground` | integer | Number of above-ground levels / 地上层数 |
| `levels_below_ground` | integer | Number of below-ground levels / 地下层数 |
| `frontage_alignment` | object | Alignment hints / 对位信息 |
| `entry_preference_faces` | array<string> | Preferred entry faces / 优先入口面 |
| `related_frontage_ids` | array<string> | Related frontages / 关联沿街界面 |
| `reserved_open_space_ids` | array<string> | Related open spaces / 关联开放空间 |

---

## 8.3 `atriums` / 中庭

Commercial atrium areas / 商业建筑中的中庭空间。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Atrium ID / 中庭 ID |
| `building_id` | string | Parent building / 所属建筑 |
| `polygon` | polygon2D | Atrium footprint / 中庭轮廓 |
| `service_radius` | number | Influence radius / 服务半径 |
| `multi_level` | boolean | Multi-level atrium flag / 是否为多层中庭 |

---

## 8.4 `cores` / 交通核

Office or mixed-use cores / 办公或混合功能建筑的交通核心。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Core ID / 交通核 ID |
| `building_id` | string | Parent building / 所属建筑 |
| `polygon` | polygon2D | Core footprint / 交通核轮廓 |
| `core_type` | string | `office_core`, `mixed_use_core`, `residential_core` / 办公核、混合核、住宅核 |
| `influence_radius` | number | Influence radius / 影响半径 |

---

## 8.5 `podium_retail_bands` / 底商带

Retail strips attached to podium edges / 附着于基座边缘的底商带。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Retail band ID / 底商带 ID |
| `building_id` | string | Parent building / 所属建筑 |
| `related_frontage_ids` | array<string> | Associated frontages / 关联沿街界面 |
| `polygon` | polygon2D | Retail band polygon / 底商带几何 |
| `shop_unit_depth` | number | Typical unit depth / 店铺进深 |
| `continuous` | boolean | Whether continuous / 是否连续 |

---

## 8.6 `reserved_open_spaces` / 预留开放空间

Reserved external open spaces / 预留的首层外部开放空间。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Open space ID / 开放空间 ID |
| `open_space_type` | string | `small_plaza`, `forecourt`, `setback_open_space`, `sunken_plaza` / 小广场、前庭、退界开放空间、下沉广场 |
| `polygon` | polygon2D | Geometry / 几何 |
| `related_frontage_ids` | array<string> | Related frontages / 关联沿街界面 |
| `related_corner_ids` | array<string> | Related corners / 关联转角 |

---

## 9. `generated.step_3_key_nodes` / 第三步：关键节点

Stores node-level generation anchors / 存储节点级别的生成锚点。

### Contents / 包含
- `key_nodes` / 关键节点
- `entrance_candidates` / 候选入口
- `service_nodes` / 服务节点

---

## 9.1 `key_nodes` / 关键节点

Important public-space nodes / 重要公共空间节点。

**Type / 类型:** `array<object>`

Possible `node_type` values / 可能的节点类型：

- `metro_access` / 地铁出入口
- `bus_access` / 公交站点
- `atrium_center` / 中庭中心
- `core_center` / 交通核中心
- `corner` / 转角节点
- `plaza_center` / 广场中心

---

## 9.2 `entrance_candidates` / 候选入口

Candidate building entrances with scoring / 带评分的建筑候选入口。

**Type / 类型:** `array<object>`

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Candidate ID / 候选入口 ID |
| `building_id` | string | Building ID / 建筑 ID |
| `building_type` | string | Building type / 建筑类型 |
| `position` | point2D | Entrance location / 入口位置 |
| `served_frontage_id` | string | Related frontage / 关联沿街界面 |
| `candidate_type` | string | `main`, `secondary`, `service` / 主入口、次入口、服务入口 |
| `score` | number | Entrance score / 入口评分 |
| `score_breakdown` | object | Weighted component scores / 分项评分 |

---

## 9.3 `service_nodes` / 服务节点

Operational or service-use nodes / 运营或服务使用节点。

**Type / 类型:** `array<object>`

Possible `service_type` values / 可能的服务节点类型：

- `pickup_node` / 取货点
- `delivery_node` / 送货点
- `property_frontdesk` / 物业前台
- `parcel_locker` / 快递柜
- `loading_point` / 装卸点
- `waiting_node` / 等候点

---

## 10. `generated.step_4_topology` / 第四步：步行拓扑层

Stores circulation graph structure and skeleton / 存储步行网络图结构和流线骨架。

### Contents / 包含
- `circulation_networks` / 步行网络图
- `circulation_skeleton` / 流线骨架

---

## 10.1 `circulation_networks` / 步行网络图

Contains three graph layers / 包含三类图层：

- `ground_outdoor` / 首层室外步行网络
- `ground_indoor_public` / 首层室内公共步行网络
- `vertical_transition` / 垂直转换网络

Each graph contains / 每个图都包含：

- `nodes` / 节点
- `edges` / 边

### Network node fields / 网络节点字段
| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Node ID / 节点 ID |
| `position` | point2D | Node location / 节点位置 |
| `node_type` | string | Node role / 节点角色 |
| `connector_mode` | string | Optional vertical connector type / 可选垂直连接方式 |

### Network edge fields / 网络边字段
| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Edge ID / 边 ID |
| `from` | string | Start node / 起点节点 |
| `to` | string | End node / 终点节点 |
| `edge_type` | string | Corridor or spine type / 通道或流线类型 |
| `length` | number | Length / 长度 |
| `priority` | string | Optional importance / 优先级 |

---

## 10.2 `circulation_skeleton` / 流线骨架

Abstract spine representation used before full space generation / 在完整空间生成前使用的抽象骨架表示。

Contains / 包含：

- `main_spines` / 主流线
- `secondary_spines` / 次流线
- `threshold_spines` / 阈值流线
- `vertical_spines` / 垂直流线

Each spine contains / 每条骨架包含：

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Spine ID / 骨架 ID |
| `polyline` | polyline2D | Path geometry / 路径几何 |
| `spine_type` | string | `main`, `secondary`, `threshold`, `vertical` / 主、次、阈值、垂直 |

---

## 11. `generated.step_5_spaces` / 第五步：步行空间层

Stores actual walkable and node-space geometries / 存储实际生成的步行空间和节点空间几何。

### Contents / 包含
- `walkable_spaces` / 可步行空间
- `node_spaces` / 节点型空间

---

## 11.1 `walkable_spaces` / 可步行空间

Generated pedestrian spaces / 生成的步行空间。

Possible `space_type` values / 可能的空间类型：

- `street_clear_path` / 街道净通行带
- `entrance_threshold` / 入口阈值空间
- `semi_public_frontage_band` / 半公共沿街带
- `indoor_public_corridor` / 室内公共走廊
- `lobby_space` / 大堂空间
- `atrium_spillout` / 中庭外溢空间

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Space ID / 空间 ID |
| `space_type` | string | Space category / 空间类型 |
| `polygon` | polygon2D | Geometry / 几何 |
| `level` | string | `ground`, `level_2`, `basement_1` / 地上一层、二层、地下一层 |
| `min_clear_width` | number | Optional width requirement / 最小净宽 |
| `related_spine_ids` | array<string> | Linked spines / 关联骨架 |
| `related_entrance_candidate_id` | string | Optional entrance reference / 关联候选入口 |
| `related_building_id` | string | Parent building / 所属建筑 |

---

## 11.2 `node_spaces` / 节点型空间

Expanded node-centered spaces / 以节点为中心扩张生成的空间。

Possible `node_space_type` values / 可能的节点空间类型：

- `small_plaza` / 小广场
- `office_forecourt` / 办公前庭
- `mall_entry_plaza` / 商场入口前场
- `corner_expansion` / 转角扩张空间
- `sunken_entry_plaza` / 下沉入口广场

---

## 12. `generated.step_6_functionalization` / 第六步：功能化层

Stores post-space functional breakdown and placed objects / 存储步行空间生成后的功能带和布置对象。

### Contents / 包含
- `functional_zones` / 功能带
- `placed_elements` / 布置对象
- `pattern_applications` / 局部规则或 pattern 应用

---

## 12.1 `functional_zones` / 功能带

Sub-zones inside spaces / 空间内部的次级功能带。

Possible `zone_type` values / 可能的功能带类型：

- `clear_zone` / 净通行带
- `frontage_zone` / 沿街界面带
- `threshold_zone` / 阈值带
- `furnishing_zone` / 家具布置带
- `waiting_zone` / 等候带
- `display_zone` / 展示/外摆带

---

## 12.2 `placed_elements` / 布置对象

Simple placed or anchored scene elements / 简单放置或锚定的场景对象。

Possible `element_type` values / 可能的对象类型：

- `bench` / 座椅
- `signage` / 标识牌
- `planter` / 花池
- `bollard` / 路桩
- `fence` / 围栏
- `awning` / 雨棚
- `window_display` / 橱窗展示
- `parcel_locker` / 快递柜
- `frontdesk` / 前台
- `turnstile` / 闸机

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Element ID / 对象 ID |
| `element_type` | string | Element class / 对象类型 |
| `placement_type` | string | `instance` or `anchor` / 实例或锚点 |
| `position` | point2D | Placement position / 放置位置 |
| `rotation` | number | Rotation angle / 旋转角度 |
| `related_zone_id` | string | Parent functional zone / 所属功能带 |

---

## 12.3 `pattern_applications` / pattern 应用

Records local grammar / pattern adjustments / 记录局部规则文法或 pattern 微调。

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Pattern application ID / pattern 应用 ID |
| `pattern_type` | string | Pattern name / pattern 名称 |
| `applied_to` | array<string> | Target IDs / 应用目标 ID |
| `parameters` | object | Pattern-specific parameters / pattern 参数 |

---

## 13. `semantics` / 语义层

Semantic layer for robotics and downstream reasoning / 服务于机器人和后续推理的语义层。

### Contents / 包含
- `space_labels` / 空间语义标签
- `node_labels` / 节点语义标签
- `element_labels` / 对象语义标签
- `restricted_areas` / 受限区域

---

## 13.1 Semantic tag format / 语义标签格式

All three label arrays share the same structure / 三类标签数组使用相同结构：

```json
{
  "target_id": "ws_001",
  "label": "traversable_area"
}
```

Possible labels / 可用标签：

- `traversable_area` / 可通行区域
- `threshold` / 阈值空间
- `entrance_portal` / 入口门廊/入口点
- `indoor_public` / 室内公共空间
- `semi_public` / 半公共空间
- `obstacle` / 障碍物
- `waiting_node` / 等候节点
- `pickup_node` / 取货节点
- `delivery_node` / 送货节点
- `transit_connector` / 交通接驳节点
- `vertical_connector_reserved` / 垂直连接预留点
- `restricted_area` / 受限区域

---

## 13.2 `restricted_areas` / 受限区域

Areas that should be considered staff-only or otherwise excluded / 应视为员工专用或其他受限区域。

Fields / 字段:

| Field / 字段 | Type / 类型 | Description / 说明 |
|---|---|---|
| `id` | string | Area ID / 区域 ID |
| `polygon` | polygon2D | Restricted region / 区域几何 |
| `reason` | string | Restriction reason / 受限原因 |

---

## 14. `render_bindings` / 渲染绑定层

Backend-neutral render and asset classification / 与后端无关的渲染分类和资产分类。

### Contents / 包含
- `material_classes` / 材质类别映射
- `asset_classes` / 资产类别映射
- `style_tags` / 风格标签

---

## 14.1 `material_classes` / 材质类别

Maps object ID to material class / 将对象 ID 映射到材质类别。

Example / 示例:
```json
"material_classes": {
  "bld_001": "building_facade_commercial",
  "ws_001": "pavement_main",
  "ws_006": "indoor_floor_office"
}
```

---

## 14.2 `asset_classes` / 资产类别

Maps element ID to reusable asset class / 将对象 ID 映射到可复用资产类型。

Example / 示例:
```json
"asset_classes": {
  "elem_001": "bench_standard",
  "elem_004": "parcel_locker_standard"
}
```

---

## 14.3 `style_tags` / 风格标签

Optional style tags per object / 每个对象可选的风格标签。

Example / 示例:
```json
"style_tags": {
  "bld_001": ["modern_commercial", "glass_frontage"],
  "bld_002": ["office_minimal", "stone_glass"]
}
```

---

## 15. `export_hints` / 导出提示

Optional backend hints / 可选的后端提示。

### Example structure / 示例结构
```json
"export_hints": {
  "blender": {
    "generate_simple_mesh": true,
    "extrude_buildings": true,
    "show_semantic_overlays": true,
    "step_collections": true
  },
  "usd": {
    "export_as_xform_hierarchy": true,
    "separate_collision_prims": true,
    "attach_semantic_labels": true,
    "use_instancing_for_repeated_assets": true
  }
}
```

These fields are not core geometry data.  
这些字段不是核心几何数据。

They are instructions or preferences for downstream tools.  
它们是给下游工具的导出偏好或提示。

---

## 16. Recommended Importer Behavior / 推荐导入器行为

A Blender importer should ideally:  
Blender 导入器理想情况下应：

1. Read `generated` step by step / 按步骤读取 `generated`
2. Create one collection per step / 为每一步创建一个 collection：
   - `Step_1_Network`
   - `Step_2_Massing`
   - `Step_3_KeyNodes`
   - `Step_4_Topology`
   - `Step_5_Spaces`
   - `Step_6_Functionalization`
3. Allow selective visualization by step / 支持按步骤显示
4. Attach semantic labels as custom properties / 将语义标签附加为自定义属性
5. Apply lightweight material bindings if available / 应用轻量材质绑定

---

## 17. Recommended Validation Strategy / 推荐校验策略

### Required minimum for a valid scene / 有效场景的最小要求
At minimum, a scene should contain / 至少应包含：

- `schema_version`
- `scene_info`
- `generated.step_1_network`
- `generated.step_2_massing`
- `generated.step_5_spaces`

### Strongly recommended / 强烈建议
Also include / 同时建议包含：

- `semantics`
- `render_bindings`

### Optional / 可选
- `export_hints`
- advanced pattern data / 更复杂的 pattern 数据
- multi-level extensions / 多层扩展

---

## 18. Minimal Step Group Template / 最小步骤模板

```json
{
  "generated": {
    "step_1_network": {
      "block_boundaries": [],
      "frontage_segments": [],
      "corners": [],
      "transit_influence_zones": []
    },
    "step_2_massing": {
      "buildable_zones": [],
      "building_masses": [],
      "atriums": [],
      "cores": [],
      "podium_retail_bands": [],
      "reserved_open_spaces": []
    },
    "step_3_key_nodes": {
      "key_nodes": [],
      "entrance_candidates": [],
      "service_nodes": []
    },
    "step_4_topology": {
      "circulation_networks": {
        "ground_outdoor": { "nodes": [], "edges": [] },
        "ground_indoor_public": { "nodes": [], "edges": [] },
        "vertical_transition": { "nodes": [], "edges": [] }
      },
      "circulation_skeleton": {
        "main_spines": [],
        "secondary_spines": [],
        "threshold_spines": [],
        "vertical_spines": []
      }
    },
    "step_5_spaces": {
      "walkable_spaces": [],
      "node_spaces": []
    },
    "step_6_functionalization": {
      "functional_zones": [],
      "placed_elements": [],
      "pattern_applications": []
    }
  }
}
```

---

## 19. Recommended File Set / 推荐文件组织

For collaboration, keep these files together / 协作时建议保留以下文件：

```text
schema/
  urban_ground_floor_scene.schema.json
  urban_ground_floor_scene.schema.md

examples/
  sample_scene.json
  sample_scene_full.json
```

- `*.schema.json` = machine-readable validation schema / 机器可读校验 schema
- `*.schema.md` = human-readable spec / 人类可读说明文档
- `sample_scene_full.json` = practical test case / 实际测试场景

---

## 20. Future Extensions / 未来扩展

Possible future schema additions / 未来可以增加：

1. **Step 7 dynamics / 动态层**
   - pedestrians / 行人
   - mobile robots / 移动机器人
   - vehicles / 车辆

2. **Step 8 task layer / 任务层**
   - pickup tasks / 取货任务
   - delivery tasks / 送货任务
   - patrol routes / 巡检路线

3. **Fine façade / storefront schema / 精细立面与首层界面 schema**
   - window modules / 窗口模块
   - sign types / 招牌类型
   - awning systems / 雨棚系统

4. **Multi-level circulation expansion / 多层流线扩展**
   - skywalk networks / 二层连廊网络
   - underground commercial passages / 地下商业通道
   - platform-to-lobby transitions / 站厅到大堂连接

---

## 21. Summary / 总结

This schema is designed to support a full workflow from:  
这套 schema 支持以下完整工作流：

- road structure / 路网结构
- frontage and massing / 沿街界面与体量
- key node generation / 关键节点生成
- walkable topology / 步行拓扑
- pedestrian space generation / 步行空间生成
- functional zoning / 功能分区
- semantic labeling / 语义标注
- lightweight rendering/export binding / 轻量渲染和导出绑定

The key structural decision in this version is:  
这一版最关键的结构决策是：

> **the `generated` layer is grouped by step result rather than flattened**  
> **`generated` 层按步骤分组，而不是扁平展开**

This makes the schema much more suitable for:  
这使得该 schema 更适合：

- Blender debugging / Blender 调试
- progressive visualization / 渐进式可视化
- pipeline validation / 流程校验
- future staged export to USD / Isaac Sim / 未来分阶段导出到 USD / Isaac Sim
