# 离线出生地区资料

制作日期：2026-10-23。运行时使用 `china_regions.json`；只包含名称、代码、层级、行政中心经纬度，不包含地图边界。源码版和后续安装包应一起附带本目录。

## 主体来源与许可

- 项目：[AreaCity-JsSpider-StatsGov](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov)。
- 上游版本：`2025.251231.260403`，发布于 2026-04-03。
- 层级来源：[`ok_data_level3.csv`](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/blob/master/src/%E9%87%87%E9%9B%86%E5%88%B0%E7%9A%84%E6%95%B0%E6%8D%AE/ok_data_level3.csv)。中心坐标来源：[同版本 `ok_geo.csv.7z`](https://github.com/xiangyuecn/AreaCity-JsSpider-StatsGov/releases/tag/2025.251231.260403) 中的 `geo` 列。
- 上游说明其区划综合国家地名信息库、高德与腾讯数据，中心为高德 **GCJ-02** 行政中心。未在本项目中重新地理编码或转换坐标。
- 上游以 MIT 许可证发布，完整声明保留在 `LICENSE-AreaCity.txt`。该许可证不用于重新许可下述 DataV 补充部分。

## 保持原界面覆盖的 DataV 补充

港澳的上游三级资料没有细分区县中心。因此从原程序使用的阿里云官方 [DataV.GeoAtlas](https://datav.aliyun.com/portal/school/atlas/area_selector) 补充以下公开数据的属性，保留原有的 18 个香港区、8 个澳门分区选择：

- [香港区县 JSON](https://geo.datav.aliyun.com/areas_v3/bound/810000_full.json)，2026-10-23 下载。
- [澳门分区 JSON](https://geo.datav.aliyun.com/areas_v3/bound/820000_full.json)，2026-10-23 下载。
- [全国一级 JSON](https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json) 中台湾省中心，取自项目原有本地缓存，原始下载日期未知。台湾省保持旧界面仅提供省中心的粒度，不补造其区县坐标。

只提取 `name`、`adcode`、`center` 和层级，不复制边界多边形。DataV 补充字段保留其来源，遵循原平台条款，不声明其采用 AreaCity 的 MIT 许可证。JSON 源响应没有声明这些 `center` 字段的坐标系，本项目不擅自标成 WGS84 或 GCJ-02。原始文件 SHA-256 与来源 URL 已写入快照元数据，便于追溯。

## 范围与处理

- 保留 34 个国内省级选择；排除上游“国外”聚合。
- 普通省为省—市—县区；直辖市展平中间的“市辖区”分组，与原界面的选择逻辑一致。
- 济源、东莞等上下两层同代码的填充条目合并，避免给同一地点伪造代码或重复区县。
- 台湾仅提供原有省中心，港澳提供上述分区；因此不宣称所有地区的县级经纬度完整覆盖。
- 行政区划是发布时的快照，不代表 2026-10-23 的最新区划，也不构成历史出生地点库。上游本版说明尚不包含新疆和康县、和安县等部分新增变更。
- 经纬度为行政中心的近似位置，不是出生医院或具体地址。用户需要更精确出生点时，应明确提供该点，不能将缺失坐标静默换成上级中心。

## 运行与更新

`china_regions.load_regions` 优先读此快照，并按文件修改时间和大小缓存解析结果。地区切换不联网、不下载边界。只有整份快照缺失时才兼容读取用户已有 `.cache/china_admin` 文件；缓存也没有时明确报错，不自动联网、不伪造坐标。

更新数据属于维护操作：先将上述 CSV/压缩包下载到 **D 盘项目 `.cache/region_sources`**，保留原始校验值；关联 CSV 的 `id/pid`，使用 `ext_id` 的行政代码和 `ext_name` 的完整名称，提取坐标表 `geo`，应用上面的层级处理，再补充 DataV 属性。输出仍须保留来源、上游版本、制作日期和输入 SHA-256；不要在用户选择出生地区时执行更新。

当前 JSON 中每条记录依次为：`name, adcode, longitude, latitude, children_num`；`children` 按父级代码索引，入口为 `100000`，已知叶节点对应空数组。空数组表示确实没有下一级；未知代码或缺失文件必须报错。载入函数返回新的字典，调用方不能修改共享缓存。
