> **Doctor 裁定（2026-11-19 /conch AI4ME · AskUserQuestion 四问均取推荐）**：新落点按本方案推荐；AI4ME 留同名 Finder 替身（`_artifact_stage` 不留）；白泽周报看板命名随迁同批改为 `白泽周报看板-YYYY-MM-DD.html`（生成器跟改，存量 8 件改名，`_最新.html` 不改）；分三批执行——管制阶梯 11-20 起、赶 11-27 前，烛照 11-21～11-22（截止 11-23 09:30 PT），白泽与 `_artifact_stage` 11-23～11-26（先以 11-22 班为迁前基线）。每批前 Doctor 先在 Cowork 用 list_triggers 存档相关班的现行提示词。
> 起草：未参与实施的只读子代理（2026-11-19）；草稿原件 `$TMPDIR/conch_ai4me/plans/`。执行记录见 brain `logs/2026-11-19-AI4ME-conch审查.md` 及各批日志。

# 烛照九阴-outputs 迁出 AI4ME · 切换方案（CC 草稿 · 2026-11-19 · 只读起草，未执行）

> 依据：Doctor 11-18 裁定（`brain/logs/2026-11-18-AI4ME-conch审查.md` 四项）；格式按 `the-conch-maiden/references/migrate.md` 第 2、3 步。
> 本稿全程只读：未移动/修改任何文件，未跑 git 写操作、未跑 py_compile。证据标注：实读 / 实跑（只读命令） / 推断 / 未核。

## 〇 现状（实读）

- 目录 `~/Documents/AI4ME/烛照九阴-outputs/`：86M，41 个文件（含 1 个 `.DS_Store`）＝根目录最新一期 `烛照九阴日报_20261117.html` 1 份 + `archived/` 29 份 + `archived/_pre-snapshots/` 9 份 + `artifact/zhuzhao-jiuyin-daily.html` 1 份；另有空目录 `.claude/.cc-writes`（CC 运行留下）。全是 HTML 报告，没有 JSON/DB 之类的数据产物；无符号链接。
- 写入方：`Projects/Financial/烛照九阴/tools/gen_daily_report.py:40` `OUT_DIR = config.OUTPUT_ROOT / "烛照九阴-outputs"`；`config.py:76` `OUTPUT_ROOT = ZZJY_OUTPUT_ROOT 或 PROJECT_ROOT.parents[3]/"AI4ME"`；`config.py:29` `PROJECT_ROOT = Path(__file__).resolve().parent`。生成器 L4266–4290 写根目录、旧报移 `archived/`、同名旧报快照进 `archived/_pre-snapshots/`。
- `artifact/zhuzhao-jiuyin-daily.html` 不由生成器写，由 Cowork 云端班按提示词「看板推送」段写入（转换版「只能写在挂载区内（如 `~/Documents/AI4ME/烛照九阴-outputs/` 下的 artifact 子目录）」，见 `brain/.tmp/zhuzhao-prompt-backup-2026-11-12.md` 第 17 行），再由 `brain/.tools/artifact_split_zhuzhao.py` 读取拆分发布。
- `config.OUTPUT_ROOT` 另被 `tools/calibrate_risk_factors.py` L112/115、`tools/test_risk_function.py` L58 用来读「回调级别判别」（另案修）⇒ **不动 OUTPUT_ROOT，只给日报另立常量**。
- 云端运行环境（实读 prompt 备份）：整挂 `Documents` 于 `$HOME/mnt/Documents`，开工把 `~/Documents` 软链到挂载点，所以 `PROJECT_ROOT` 在云端解析为挂载区内真实路径，日报改写到项目目录后云端与 Mac 两边都能看到。
- 时区：Mac 本机为 America/Los_Angeles（`/etc/localtime` 实读）；下文时刻均为 PT。
- 项目仓 `git status`（只读）：有别的会话未提交改动（`scripts/integration_slots.py`、`data/…`、多份 `docs/daily_integration_*.json` 未跟踪）；本方案要改的 `config.py`、`tools/gen_daily_report.py`、`.gitignore` 当前干净。

