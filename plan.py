import json
import openai
import sqlite3
import os
from typing import List, Dict, Any, Optional

# 配置LLM客户端
client = openai.OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY", "your-api-key"),
    base_url="https://api.deepseek.com/v1"
)

# ==================== 动态获取数据库元数据 ====================

def get_database_metadata(db_path: str = None) -> Dict:
    """
    动态获取数据库元数据
    
    :param db_path: 数据库文件路径，如果为None则返回示例元数据
    :return: 数据库元数据字典
    """
    if db_path and os.path.exists(db_path):
        return _extract_metadata_from_db(db_path)
    else:
        return _get_sample_metadata()


def _extract_metadata_from_db(db_path: str) -> Dict:
    """从SQLite数据库中提取元数据"""
    metadata = {"tables": {}}
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 获取所有表名
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [row[0] for row in cursor.fetchall()]
        
        for table_name in tables:
            table_info = {
                "columns": {},
                "indexes": [],
                "foreign_keys": []
            }
            
            # 获取列信息
            cursor.execute(f"PRAGMA table_info({table_name})")
            columns = cursor.fetchall()
            
            for col in columns:
                cid, name, col_type, notnull, default_value, pk = col
                table_info["columns"][name] = {
                    "type": col_type,
                    "nullable": not notnull,
                    "default": default_value,
                    "primary_key": bool(pk),
                    "comment": ""  # SQLite不直接支持注释，可以后续补充
                }
            
            # 获取外键信息
            cursor.execute(f"PRAGMA foreign_key_list({table_name})")
            foreign_keys = cursor.fetchall()
            
            for fk in foreign_keys:
                id, seq, ref_table, from_col, to_col, on_update, on_delete, match = fk
                table_info["foreign_keys"].append({
                    "from_column": from_col,
                    "to_table": ref_table,
                    "to_column": to_col,
                    "on_update": on_update,
                    "on_delete": on_delete
                })
            
            # 获取索引信息
            cursor.execute(f"PRAGMA index_list({table_name})")
            indexes = cursor.fetchall()
            
            for idx in indexes:
                seq, name, unique, origin, partial = idx
                if not name.startswith("sqlite_"):
                    cursor.execute(f"PRAGMA index_info({name})")
                    index_cols = cursor.fetchall()
                    col_names = [col[2] for col in index_cols]
                    table_info["indexes"].append({
                        "name": name,
                        "columns": col_names,
                        "unique": bool(unique)
                    })
            
            metadata["tables"][table_name] = table_info
        
        conn.close()
        print(f"✅ 从数据库提取元数据: {len(tables)} 张表")
        return metadata
        
    except Exception as e:
        print(f"⚠️ 提取数据库元数据失败: {e}")
        return _get_sample_metadata()


