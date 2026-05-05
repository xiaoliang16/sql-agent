import openai
import json
from typing import List, Dict, Any, Optional

# 配置 API（以 DeepSeek 为例）
client = openai.OpenAI(
    api_key="your-api-key",
    base_url="https://api.deepseek.com/v1"  # 替换为实际 endpoint
)

# 意图定义（用于验证和提示词生成）
INTENT_DEFINITIONS = {
    "modify_prize_probability": {
        "description": "修改活动中奖品的概率",
        "parameters": {
            "activity_name": {"type": "string", "description": "活动名称"},
            "prize_name": {"type": "string", "description": "奖品名称"},
            "new_probability": {"type": "number", "description": "新的概率值，0~1之间"}
        },
        "required": ["activity_name", "prize_name", "new_probability"]
    },
    "generate_invitees": {
        "description": "为活动生成指定数量的邀请码",
        "parameters": {
            "activity_name": {"type": "string", "description": "活动名称"},
            "count": {"type": "integer", "description": "邀请码数量"}
        },
        "required": ["activity_name", "count"]
    },
    "set_reward_rule": {
        "description": "设置活动的奖励规则",
        "parameters": {
            "activity_name": {"type": "string", "description": "活动名称"},
            "action": {"type": "string", "enum": ["invite", "purchase"], "description": "触发动作"},
            "reward_type": {"type": "string", "enum": ["points", "coupon"], "description": "奖励类型"},
            "reward_value": {"type": "number", "description": "奖励数值"}
        },
        "required": ["activity_name", "action", "reward_type", "reward_value"]
    }
}

def build_system_prompt() -> str:
    """构建系统提示词，包含意图定义和输出格式要求"""
    intent_desc = []
    for name, defn in INTENT_DEFINITIONS.items():
        params_desc = ", ".join([f"{p} ({info['type']}): {info.get('description', '')}" for p, info in defn["parameters"].items()])
        intent_desc.append(f"- {name}: {defn['description']}，参数：{params_desc}，必需参数：{defn['required']}")
    
    prompt = f"""你是一个测试配置助手，负责将用户关于活动配置的需求转化为结构化的意图列表。支持以下意图：
{chr(10).join(intent_desc)}

请根据用户输入，返回一个 JSON 数组，数组每个元素包含两个字段：
- intent: 字符串，必须是上述意图名称之一。
- parameters: 对象，包含该意图所需的参数。如果参数缺失，请尽量从上下文推断，若无法推断则省略该参数（或设为 null）。

注意：如果用户输入包含多个需求，请返回多个意图对象。如果只有一个，也返回数组。

示例：
用户：把双十一活动的一等奖概率改成5%
输出：[{{"intent": "modify_prize_probability", "parameters": {{"activity_name": "双十一", "prize_name": "一等奖", "new_probability": 0.05}}}}]

用户：为新年活动配置10个邀请人，并设置奖励为积分10
输出：[{{"intent": "generate_invitees", "parameters": {{"activity_name": "新年活动", "count": 10}}}}, {{"intent": "set_reward_rule", "parameters": {{"activity_name": "新年活动", "action": "invite", "reward_type": "points", "reward_value": 10}}}}]

现在，请处理以下用户输入。
"""
    return prompt

def detect_intents(user_input: str, history: Optional[List[Dict[str, str]]] = None) -> List[Dict[str, Any]]:
    """调用模型进行多意图识别，返回意图列表"""
    messages = [{"role": "system", "content": build_system_prompt()}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_input})

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",  # 或其他模型名称
            messages=messages,
            response_format={"type": "json_object"},
            temperature=0.1,
        )
        content = response.choices[0].message.content
        # 解析 JSON
        intents = json.loads(content)
        # 确保是列表
        if not isinstance(intents, list):
            intents = [intents]  # 如果模型返回单个对象，转为列表
        # 基本验证：每个元素必须有 intent 和 parameters
        validated = []
        for item in intents:
            if isinstance(item, dict) and "intent" in item and "parameters" in item:
                validated.append(item)
            else:
                print(f"警告：忽略不符合格式的意图项: {item}")
        return validated
    except Exception as e:
        print(f"意图识别失败: {e}")
        return []

# 后处理示例：验证参数类型并补充默认值
def validate_and_fix_intents(intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """根据意图定义校验参数，尝试类型转换，标记缺失"""
    fixed = []
    for intent in intents:
        name = intent["intent"]
        params = intent.get("parameters", {})
        if name not in INTENT_DEFINITIONS:
            print(f"未知意图: {name}，跳过")
            continue
        defn = INTENT_DEFINITIONS[name]
        # 检查必需参数
        missing = [p for p in defn["required"] if p not in params]
        if missing:
            print(f"意图 {name} 缺少必需参数: {missing}，将在后续补齐")
        # 类型转换（简单示例）
        for p, value in list(params.items()):
            if p in defn["parameters"]:
                expected_type = defn["parameters"][p]["type"]
                try:
                    if expected_type == "number" and isinstance(value, str):
                        # 处理百分比 "5%" -> 0.05
                        if value.endswith("%"):
                            params[p] = float(value.rstrip("%")) / 100
                        else:
                            params[p] = float(value)
                    elif expected_type == "integer" and isinstance(value, str):
                        params[p] = int(value)
                except (ValueError, TypeError):
                    print(f"参数 {p} 类型转换失败，保留原值 {value}")
        fixed.append({"intent": name, "parameters": params})
    return fixed

# 示例使用
if __name__ == "__main__":
    # 单意图
    user_input1 = "把双十一活动的一等奖概率改成5%"
    intents1 = detect_intents(user_input1)
    print("原始意图1:", json.dumps(intents1, indent=2, ensure_ascii=False))
    fixed1 = validate_and_fix_intents(intents1)
    print("修复后1:", json.dumps(fixed1, indent=2, ensure_ascii=False))

    # 多意图
    user_input2 = "为新年活动配置10个邀请人，并设置奖励为积分10，同时将一等奖概率设为1%"
    intents2 = detect_intents(user_input2)
    print("原始意图2:", json.dumps(intents2, indent=2, ensure_ascii=False))
    fixed2 = validate_and_fix_intents(intents2)
    print("修复后2:", json.dumps(fixed2, indent=2, ensure_ascii=False))

    # 带历史对话
    history = [
        {"role": "assistant", "content": "好的，您想配置哪个活动？"},
        {"role": "user", "content": "就叫'新春大促'吧"}
    ]
    user_input3 = "为这个活动生成50个邀请码"
    intents3 = detect_intents(user_input3, history)
    print("带上下文意图3:", json.dumps(intents3, indent=2, ensure_ascii=False))