## 一 方向与替换规则（待 Doctor 确认的三项见第七节）

**新落点（推荐）**：`~/Documents/Claude/Projects/Financial/烛照九阴/outputs/`，整个目录原样迁入，内部结构不变（根目录最新一期、`archived/`、`archived/_pre-snapshots/`、`artifact/`）。

理由：
1. Doctor 裁定原话是「AI4ME 留一个指向**项目目录**的快捷方式」；brain `CLAUDE.md` 文件落点规则把「某个项目的产物」归项目文件夹，把 Database 层限定为 recap.db、Raw-Recap 这类结构化库与语料。日报 HTML 不属 DB 层。
2. 有先例：风险日报的 `dashboard/risk-daily.html`、剑酒青丘的 `outputs/` 都放在项目目录里，`test_artifact_split_guards.py` 读风险日报也是读项目目录。
3. 写入方锚到 `PROJECT_ROOT`（`__file__` 所在目录），不用 `parents[N]` 推算层级，云端与 Mac 同解；云端班本来就要求 `烛照九阴` 可写，改完后不再依赖 AI4ME。
4. 同卷（`df` 两处同为 `/dev/disk3s5`），`mv` 是重命名，不复制、瞬时完成。

**不推荐 `Database/烛照九阴/日报/`**：不是 DB 层数据，和 Doctor「项目目录」原话不符；唯一好处是不进项目工作树。若 Doctor 介意项目目录变大（推断：每交易日约 2.2 MB，一年约 550 MB，另加快照），可改选它，本方案其余步骤只换路径前缀。

**数据产物与成品要不要分开**：目录里没有数据产物（烛照的数据在 `Database/烛照九阴/` 与项目 `docs/`、`data/`）。`artifact/` 是发布用的中间转换件，不是成品，但它的位置写在云端提示词和拆分器里，这次两处都要改；保持为 `outputs/artifact/` 子目录、不另拆，改动面最小。

**替换规则**：
- 现行引用：`AI4ME/烛照九阴-outputs` → `Claude/Projects/Financial/烛照九阴/outputs`（绝对路径 `/Users/lunarabbit/Documents/AI4ME/烛照九阴-outputs` → `/Users/lunarabbit/Documents/Claude/Projects/Financial/烛照九阴/outputs`；`~/Documents/...` 写法同理）。
- 一律不动：留痕（brain `logs/`、`agents/*/logs/`、`*.bak_*`、`_bak/`、`backups/`、`archived/`、`official_pre_sync_*`、`.tmp/prompt-fix-*`、`.tmp/*.pushed-*.jsonl`、`md5_baseline.txt`、GOTCHAS 硬证据行、决策记录背景行、经验库案例行、Codex `archives/`、`runs/`、`ai4me-migration-20261004/`、研究包 inputs、孔明证据）。
- `config.OUTPUT_ROOT` 与 `ZZJY_OUTPUT_ROOT` 不动（其余读方另案）。
- `gen_daily_report.py` L3206 是历史注释，不动。

**快捷方式形态（推荐）**：在 AI4ME 放一个 **Finder 替身（alias），名字仍叫 `烛照九阴-outputs`**，指向新目录。
- Finder 里双击直达项目目录，Doctor 习惯不变。
- 替身在 POSIX 层是普通文件：Python/shell 读不穿。漏改的读方会当场报错，不会悄悄读到；漏改的写方 `mkdir -p …/烛照九阴-outputs/artifact` 也会报 File exists 失败，不会在 AI4ME 悄悄重建旧目录（云端提示词若漏改，就是这个失败面）。
- **不推荐**同名符号链接：等于兼容链接，所有旧读写都会悄悄穿过去，违背 `migrate.md`「不做」第 1 条，也违背「AI4ME 报告不得被项目引用或消费」的本意。
- 次选：不同名替身（如 `烛照九阴日报→项目目录`）。代价是旧路径变成「不存在」，写方会 `mkdir` 静默重建旧目录，发现得更晚。
- `.webloc` / README 指针不推荐：.webloc 能用 file:// 打开但不直观；README 不能点进目录。

