# QQBot Notify

Home Assistant 自定义通知集成：把 HA 告警、自动化消息直接推送到 QQ（单聊）或 QQ 群。

集成直接调用 QQ 机器人官方 API，内部处理 `access_token` 的获取、缓存与刷新，不依赖任何第三方 Webhook 服务。

## 更新说明

### 1.2.0（发布版）

- 新增**选项流程**：可以在「设置 → 设备与服务 → QQBot Notify → 配置」里随时修改默认接收者（留空即删除），保存后自动重载；
- **添加集成时即校验凭证**：AppID/AppSecret 填错直接在表单上报“AppID 或 AppSecret 不正确”，不再等到发送时才失败；
- 发送遇到 `11242`/`11253`/`40012002` 这类 token 失效错误时，会丢弃缓存的 `access_token` **自动重试一次**；
- 异常按类型区分（凭证错误 / 网络问题 / token 失效），便于上层给出准确提示。

### 1.1.1（修复 401 `Token错误` / code 11242）

1.1.0 发送时用的是 `Authorization: Bot <access_token>`（旧版频道接口的写法），QQ v2 接口只认
`Authorization: QQBot <access_token>`，因此发送阶段会返回：

```text
发送 QQ 消息失败（HTTP 401）：{"message":"Token错误","code":11242,"err_code":40012002,...}
```

