# 小红书授权素材归档 Plugin

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个面向 Codex、DeepSeek 等支持 Agent Skills 工作流的项目，用于归档用户本人拥有或已经获得明确授权的小红书素材。

仓库现在包含两个相互独立的 Skill：

- `xhs-public-note-assets`：公开图文笔记及轮播图片；
- `xhs-authorized-shop-assets`：本人或已授权店铺的商品详情图与当前可见价格。

两个 Skill 都会保留原始图片字节和页面顺序，并生成经过校验的 JSON/CSV 清单。它们不处理订单、库存修改、商品发布、视频下载、去水印、验证码绕过或未经授权的批量采集。

## 一条命令快速安装

Windows 使用 Python 3：

```bat
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))"
```

macOS / Linux：

```bash
python3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))"
```

这条命令只安装两个 Skill 到当前用户的 `~/.agents/skills`，使用纯 Python 标准库，不安装 XHS-Downloader 或 Python 依赖。安装后若未立即显示，请重启 Agent。

更新已有安装时加入 `--replace`：

```bat
py -3 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))" --replace
```

安装器不会静默覆盖旧版本；使用 `--replace` 时会先把旧目录改名为带时间戳的备份。

## 仓库结构

```text
skills/xhs-public-note-assets/
  SKILL.md
  agents/openai.yaml
  scripts/
    bootstrap_xhs_downloader.py
    configure_cookie.py
    build_capture_from_mcp.py
    materialize_export.py
    validate_export.py
  references/
skills/xhs-authorized-shop-assets/
  SKILL.md
  agents/openai.yaml
  scripts/
    materialize_shop_export.py
    validate_shop_export.py
  references/
.codex-plugin/plugin.json
install.py
tests/
```

本仓库不应包含任何实际下载素材、Cookie、Token、账号专属数据、浏览器配置或个人绝对路径。

## 通过 Agent 安装

也可以让 Codex 的 `$skill-installer` 从 GitHub 安装以下路径：

```text
skills/xhs-public-note-assets
skills/xhs-authorized-shop-assets
```

仓库同时提供 Plugin 清单，支持一次发现两个 Skill。官方 OpenAI 文档建议，多 Skill 分发优先使用 Plugin；直接 Skill 安装仍保留用于本地开发和跨 Agent 兼容。

## 可选：配置图文下载 MCP

店铺抓取主要使用登录后的可见浏览器页面，不要求 XHS-Downloader。只有希望使用 MCP 加速图文笔记下载时，才需要安装该运行环境。

一条命令同时安装 Skill 和 XHS-Downloader 运行环境：

```bat
py -3.12 -c "import urllib.request; exec(urllib.request.urlopen('https://raw.githubusercontent.com/K1ngq1/xhs-note-downloader-skill/main/install.py').read().decode('utf-8'))" --with-runtime
```

XHS-Downloader 是独立的 GPL-3.0 依赖，本仓库不复制或打包其源码。运行时安装需要 Git 和 Python 3.12；检测到 `uv` 时会优先使用它安装依赖，否则回退到 `pip`：

```text
python skills/xhs-public-note-assets/scripts/bootstrap_xhs_downloader.py \
  --python /path/to/python3.12 \
  --install-dir /path/to/XHS-Downloader-2.7 \
  --installer auto
```

安装脚本生成的本地启动器会：

- 固定已经测试的 `fastmcp==2.14.5` 接口版本；
- 仅监听 `127.0.0.1:5556`，不会暴露到局域网；
- 兼容当前小红书页面状态中的 `new Map([])` 等值；
- 将上游源码及其 GPL 许可证与本 MIT 仓库保持分离。

使用生成的 `.venv` Python 运行 `run_mcp_local.py`，然后在 Codex 桌面版中配置：

```text
名称：xhsDownloader
传输方式：Streamable HTTP
URL：http://127.0.0.1:5556/mcp/
```

## 可选 Cookie

部分公开笔记需要当前有效的 `xsec_token`，获取它有时需要已登录的主页会话。只有用户主动选择时才应私密配置 Cookie：

```text
python skills/xhs-public-note-assets/scripts/configure_cookie.py \
  --settings /path/to/XHS-Downloader-2.7/Volume/settings.json
```

终端输入不会回显。辅助脚本会清除意外混入的回车、换行和制表符，并且不会打印 Cookie 值。

不要把 Cookie 粘贴到聊天中，也不要把它放进命令参数、日志、清单或 Git 仓库。如果 Cookie 曾出现在任何日志或输出中，请立即重新登录并更换 Cookie。

## 使用方法

中文提示示例：

```text
使用 $xhs-public-note-assets 归档这篇已授权的小红书图文笔记，并生成经过校验的素材清单。
```

店铺示例：

```text
使用 $xhs-authorized-shop-assets 归档我已授权店铺的商品详情图和当前可见价格。
```

处理账号主页时，Skill 会先建立完整笔记清单，只处理已经授权的 `normal`/图文笔记，再将包含临时 `xsec_token` 的完整 URL 直接交给 MCP。导出的清单只保留规范化 URL，所有签名和追踪查询参数都会被移除。

处理店铺时，Skill 会先建立商品清单，再逐一读取商品详情图和页面当前显示价格。价格始终带采集时间，并保留区间、促销和规格歧义；不会推断一个不存在的统一价格。

## 使用边界

- 可以处理用户本人发布的公开图文笔记。
- 可以处理用户已获得明确授权的其他账号公开图文笔记。
- 可以处理用户本人管理或已经获得店主授权的店铺商品详情图与可见价格。
- 不应采集私密、已删除或正常会话无法访问的内容。
- 不支持未经授权地批量下载其他用户内容。
- 不支持未经授权的竞品店铺批量采集。
- 遇到登录阻断、验证码、限流或访问控制时立即暂停，不尝试绕过。
- 图片保持原始格式和字节，不放大、不转码、不去除水印。

## 已验证行为

当前集成已使用 XHS-Downloader 2.7 对一篇包含五张图片的 `normal` 笔记完成真实前向测试。五张 JPEG 均成功下载到本地、可正常解码，尺寸均为 `3600 × 4800`，且 SHA-256 哈希互不重复。仓库未包含测试图片或账号数据。

以上结果只代表当前兼容性测试，不保证小红书接口未来不会变化。

## 开发与测试

```text
python -m pip install Pillow
python -m unittest discover -s tests -v
python scripts/validate_skill.py
```

发布前还应分别运行 Codex `skill-creator/scripts/quick_validate.py` 校验两个 Skill，并使用 `plugin-creator/scripts/validate_plugin.py` 校验仓库根目录。

## 许可证

本仓库使用 MIT License。XHS-Downloader 仍受 GPL-3.0 约束；导出内容的权利归内容所有者所有，并应遵守适用的平台规则。