## 二 切换顺序表

| 步 | 谁 | 动作 |
|---|---|---|
| 0 | Doctor | 拍板第七节三问；约定窗口 |
| 1 | Doctor 在 Cowork（窗口前） | 读出云端班 `zhuzhao-market-fetch-daily-report`（`trig_01GfLb5GmuwSQdgtE91sX9Jr`）**现行提示词全文**，机器对拷存档（请求草稿 §5.3 第 1 步）。改动先不提交 |
| 2 | CC | 查并发：`find ~/Documents/AI4ME/烛照九阴-outputs -type f -mmin -120`；项目仓与 brain 跑只读 `git status`。有新写入就先问 |
| 3 | CC | 打快照 + 写迁移前清单（见第六节） |
| 4 | CC | 项目 `.gitignore` 加 `outputs/`（**先于移动**，防 86 MB HTML 进未跟踪区，被 `git add -A` 带走） |
| 5 | CC | `[ ! -e <新> ] && mv ~/Documents/AI4ME/烛照九阴-outputs ~/Documents/Claude/Projects/Financial/烛照九阴/outputs`；迁后清单与迁前逐行比对 sha256 |
| 6 | CC | 改同批 CC 侧现行引用（§4.1）：config.py、gen_daily_report.py、拆分器、守卫测试、云端正文镜像 SKILL.md、待推队列 4 行 |
| 7 | Doctor 在 Cowork | 提交步 1 准备好的提示词替换（§5.3），回读回执 |
| 8 | Doctor（Finder 或终端） | 在 AI4ME 建替身 `烛照九阴-outputs`（命令见 §5.4） |
| 9 | CC | 自验（第三节末）+ 可后改文档（§4.2）+ 决策记录追加新旧路径对照 + TODO 更新 |
| 10 | Doctor 转达 V.V. | §5.2 请求；V.V. 回执后 CC 回读 |
| 11 | CC 开子代理（未参与实施） | 按 `migrate.md` 第 1 步三种写法重扫，报残留与断链 |
| 12 | CC | 首次自然运行后核对（第三节末） |
| 13 | Doctor 终端 | commit/push（CC 给按清单的 `git add --pathspec-from-file=`，不用 `-A`） |

步 5–8 必须在同一个无班窗口里做完；步 9 起的文档与 V.V. 侧可以在窗口之后。

## 三 切换窗口

**相关班的触发时刻（实读；PT）**：

| 班 | 来源 | 触发 | 是否碰本目录 |
|---|---|---|---|
| `zhuzhao-market-fetch-daily-report` | Cowork 云端（镜像 `live/…/SKILL.md` 为正文真源） | `0 10 * * 1-5`（周一至周五 10:00；11-18 实际 18:05Z＝10:05 PST 触发，10:06 写报，18:10Z 登记待推） | **写**：日报、archived、artifact；读：拆分器 |
| `com.zhuzhao.marketdata`（launchd） | `~/Library/LaunchAgents` | 周一至周五 02:30 | 否（`mac_daily_marketdata.py` 无 OUT_DIR/AI4ME 引用，实跑 grep） |
| `com.zhuzhao.usclose`（launchd） | 同上 | 周一至周五 14:00 | 否 |
| `com.zhuzhao.ipo-rolling`（launchd） | 同上 | 每日 09:00 | 否 |
| `com.fuxi4ai.audit-harness.dispatch`（launchd） | 同上 | 每 60 s + 监视 inbox | 只在有审计请求点名 `zhuzhao-output` 资源时读（V.V. 侧，见 §5.2） |
| `com.lunarabbit.morning-post` | 同上 | `.plist.disabled`，休眠 | 读（休眠） |
| `~/.codex/automations` 7 个 | Codex | 无一引用本目录（实跑 grep：烛照/zhuzhao/AI4ME 0 命中） | 否 |
| 本机限期班 `update-all-tech-reversal-watch` | `~/.claude/scheduled-tasks` | — | 否（只把「烛照九阴」当经验索引检索词） |
| 其余 Cowork 云端班（mirror `live/` 25 个目录） | 镜像 | — | 否（`live/*/SKILL.md` 只有 zhuzhao 一班命中） |

