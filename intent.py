import openai
import json
import os
from typing import List, Dict, Any, Optional


# ==================== Intent Registry ====================

class IntentRegistry:
    """意图定义注册器 - 支持从 JSON 加载和运行时动态注册"""

    def __init__(self, config_path: Optional[str] = None):
        self._definitions: Dict[str, Dict] = {}
        if config_path:
            self.load_from_file(config_path)
        else:
            default_path = os.path.join(os.path.dirname(__file__), "intent_definitions.json")
            if os.path.exists(default_path):
                self.load_from_file(default_path)

    def load_from_file(self, file_path: str):
        """从 JSON 文件加载意图定义"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("意图定义文件必须是一个 JSON 对象")
        for name, defn in data.items():
            self._validate_definition(name, defn)
            self._definitions[name] = defn
        print(f"✅ 从 {file_path} 加载了 {len(data)} 个意图定义")

    def register(self, name: str, definition: Dict):
        """运行时注册一个新的意图"""
        if name in self._definitions:
            raise ValueError(f"意图 '{name}' 已注册")
        self._validate_definition(name, definition)
        self._definitions[name] = definition

    def unregister(self, name: str):
        """移除一个意图定义"""
        if name not in self._definitions:
            raise KeyError(f"意图 '{name}' 未注册")
        del self._definitions[name]

    def get(self, name: str) -> Optional[Dict]:
        """获取指定意图定义"""
        return self._definitions.get(name)

    def list_all(self) -> Dict[str, Dict]:
        """获取所有意图定义"""
        return dict(self._definitions)

    def list_names(self) -> List[str]:
        """获取所有意图名称"""
        return list(self._definitions.keys())

    def count(self) -> int:
        """获取意图数量"""
        return len(self._definitions)

    def validate_intent(self, intent_name: str, parameters: Dict) -> Dict:
        """校验意图参数并进行类型转换"""
        result = {"valid": True, "errors": [], "fixed_parameters": dict(parameters)}
        if intent_name not in self._definitions:
            result["valid"] = False
            result["errors"].append(f"未知意图: {intent_name}")
            return result

        defn = self._definitions[intent_name]
        fixed = result["fixed_parameters"]

        missing = [p for p in defn["required"] if p not in parameters]
        if missing:
            result["errors"].append(f"缺少必需参数: {missing}")

        for p, value in list(fixed.items()):
            if p in defn["parameters"]:
                expected = defn["parameters"][p]["type"]
                try:
                    converted = self._convert_type(value, expected)
                    if converted is not None:
                        fixed[p] = converted
                except (ValueError, TypeError) as e:
                    result["errors"].append(f"参数 {p} 类型转换失败: {e}")

        return result

    def _convert_type(self, value: Any, expected_type: str) -> Any:
        if expected_type == "number" and isinstance(value, str):
            if value.endswith("%"):
                return float(value.rstrip("%")) / 100
            return float(value)
        elif expected_type == "integer" and isinstance(value, str):
            return int(value)
        elif expected_type == "string" and not isinstance(value, str):
            return str(value)
        return None

    def _validate_definition(self, name: str, definition: Dict):
        for key in ["description", "parameters", "required"]:
            if key not in definition:
                raise ValueError(f"意图 '{name}' 缺少必需字段: {key}")
        if not isinstance(definition["description"], str):
            raise ValueError(f"意图 '{name}' description 必须是字符串")
        if not isinstance(definition["parameters"], dict):
            raise ValueError(f"意图 '{name}' parameters 必须是对象")
        if not isinstance(definition["required"], list):
            raise ValueError(f"意图 '{name}' required 必须是数组")
        for pn, pd in definition["parameters"].items():
            if "type" not in pd or "description" not in pd:
                raise ValueError(f"意图 '{name}' 参数 '{pn}' 缺少 type 或 description")

    def save_to_file(self, file_path: Optional[str] = None):
        """保存意图定义到 JSON 文件"""
        if file_path is None:
            file_path = os.path.join(os.path.dirname(__file__), "intent_definitions.json")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self._definitions, f, ensure_ascii=False, indent=2)
        print(f"✅ 已保存 {len(self._definitions)} 个意图定义到 {file_path}")


# 全局注册器单例
_registry: Optional[IntentRegistry] = None


def get_registry() -> IntentRegistry:
    """获取全局意图注册器实例（惰性初始化）"""
    global _registry
    if _registry is None:
        _registry = IntentRegistry()
    return _registry


# 配置 API
client = openai.OpenAI(
    api_key="your-api-key",
    base_url="https://api.deepseek.com/v1"
)

def build_system_prompt(registry: Optional[IntentRegistry] = None) -> str:
    """构建系统提示词，包含意图定义和输出格式要求"""
    if registry is None:
        registry = get_registry()

    intent_desc = []
    for name, defn in registry.list_all().items():
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

def detect_intents(user_input: str, history: Optional[List[Dict[str, str]]] = None, registry: Optional[IntentRegistry] = None) -> List[Dict[str, Any]]:
    """调用模型进行多意图识别，返回意图列表"""
    messages = [{"role": "system", "content": build_system_prompt(registry)}]
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

def validate_and_fix_intents(intents: List[Dict[str, Any]], registry: Optional[IntentRegistry] = None) -> List[Dict[str, Any]]:
    """根据意图定义校验参数，尝试类型转换，标记缺失"""
    if registry is None:
        registry = get_registry()

    fixed = []
    for intent in intents:
        name = intent["intent"]
        params = intent.get("parameters", {})

        validation = registry.validate_intent(name, params)
        if not validation["valid"]:
            print(f"未知意图: {name}，跳过")
            continue

        for error in validation["errors"]:
            print(f"意图 {name}: {error}")

        fixed.append({"intent": name, "parameters": validation["fixed_parameters"]})

    return fixed

# 示例使用
if __name__ == "__main__":
    registry = get_registry()
    print("=" * 60)
    print(f"已注册意图: {registry.list_names()}")
    print("=" * 60)

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

    # 运行时注册演示
    print("\n" + "=" * 60)
    print("运行时注册演示")
    print("=" * 60)
    registry.register("new_test_intent", {
        "description": "测试新增意图",
        "parameters": {
            "param1": {"type": "string", "description": "参数1"}
        },
        "required": ["param1"]
    })
    print(f"注册后意图列表: {registry.list_names()}")