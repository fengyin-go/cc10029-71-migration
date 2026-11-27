# 教学诊改协同台

教师、教研室主任和教务处在课堂观摩后填写教学反馈、制定改进方案、跟踪实施进度并在学期末完成复盘归档。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 入口与迁移

工作台已从独立站点的根路径迁移到教务门户子路径，迁移期两套入口同时在线，
指向**同一个业务实例**（同一份数据、同一套编号）：

| 入口 | 页面地址 | 接口前缀 |
| --- | --- | --- |
| 独立站点（旧地址，收藏链接继续可用） | `/`、`/review_meeting/3`、`/improve_task/4` | `/api/...` |
| 教务门户（新入口） | `/portal/`、`/portal/review_meeting/3`、`/portal/improve_task/4` | `/portal/api/...` |

- 以前保存的会议纪要、诊改任务深链**不需要跳转**即可打开，编号保持不变。
- 两套页面路径由同一份构建产物 + 前端路由解析；`/assets` 与 `/portal/assets` 等价。
- 导出/下载接口在新旧路径都可用：`/api/<模块>/export` 与 `/portal/api/<模块>/export`。
- 侧栏显示当前入口徽标，并提供「进入教务门户 / 返回独立站点」的切换，切换时保留当前记录。

### 分发回执与同编号演示实例

同一笔会议纪要分发可能从两个入口各收到一份请求。回执按 **M-56** 形式编号
（未显式给出时用 `M-<纪要编号>`），统一记在进程内回执账本里：

| 状态 | 含义 | 处理建议 |
| --- | --- | --- |
| 已分发 | 任务已实际发出，重复提交不会再次写入 | 直接使用任务 #N |
| 可续办 | 分发已完成，另一入口也提交过，任务仍待认领 | 在当前入口继续办理 |
| 尚待原入口处理 | 原入口的分发请求仍在途中或纪要尚未签认 | 回到原入口点开原回执核验后再办理 |

- 两个入口读写的都是同一个 `Store` 实例；同编号的**演示实例**（`demo-*`）一律
  **拒收写入**（HTTP 409），不会污染业务数据。
- 「认领任务」只接受该回执**实际发出**的那一项任务；伪造的同回执任务会被拦截。
- 回执核验页：`/receipts/M-56`（门户：`/portal/receipts/M-56`）。
- 回执接口（两套前缀都有）：`GET /api/receipts`、`GET /api/receipts/{回执号}`、
  `GET /api/meetings/{纪要编号}/receipt`、`POST /api/receipts`（原入口登记在途回执）。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue      全部模块共享工作台（含回执徽标与认领约束）
│   ├── src/views/ReceiptView.vue        分发回执核验页
│   ├── src/api/entry.ts                 入口基址、接口前缀与站内链接
│   ├── src/data/modules.ts              20个业务模块配置
│   ├── src/router/index.ts              两套入口共用的路由表
│   ├── server.mjs                       部署用静态服务器（双入口 + 接口代理）
│   ├── scripts/postbuild.mjs            生成 dist/portal/index.html
│   └── vite.config.ts                   dev/preview 双入口与代理
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py     通用查询/导出/登记/动作接口（双前缀）
│   ├── app/routers/distributions.py 分发回执接口（双前缀）
│   ├── app/services/distribution.py 回执账本与状态判定
│   ├── app/services/<key>.py       每个模块独立领域逻辑
│   ├── app/context.py              请求入口上下文（入口/回执/实例）
│   ├── app/services/base.py        共享服务骨架与写入守卫
│   └── app/store.py                内存数据仓库、实例标识与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`（门户同一份：`/portal/api/health`）

### 前端（开发）

```bash
cd frontend
npm ci
npm run dev
```

- 门户：`http://127.0.0.1:5173/portal/`
- 旧地址：`http://127.0.0.1:5173/`
- dev server 不会自动打开浏览器。`/api` 与 `/portal/api` 都由 vite 代理到后端。

### 前端（构建与部署）

```bash
npm run build      # 产出 dist/ 与 dist/portal/index.html
node server.mjs    # 同端口提供两套入口，并代理两套接口前缀
```

`server.mjs` 支持 `PORT`、`HOST`、`BACKEND_TARGET`、`DIST_DIR` 环境变量。
`docker-compose.yml` 已按此方式配置（`BACKEND_TARGET=http://backend:8000`）。

## 测试

```bash
cd backend && .venv/bin/python -m pytest -q      # 含双入口路由与回执流程
cd frontend && npm test                          # 单元 + 真实后端联调（后端未启动时自动跳过）
cd frontend && npm run typecheck && npm run typecheck:spec
```

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 课堂观摩 | `observation` | 观摩记录 | 教师姓名、课程名称、授课日期 |
| 教学反馈 | `feedback` | 反馈单 | 反馈对象、反馈要点、改进建议 |
| 改进方案 | `improve_plan` | 改进方案 | 关联反馈、改进目标、改进措施 |
| 实施进展 | `progress_log` | 进展记录 | 关联方案、当前阶段、完成情况 |
| 同行评议 | `peer_review` | 评议表 | 被评教师、评议维度、得分 |
| 教学档案 | `teach_record` | 档案条目 | 教师姓名、档案类型、内容摘要 |
| 学期目标 | `semester_goal` | 学期目标 | 目标描述、量化指标、责任教师 |
| 复盘会议 | `review_meeting` | 会议纪要 | 会议主题、参会人员、召开日期 |
| 诊改任务 | `improve_task` | 诊改任务 | 任务描述、承接方案、执行人员 |
| 外部评估 | `external_eval` | 评估报告 | 评估机构、评估指标、评估结论 |
| 课程组编排 | `course_group` | 课程组 | 组名、覆盖课程、组长教师 |
| 大纲修订 | `syllabus_rev` | 修订稿 | 课程名称、修订章节、原内容 |
| 教学成果申报 | `teach_award` | 成果申报 | 成果名称、完成团队、成果概要 |
| 集体备课 | `lesson_prep` | 备课记录 | 备课章节、主备教师、参与教师 |
| 师徒结对 | `mentor_pair` | 结对记录 | 指导教师、青年教师、结对目标 |
| 试卷分析 | `exam_analysis` | 分析记录 | 考试名称、任课教师、参考人数 |
| 排课编排 | `class_schedule` | 排课单 | 课程名称、授课教师、上课时间 |
| 教学资源申请 | `resource_apply` | 资源申请 | 申请资源、用途说明、使用时间 |
| 质量简报 | `quality_report` | 质量简报 | 覆盖学期、教学质量概况、突出问题 |
| 教材选用 | `textbook_select` | 选用单 | 教材名称、主编、出版社 |

## 约定

- 全部模块共享 `frontend/src/views/WorkbenchView.vue` 和一套资源路由；
  两套入口前缀复用同一批路由处理器。
- 每个模块仍保留独立 `backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size, instance }`，动作接口统一返回
  `{ ok, message, entry, status, receipt }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。
- 写入只允许落在当前业务实例；`demo-*` 演示实例返回 409。

领域：应用开发
子方向：web前端/全栈开发