**推荐窗口**：**周六 11-21 至周日 11-22（PT）**。zhuzhao 班周末不跑，下一次是周一 11-23 10:00 PT，跨侧改动（Cowork 提示词）有约 40 小时余量。**截止**：周一 11-23 09:30 PT 前步 5–8 全部完成并回读。
备选：周五 11-20 当班跑完后（核到 `烛照九阴日报_20261119.html` 写出、待推或发布已收尾，约 10:30 PT 后）至周一 09:30。工作日夜间窗口（当日 11:00 至次日 09:30）也可，但余量只有约 22 小时，Cowork 侧若没及时改就会撞班。
**避免**：任何工作日 09:30–11:00 PT。

**自验（步 9）**：
- `cd <项目> && python3 -B -c 'import config; print(config.REPORT_DIR, config.REPORT_DIR.is_dir(), config.OUTPUT_ROOT)'`：新目录存在，OUTPUT_ROOT 仍为 AI4ME。
- `python3 -B ~/Documents/Claude/brain/.tools/test_artifact_split_guards.py`：全 PASS（在临时 BRAIN_ROOT 里跑，读新的 ZZ_SRC，不碰盘上产物）。
- 迁后清单与迁前清单 sha256 逐行一致（40 个文件 + `.DS_Store`）。
- `[ -f ~/Documents/AI4ME/烛照九阴-outputs ] && [ ! -d ~/Documents/AI4ME/烛照九阴-outputs ]`：替身是文件不是目录。
- 可选重渲测试：`python3 -B tools/gen_daily_report.py --output $TMPDIR/zz_test --no-archive --no-deploy`，不写正式目录；会读真实库、耗时，Doctor 定是否跑。
- 三种写法重扫（步 11 由独立子代理做）。

**首次自然运行核对（周一 11-23 10:00 PT 班后）**：
- `outputs/烛照九阴日报_20261120.html` 写出，前一期移入 `outputs/archived/`；
- `outputs/artifact/zhuzhao-jiuyin-daily.html` mtime 为本班；拆分产物与发布（或待推行 html_path 为新路径）正常；
- `agents/烛阴/logs/2026-11-23-行情拉取与日报.md` 里的路径是新路径；
- AI4ME 下 `烛照九阴-outputs` 仍是替身、mtime 不变，没有被重建成目录；
- 日报里「不可用 / 缺数」项不比迁移前（20261117 那期）多。
核完之前 TODO 保留这一项。

## 四 CC 侧改动清单（逐文件:行；实读）

### 4.1 必须同批（不改下一班就坏）

