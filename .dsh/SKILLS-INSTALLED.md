# 自定义技能安装记录（Skills installation manifest）

安装日期：2026-01（本次会话）
安装者：DeepSeek Harness agent
状态：**已实测通过 23/23 项自检**

## 1. 安装位置

技能同时安装到两个 DSH 技能根目录（`project-dsh` 排名 100、`user-dsh` 排名 400），内容完全一致：

| 作用域 | 路径 | 生效范围 |
|---|---|---|
| 本仓库 | `.dsh/skills/` | 仅在当前 git 仓库内可用 |
| 用户级（全局） | `C:\Users\16240\.dsh\skills\` | 本机所有项目可用 |

用户级目录在当前沙箱下需要一次提权写入（NTFS 权限本身允许，是 DSH 工作区策略限制）。两个根目录的文件集合已核对为**完全一致（30 个文件）**。

## 2. 技能清单（8 个）

### 学术顶刊写作（对应需求 1）

| 技能 | 内容 | 附带脚本 |
|---|---|---|
| `academic-paper-writing` | Nature 及 Nature 系列、Science、Cell、PNAS、Lancet/NEJM、IEEE/ACM 的**整体架构**：漏斗/沙漏结构、每节每段的修辞任务、摘要与标题设计、图注逻辑、期刊格式限制 | — |
| `academic-language-editing` | **语法、时态语态、hedging 标定、用词、术语一致性、衔接、标点与单位/统计格式**，以及 AI 味与非母语表达清理 | `academic_lint.py`（71 条规则，离线） |
| `academic-citations-and-references` | 引用体例机制（上标数字/编号/作者-年份）、文献表字段完整性、孤立引用与未引用条目、重复 DOI、预印本与撤稿标记、引用准确性核查 | `ref_audit.py`（.bib/.tex/.md/.docx） |
| `academic-submission-and-revision` | 投稿信、significance statement、highlights、graphical abstract 说明、CONSORT/STROBE/PRISMA/ARRIVE 清单、数据与代码可用性声明、审稿意见逐条回复与修订策略 | — |

配套参考文档：`journal-conventions.md`（各刊体例对照）、`section-blueprints.md`（逐段模板）、`self-audit-checklist.md`（七阶段自审）、`style-rules.md`、`tense-and-voice.md`、`word-choice.md`。

### 修图 / 修 PPT / 编译 PDF（对应需求 2）

| 技能 | 内容 | 附带脚本 |
|---|---|---|
| `publication-figures` | 科研图像处理与出版级图件：无损式校正、按期刊像素预算缩放、多面板拼版＋面板字母＋比例尺＋箭头、色盲安全配色、TIFF/PNG/PDF/EPS 导出与期刊规范核查 | `figtool.py`（JSON 操作清单，确定性可复现）、`figqa.py`（期刊规范核查） |
| `slide-editing` | 修 PPT：叙事结构先于像素、单页信息密度、字体与对比度、演讲备注与 backup slides、图片替换与媒体卫生、导出 PDF。底层 `.pptx` 读写按内置 `office-pptx` 技能执行 | — |
| `pdf-compilation` | LaTeX/Markdown/Office → PDF 全流程：多趟编译循环（引擎→bib→索引→重跑）、原始日志排错、CJK 与字体嵌入、PDF 交付校验 | `texbuild.py`（编译循环＋日志分诊）、`pdfqa.py`（纯 Python PDF 结构分析） |

配套参考文档：`integrity-checklist.md`（图像诚信与投稿筛查）、`image-techniques.md`（校正顺序、像素预算、配色与格式）、`tex-troubleshooting.md`（错误目录）、`build-recipes.md`（可复制模板）。

### STEP 结构文件读写与输出（对应需求 3）

| 技能 | 内容 | 附带脚本 |
|---|---|---|
| `step-file-engineering` | ISO 10303-21 / AP203 / AP214 / AP242 的 `.step`/`.stp`：头部与实体图解析、产品与 BOM/装配树提取、单位换算、颜色与图层、参数与字符串安全编辑（含变更日志）、保真回写、结构校验；无核几何信息提取；CAD 内核桥接 | `step_tool.py`、`step_geom.py`、`cad_bridge.py` |

**三层能力与当前实测状态**：

| 层级 | 能力 | 本机状态 |
|---|---|---|
| 1 文本/实体图 | 解析、查询、BOM、单位、颜色、改名/改参数/脱敏、校验、**字节保真回写** | ✅ 可用（纯 Python，零依赖） |
| 2 无核几何 | 包围盒、尺寸、质心、点云导出、XY/XZ/YZ/ISO 投影 SVG | ✅ 可用（numpy） |
| 3 真实 CAD 内核 | STL 导出、体积/表面积/质量属性、布尔、倒角、协议转换 | ❌ **本机无内核且无网络**，`cad_bridge.py` 会如实报告并给出安装命令，绝不近似 |

关键实测结论（见第 4 节）：
- `step_tool.py` 对未修改的实体**逐字节保留原文**，改名操作产生的 diff 只有 1 行；
- 中文产品名编码为 `\X2\7D2756FA4EF6\X0\`，8 组编码/解码往返全部通过；
- **复合实例（complex instance）** 如 `(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MILLI.,.METRE.))` 被原样保留，不会被破坏性重写（这是 STEP 工具最常见的致命 bug）；
- CRLF/LF 行尾在回写时保持不变。

配套参考文档：`step-format.md`（实体图与编辑安全规则）、`cad-kernel-setup.md`（内核安装与离线替代方案）。

## 3. 环境事实（影响可用能力）

| 项目 | 实测值 |
|---|---|
| Python | `C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe`（3.12.14） |
| 已装 Python 库 | Pillow 12.3、numpy 2.3.5、pandas 3.0.1、python-docx、python-pptx、openpyxl、lxml、XlsxWriter |
| **未装** | matplotlib、PyMuPDF、cairosvg、reportlab、CAD 内核（OCP/cadquery/FreeCAD）、trimesh |
| TeX | TeX Live 2026，`C:\texlive\2026\bin\windows`（pdflatex/xelatex/lualatex/latexmk/bibtex/biber/makeindex/dvisvgm） |
| **未装 CLI** | pandoc、Ghostscript、qpdf、ImageMagick、Inkscape、ffmpeg |
| 网络 | **不可达**（PyPI、清华/阿里镜像、公网均失败）→ 无法从远程仓库安装技能或 Python 包 |

因此：所有技能均为**本地自建 + 本地实测**，没有从网络下载任何内容。

## 4. 自检与复现

自检脚本：`.dsh/skills/_verify/_verify.py`（下划线开头，不会被技能发现机制扫描为技能）

```powershell
$py = "C:\Users\16240\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
& $py ".dsh\skills\_verify\_verify.py" `
      --skills ".dsh\skills" `
      --artifacts ".dsh\_selftest\verify" `
      --python $py
```

