# MaaYuan 故障反馈助手

把“运行中截了一张图，不知道怎样说明问题”整理成有日志依据的反馈。

这是社区参与者提供的独立 Agent Skill，适用于 MaaYuan 桌面版。AI 协助收集日志、关联异常和整理说明，方便其他参与者或维护者继续排查。它不代表 MaaYuan 开发团队，也不是新的官方反馈入口。

**使用前建议复制一份完整的 MaaYuan 文件夹，保留原目录，让 AI 在副本中分析和尝试修复。** 技能默认只整理反馈；进一步修复需要使用者明确提出，并先确认副本。AI 的本地修改可能被后续更新覆盖，或与新版不兼容。即使本地验证成功，也不等于官方已修复。副本不包含模拟器或游戏账号的外部状态。

## 能得到什么

| 产物 | 用途 |
|---|---|
| `forum-post.txt` | 可直接复制到 QQ 频道的短反馈；不能传附件时仍能使用 |
| `report.md` | 含时间线、版本来源、日志证据和待确认项的详细报告 |
| 日志 ZIP | 选定文本日志、上述报告和文件清单，供进一步排查 |

脚本负责确定性采集与常见敏感信息脱敏，AI 负责分析和完成报告。脚本单独运行只生成报告骨架，不会自动诊断根因。仅凭截图或没有匹配日志时，报告会注明证据不足。

## 下载与安装

**不需要 GitHub 账号，也不要求安装 Git。** 下载下面的包，或使用 Code → Download ZIP 下载源码；也可以由他人通过网盘转发同一份安装包。网盘文件与 GitHub 文件的使用方式相同。

- [下载技能安装包 v0.1.0](https://github.com/zhimaheiye/maayuan-issue-helper/raw/refs/heads/main/downloads/maayuan-issue-helper-skill-v0.1.0.zip)：根目录就是 `SKILL.md`，包含脚本和参考资料。
- [下载完整源码包 v0.1.0](https://github.com/zhimaheiye/maayuan-issue-helper/raw/refs/heads/main/downloads/maayuan-issue-helper-source-v0.1.0.zip)：额外包含本文、设计说明、测试与打包工具。
- [SHA-256 校验值](downloads/SHA256SUMS.txt)：转发网盘时可一起提供。

| 软件 | 安装方式 |
|---|---|
| WorkBuddy 桌面版 | 技能页面 → 添加技能 → 上传技能，选择技能安装包 |
| Qoder | Extensions → Skills → Add Skills → Upload Skill，选择技能安装包 |
| Qoder IDE 等采用目录安装的版本 | 按该版本官方说明，将整个技能文件夹放到其 skills 目录；不要只复制 `SKILL.md` |
| 其他可读本地文件的 Agent | 解压源码包，让它读取 `skills/maayuan-issue-helper/SKILL.md`，并授权访问 MaaYuan 副本 |

操作入口核对日期：2026-10-26。依据 [WorkBuddy 官方文档](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)、[Qoder 官方文档](https://docs.qoder.com/qoder/skills) 和 [Qoder IDE 技能说明](https://docs.qoder.com/extensions/skills)。不同产品、版本和组织权限可能不同；目前未对所有宿主做实际导入测试。WorkBuddy 市场上架是另外一项流程，GitHub 发布不等于已上架市场。

本技能采用 `SKILL.md` 的 `name`、`description` 和 Markdown 指令，避免绑定某一家 Agent 的专用工具。通用格式不等于所有软件都会自动扫描任意目录。安装后确认技能已启用且 `scripts/collect.py` 与 `references/` 存在。

## 直接对 AI 这样说

安装后：

> 请使用 maayuan-issue-helper 帮我整理 MaaYuan 故障反馈。我的程序副本在“填写实际路径”，问题发生在“填写日期和大概时间”。我做了……，预期……，实际……。请先收集和分析日志，生成频道短文、详细报告和日志包，暂不修改程序。

未安装、直接解压使用：

> 请读取“解压目录/skills/maayuan-issue-helper/SKILL.md”，按其中流程处理。MaaYuan 副本在“填写实际路径”。问题是……。请先整理故障反馈，不修改程序。

需要能读取本机文件、执行 Python 的 Agent。纯网页聊天窗口或只上传一个 `SKILL.md`，通常不足以自动收集电脑里的日志。优先使用 MaaYuan 自带的 Python；采集器仅使用标准库，无需安装额外依赖。AI 软件的可用额度、费用和数据处理方式以软件本身为准。

## 如何反馈

1. AI 完成后，核对“操作、预期、实际”是否符合你遇到的问题，检查正文和日志是否仍有个人信息。
2. 按社区现有规则发布 `forum-post.txt` 内容。没有附件也可以先发文字。
3. 保存日志包。有需要且渠道允许时，再补充网盘链接和有效期；熟悉 GitHub 的用户也可提交到 [MaaYuan Issues](https://github.com/syoius/MaaYuan/issues)。本技能不会自动上传或替你发帖。

AI 判断是排查线索，不是已经确认的结论。MaaYuan 本体的问题沿用项目现有反馈方式；这个仓库的 Issues 用于技能自身的采集、脱敏和报告问题。请勿在本仓库公开个人原始日志。

## 采集范围与隐私

默认读取 `logs/log-*.log`、`debug/maa.log`、`debug/maa.bak.log`、`debug/custom/*.log`，提取 `interface.json` 的资源版本。保留原始行号，记录筛选、截断、读取失败和读取期间变化。

不默认复制完整配置、截图、游戏数据或安装包。规则脱敏能处理常见令牌、密码、账号字段、路径、邮箱、手机号、IP 等，但无法保证覆盖任意 OCR 文本、昵称或自定义格式，分享前仍需检查。截图需单独遮挡后提供。本地采集脚本不联网；AI 软件读取材料后的模型服务传输取决于所用软件，不应理解为全流程离线。

## 开发与打包

需要 Python 3.9+。在本仓库根目录运行：

```sh
python -m unittest discover -s tests -v
python tools/build_release.py
```

输出到 `downloads/`，采用明确文件白名单，不打包使用者日志、配置、测试临时数据或整个 MaaYuan。附 `SHA256SUMS.txt`，方便网盘转发后核对。源码包不包含下载包本身，避免递归打包；修改源文件后应重新运行打包脚本并同步提交下载包。

技能工作流见 [SKILL.md](skills/maayuan-issue-helper/SKILL.md)，设计依据见 [docs/design.md](docs/design.md)，社区提议草稿见 [docs/community-proposal.md](docs/community-proposal.md)。

## 许可

本仓库原创技能、脚本和文档采用 [MIT License](LICENSE)。MaaYuan 及相关软件的名称、代码与资产归各自项目所有；本仓库不打包它们。