| 文件 | 行 | 改法 |
|---|---|---|
| `Projects/Financial/烛照九阴/config.py` | L76 后新增 | `REPORT_DIR = Path(os.environ.get("ZZJY_REPORT_DIR") or (PROJECT_ROOT / "outputs"))`，注释写明「日报产出目录，2026-11 迁出 AI4ME；OUTPUT_ROOT 仍供回调级别判别等旧读方，另案修」。**L75–76 不动** |
| `…/烛照九阴/tools/gen_daily_report.py` | L40 | `OUT_DIR = config.REPORT_DIR` |
| 同上 | L16、L19、L4260、L4262、L2534 | 说明文字「AI4ME/烛照九阴-outputs」「写 AI4ME」「仅写 AI4ME」改为 `outputs/`（不影响行为，同批顺手改，免得误导）。L2523 那句「AI4ME 侧本地镜像」说的是 `Claude/Artifacts`，本身就写错了；改不改由 Doctor 定，不改不影响 |
| `…/烛照九阴/.gitignore` | 末尾新增 | `outputs/`（先于移动） |
| `brain/.tools/artifact_split_zhuzhao.py` | L29 | `DEFAULT_SRC = "Claude/Projects/Financial/烛照九阴/outputs/artifact/zhuzhao-jiuyin-daily.html"`（仍相对 Documents 根，`default_src()` 的推算不变） |
| 同上 | L52 | 注释同步 |
| `brain/.tools/test_artifact_split_guards.py` | L13 | `ZZ_SRC` 同步新路径 |
| `brain/references/scheduled-live-mirror/live/zhuzhao-market-fetch-daily-report/SKILL.md`（云端 8 个推看板班的**正文真源**，CC 改镜像＝改班正文） | L3、L12、L16、L18、L111、L113、L119（7 行） | L3 description「生成暖色日报到AI4ME」→「到项目 outputs/」；L12 必需可写目录改为 `Database`、`烛照九阴` 两者；L16 去掉 AI4ME；L18 `export ZZJY_OUTPUT_ROOT` 一条改为「日报已改写项目 `outputs/`（config.REPORT_DIR，按脚本位置解析，无需 env）」；L111 步骤 6 输出目录；L113 步骤 6.5 源文件目录；L119 约束里「AI4ME 日报输出」。改前按命名规则备份到同目录 `_bak/SKILL.md.bak_YYYY-MM-DD_outputs-move` |
| `brain/.tmp/pending-artifact-push.jsonl` | L3、L6、L11、L13（zhuzhao 4 行） | 这是待消费队列，不是只追加账本。二选一：①（推荐）窗口前由 Doctor 在 Cowork 说「补推看板」先把队列消费掉；② 没消费就把这 4 行的 `html_path` 按替换规则改写（4 行都指向同一个每日被覆盖的转换件，改写不丢信息）。已归档的 `pending-artifact-push.pushed-*.jsonl` 是留痕，不改 |

> `brain/.tmp/artifact-publish/zhuzhao-jiuyin-daily/manifest.json` 的 `source` 字段每次拆分都重写（现值还是 11-12 的 `/sessions/…` 路径），不手改，首班后自然更新。

### 4.2 可以后改（文档或休眠代码，不影响下一班）

| 文件 | 行 | 说明 |
|---|---|---|
| `Projects/Financial/烛照九阴/PRD.md` | L28 | 产出目录列。同行写的班时「07:00」与云端 cron 10:00 PT 不符，另记，不在本次范围 |
| `brain/烛照九阴/烛照九阴.md` | L25 | 项目 stub「产出目录」 |
| `brain/司南/architecture/系统概览.md` | L44 | 订阅分发上游路径 |
| `Projects/Financial/Event-Attribution-Ledger/研究材料/锚定-跟随流派/与烛照九阴日报的对位.md` | L59 | EAL 项目文档，按 EAL 流程改 |
| `Projects/司南/订阅分发/金融/观潮市场日评/build_dist_report.py` | L33 | 观潮线休眠。找不到输入时 `return 2` 并打印「未找到内部日报产物」，不会静默失败；建议同批顺手改，改法同样是写死新路径，或改为读 `烛照九阴/config.REPORT_DIR` |
| `brain/烛照九阴/architecture/决策记录.md` | 追加 | **烛照九阴没有 `迭代记录.md`**（项目仓与 brain 均实查无此文件），新旧路径对照建议写在这里一条，并在项目 README 写一句「产出目录 `outputs/`（已 gitignore）」 |
| `brain/TODO.md` | L29–30 | 收尾时更新「AI4ME 整理二、三期」条 |
| `brain/references/定时班冒烟前置节-模板.md` | L590 | 模板未落到现行班（live SKILL 无「冒烟」字样，实读）；将来启用时把 `AI4ME` 那项改为 `outputs` 或去掉。现在不改 |

