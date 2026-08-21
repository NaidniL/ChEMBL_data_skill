# 开发日志

## Q1：工程结构建立与学习

如何将 TeachOpenCADD T001 的 ChEMBL IC50 数据准备流程固化为可复用、可追溯的 Codex Skill。

### AI 协作的方案：

按openai的developer页面指导，按照
```
ngineering-workflow/
│
├── README.md
├── requirements.txt
├── app.py  统一入口
│
├── src/  业务逻辑核心（打算支持skill和streamlit调用）
│   └── workflow/
│       ├── init.py
│       ├── pipeline.py  除开业务具体逻辑的调用顺序
│       ├── validators.py  首先确认输入（遵循fail fast原则）
│       └── models.py  数据结构统一规则
│
├── .agents/
│   └── skills/
│       └── chembl-workflow/
│           ├── SKILL.md  
│           ├── scripts/  外部工具调用（主要python）
│           ├── references/  领域规范参考
│           └── assets/
│
├── tests/  回归测试（随更改实时保证测试成功）
│   ├── test_pipeline.py
│   └── fixtures/  某（些）bug对应小样本测试
│
├── examples/  方便用户理解skill的使用
│   ├── input/
│   └── expected_output/
│
└── docs/
    └── decision_log.md  此项目特殊需要的记录文档
```
建立空白仓库，学习每一个文件所需要承担的责任（见上）

## Q2：工作流拆解

拆解工作流的大块分割与小块语义，整理Agent（面对人）和python（面对数据）各自需要分工的内容，建立milestone

### AI协作的方案

根据我给出的自然语言描述
```
网络连接ChEMBL数据库（需要chembl_webresource_client.new_client去连接、顺便import pandas numpy等处理数据，我认为需要先整理requirements.txt）-> 获取用户指定的Uniport -> 通过api查询指定数据（这里如何确定需要的列？通过用户指定未免太麻烦，skill的目的就是通过模型识别自然语言中的需求） ->选择关注对象筛查出指定需求的数据集 -> 确认后下载pandas dataframe格式的数据以便处理（前面的数据都属于决策查询）

到这里是第一个部分：获取需要的未处理数据

接下来转换需要的数据类型、删除包含缺失值的条目、删除重复的分子（取最好？平均？随机？可能需要用户确认）、重新索引留下的条目、整体列重命名以与后续接口对应、接下来根据筛选出来的分子去下载结构数据、删除包含缺失值的条目、按唯一id删除重复条目、按唯一id合并两个数据集

到这里是第二个部分：常规数据处理，不包含太专业的生物化学内容

接下来针对需要研究的列（用户输入）、处理单位和数量级、整体统计、关注高值或低值排序下相关的其他列信息（这里需要模型辅助去理解信息的价值）

到这里是最后一个部分：专业的数据考量
```
整理为 docs/workflow_spec.md，经我同意调整默认决策等并在末尾添加失败处理、模型决策边界等问题

建立 docs/progress_check.md，加入最小单元功能核对

## Q3：基础环境配置

为基础版本skill和测试准备python环境，建立git仓库

### Agent工作
将 chembl_webresource_client pandas numpy rdkit 作为最小版本的 requirements.txt 并梳理兼容要求；初始化git，ssh将以上内容同步到github private仓库

## Q4: M1 数据库连接与靶点数据拉取

针对已经解析好的 target，需要把靶点数据拉下来并保存
补齐不联网、错误API返回、多候选情况下的程序逻辑测试，要求程序正确报错、无揣测性增删修改

### Agent工作
建立 scripts/discover_target.py的输入约束（target name / UniProt accession / ChEMBL target ID + optional organism）、输出约束（0~N 个 target candidates的JSON格式）、责任约束（只负责拉取数据，禁止筛选删改），并写入python程序
人工干预：允许预留其他查询字段的接口，给出api调用数据库范例
完成固定target（uniprot_id = "P00533"）可以稳定返回结构化数据的最小集成测试
构造unit测试样例，验证离线运行下所有 ChEMBL 客户端调用都会被 mock；多候选记录原样保留；API 异常被明确报告并返回非零状态。

## Q5: M2 活性数据拉取

给出M1查询到的/确定的chembl_id和关心的数据type，获取活性数据集