def _get_sample_metadata() -> Dict:
    """返回示例数据库元数据（用于测试或无数据库时）"""
    return {
        "tables": {
            "activity": {
                "columns": {
                    "id": {"type": "INTEGER", "primary_key": True, "nullable": False, "comment": "活动ID"},
                    "name": {"type": "VARCHAR(100)", "nullable": False, "comment": "活动名称"},
                    "start_time": {"type": "DATETIME", "nullable": True, "comment": "开始时间"},
                    "end_time": {"type": "DATETIME", "nullable": True, "comment": "结束时间"},
                    "status": {"type": "TINYINT", "nullable": False, "default": 0, "comment": "状态：0-未开始，1-进行中，2-已结束"}
                },
                "indexes": [{"name": "sqlite_autoindex_activity_1", "columns": ["id"], "unique": True}],
                "foreign_keys": []
            },
            "prize_config": {
                "columns": {
                    "id": {"type": "INTEGER", "primary_key": True, "nullable": False, "comment": "奖品配置ID"},
                    "activity_id": {"type": "INTEGER", "nullable": False, "comment": "所属活动ID"},
                    "prize_name": {"type": "VARCHAR(100)", "nullable": False, "comment": "奖品名称"},
                    "probability": {"type": "FLOAT", "nullable": False, "default": 0.0, "comment": "中奖概率"},
                    "stock": {"type": "INTEGER", "nullable": False, "default": 0, "comment": "库存数量"},
                    "remaining": {"type": "INTEGER", "nullable": False, "default": 0, "comment": "剩余数量"}
                },
                "indexes": [{"name": "sqlite_autoindex_prize_config_1", "columns": ["id"], "unique": True}],
                "foreign_keys": [
                    {
                        "from_column": "activity_id",
                        "to_table": "activity",
                        "to_column": "id",
                        "on_update": "NO ACTION",
                        "on_delete": "NO ACTION"
                    }
                ]
            },
            "invitation_code": {
                "columns": {
                    "code": {"type": "VARCHAR(50)", "primary_key": True, "nullable": False, "comment": "邀请码"},
                    "activity_id": {"type": "INTEGER", "nullable": False, "comment": "所属活动ID"},
                    "user_id": {"type": "INTEGER", "nullable": True, "comment": "绑定用户ID"},
                    "used": {"type": "TINYINT", "nullable": False, "default": 0, "comment": "是否已使用：0-未使用，1-已使用"},
                    "created_at": {"type": "DATETIME", "nullable": False, "default": "CURRENT_TIMESTAMP", "comment": "创建时间"}
                },
                "indexes": [{"name": "sqlite_autoindex_invitation_code_1", "columns": ["code"], "unique": True}],
                "foreign_keys": [
                    {
                        "from_column": "activity_id",
                        "to_table": "activity",
                        "to_column": "id",
                        "on_update": "NO ACTION",
                        "on_delete": "NO ACTION"
                    }
                ]
            }
        }
    }


# ==================== 动态加载业务规则 ====================

def load_business_rules(rules_file: str = None) -> List[str]:
    """
    动态加载业务规则
    
    :param rules_file: 规则文件路径（JSON或TXT格式），如果为None则返回默认规则
    :return: 业务规则列表
    """
    if rules_file and os.path.exists(rules_file):
        return _load_rules_from_file(rules_file)
    else:
        return _get_default_business_rules()


def _load_rules_from_file(rules_file: str) -> List[str]:
    """从文件加载业务规则"""
    try:
        if rules_file.endswith('.json'):
            with open(rules_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    rules = data
                elif isinstance(data, dict) and 'rules' in data:
                    rules = data['rules']
                else:
                    raise ValueError("JSON文件格式不正确")
        elif rules_file.endswith('.txt'):
            with open(rules_file, 'r', encoding='utf-8') as f:
                rules = [line.strip() for line in f.readlines() if line.strip() and not line.startswith('#')]
        else:
            raise ValueError(f"不支持的文件格式: {rules_file}")
        
        print(f"✅ 从文件加载业务规则: {len(rules)} 条")
        return rules
        
    except Exception as e:
        print(f"⚠️ 加载业务规则文件失败: {e}，使用默认规则")
        return _get_default_business_rules()


def _get_default_business_rules() -> List[str]:
    """返回默认业务规则"""
    return [
        "活动必须在有效期内才能进行操作",
        "奖品库存不能为负数",
        "邀请码只能绑定一次",
        "删除活动前必须先删除关联的奖品和邀请码",
        "修改活动状态需要记录操作日志",
        "概率总和不能超过1.0",
        "同一活动下奖品名称不能重复"
    ]


def save_business_rules(rules: List[str], output_file: str = "business_rules.json"):
    """保存业务规则到文件"""
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump({"rules": rules}, f, ensure_ascii=False, indent=2)
        print(f"✅ 业务规则已保存到: {output_file}")
    except Exception as e:
        print(f"❌ 保存业务规则失败: {e}")


# ==================== LLM调用封装 ====================

def call_llm(prompt: str, system_msg: str = "你是一个专业的数据库助手。") -> Dict:
    """调用LLM并返回JSON响应"""
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": prompt}
    ]
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
            timeout=30
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"❌ LLM调用失败: {e}")
        raise