### 4.3 留痕，不改（扫描命中按文件计）

`refs.txt` 中命中名「烛照九阴-outputs」的 221 个文件，分类结果：CC 现行·同批 5、CC 现行·可后改 6、V.V. 现行 7、CC 留痕 163、V.V. 留痕 40。另有 `config.py`（分段拼接，字面扫不到）、`.gitignore`（新增），不在这 221 个里。
- CC 留痕 163：`agents/烛阴/logs` 117 + `agents/句芒/logs` 1、brain `logs/` 9、`*.bak_*` 与 `backups/` 共 15、`official_pre_sync_2026-10-21/` 6、`.tmp/prompt-fix-2026-11-04/` 2、`.tmp/zhuzhao-prompt-backup-2026-11-12.md`、`.tmp/*.pushed-*.jsonl` 2、`staging/…SKILL.new.md`（11-01 旧稿）、`logs/app.log`、`md5_baseline.txt`、`docs/2026-11-17-课件依赖清单.md`、`经验库.md` L3748、`GOTCHAS.md` L1052（L923 状态行）、`决策记录.md` L425 等。
- 与 `findings.md` 记的「现行引用 144 处」口径不同：那次把烛阴每日班日志也算进了现行；按 `migrate.md` 分类，班日志是留痕。

## 五 跨侧请求草稿（Doctor 转达）

### 5.1 三类改动汇总
- CC 侧：§4.1 共 7 个文件（config.py、gen_daily_report.py、.gitignore、拆分器、守卫测试、镜像 SKILL.md 7 行、待推队列 4 行）；§4.2 共 8 处，可后改。
- V.V. 侧：5 组文件，见 5.2。
- Cowork 云端：1 个班 `zhuzhao-market-fetch-daily-report`，提示词里至少 1 处（11-12 改版前的备份有 1 处；11-12 改版后的现行全文镜像里没有，**处数未核**），见 5.3。

### 5.2 致 V.V.（可直接转达）

> 烛照九阴日报的产出目录已从 `/Users/lunarabbit/Documents/AI4ME/烛照九阴-outputs/` 迁到 `/Users/lunarabbit/Documents/Claude/Projects/Financial/烛照九阴/outputs/`，内部结构不变（根目录最新一期、`archived/`、`archived/_pre-snapshots/`、`artifact/`）。旧路径现在是 Finder 替身（普通文件，程序读不穿）。请按 V.V. 侧流程改以下现行引用；历史留痕（`loop-engineering/archives/`、`runs/`、`Infrastructure/tools/ai4me-migration-20261004/`、`Project Mirror/剑酒青丘/research/…/inputs/`、`孔明/回测/…/证据/`、`Project Mirror/烛照九阴日报/notes/`、`INDEX.md` L54 历史行、`reference/cc-handoff-visual-v1.md`、`Codex Brain/references/Documents架构摸底.md`）不改：
> 1. `Infrastructure/loop-engineering/config/audit-resources.v1.json` L202 `zhuzhao-output.path`。改后请跑 `tests/test_audit_registration.py`；`runs/audit-harness/resource-index.json` 要不要重建由你判断。
> 2. `Morning Post/config/after-hours-ops.json` L41 `zhuzhao_outputs_directory`（Morning Post 休眠，建议同批改，免得复活时读空；`snapshot-morning-post-inputs.mjs` 用 `exactPath(…, "directory")` 读它）。
> 3. `Morning Post/PRD.md` L1738。
> 4. `Project Mirror/烛照九阴日报/README.md` L25（L62 是历史定位记录，由你定）、`GOTCHAS.md` L16、L23、`reference/production-process.md` L25、L36、L66。
> 5. `Codex Brain/permanent/文件管理标准.md` L81：AI4ME 目录列表去掉 `烛照九阴-outputs/`（Doctor 11-18 裁定：被整文件读取的系列不放 AI4ME）。
> 回执请列：改了的文件:行、测试结果。

