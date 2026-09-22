# 📰 AstrBot Daily News

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](CONTRIBUTING.md)
[![Contributors](https://img.shields.io/github/contributors/anka-afk/astrbot_plugin_daily_news?color=green)](https://github.com/anka-afk/astrbot_plugin_daily_news/graphs/contributors)
[![Last Commit](https://img.shields.io/github/last-commit/anka-afk/astrbot_plugin_daily_news)](https://github.com/anka-afk/astrbot_plugin_daily_news/commits/main)

</div>

<div align="center">

[![Moe Counter](https://count.getloli.com/get/@DailyNewsPlugin?theme=moebooru)](https://github.com/anka-afk/astrbot_plugin_daily_news)

</div>

每日 60 秒新闻推送插件 - 自动推送每日热点新闻，让你的群聊成员快速了解全球大事！

## v2.2.1：多栏目合并发送

- 图片模式：所有选中栏目合并为一张图，不再逐栏目发图；4 个及以上栏目采用双栏分区布局。
- 文字模式：合并为一条消息，按栏目分区，注明各自数据日期或获取时间。
- 图文模式：一张汇总图 + 一段汇总文字放入同一个 MessageChain，每个接收目标只调用一次平台发送接口。平台适配器可能仍将混合消息显示为多个气泡，插件不能保证各平台的 UI 行为。
- 图片标题最多展示三行，超出以省略号标记；文字汇总限制在约 3500 字符以内，公平分配各栏目篇幅，必要时省略条目、截短标题或省略链接，并提供单独查询命令。不通过多次发送规避长度限制。
- 原始来源抓取和缓存逻辑不变；不可用栏目集中标注在汇总末尾，所有栏目失败则发送一条明确提示。图片失败时整体降级为一条文字消息。
- 单独获取 60 秒早报时保留原图/旧海报配置，多栏目图片始终在本地合成。
- 更新或重载插件后生效。实际消息长度和图片尺寸限制仍取决于接入平台。

## v2.2.0：内置 12 个栏目，无需填写链接

新增栏目通过开源 [60s API](https://github.com/vikiboss/60s) 聚合，不是各平台的官方授权 API。公共实例没有可用性保证；热榜只反映讨论热度，不代表内容已经核实。

| 查询代号 | 栏目 | 定时默认 |
|---|---|---|
| `60s` | 每日60秒新闻（综合早报） | 开启 |
| `it` | IT之家资讯（科技资讯） | 开启 |
| `it_rank` | IT之家日榜（科技榜单） | 关闭 |
| `ai` | AI资讯快报（AI资讯） | 开启 |
| `hn` | Hacker News（开发者资讯） | 关闭 |
| `weibo` | 微博热搜（热榜） | 关闭 |
| `zhihu` | 知乎热榜（热榜） | 关闭 |
| `baidu` | 百度热搜（热榜） | 关闭 |
| `toutiao` | 今日头条热榜（热榜） | 关闭 |
| `douyin` | 抖音热榜（热榜） | 关闭 |
| `bili` | B站热搜（热榜） | 关闭 |
| `tieba` | 贴吧热议（热榜） | 关闭 |

### 直接使用

- `/news_sources`：列出全部内置栏目及定时启用状态。
- `/news 微博`、`/news 科技`、`/news ai`、`/news hn`：查询指定栏目，默认文字。
- `/news ai image`、`/news it all`：图片或图文模式。
- `/news all`：查询当前启用的定时栏目，不是强制抓取全部 12 个。
- `/get_news text`：兼容原有 60 秒早报命令。
- `/get_news text zhihu`：使用原命令指定新栏目。
- `/push_news text ai`：管理员向配置的所有目标推送指定栏目。
- `/push_news all`：管理员向所有目标推送已启用栏目。

### 配置与升级

在 AstrBot 插件配置中展开「内置栏目开关」，直接开关栏目，无需 RSS 链接或 Token。默认定时推送「60秒早报 + IT之家资讯 + AI快报」；只想保持原来的推送量，请关闭 IT 和 AI。

每个新增栏目默认 5 条，可设置 1–10 条；原有 60 秒新闻保持完整。缓存默认 600 秒，可设置 60–3600 秒。开关只控制定时推送及 `all`，不禁止用户单独查询关闭的栏目。

新增栏目的图片在本地绘制，使用仓库自带字体，不依赖上游提供海报。60 秒早报仍可选上游原图或原来的本地海报；上游原图失败会尝试本地绘制，绘图也失败则降级文字。纯文字模式不会下载或绘制图片。

数据标注上游实际日期；热榜等没有统一发布日期的栏目只标注获取时间。AI 快报可能默认返回前一天，不会改成今天。文字带有原文链接；同一栏目内相同标题去重，不做跨平台事件语义合并，也不自动生成 AI 摘要。

### 容错和权限

各栏目独立缓存、独立错误冷却（60秒）、同源并发查询合并；最多并行抓取 3 个栏目。单请求超时 6 秒，获得并发名额后单栏目最多等待 18 秒；启用很多栏目时总耗时可能更长。公共实例不支持某个接口、限流或错误时会尝试内置备用实例；实例相互不保证内容独立，平台级故障可能全部失败。

一个栏目失败不阻断其他栏目，会明确提示哪些栏目不可用。不把历史过期缓存冒充新内容。手动群发 `/push_news` 现限制为 AstrBot 管理员，避免普通用户群发刷屏；查询命令仍可正常使用。发送失败会反馈实际结果，不再笼统报告全部成功。

升级或修改配置后请重启/重载插件。源代码测试不能替代你实际平台中的消息发送测试。B站热搜在接入检查时出现上游错误，默认关闭，但可手动尝试；不要假定所有公共接口始终可用。

---

## 📢 通知

### 🎉 现在支持全平台推送 (2025-5-13), 配置方式也同样更新了, 参见下方

### 🎉 现在支持本地绘制每日新闻图片(当然也可选 api, 目前 api 的信息源不再提供图片服务, 也许可以等待恢复)

## ✨ 功能特性

- 🕒 支持定时推送，每日固定时间更新
- 📊 图文并茂，内容丰富
- 🔄 支持手动触发更新
- 🎯 支持多群组推送
- 📱 同时支持图片与文字模式
- 🌐 数据源可靠稳定

# 💡 常见问题

为什么修改配置后插件不生效？

- 请确保在修改配置后重启插件以使更改生效(这是必须的)。

## 🛠️ 配置说明

在插件配置中设置以下参数:

```json
{
  "target_groups": {
    "description": "需要推送60s新闻的群组唯一标识符列表",
    "type": "list",
    "hint": "填写需要接收60s新闻推送的群组唯一标识符，如: 你的平台名称(自己起的):GroupMessage:1350989414, napcat:FriendMessage:123456, telegram:FriendMessage:123456",
    "default": ["这里填你的平台名字:GroupMessage:这里填写你的群号"]
  },
  "push_time": {
    "description": "推送时间(以服务器时区为准)",
    "type": "string",
    "hint": "填写推送的时间，如: 08:00, 12:30, 18:00",
    "default": "08:00"
  },
  "show_text_news": {
    "description": "是否显示文字新闻",
    "type": "bool",
    "hint": "是否显示文字新闻，默认隐藏",
    "default": false
  },
  "use_local_image_draw": {
    "description": "是否使用本地图片绘制",
    "type": "bool",
    "hint": "是否使用本地图片绘制，为否则使用api获取图片",
    "default": false
  }
}
```

### 🛠️ 参数说明

下面是一份参数对照表:
| 参数名称 | 类型 | 默认值 | 描述 |
|----------------------|--------|----------------------------|--------------------------------------------------------------|
| target_groups | list | ["aiocqhttp:GroupMessage:这里填写你的群号"] | 需要推送 60s 新闻的群组唯一标识符列表 |
| push_time | string | "08:00" | 推送时间(以服务器时区为准) |
| show_text_news | bool | false | 是否显示文字新闻，默认隐藏 |
| use_local_image_draw | bool | true | 是否使用本地图片绘制，为否则使用 api 获取图片 |

群聊唯一标识符分为: 前缀:中缀:后缀

# AstrBot 4.0 及以后群聊前缀直接填你自己起的名字, 例如我连接了 napcat 平台, 起名字叫"困困猫", 那么前缀就是"困困猫"!

AstrBot 4.0 及以前:

**下面是所有可选的群组唯一标识符前缀:**

| 平台 | 群组唯一标识符前缀 |
|------------------|-------------------------------------|
| qq, napcat, Lagrange 之类的 | aiocqhttp |
| qq 官方 bot | qq_official |
| telegram | telegram |
| 钉钉 | dingtalk |
| gewechat 微信(虽然已经停止维护) | gewechat |
| lark | lark |
| qq webhook 方法 | qq_official_webhook |
| astrbot 网页聊天界面 | webchat |

**下面是所有可选的群组唯一标识符中缀:**

| 群组唯一标识符中缀 | 描述 |
|----------------------|--------|
| GroupMessage | 群组消息 |
| FriendMessage | 私聊消息 |
| OtherMessage | 其他消息 |

**群组唯一标识符后缀为群号, qq 号等**

下面提供部分示例:

1. napcat 平台向私聊用户 1350989414 推送消息, 我将平台命名为困困猫

   - `困困猫:FriendMessage:1350989414`

2. napcat 平台向群组 1350989414 推送消息

   - `aiocqhttp:GroupMessage:1350989414`

3. telegram 平台向私聊用户 1350989414 推送消息

   - `telegram:FriendMessage:1350989414`

4. telegram 平台向群组 1350989414 推送消息
   - `telegram:GroupMessage:1350989414`

## 📝 使用命令

### 查看插件状态

```
/news_status
```

显示当前配置的目标群组、推送时间、是否显示文字新闻，以及距离下次推送的剩余时间。

### 手动推送新闻

```
/push_news [模式]
```

支持的模式:

- `image` - 仅推送图片新闻
- `text` - 仅推送文字新闻
- `all` - 同时推送图片和文字新闻（默认）

此命令会将新闻推送到配置的所有目标群组。

### 用户手动获取新闻

```
/get_news [模式]
```

支持的模式:

- `image` - 仅推送图片新闻
- `text` - 仅推送文字新闻
- `all` - 同时推送图片和文字新闻（默认）

此命令会将新闻发送至请求获取新闻的用户会话。

## 🔄 版本历史

- v1.0.0
  - ✅ 实现基础的新闻监控与推送
  - ✅ 支持图片和文字两种模式
  - ✅ 支持定时和手动推送功能
  - ✅ 多群组推送支持
- v1.0.1
  - ✅ 修复当消息推送平台和 astrbot 不在一个环境中时不能推送图片的 bug
- v2.0
  - ✅ 支持全平台推送
  - ✅ 支持本地绘制每日新闻图片
  - ✅ 优化配置方式
- v2.1.0
  - ✅ 新增备用API域名
  - ✅ 新增用户手动获取新闻的指令
  - ✅ 修复插件卸载或停用时未销毁定时器的问题

## 💡 使用提示

1. 为获得最佳体验，建议将推送时间设置在早晨（如 08:00），帮助群成员快速了解每日新闻
2. 如果群内成员更喜欢文字阅读，可以将 `show_text_news` 设为 true
3. 使用 `/news_status` 命令可随时查看插件运行状态和下次推送时间
4. 如遇特殊情况需要立即全局推送新闻，可使用 `/push_news` 命令手动触发
5. 如用户想自行获取新闻，可使用 `/get_news` 命令手动获取

## 👥 贡献指南

欢迎通过以下方式参与项目：

- 🐛 提交 Issue 报告问题
- 💡 提出新功能建议
- 🔧 提交 Pull Request 改进代码

## 🌟 鸣谢

- 感谢 [每日 60 秒新闻 API](https://60s-api.viki.moe/v2/60s) 提供的数据支持
- 感谢所有为这个项目做出贡献的开发者！

---

> 信息知天下，六十秒读懂世界 📰
