"""
数据库任务规划系统 - 完整测试示例
演示从自然语言意图 → 执行计划生成 → SQL执行的完整流程
"""

import json
import os
import sys
from typing import Dict, List, Any

# 导入模块
from dataproject.sqlengine import ExecutionEngine
from dataproject.plan import (
    multi_step_planning, 
    get_database_metadata,
    load_business_rules
)
from dataproject.intent import detect_intents, validate_and_fix_intents


def setup_test_database(db_path: str = "test.db"):
    """初始化测试数据库，创建表结构和示例数据"""
    import sqlite3
    
    # 如果数据库已存在，先删除
    if os.path.exists(db_path):
        os.remove(db_path)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 创建活动表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            start_time DATETIME,
            end_time DATETIME,
            status TINYINT DEFAULT 0
        )
    """)
    
    # 创建奖品配置表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prize_config (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            activity_id INTEGER NOT NULL,
            prize_name VARCHAR(100) NOT NULL,
            probability FLOAT DEFAULT 0.0,
            stock INTEGER DEFAULT 0,
            remaining INTEGER DEFAULT 0,
            FOREIGN KEY (activity_id) REFERENCES activity(id)
        )
    """)
    
    # 创建邀请码表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invitation_code (
            code VARCHAR(50) PRIMARY KEY,
            activity_id INTEGER NOT NULL,
            user_id INTEGER,
            used TINYINT DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (activity_id) REFERENCES activity(id)
        )
    """)
    
    # 插入测试数据
    cursor.execute("INSERT INTO activity (name, start_time, end_time, status) VALUES (?, ?, ?, ?)",
                   ("双十一", "2026-11-01 00:00:00", "2026-11-11 23:59:59", 1))
    cursor.execute("INSERT INTO activity (name, start_time, end_time, status) VALUES (?, ?, ?, ?)",
                   ("春节活动", "2026-02-01 00:00:00", "2026-02-15 23:59:59", 0))
    
    cursor.execute("INSERT INTO prize_config (activity_id, prize_name, probability, stock, remaining) VALUES (?, ?, ?, ?, ?)",
                   (1, "一等奖", 0.01, 10, 10))
    cursor.execute("INSERT INTO prize_config (activity_id, prize_name, probability, stock, remaining) VALUES (?, ?, ?, ?, ?)",
                   (1, "二等奖", 0.05, 50, 50))
    
    conn.commit()
    conn.close()
    
    print(f"✅ 测试数据库已初始化: {db_path}")


def test_scenario_1_modify_probability():
    """场景1：修改奖品概率（使用预定义计划）"""
    print("\n" + "=" * 80)
    print("📋 场景1：修改奖品概率")
    print("=" * 80)
    
    # 初始化数据库
    setup_test_database("test_scenario1.db")
    
    # 意图参数
    initial_context = {
        "intent": {
            "parameters": {
                "activity_name": "双十一",
                "prize_name": "一等奖",
                "new_probability": 0.05
            }
        }
    }
    
    # 预定义的执行计划
    plan = {
        "steps": [
            {
                "type": "query",
                "sql": "SELECT id FROM activity WHERE name = ?",
                "params": ["{{intent.parameters.activity_name}}"],
                "result_var": "activity_rows"
            },
            {
                "type": "condition",
                "condition_sql": "SELECT COUNT(*) FROM prize_config WHERE activity_id = ? AND prize_name = ?",
                "params": ["{{activity_rows[0].id}}", "{{intent.parameters.prize_name}}"],
                "if_true_steps": {
                    "type": "update",
                    "sql": "UPDATE prize_config SET probability = ? WHERE activity_id = ? AND prize_name = ?",
                    "params": [
                        "{{intent.parameters.new_probability}}",
                        "{{activity_rows[0].id}}",
                        "{{intent.parameters.prize_name}}"
                    ]
                },
                "if_false_steps": {
                    "type": "update",
                    "sql": "INSERT INTO prize_config (activity_id, prize_name, probability) VALUES (?, ?, ?)",
                    "params": [
                        "{{activity_rows[0].id}}",
                        "{{intent.parameters.prize_name}}",
                        "{{intent.parameters.new_probability}}"
                    ]
                }
            },
            {
                "type": "query",
                "sql": "SELECT * FROM prize_config WHERE activity_id = ?",
                "params": ["{{activity_rows[0].id}}"],
                "result_var": "final_prizes"
            }
        ]
    }
    
    print("\n📝 用户意图: 把双十一的一等奖概率改成5%")
    print("\n🔧 执行计划:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    
    # 执行
    engine = ExecutionEngine("test_scenario1.db")
    results = engine.execute_plan(plan, initial_context)
    
    print("\n✅ 执行结果:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # 验证结果
    final_prizes = engine.context.get("final_prizes", [])
    print(f"\n📊 最终奖品配置（共{len(final_prizes)}个）:")
    for prize in final_prizes:
        print(f"   - {prize['prize_name']}: 概率={prize['probability']}, 库存={prize['stock']}")
    
    return results


def test_scenario_2_natural_language_to_plan():
    """场景2：从自然语言到执行计划（完整流程）"""
    print("\n" + "=" * 80)
    print("📋 场景2：自然语言 → 意图识别 → 计划生成 → 执行")
    print("=" * 80)
    
    # 初始化数据库
    db_path = "test_scenario2.db"
    setup_test_database(db_path)
    
    # Step 1: 用户输入自然语言
    user_input = "把双十一活动的一等奖概率改成5%"
    print(f"\n💬 用户输入: {user_input}")
    
    # Step 2: 意图识别
    print("\n【步骤1】意图识别...")
    intents = detect_intents(user_input)
    if not intents:
        print("❌ 意图识别失败，使用模拟数据")
        intents = [{
            "intent": "modify_prize_probability",
            "parameters": {
                "activity_name": "双十一",
                "prize_name": "一等奖",
                "new_probability": 0.05
            }
        }]
    
    print(f"✅ 识别到 {len(intents)} 个意图:")
    print(json.dumps(intents, indent=2, ensure_ascii=False))
    
    # Step 3: 参数验证和修复
    print("\n【步骤2】参数验证...")
    fixed_intents = validate_and_fix_intents(intents)
    print(f"✅ 验证完成")
    
    # Step 4: 获取数据库元数据和业务规则
    print("\n【步骤3】获取数据库知识...")
    metadata = get_database_metadata(db_path)
    business_rules = load_business_rules()
    print(f"✅ 元数据包含 {len(metadata['tables'])} 张表")
    print(f"✅ 业务规则共 {len(business_rules)} 条")
    
    # Step 5: 生成执行计划
    print("\n【步骤4】生成执行计划...")
    try:
        plan = multi_step_planning(
            intents=fixed_intents,
            metadata=metadata,
            business_rules=business_rules
        )
        print(f"✅ 计划生成成功，共 {len(plan['steps'])} 个步骤")
        print("\n📋 执行计划:")
        print(json.dumps(plan, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"⚠️ 计划生成失败: {e}")
        print("使用预定义计划继续测试...")
        plan = {
            "steps": [
                {
                    "type": "query",
                    "sql": "SELECT id FROM activity WHERE name = ?",
                    "params": ["双十一"],
                    "result_var": "activity_rows"
                },
                {
                    "type": "update",
                    "sql": "UPDATE prize_config SET probability = ? WHERE activity_id = ? AND prize_name = ?",
                    "params": [0.05, "{{activity_rows[0].id}}", "一等奖"]
                }
            ]
        }
    
    # Step 6: 执行计划
    print("\n【步骤5】执行计划...")
    try:
        engine = ExecutionEngine(db_path)
        results = engine.execute_plan(plan, {})
        print(f"✅ 执行完成")
        print(f"📊 执行结果: {json.dumps(results, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"⚠️ 执行失败: {e}")
    
    return plan


def test_scenario_3_complex_transaction():
    """场景3：复杂事务操作（批量生成邀请码）"""
    print("\n" + "=" * 80)
    print("📋 场景3：批量生成邀请码（事务操作）")
    print("=" * 80)
    
    # 初始化数据库
    setup_test_database("test_scenario3.db")
    
    initial_context = {
        "intent": {
            "parameters": {
                "activity_name": "双十一",
                "count": 5
            }
        }
    }
    
    # 复杂的执行计划：查询活动ID → 事务中批量插入邀请码
    plan = {
        "steps": [
            {
                "type": "query",
                "sql": "SELECT id FROM activity WHERE name = ?",
                "params": ["{{intent.parameters.activity_name}}"],
                "result_var": "activity_rows"
            },
            {
                "type": "transaction",
                "steps": [
                    {
                        "type": "update",
                        "sql": "INSERT INTO invitation_code (code, activity_id) VALUES (?, ?)",
                        "params": ["INV001", "{{activity_rows[0].id}}"]
                    },
                    {
                        "type": "update",
                        "sql": "INSERT INTO invitation_code (code, activity_id) VALUES (?, ?)",
                        "params": ["INV002", "{{activity_rows[0].id}}"]
                    },
                    {
                        "type": "update",
                        "sql": "INSERT INTO invitation_code (code, activity_id) VALUES (?, ?)",
                        "params": ["INV003", "{{activity_rows[0].id}}"]
                    }
                ]
            },
            {
                "type": "query",
                "sql": "SELECT * FROM invitation_code WHERE activity_id = ?",
                "params": ["{{activity_rows[0].id}}"],
                "result_var": "all_codes"
            }
        ]
    }
    
    print("\n📝 用户意图: 为双十一活动生成5个邀请码")
    print("\n🔧 执行计划（包含事务）:")
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    
    # 执行
    engine = ExecutionEngine("test_scenario3.db")
    results = engine.execute_plan(plan, initial_context)
    
    print("\n✅ 执行结果:")
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # 验证结果
    all_codes = engine.context.get("all_codes", [])
    print(f"\n📊 生成的邀请码（共{len(all_codes)}个）:")
    for code in all_codes:
        print(f"   - {code['code']} (活动ID: {code['activity_id']})")
    
    return results


def test_scenario_4_user_confirmation():
    """场景4：需要用户确认的危险操作"""
    print("\n" + "=" * 80)
    print("📋 场景4：删除活动（需要用户确认）")
    print("=" * 80)
    
    # 初始化数据库
    setup_test_database("test_scenario4.db")
    
    plan = {
        "steps": [
            {
                "type": "query",
                "sql": "SELECT id, name FROM activity WHERE name = ?",
                "params": ["春节活动"],
                "result_var": "activity_rows"
            },
            {
                "type": "user_confirmation",
                "message": "即将删除活动'春节活动'及其所有关联数据，是否继续？"
            },
            {
                "type": "transaction",
                "steps": [
                    {
                        "type": "update",
                        "sql": "DELETE FROM prize_config WHERE activity_id = ?",
                        "params": ["{{activity_rows[0].id}}"]
                    },
                    {
                        "type": "update",
                        "sql": "DELETE FROM invitation_code WHERE activity_id = ?",
                        "params": ["{{activity_rows[0].id}}"]
                    },
                    {
                        "type": "update",
                        "sql": "DELETE FROM activity WHERE id = ?",
                        "params": ["{{activity_rows[0].id}}"]
                    }
                ]
            }
        ]
    }
    
    print("\n📝 用户意图: 删除春节活动")
    print("\n⚠️ 注意: 此操作需要用户确认")
    
    # 执行（会等待用户输入）
    try:
        engine = ExecutionEngine("test_scenario4.db", allow_ddl=False)
        results = engine.execute_plan(plan, {})
        print("\n✅ 执行成功")
    except Exception as e:
        print(f"\n⚠️ 操作被取消或失败: {e}")
    
    return plan


def main():
    """主函数：运行所有测试场景"""
    print("\n" + "=" * 80)
    print("🚀 数据库任务规划系统 - 完整测试套件")
    print("=" * 80)
    
    scenarios = [
        ("场景1: 修改奖品概率", test_scenario_1_modify_probability),
        ("场景2: 自然语言到计划", test_scenario_2_natural_language_to_plan),
        ("场景3: 批量生成邀请码", test_scenario_3_complex_transaction),
        ("场景4: 用户确认操作", test_scenario_4_user_confirmation),
    ]
    
    results = {}
    
    for name, func in scenarios:
        try:
            print(f"\n{'=' * 80}")
            print(f"▶️  开始执行: {name}")
            print('=' * 80)
            
            result = func()
            results[name] = {"status": "success", "result": result}
            
        except Exception as e:
            print(f"\n❌ {name} 执行失败: {e}")
            import traceback
            traceback.print_exc()
            results[name] = {"status": "failed", "error": str(e)}
    
    # 打印总结
    print("\n" + "=" * 80)
    print("📊 测试总结")
    print("=" * 80)
    
    for name, result in results.items():
        status = "✅ 成功" if result["status"] == "success" else "❌ 失败"
        print(f"{status} - {name}")
    
    success_count = sum(1 for r in results.values() if r["status"] == "success")
    print(f"\n总计: {success_count}/{len(results)} 个场景通过")
    
    return results


if __name__ == "__main__":
    # 设置API密钥（从环境变量读取）
    if not os.getenv("DEEPSEEK_API_KEY"):
        print("⚠️ 警告: 未设置 DEEPSEEK_API_KEY 环境变量")
        print("   意图识别功能将使用模拟数据")
        print("   如需启用，请设置: export DEEPSEEK_API_KEY=your-api-key\n")
    
    # 运行测试
    results = main()
    
    # 清理测试数据库（可选）
    print("\n" + "=" * 80)
    cleanup = input("是否清理测试数据库文件？(y/n): ").strip().lower()
    if cleanup == 'y':
        for db_file in ["test_scenario1.db", "test_scenario2.db", 
                       "test_scenario3.db", "test_scenario4.db"]:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"🗑️  已删除: {db_file}")
        print("✅ 清理完成")
