# 小红书图文下载 Skill

[English](README.md) | [简体中文](README.zh-CN.md)

这是一个面向 Codex 桌面版的 Skill，用于导出用户本人拥有或已获得明确授权的小红书公开图文笔记素材。

Skill 使用外部 XHS-Downloader MCP 获取笔记信息和下载图片，保留原始图片字节及轮播顺序，并生成经过校验的 JSON/CSV 清单。它不处理店铺、价格、视频下载、去水印、私密内容、验证码绕过或未经授权的批量采集。

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
tests/
```

本仓库不应包含任何实际下载素材、Cookie、Token、账号专属数据、浏览器配置或个人绝对路径。

## 安装 Skill

让 Codex 从 GitHub 仓库安装以下 Skill 路径：

```text
skills/xhs-public-note-assets
```

安装后的 Skill 名称为 `xhs-public-note-assets`。

## 配置 XHS-Downloader MCP

XHS-Downloader 是独立的 GPL-3.0 依赖，本仓库不复制或打包其源码。安装辅助脚本需要 Git 和 Python 3.12：

```text
python skills/xhs-public-note-assets/scripts/bootstrap_xhs_downloader.py \
  --python /path/to/python3.12 \
  --install-dir /path/to/XHS-Downloader-2.7
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

处理账号主页时，Skill 会先建立完整笔记清单，只处理已经授权的 `normal`/图文笔记，再将包含临时 `xsec_token` 的完整 URL 直接交给 MCP。导出的清单只保留规范化 URL，所有签名和追踪查询参数都会被移除。

## 使用边界

- 可以处理用户本人发布的公开图文笔记。
- 可以处理用户已获得明确授权的其他账号公开图文笔记。
- 不应采集私密、已删除或正常会话无法访问的内容。
- 不支持未经授权地批量下载其他用户内容。
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

发布前还应使用 Codex `skill-creator/scripts/quick_validate.py` 校验 `skills/xhs-public-note-assets`。

## 许可证

本仓库使用 MIT License。XHS-Downloader 仍受 GPL-3.0 约束；导出内容的权利归内容所有者所有，并应遵守适用的平台规则。