### 5.3 致 Cowork 云端班（Doctor 在 Cowork 交互会话里转达）

> 对定时班 `zhuzhao-market-fetch-daily-report`（`trig_01GfLb5GmuwSQdgtE91sX9Jr`）：
> 1. 先读出现行提示词全文，机器对拷存到 `~/Documents/Claude/brain/.tmp/zhuzhao-prompt-backup-YYYY-MM-DD-pre-outputs-move.md`，回报字符数与 sha256。
> 2. 把提示词里所有 `~/Documents/AI4ME/烛照九阴-outputs` 与 `/Users/lunarabbit/Documents/AI4ME/烛照九阴-outputs` 换成 `~/Documents/Claude/Projects/Financial/烛照九阴/outputs`（Mac 绝对路径 `/Users/lunarabbit/Documents/Claude/Projects/Financial/烛照九阴/outputs`）。若提示词里调用 `artifact_split_zhuzhao.py` 时带了 `--src`，同样替换。其余一字不改；不改排期、启停、模型和其他段落。
> 3. 回报：替换了几处；改后全文与「备份全文 + 机械替换」的结果逐字相等；`update_trigger` 回执。
> 背景：提示词的「看板推送」段优先于正文。漏改的话，转换件仍会往旧路径写；那里现在是替身文件，写入会失败，看板回落到登记待推。

### 5.4 建替身（Doctor）
- Finder：在新目录 `Claude/Projects/Financial/烛照九阴/outputs` 上右键「制作替身」，把替身拖到 `~/Documents/AI4ME/`，改名为 `烛照九阴-outputs`。
- 或终端（未核：沙箱禁 osascript，CC 没法试跑）：
  `osascript -e 'tell application "Finder" to make new alias file at (POSIX file "/Users/lunarabbit/Documents/AI4ME" as alias) to (POSIX file "/Users/lunarabbit/Documents/Claude/Projects/Financial/烛照九阴/outputs" as alias) with properties {name:"烛照九阴-outputs"}'`
- 第一批实测（2026-11-19 中美管制阶梯，命令不带 `with properties`）：英文系统生成的是「目标名 alias」（后缀是英文「 alias」，不是「替身」）。带 `name` 属性能否直接定名未核。建好后 `ls ~/Documents/AI4ME` 看实际名，不对就 `mv -n` 改成 `烛照九阴-outputs`，再用 `test -f` 为真、`test -d` 为假确认是替身。

## 六 回退与切换前快照

**快照（步 3，必须真做；做不了要在决策记录如实写明）**：
- 迁前清单：`cd ~/Documents/AI4ME/烛照九阴-outputs && find . -type f -print0 | xargs -0 shasum -a 256 | sort -k2 > ~/Documents/Claude/brain/backups/zhuzhao-outputs-pre-move-YYYY-MM-DD.sha256`
- 打包：`tar czf ~/Documents/Claude/brain/backups/zhuzhao-outputs-pre-move-YYYY-MM-DD.tar.gz -C ~/Documents AI4ME/烛照九阴-outputs Claude/Projects/Financial/烛照九阴/config.py Claude/Projects/Financial/烛照九阴/tools/gen_daily_report.py Claude/Projects/Financial/烛照九阴/.gitignore Claude/brain/.tools/artifact_split_zhuzhao.py Claude/brain/.tools/test_artifact_split_guards.py Claude/brain/references/scheduled-live-mirror/live/zhuzhao-market-fetch-daily-report/SKILL.md Claude/brain/.tmp/pending-artifact-push.jsonl`，记 SHA-256。brain `backups/` 已被 `.gitignore` 排除（实读 L40）。压缩后体积未核（86 MB HTML 里有 base64 图与内联 echarts）。
- 云端提示词改前全文：步 1 的机器对拷文件。
- 保留期：首次自然运行核对和独立核验都通过后，按 conch 回收站流程处理，不长期占 brain。