### AI方案
构造 fetch_activities.py 的流程：验证参数、构造 ChEMBL query、执行 query、检查 requested property 是否有数据、转换成 DataFrame、验证 raw schema、保存 CSV、报告 record count
需要重点关注的数据列：
activity_id
molecule_chembl_id
target_chembl_id
assay_chembl_id
standard_type
standard_relation
standard_value
standard_units
pchembl_value
data_validity_comment
potential_duplicate
需要自行构建的数据：metadata（对最终csv格式raw data的JSON描述），例如
{
  "target_chembl_id": "CHEMBL203",
  "activity_type": "IC50",
  "record_count":
  "columns": [

  ]
}

### Agent工作
写入fetch_activities.py，按 target ID + activity type 获取原始活动记录，校验 schema、target/type 一致性，保存 activities.csv 与 metadata.json。
人工干预：注意到ChEMBL 客户端存在间歇性代理/SSL 初始化失败；策略是仅对明确网络异常增加一次重试，二次失败会显式报错。

## Q6: M3 活性与SMILES数据集合并

拆解任务为三部分：(a)活性数据集清理、(b)生成SMILES结构数据集、(c)合并

### AI方案
先做M2-M3交接的小数据观察：
df.shape
df.columns.tolist()
df.dtypes
df["standard_value"].isna().sum()
df["standard_units"].value_counts(dropna=False)
df["standard_relation"].value_counts(dropna=False)
df["potential_duplicate"].value_counts(dropna=False)
df["data_validity_comment"].value_counts(dropna=False)
df["molecule_chembl_id"].nunique()
df["molecule_chembl_id"].duplicated().sum()
并检查是否存在完全重复、activity_id是否唯一、同一id的数据量

(a)部分：raw activities.csv检查真实数据分布后做类型转换、检查缺失值、排除重复条目、保留同一物质多条测试数据、统一列名和索引；
(b)部分：唯一chembl_id查询SMILES字段、检查缺失值、RDkit核验，得到结构表
(c)部分：根据唯一chembl_id合并活性表与结构表、检查fingerprint（Morgan radius 2、2048-bit）

### Agent工作
做--limit=200，观察并报告核心项，结果显示20条id缺失
人工干预：排查：去掉 .only(...) 再跑同一个查询（无影响）、按异常 activity_id 单条重新查询（可查询）、沿 assay_chembl_id 查 assay（可查询）、关闭 client cache 重新测试查询200全量（可查询）、检查缺失id行位置（21-40）；**排查后确定需要关闭缓存（将策略修改为默认cache =off但是留出--use-cache接口）**
实现prepare_dataset.py
人工干预：unit测试发现fingerprint的2048-bit会被pandas识别为超大整数并截断，**转化为带前缀的bitstring**；skill-creator自动校验需要加入依赖PyYaml，**允许加入并写入requirements.txt、运行一次自动校验测试（valid）**

## Q7: M4 基于领域语义的数据处理与统计分析
拆解任务为三部分 (a)数据量化 (b)数据量级处理、数据统一函数变换 (c)统计分析

### AI方案

(a)部分：建立standard_relation/value/units的策略并统一单位
=     → exact
'>/<'  → censored
null  → 无法量化
(b)部分：针对选取的IC50，检验合法性，考虑数量级转换为pIC50（新增列）
(c)部分：计算常见统计量（数量、均值、中位数、标准差、四分位数、最大最小值）；决定排序方向，输出 top/bottom 记录及相关 metadata

### Agent工作
此阶段输出analyzed_dataset.csv、top/bottom_records.csv、statistics.json，仅保留 =、有限且大于 0 的 IC50。支持 pM、nM、uM、µM、μM、mM，统一新增 ic50_nM、pIC50
人工干预：M2→M3→M4 的真实 API 全链路冒烟测试在外部 ChEMBL 请求的 30 秒窗口内未返回，**指派为网络连接速度问题**；原始仅显式保留无 data_validity_comment的IC50，**改写策略为accepted validity:null、excluded validity:Outside typical range、unknown non-null comments:fail / report for review，避免数据库更新comment带来的隐形漂移**

## Q8：M5 数据处理流程分析
同样拆分三部分 (a)记录M4删除数据操作细节 (b)独立核对数据validation (c)汇总数据生成与处理流程配置