# ==================== 步骤1：需求理解 ====================

def step_understand_requirements(intents: List[Dict], business_rules: List[str]) -> Dict:
    """深入理解每个意图的业务含义"""
    prompt = f"""
请根据以下意图列表和业务规则，深入理解每个意图的业务含义，并输出一个JSON对象，包含对每个意图的解释、所需数据实体、以及意图间的依赖关系。

意图列表：
{json.dumps(intents, indent=2, ensure_ascii=False)}

业务规则：
{chr(10).join(business_rules)}

输出格式：
{{
  "intent_analysis": [
    {{
      "intent": "意图名称",
      "business_meaning": "业务含义描述",
      "required_entities": ["活动", "奖品", ...],
      "dependencies": ["前置意图名称"],
      "implicit_operations": "隐含的额外操作，例如检查存在性、自动创建等"
    }}
  ],
  "overall_dependencies": "整体依赖关系描述"
}}
只输出JSON。
"""
    return call_llm(prompt, system_msg="你是一个业务需求分析师。")

# ==================== 步骤2：数据库理解与映射 ====================

def step_understand_database(metadata: Dict) -> Dict:
    """生成数据库知识摘要"""
    prompt = f"""
请根据以下数据库元数据，生成一个数据库知识摘要，包括每张表的用途、关键字段解释、表间关系，以及如何将常见的业务概念（如活动、奖品、邀请码、奖励规则）映射到具体的表和字段。

数据库元数据：
{json.dumps(metadata, indent=2, ensure_ascii=False)}

输出格式：
{{
  "table_summaries": {{
    "表名": {{
      "purpose": "表的用途说明",
      "key_fields": {{
        "字段名": "字段含义"
      }},
      "relationships": "与其他表的关系（如外键）"
    }}
  }},
  "business_mapping": {{
    "活动": {{
      "table": "表名",
      "id_field": "ID字段",
      "name_field": "名称字段"
    }},
    "奖品": {{
      "table": "表名",
      "id_field": "ID字段",
      "activity_fk": "活动外键字段"
    }},
    "邀请码": {{
      "table": "表名",
      "code_field": "邀请码字段",
      "activity_fk": "活动外键字段"
    }},
    "奖励规则": {{
      "table": "表名",
      "id_field": "ID字段",
      "activity_fk": "活动外键字段"
    }}
  }}
}}
只输出JSON。
"""
    return call_llm(prompt, system_msg="你是一个数据库专家。")

# ==================== 步骤3：生成执行计划 ====================

def step_generate_plan(requirement_analysis: Dict, db_knowledge: Dict, business_rules: List[str]) -> Dict:
    """生成可执行的SQL操作计划"""
    prompt = f"""
你是一个数据库任务规划专家。请根据以下需求分析结果、数据库知识摘要和业务规则，生成一个可执行的SQL操作计划。

需求分析结果：
{json.dumps(requirement_analysis, indent=2, ensure_ascii=False)}

数据库知识摘要：
{json.dumps(db_knowledge, indent=2, ensure_ascii=False)}

业务规则：
{chr(10).join(business_rules)}

每个步骤可以是以下类型之一：
- query: 执行SELECT查询，用于获取数据（如查询ID）。需要指定sql和预期的结果变量名result_var。
- update: 执行INSERT/UPDATE/DELETE语句，改变数据。需要指定sql。
- transaction: 包裹一组步骤，使其原子执行。需要包含steps数组。
- user_confirmation: 请求用户确认关键操作。需要包含message。
- condition: 条件分支，根据查询结果决定后续步骤。需要包含condition_sql, if_true_steps, if_false_steps。

输出必须是一个JSON对象，包含一个"steps"数组，每个步骤包含"type"和对应的字段。
所有SQL语句必须使用参数占位符（如%s或?），并在步骤中提供"params"数组。参数值可以从意图参数或上下文变量中引用，格式为 {{{{变量名}}}}。

请确保生成的计划符合业务规则，并正确处理依赖关系（例如先查询活动ID，再执行更新）。如果缺少必要信息，请在计划中包含用户确认步骤或错误处理。

只输出JSON，不要添加任何解释。
"""
    return call_llm(prompt, system_msg="你是一个数据库任务规划专家。")