**回退（反向操作，顺序与切换相反）**：
1. Cowork：用步 1 的备份全文恢复提示词（Doctor 在 Cowork）。
2. 删除 AI4ME 下的替身文件 `烛照九阴-outputs`（它只是指针，删前确认 `[ -f … ] && [ ! -d … ]`）。
3. `mv ~/Documents/Claude/Projects/Financial/烛照九阴/outputs ~/Documents/AI4ME/烛照九阴-outputs`（迁移后新写入的报告随目录一起回去，不丢）。
4. 代码：从快照 tar 里取回 `config.py`、`gen_daily_report.py`、`.gitignore`、拆分器、守卫测试、镜像 SKILL.md、待推队列；或者对项目仓这三个文件做文件级 `git restore`，前提是它们除本次以外没有别的未提交改动（切换前它们是干净的）。
5. 回读：`sha256` 清单比对；`test_artifact_split_guards.py` 全 PASS。
6. 回退要在下一次 10:00 PT 触发前完成，否则同样撞班。

## 七 待 Doctor 拍板（方向性 · 三问）

1. **新落点**：`Projects/Financial/烛照九阴/outputs/`（**推荐**：合裁定原话与落点规则，有先例，锚 PROJECT_ROOT）／`Database/烛照九阴/日报/`（不推荐：不是 DB 层数据，唯一好处是不进项目工作树）。
2. **快捷方式**：同名 Finder 替身 `烛照九阴-outputs`（**推荐**：Finder 可点，程序读不穿，漏改的读写方会当场报错）／不同名替身（次选：旧路径消失后写方会静默重建旧目录）／同名符号链接（**不推荐**：等于兼容链接，旧读写悄悄穿过，违背 migrate.md 与「AI4ME 不被消费」）。
3. **窗口**：周六 11-21 至周日 11-22 PT，截止周一 09:30 PT（**推荐**：约 40 小时余量）／周五 11-20 班后（余量同样够，但要先确认当班收尾）。
（事务性附带：待推队列 4 行先消费还是改写，推荐先在 Cowork「补推看板」消费。）

## 八 没核到的部分

- **云端班现行提示词全文**：镜像里只有 11-12 改版**前**的备份；改版后「看板推送」段里旧路径有几处、拆分器调用带不带 `--src`，都没核（11-12 适配卡只说两条烛照特有条款「并入新段」）。
- launchd 是否已加载：沙箱里 `launchctl list` 看不到，只读了 plist。
- `test_audit_registration.py` 会不会校验 `zhuzhao-output.path` 存在：没读全文，归 V.V.。
- `snapshot-morning-post-inputs.mjs` 的 `exactPath(…,"directory")` 遇到替身文件是否当场失败：推断会失败（不是目录），没实测。
- Finder 替身的 osascript 命令：沙箱禁 Launch Services / Apple Events，没试跑。
- 快照 tar 压缩后的体积；项目目录会不会被别的整目录打包或同步（如 conch 的 `financial-pre-conch` 类 tar、fuxi 备份）带上 `outputs/` 增量：没核。
- 云端 `PROJECT_ROOT` 解析为挂载区路径：由 prompt 备份「`~/Documents` 软链到 `$HOME/mnt/Documents`」与 `config.py:29` `resolve()` 推断，没在云端实跑。
- 字面扫描有漏：变量拼接的读方扫不到（11-18 复查补出过 2 处）；本稿另扫了 `zhuzhao-jiuyin-daily.html`、`烛照九阴日报_`、`ZZJY_OUTPUT_ROOT`/`OUTPUT_ROOT`，以及同行出现 `AI4ME`+`烛照` 的写法，代码文件里没有新的读方，但没把 Database 层另跑一遍（Database 只在 refs.txt 那次两段扫描里覆盖过）。
- `scheduler-weekly-audit`（周日 20:00）会不会把镜像 SKILL 与云端提示词的不一致报成异常：没核。
