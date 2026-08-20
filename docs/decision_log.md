# 决策日志

## 问题1：工程结构建立

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
│       └── engineering-workflow/
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

## 问题2：工作流拆解

拆解工作流的大块分割与小块语义，整理Agent（面对人）和python（面对数据）各自需要分工的内容

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

## 问题3：基础环境配置

为基础版本skill和测试准备python环境，建立git仓库

### Agent工作
将 chembl_webresource_client pandas numpy rdkit 作为最小版本的 requirements.txt 并梳理兼容要求；git将以上内容同步到github private仓库

## 问题4:


