# 📰 AstrBot Daily News

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey)
[![PRs Welcome](https://img.shields.io/badge/PRs-Welcome-brightgreen)](CONTRIBUTING.md)
[![Contributors](https://img.shields.io/github/contributors/anka-afk/astrbot_plugin_daily_news?color=green)](https://github.com/shizegame/astrbot_plugin_daily_news/graphs/contributors)
[![Last Commit](https://img.shields.io/github/last-commit/anka-afk/astrbot_plugin_daily_news)](https://github.com/shizegame/astrbot_plugin_daily_news/commits/main)

</div>

<div align="center">

[![Moe Counter](https://count.getloli.com/get/@DailyNewsPlugin?theme=moebooru)](https://github.com/shizegame/astrbot_plugin_daily_news)

</div>

每日 60 秒新闻推送插件 - 自动推送每日热点新闻，让你的群聊成员快速了解全球大事！

## v2.4.2：修复配置类型导致的加载失败

- v2.4.1 新增的 `language_label_style` 类型误写成 `str`，AstrBot 只支持 `int/float/bool/string/text/list/file/object/template_list/dict`，会在解析 `_conf_schema.json` 时抛 `TypeError: 不受支持的配置类型 str`，插件配置页/加载随之失败。已改为 `string`（默认 `title`，非法值按 `title` 处理）。
- 新增 `tests/test_conf_schema.py`：递归校验所有配置项类型合法、有 description、default 与类型一致，并断言 schema 默认值能被 `language_list`/`AISummarizer`/`WeatherClient` 直接接受、hint 里的范围与代码钳制一致。此类问题以后在测试阶段就会暴露。
- 运行时行为与 v2.4.1 一致；已调大的超时配置无需重设。

## v2.4.1：修复回退文档没有标题、多语言标题丢失

- **回退文档改成 Markdown**：AI总结超时/失败/关闭时，图片与翻译改用 `# 新闻与热榜汇总 · 日期` + `## 栏目 · 分类` + 编号条目的 Markdown 文档，不再是 `【栏目名 · 分类】` 纯文本。这就是“翻译之后大标题不见了、满屏【】”的原因——那份【】文本被翻译并渲染成图片。中文文字消息仍保留【】格式（聊天里不渲染 Markdown），`/news_raw` 不变。
- **标题由程序按语言生成**：`# 每日简报 · 日期`、`# Daily Digest · 日期`、`# 每日簡報 · 日期`、`# デイリーダイジェスト · 日期` 等，模型只翻译正文，标题不会被丢掉或改成括号。`language_label_style` 可选 `title`（默认，本地化大标题）/`bracket`（旧的【语言】前缀行）/`none`。
- **结构守卫**：译文标题数少于原文时，先把“只有括号的短行”按原文层级修复成 `#`/`##`；仍不足则该语言明确失败并提示，不发没有结构的整块文本。翻译提示词同时要求逐行保留 `#`、列表符号、`---`。
- **超时与并发**：`ai_summary_timeout` 默认120（上限300）、新增 `translate_timeout`（默认120）、`translate_concurrency`（默认2，1–4，多语言并发翻译）、`ai_summary_max_items`（默认20，缩短提示词）；`image_render_timeout` 默认90（上限300）；译文长度上限提高到20000。
- **更新后请手动调大超时**：已安装配置里的旧值（60）不会自动变更，建议 `ai_summary_timeout` 设 120–180、`translate_timeout` 设 120–180。自建文转图服务后 `image_render_timeout` 保持默认即可。
- 边界：以上均为离线契约测试验证（94项），真实模型超时表现、译文质量、平台收图仍需你更新重载后验收。

## v2.4.0：开场去重与多语言分开发送

- 修复开场白重复：系统提示词限定模型只输出新闻正文，程序对正文首尾重复的配置文案作空白/Markdown/标点容错去重，再统一加一次开场白和结束语。对常见改写问候也做边界清理，但任意语义改写不能保证全部识别。
- `multilingual_enabled` 默认开启，`news_languages` 默认 `["zh-CN", "en"]`，最多5种，按配置顺序发送，支持简/繁中文、英语、日语、韩语、法语、德语、西语、俄语、阿拉伯语。关闭多语言或仅留zh-CN可恢复单语言。
- 抓取和中文编辑只做一次，再翻译整份简报；每个语言一张独立图片，文字分次发送。图文模式每语言图片+文字一起发送。译文超过3200字符时按段落分条，而不是丢弃新闻或把所有语言挤在一张图上。
- 手动 `/news`、定时推送、管理员 `/push_news` 都使用语言配置。兼容 `/get_news`；`/news_raw` 始终不调用AI或翻译；`/news_image_test`仍只测试一张图。
- 翻译使用所选AstrBot模型，有额外调用成本；即使关闭AI总结，多语言翻译仍会使用模型。来源链接以占位符保护，缓存10分钟。翻译失败会明确跳过该版本，其余语言继续；图片失败只对该语言降级文字。
- 不同语言发送并非平台层面原子操作。一条消息失败仍继续后面的语言，最后报告部分发送失败。`/news_status` 显示配置语言和最近翻译结果。翻译质量/事实准确性仍需核实，程序检查不等同完整语言鉴别。
- 所有更新记录在 CHANGELOG.md；下方旧版“单张图片/一次发送”指旧版或当前单语言模式。

## v2.3.1：按 SeaSmall 正文流程生成完整简报

- 修复 `JSONDecodeError`：上一版额外要求模型输出 JSON，和 SeaSmall 的正文流程不一致。本版不解析模型输出的 JSON，直接使用简报正文。正常的 Markdown、小标题、段落和列表都支持。
- 参考其默认提示词和配置：按板块先概括、再列3–5条要点；重要条目附原始链接，正文目标1800字。标题、开场白、结束语由程序统一添加，避免遗漏，均可配置。新配置 `llm_prompt` 可编辑完整提示词，旧 `ai_summary_prompt` 仅作为补充偏好保留。
- `digest_sections` 设置板块名称/顺序，模型只根据实际素材归类，没有素材就省略。国内/国际不强行标“昨日”；开源项目不伪称日增星标榜。板块名称配置不等于已实现所有专属新闻源。
- 可选 Open-Meteo 天气：先打开 `weather_enabled`，再填写 `weather_city`（最多3个），可设置国家代码、预报时区、缓存时间及请求间隔。默认关闭且城市留空，不擅自指定上海。结果注明匹配地点、当地日期、时区、温度和降水概率。
- 天气只附加到当前全部启用栏目查询/推送中；单独查询知乎等不附加。城市缺失或接口失败时明确提示，其余新闻仍发送。预报时区不改变定时推送的服务器时区。
- `/news`：AI完整简报图片；`/news all text`：同份正文文字；`/news_raw`：绕过AI的原始素材。`/news_status` 显示AI及天气状态。
- 未配置模型时仍回退原始汇总；本次不修改已安装AstrBot配置。AI正文可能有误，程序去除外部图片及非素材链接，但不等同于事实核查。
- 每次版本更新记录在 [CHANGELOG.md](CHANGELOG.md)。以下旧版章节为历史记录，当前行为以本节为准。

## v2.3.0：AI编辑简报与三个来源修复

参考 SeaSmall 的「抓取 → AI总结 → 文转图」流程，默认开启 AI 总结，直接使用 AstrBot 已配置的文本模型，无需另外填 API Key（调用可能产生模型费用）。

- 模型提炼/去重每个栏目素材、每栏最多3条。输入是标题及已有摘要，不是已读取全文；每栏最多送入10条候选。AI摘要需谨慎核实，不代表事实核查。
- 可设置 `ai_provider_id` 指定提供商。留空时，手动查询使用当前会话模型，定时推送使用默认模型。兼容新版 `llm_generate` 和旧版 `text_chat`；显式指定的模型失败不会偷偷切换其他模型。
- 配置支持开关、编辑偏好和超时。空输出、格式错误、遗漏栏目、引用越界或模型失败会回退原始素材，并在简报内提示；`/news_status` 显示结果。取消任务不会被吞掉。
- 不传入聊天历史、不执行工具；来源内容作为不可信素材。模型返回结构化摘要，来源链接、提供方与日期由插件保留，模型不能另造引用地址。同素材同会话缓存10分钟（最多32份）。
- `/news` 默认一张AI简报图；`/news all text` 查看AI整理文字；`/news_raw`、`/news_raw ai` 绕过AI查看原始素材；`/news_image_test` 仍只测试渲染和发送。
- 知乎改为公开热榜直接接口，B站改为公开搜索热榜直接接口，失败再尝试60s聚合。公共接口仍可能限流/变更，无可用性保证。
- AI快报聚合接口空数据时，使用**量子位 RSS**作为明确标注的独立备用来源，仅保留近7天文章，并注明实际日期；不会把备用资讯伪装为原快报，也不会伪造“今日”日期。移除已无法解析域名的旧镜像。
- 天气、医药、政策、GitHub等完整板块扩展尚未包含，本版先落地AI整理及三个来源修复。

## v2.2.3：默认图片输出，使用 AstrBot 官方文转图

> 以下 v2.2.1 及更早章节的旧海报、原图和双栏绘图说明属于历史记录；当前渲染方式与配置以本节为准。

- `/news`、`/news all` 默认输出图片（可在「/news 默认输出模式」中修改）。`/news all image` 强制图片，`/news all text` 明确只发文字，`/news all all` 图文一次发送。
- 主要参考 [SeaSmall/daily-digest](https://github.com/SeaSmall/astrbot-plugin-daily-digest) 的流程：整份简报文本 → `await self.text_to_image(text, return_url=True)` → 图片消息。API 用法见 [AstrBot 官方文转图文档](https://docs.astrbot.app/dev/star/guides/html-to-pic.html)。这次采用 text_to_image，不是自定义 HTML 模板。
- URL 使用 `Image.fromURL`，本地图片路径使用 `Image.fromFileSystem`，不再把返回值当作 Base64。由 AstrBot 与平台适配器处理图片发送。
- 所有栏目（包括单独 60 秒早报）统一走 AstrBot 转图，旧配置 `use_local_image_draw` 不再使用。历史绘图文件保留，但主流程不再导入、不依赖它们，插件不再额外要求安装 Pillow。
- 转图需 AstrBot 自身的文转图后端正常可用；本插件不自动修改 AstrBot 全局渲染设置。后端返回图片 URL 时，机器人/平台还必须能访问该 URL；跨环境本地文件发送是否支持取决于适配器。
- 管理员运行 `/news_image_test` 可在不抓取新闻的情况下单独测试渲染与发送；`/news_status` 可查看默认模式、最近渲染状态及最近发送状态。渲染成功不等于平台已接收。
- 转图失败或超时会明确提示后降级成一条汇总文字，不会静默伪装为图片成功。平台发送失败会记录异常，不自动重复发送，以免部分已送达时刷屏。
- 本次优先修复图片输出；此前讨论的天气、医药、政策、AI 总结等完整简报扩展尚未在此版本实现。

## 安装与更新地址（v2.2.2）

本仓库是多源汇总增强版，安装时请使用：

```text
https://github.com/shizegame/astrbot_plugin_daily_news
```

插件 `metadata.yaml` 中的 `repo` 及版本信息已与本仓库同步，后续从本 fork 安装并按其元数据更新时应使用本 fork。插件内部名称保持 `astrbot_plugin_daily_news`，未改变配置识别名称。

原作者：[anka](https://github.com/anka-afk/astrbot_plugin_daily_news)；本 fork 的功能扩展与维护：shizegame。插件市场原作者条目、分类翻译、Star 数和缓存不由本仓库控制。从旧元数据安装的副本不会因 GitHub 上修改了一行而自动切换更新源；本次不修改已安装的插件或用户配置。

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