# ==================== 主流程 ====================

def multi_step_planning(
    intents: List[Dict], 
    db_path: str = None, 
    rules_file: str = None,
    metadata: Dict = None,
    business_rules: List[str] = None
) -> Dict:
    """
    多步骤规划主流程
    
    :param intents: 意图列表
    :param db_path: 数据库文件路径（可选，用于动态提取元数据）
    :param rules_file: 业务规则文件路径（可选，用于动态加载规则）
    :param metadata: 直接传入的元数据（可选，优先级高于db_path）
    :param business_rules: 直接传入的业务规则（可选，优先级高于rules_file）
    :return: 执行计划
    """
    
    print("=" * 60)
    print("🎯 开始多步骤数据库任务规划")
    print("=" * 60)
    
    # 步骤0: 准备元数据和业务规则
    print("\n【准备阶段】加载数据库知识和业务规则...")
    
    if metadata is None:
        metadata = get_database_metadata(db_path)
        print(f"✅ 元数据包含 {len(metadata.get('tables', {}))} 张表")
    
    if business_rules is None:
        business_rules = load_business_rules(rules_file)
        print(f"✅ 业务规则共 {len(business_rules)} 条")
    
    # 步骤1: 需求理解
    print("\n【步骤1】需求理解...")
    req_analysis = step_understand_requirements(intents, business_rules)
    print("✅ 需求理解完成")
    print(json.dumps(req_analysis, indent=2, ensure_ascii=False)[:500] + "...")
    
    # 步骤2: 数据库理解
    print("\n【步骤2】数据库理解...")
    db_knowledge = step_understand_database(metadata)
    print("✅ 数据库理解完成")
    print(json.dumps(db_knowledge, indent=2, ensure_ascii=False)[:500] + "...")
    
    # 步骤3: 生成计划
    print("\n【步骤3】生成执行计划...")
    plan = step_generate_plan(req_analysis, db_knowledge, business_rules)
    print("✅ 计划生成完成")
    
    return plan


# ==================== 便捷函数 ====================

def quick_plan_from_text(
    user_input: str, 
    db_path: str = None,
    rules_file: str = None
) -> Dict:
    """
    从自然语言快速生成执行计划
    
    :param user_input: 用户自然语言输入
    :param db_path: 数据库文件路径
    :param rules_file: 业务规则文件路径
    :return: 执行计划
    """
    from dataproject.intent import detect_intents, validate_and_fix_intents
    
    print(f"\n💬 用户输入: {user_input}\n")
    
    # 意图识别
    intents = detect_intents(user_input)
    if not intents:
        raise Exception("意图识别失败")
    
    fixed_intents = validate_and_fix_intents(intents)
    
    # 生成计划
    plan = multi_step_planning(
        intents=fixed_intents,
        db_path=db_path,
        rules_file=rules_file
    )
    
    return plan


if __name__ == "__main__":
    # 示例用法
    print("测试动态元数据提取...")
    
    # 测试1: 从示例数据获取
    metadata = get_database_metadata()
    print(f"\n示例元数据: {len(metadata['tables'])} 张表")
    
    # 测试2: 从真实数据库获取（如果存在）
    if os.path.exists("test.db"):
        metadata_from_db = get_database_metadata("test.db")
        print(f"\n数据库元数据: {len(metadata_from_db['tables'])} 张表")
    
    # 测试3: 加载业务规则
    rules = load_business_rules()
    print(f"\n业务规则: {len(rules)} 条")
    for i, rule in enumerate(rules, 1):
        print(f"  {i}. {rule}")