当前结果：**PASS 23/23**，覆盖 9 个脚本的文本输出、JSON 输出、错误路径，以及 STEP 字节保真回写。

单独试用（示例）：

```powershell
# 学术语言检查（71 条规则，支持 .txt/.md/.tex/.docx）
& $py ".dsh\skills\academic-language-editing\scripts\academic_lint.py" 稿件.docx --severity medium

# 参考文献审计
& $py ".dsh\skills\academic-citations-and-references\scripts\ref_audit.py" refs.bib

# 图件：先探测再按清单编辑，最后按期刊规范核查
& $py ".dsh\skills\publication-figures\scripts\figtool.py" probe panel.png --json
& $py ".dsh\skills\publication-figures\scripts\figtool.py" apply panel.png --ops edits.json --out out
& $py ".dsh\skills\publication-figures\scripts\figqa.py" Figure1.tif --journal nature

# PDF：编译循环 + 交付校验
& $py ".dsh\skills\pdf-compilation\scripts\texbuild.py" main.tex --outdir build --pdf out.pdf
& $py ".dsh\skills\pdf-compilation\scripts\pdfqa.py" out.pdf --require-fonts-embedded

# STEP：概览 → 校验 → 编辑 → 复验 → 几何
& $py ".dsh\skills\step-file-engineering\scripts\step_tool.py" summary model.step
& $py ".dsh\skills\step-file-engineering\scripts\step_tool.py" validate model.step --strict
& $py ".dsh\skills\step-file-engineering\scripts\step_tool.py" rename model.step --product PART-001 --to "支架-A" --out model_v2.step
& $py ".dsh\skills\step-file-engineering\scripts\step_geom.py" bounds model.step --json
& $py ".dsh\skills\step-file-engineering\scripts\cad_bridge.py" --probe
```

## 5. 已知边界（诚实声明）

1. **CAD 几何运算（第 3 层）本机不可用**。体积、表面积、质量属性、STL、布尔、倒角、AP203↔AP242 转换都需要 OpenCASCADE。装上 cadquery 或 FreeCAD 后 `cad_bridge.py` 会自动切到第 3 层；安装命令见 `references/cad-kernel-setup.md`。
2. **期刊字数/图数上限是"典型值"**，不是承诺。技能内明确要求以投稿时的最新作者指南为准，并已把这一点写进技能正文与参考文档。
3. **学术语言检查器是规则式的**，会漏掉需要语义判断的问题（例如 Methods 里合法的被动语态）。技能正文明确要求把每条命中当作"待确认"而非判决。
4. **PDF 字体嵌入检测是宽松扫描器**：遇到无法判定的结构会返回 `unknown` 而不是猜测，需在 PDF 阅读器里复核。
5. **无法验证 DOI、撤稿状态、引用内容准确性**（无网络）。引用审计只做形式与一致性检查，并在报告顶部显式标注这一点。
6. matplotlib 未安装，因此「按期刊规范生成统计图」目前需借助 LaTeX/PGF 或 `figtool.py` 的合成能力；装上 matplotlib 后可扩展。

## 6. 与内置技能的关系

内置技能 `office-docx` / `office-pptx` / `office-xlsx` 未被修改。`slide-editing`（PPT 内容与设计）与 `pdf-compilation`（PDF 交付）在设计上**引用并复用**它们处理 Office 文件的机制，不重复实现、也不冲突。
