# Rinnai 采暖设备集成（Home Assistant 插件）

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/releases)
[![GitHub license](https://img.shields.io/github/license/palafin02back/rinnai_integration.svg)](https://github.com/palafin02back/rinnai_integration/blob/master/LICENSE)

本项目 fork 自 palafin02back/rinnai_integration，并在此基础上进行了功能完善和适配。

本集成适用于 Rinnai（林内）REB 系列冷凝炉，可在 Home Assistant 中实现本地化的采暖与热水控制与状态监控。

---

## ⚠️ 重要风险提示

**使用本集成存在被官方服务器封号的风险**。一旦被封号，可能导致原厂 App 中设备一直显示离线，无法远程控制。  
**请在充分了解风险并自行承担责任的前提下使用本插件。严格不建议在主账号下使用。本项目及开发者对由此引发的任何后果不承担责任。**

---

## 功能特性

- 采暖气候实体  
  - 支持设置采暖目标温度  
  - 支持在四种模式间切换：普通、快速、外出、关闭  
  - 能显示当前运行状态（采暖中 / 待机 / 关闭）及目标温度
- 热水器实体  
  - 支持设置热水目标温度  
  - 展示热水温度上下限等基础信息  
- 热水器节能模式（Eco Mode）开关：与 REB 设备节能位同步，可单独在控制面板上切换  
- 诊断与传感器信息：采暖 / 热水燃烧状态、水压、采暖 / 热水设定温度等  
- MQTT 被动更新：无需等待下一次轮询即可刷新实体状态  

### v1.0.7 新增

- **实测水温传感器**：采暖出水温度、采暖回水温度、热水出水温度、室内温度。
  - ⚠️ 这四个是**实测值**，与「设定温度」不同。设备端确有独立传感器（故障码 353 / 363），
    但林内官方 App 对 REB-`*`FF-CH（云端 classID `0F060B0B`）机型从不显示它们，
    因此**云端是否上报这些字段必须实测确认**。
  - 若云端未下发，实体显示「不可用」——这是正确行为，不是 Bug。
- **调试实体「调试原始数据」**：默认禁用，启用后其属性会列出云端当前上报的**全部字段名和原始值**。
  这是确认某一机型到底上报哪些数据的唯一可靠方式。
- **其它遥测传感器**：热水流量、耗气量、累计运行时长、故障代码、运行模式原始值。
- **云端请求保护**（见下方「请求频率与封号风险」）。

---

## 请求频率与封号风险

集成以 **MQTT 推送为主、HTTP 轮询为兜底**，正常运行时请求量很低：

| 场景 | 请求量 |
| --- | --- |
| 正常运行（MQTT 在线） | 约 22 次 HTTP / 天 |
| 云端持续失败（最坏） | 约 6 次 HTTP / 天 |
| 用户设温度 / 切模式 | 各 1 次 MQTT 发布，无额外 HTTP |

设计要点：

- **HTTP 兜底 1 小时一次**，仅在 MQTT 漏数据时补位。
- **失败退避**：连续失败按 1h → 3h → 6h 逐级拉长，避免故障时退化成每 5 分钟重试。
- **Token 失效自动重登**：凭证被服务端提前作废时仅重登一次并重试，不会带着死 Token 反复请求。
- **请求节流**：任意两次云端 HTTP 至少间隔 3 秒。
- **固定的 MQTT client_id**：避免频繁换号被服务端视为异常行为。

> 仍建议使用**子账号**运行本集成。主账号一旦受限，官方 App、家人手机与售后报修都会受影响。

---

## 安装方式

### 方法一：HACS 安装（推荐）

1. 确保已安装 [HACS](https://hacs.xyz/)
2. 在 HACS → 自定义存储库 中添加 `https://github.com/kaattz/rinnai_integration`
3. 类别选择 “Integration”，点击添加
4. 在 HACS 集成页面搜索 “Rinnai” 并安装
5. 重启 Home Assistant

### 方法二：手动安装

1. 下载本仓库源码
2. 将 `custom_components/rinnai` 目录拷贝到 Home Assistant 配置目录的 `custom_components` 中
3. 重启 Home Assistant

---

## 配置方法

1. 打开 Home Assistant → 设置 → 设备与服务 → 添加集成
2. 搜索 “Rinnai”
3. 按向导填写账号、密码等参数完成配置

---

## 支持设备

- 主要支持林内 REB 系列采暖冷凝炉
- 其他系列暂未适配，如适配成功欢迎反馈
- 已在 Home Assistant `2025.9.0` 版本测试，其余版本请自行验证兼容性

---

## 效果展示
<img width="262" height="338" alt="rinnai1" src="https://github.com/user-attachments/assets/c526019a-2300-4b03-bab5-6450aff5f549" />
<img width="261" height="231" alt="2" src="https://github.com/user-attachments/assets/830fe418-2232-4468-b2bb-b0c24e1e4913" />
<img width="143" height="362" alt="3" src="https://github.com/user-attachments/assets/6428cba8-d71b-41d5-a8b8-f0635f9b7a2a" />



---

## 常见问题与排查

1. 设备是否已成功连网，可否通过官方 App 正常控制  
2. 检查 Home Assistant 日志中有无 `custom_components.rinnai` 报错  
3. 如问题无法解决，请开启调试日志，附带完整日志、HA 版本等信息提交 Issue

---

## 参与贡献

欢迎通过 Issue / PR 提交反馈、建议或代码，一起完善 REB 系列的支持。

---

## 免责声明

本项目为非官方爱好者开发，与 Rinnai 官方无关。任何因使用本项目造成的账号封禁、设备异常或其他损失，由使用者自行承担风险与责任；作者及贡献者不承担任何责任，敬请知悉。

---

## 许可证

项目采用 MIT License，详见 [LICENSE](LICENSE)。