### AI方案
此阶段允许做前面成果的最小修改，以满足分析要求；优先离线
(a)部分：统计raw data- M3基础清清洗与合并过程损失- M4语义清洗损失整个流程中，每一步新排除的数据（当前结果-上一步结果）即原因，给出推荐的schema（json）
(b)部分：建立scripts/validate_run.py，独立读取artifacts做验证，检验目标字段存在、SMILES结构字段正确可解析、fingerprint字段正确可解析、量化数据合法、结束清洗后的数据表大小一致、M4c统计正确等各种流程验证。需要输出面对用户读取的结果报告（若valid）、指向明确且正确的错误分析（invalid）
(c)部分：建立run_manifest.json，严禁模型参与生成，必须基于实际代码、参数、metadata、统计手段。需要记录数据获取、基础清洗、语义清洗等各阶段的单一可验证配置
测试需要覆盖invalid涉及全流程各种可能的错误情况

### Agent工作
exclusions.json记录字段包括stage/input_records/newly_excluded_records/newly_excluded_records/output_records
nvalid 测试覆盖 raw 字段缺失、错误 SMILES、错误 fingerprint、错误 pIC50、错误 exclusion transition，并输出 artifact、错误原因和修复建议
人工干预：**增加M2-M4的--limits=20测试+M5生成**（M2记录20，M3清理后20，M4量化值14，排除非精确关系2/comment非空4，M5独立验证valid）

## Q9：M6 pipeline向skill包装
定义Agent在此流程首末段与用户交互的行为（允许+严禁）

### AI方案
Agent 可以理解和选择，但不能伪造事实；可以编排 pipeline，但不能替代 pipeline 计算；可以解释结果，但数字必须来自 artifacts；validator 没有 PASS，Agent 就不能宣称成功。提供SKILL.md插入文本

### Agent工作
完成SKILL.md文本插入，推送结果

## Q10: 学习验证skill有效性

### 验证结果
测试SKILL的四部分：正确触发、正确编排 M1–M5、守住 Agent 边界、回答忠于 artifacts
（1）
Codex通过项目扫描$repo-root/.agents/skills读取当前项目可获得的skill，通过$HOME/.agents/skills读取跨项目复用的skill，当前开fresh-session可直接使用/skill或$name调用：**排查无法调用原因:子目录SKILL不会被工作根目录的Codex session读取**

非显式调用下自然语言描述已验证的配置“构建人 EGFR 的 ChEMBL IC50 数据集”，测试 自然语言-skill匹配-转换target/property-M1启动 的链路及后续处理：**CHEMBL203转换成功，等待网络下载而非超时截断，询问是否允许限定数据量，API报错status500后停止**

（2）
前序API调用失败的情况下，手动准备进入M3的数据集，显式指定SKILL并显式指定测试环节M3-M6，成功生成offline-smoke测试，与生成SKILL时的数据结果相同

fresh-session非显式调用下给出手动准备的数据集，自然语言描述“用这里已有的离线 ChEMBL数据tests/fixtures/egfr-limit20，完成 IC50数据分析，并验证最终运行结果。不要访问外部数据库。”成功生成offline-fixture-run测试，与生成SKILL时的数据结果相同

API恢复后抓取100条数据测试，结果：清理6条缺失值，9条非精确关系，29条Outside typical range，得到56条IC50，对应43个分子，pIC50：均值 6.2610，中位数 6.4397，范围 4.0177–9.3468

抓取全量数据集，虽然API返回正确但是耗时太长

（3）
仅测试自然语言描述“分析 tests/fixtures/egfr-limit20的数据，把 >500 nM 当成 500 nM，<10 nM 当成 10 nM 就行”，结果是生成数据分析但不保存文件、不运行验证，因此**加强No ad-hoc bypass并显式写入对用户要求违反策略时的行为**；修改后同样测试，agent拒绝执行

（4）
针对 egfr-limit20结果，自然语言描述“总结 egfr-limit20的分析结果”，询问“哪个分子活性最强”会限制当前样本，询问“实验条件”会从原始数据的assay中找到并核对论文；修改analysis下statistics.json中某一count值后fresh-session中agent能发现不一致

## Q11 收尾
调用openai官方插件 $skill-creator 整理项目目录结构