1.1.1 改用官方文档与官方 SDK（[botpy](https://github.com/tencent-connect/botpy) 中 `TYPE_BOT = "QQBot"`）一致的
`QQBot ` 前缀，并按官方 SDK 补上 `X-Union-Appid` 头；同时对常见错误码追加中文排查建议。

### 1.1.0（修复“集成不能用”）

1.0.x 版本用的是**旧版 YAML 通知平台接口**（`async_get_service` + `BaseNotificationService`），
而这个集成是通过 UI 配置条目（Config Entry）加载的。HA 2026.7 中配置条目走的是
`EntityPlatform.async_setup_entry` → `platform.async_setup_entry(...)` 这条路，
旧接口只在 `configuration.yaml` 写 `notify: - platform: qqbot_notify` 时才会被调用。
结果就是平台永远加载失败：

```text
Error while setting up qqbot_notify platform for notify:
module 'custom_components.qqbot_notify.notify' has no attribute 'async_setup_entry'
```

于是不会创建任何 notify 实体，也不会注册 `notify.qqbot_notify` 服务，自动化报“找不到操作”。

1.1.0 改为现代的 [Notify 实体](https://developers.home-assistant.io/docs/core/entity/notify/) 实现：

- `notify.py` 提供 `async_setup_entry` 并创建 `NotifyEntity` 子类；
- 凭证与默认接收者存放在 `ConfigEntry.runtime_data`，多机器人不再互相串数据；
- 新增 `qqbot_notify.send` 动作，支持 `target` / `is_group` / `msg_id` / 多机器人 `entry_id`；
- 使用 HA 自带的 aiohttp 会话并加 15 秒超时，不再泄漏 ClientSession；
- 补齐 `strings.json`、`translations/`、`services.yaml`，配置界面有中文/英文文案。

## 前置要求

- Home Assistant 2025.1.0 及以上（已在 2026.7 上实测推送成功）
- 已在 QQ 开放平台创建机器人，拿到 AppID、AppSecret，并且机器人已上线
- 已获得接收者的 `user_openid`（群聊为 `group_openid`）

## 安装

### 通过 HACS

1. HACS → **Integrations** → 右上角菜单 → **Custom repositories**。
2. 仓库地址填 `https://github.com/Mango-lei/ha-qqbot-notify`，Category 选 **Integration**。
3. 搜索 **QQBot Notify** 并安装，然后重启 Home Assistant。

### 手动安装

把 `custom_components/qqbot_notify` 复制到 HA 配置目录的 `custom_components/` 下，重启 Home Assistant。

## 配置

1. **设置 → 设备与服务 → 添加集成**，搜索 **QQBot Notify**。
2. 填写：

| 字段 | 说明 |
| --- | --- |
| AppID | QQ 开放平台机器人的 AppID（纯数字） |
| AppSecret | QQ 开放平台机器人的 AppSecret |
| 默认接收者 OpenID | 可选；填写后可直接用 `notify.send_message` 推送 |

3. 保存后会出现一个通知实体，实体 ID 形如 `notify.qqbot_<appid>`（例如 `notify.qqbot_102912345`）。

### 修改默认接收者

**设置 → 设备与服务 → QQBot Notify → 配置**，修改「默认接收者 OpenID」即可（留空表示删除该默认值），保存后条目会自动重载。不需要删除集成重新添加。

即使不设置默认接收者，也可以用 `qqbot_notify.send` 动作显式传 `target` 发送。

## 获取用户 OpenID

QQ 官方接口用 **OpenID** 标识用户，不是 QQ 号，且同一用户在不同 AppID 下 OpenID 不同。

1. 让机器人上线并开启消息事件接收。
2. 用目标 QQ 号给机器人发一条任意消息。
3. 在收到的事件里找到 `author.user_openid`，填进集成的默认接收者，或在自动化里用 `target` 传入。

```json
{
  "author": {
    "user_openid": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  },
  "content": "test"
}
```

## 使用示例

### 1. 发送给默认接收者（标准通知实体）

```yaml
action:
  - action: notify.send_message
    target:
      entity_id: notify.qqbot_102912345
    data:
      title: "HA 通知"
      message: "这是一条测试消息。"
```

`title` 会作为消息的第一行发送（QQ 文本消息没有独立的标题字段）。

### 2. 指定接收者 / 群聊（扩展动作）

```yaml
action:
  - action: qqbot_notify.send
    data:
      message: "检测到水浸，请立刻检查。"
      title: "水浸告警"
      target: "用户的 user_openid"
      # is_group: true        # target 为 group_openid 时打开
      # msg_id: "..."         # 被动回复时填入事件里的 msg_id
      # msg_seq: 1            # 同一个 msg_id 的第几条回复
      # entry_id: "..."       # 配置了多个机器人时指定用哪个
```

### 3. 水浸告警自动化

```yaml
automation:
  - alias: "水浸告警推送到 QQ"
    triggers:
      - trigger: state
        entity_id: binary_sensor.water_leak
        to: "on"
    actions:
      - action: notify.send_message
        target:
          entity_id: notify.qqbot_102912345
        data:
          title: "水浸告警"
          message: "检测到水浸，请立刻检查。"
```

## 从 1.0.x 迁移

- `notify.qqbot_notify` 这个老服务名**不再存在**（它是旧版 YAML 平台的产物）。请把自动化改成：
  - 默认接收者：`notify.send_message` + `entity_id: notify.qqbot_<appid>`；
  - 需要 `target` / 群聊：`qqbot_notify.send`。
- `notify.send_message` 只接受 `message` 和 `title`，`target` / `is_group` 这类额外字段会被 HA 的 schema 拒绝，请改用 `qqbot_notify.send`。
- 升级后请重新加载集成（或重启 HA），并在“设置 → 设备与服务”确认没有报错。

## 故障排查

| 现象 | 原因 / 处理 |
| --- | --- |
| 日志出现 `has no attribute 'async_setup_entry'` | 还在用 1.0.x 的旧平台接口，升级到 1.1.0 及以上 |
| 自动化报“找不到操作 notify.qqbot_notify” | 老服务名已移除，改用 `notify.send_message` 或 `qqbot_notify.send` |
| 发送报 `Token错误` / `code 11242`（HTTP 401） | 1.1.0 的鉴权头是旧的 `Bot` 前缀，升级到 1.1.1 及以上（`QQBot` 前缀） |
| 添加集成时提示“AppID 或 AppSecret 不正确” | 1.2.0 起的凭证校验失败，请与开放平台管理端核对（错误码 100007/100016） |
| 发送报 `code 40054` / `code 22009` | QQ 侧限制：主动消息需要用户先与机器人交互、有主动消息额度，或机器人未上线 |
| 发送报 `40034105` / `40034100` | 用户关闭了“允许主动发送”，或触发了主动消息频控 |
| 报“没有设置默认接收者” | 请在集成「配置」里补上默认接收者，或用 `qqbot_notify.send` 显式传 `target` |
| 收不到消息但没有报错 | 打开集成调试日志（`logger: logs: custom_components.qqbot_notify: debug`）查看请求/响应 |

## 注意事项

- QQ 对个人号单聊主动消息限制较严，建议只用于关键告警。
- AppID、AppSecret 属于敏感凭证，日志中不会打印明文（仅 debug 级别记录响应摘要）。
- 本集成只负责推送，不处理 QQ 消息接收与事件订阅；`msg_id` 需要你自己从 QQ 事件里取得。
- `access_token` 默认有效期 7200 秒，集成会在到期前 5 分钟自动刷新。

## 许可证

本项目采用 MIT 许可证，详见 [LICENSE](LICENSE)。
