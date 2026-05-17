import openai
import json
import os
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum


# ==================== Intent Conflict Detection ====================

class ConflictType(Enum):
    """冲突类型枚举"""
    MUTUAL_EXCLUSION = "mutual_exclusion"  # 互斥冲突
    PARAMETER_CONFLICT = "parameter_conflict"  # 参数冲突
    ORDER_DEPENDENCY = "order_dependency"  # 顺序依赖
    RESOURCE_CONFLICT = "resource_conflict"  # 资源竞争
    LOGICAL_CONTRADICTION = "logical_contradiction"  # 逻辑矛盾


class ConflictSeverity(Enum):
    """冲突严重程度"""
    CRITICAL = "critical"  # 严重：必须解决才能执行
    WARNING = "warning"    # 警告：建议调整
    INFO = "info"          # 提示：仅提供信息


class IntentConflict:
    """意图冲突对象"""
    
    def __init__(
        self,
        conflict_type: ConflictType,
        severity: ConflictSeverity,
        intent1: str,
        intent2: str,
        description: str,
        suggestion: str = "",
        params_involved: List[str] = None
    ):
        self.conflict_type = conflict_type
        self.severity = severity
        self.intent1 = intent1
        self.intent2 = intent2
        self.description = description
        self.suggestion = suggestion
        self.params_involved = params_involved or []
    
    def to_dict(self) -> Dict:
        return {
            "conflict_type": self.conflict_type.value,
            "severity": self.severity.value,
            "intent1": self.intent1,
            "intent2": self.intent2,
            "description": self.description,
            "suggestion": self.suggestion,
            "params_involved": self.params_involved
        }


class ConflictDetector:
    """意图冲突检测器"""
    
    def __init__(self, registry: IntentRegistry):
        self.registry = registry
        # 定义互斥规则：哪些意图不能同时执行
        self.mutual_exclusions = self._load_mutual_exclusions()
        # 定义顺序依赖：某些意图必须在其他意图之前执行
        self.order_dependencies = self._load_order_dependencies()
        # 定义参数冲突规则
        self.parameter_conflicts = self._load_parameter_conflicts()
    
    def _load_mutual_exclusions(self) -> List[Tuple[str, str]]:
        """加载互斥规则"""
        return [
            # 示例：删除活动和修改活动互斥
            ("delete_activity", "modify_prize_probability"),
            ("delete_activity", "generate_invitees"),
            ("delete_activity", "set_reward_rule"),
            # 可以根据业务扩展更多规则
        ]
    
    def _load_order_dependencies(self) -> Dict[str, List[str]]:
        """加载顺序依赖规则：key必须在value之前执行"""
        return {
            # 示例：创建活动必须在其他操作之前
            "create_activity": ["modify_prize_probability", "generate_invitees", "set_reward_rule"],
            # 生成邀请码前应该先设置奖励规则
            "set_reward_rule": ["generate_invitees"],
        }
    
    def _load_parameter_conflicts(self) -> List[Dict]:
        """加载参数冲突规则"""
        return [
            {
                "intents": ["modify_prize_probability"],
                "param": "new_probability",
                "constraint": lambda v: 0 <= v <= 1,
                "error_msg": "概率值必须在0到1之间"
            },
            {
                "intents": ["generate_invitees"],
                "param": "count",
                "constraint": lambda v: v > 0 and v <= 10000,
                "error_msg": "邀请码数量必须在1到10000之间"
            }
        ]
    
    def detect_conflicts(self, intents: List[Dict[str, Any]]) -> List[IntentConflict]:
        """
        检测意图列表中的冲突
        
        :param intents: 意图列表，每个元素包含 intent 和 parameters
        :return: 冲突列表
        """
        conflicts = []
        
        if not intents or len(intents) < 1:
            return conflicts
        
        # 1. 检测互斥冲突
        conflicts.extend(self._check_mutual_exclusions(intents))
        
        # 2. 检测顺序依赖
        conflicts.extend(self._check_order_dependencies(intents))
        
        # 3. 检测参数冲突
        conflicts.extend(self._check_parameter_conflicts(intents))
        
        # 4. 检测资源竞争（同一资源的并发修改）
        conflicts.extend(self._check_resource_conflicts(intents))
        
        # 5. 检测逻辑矛盾
        conflicts.extend(self._check_logical_contradictions(intents))
        
        # 按严重程度排序
        severity_order = {
            ConflictSeverity.CRITICAL: 0,
            ConflictSeverity.WARNING: 1,
            ConflictSeverity.INFO: 2
        }
        conflicts.sort(key=lambda c: severity_order[c.severity])
        
        return conflicts
    
    def _check_mutual_exclusions(self, intents: List[Dict]) -> List[IntentConflict]:
        """检查互斥冲突"""
        conflicts = []
        intent_names = [i["intent"] for i in intents]
        
        for intent1_name, intent2_name in self.mutual_exclusions:
            if intent1_name in intent_names and intent2_name in intent_names:
                conflicts.append(IntentConflict(
                    conflict_type=ConflictType.MUTUAL_EXCLUSION,
                    severity=ConflictSeverity.CRITICAL,
                    intent1=intent1_name,
                    intent2=intent2_name,
                    description=f"意图 '{intent1_name}' 和 '{intent2_name}' 互斥，不能同时执行",
                    suggestion=f"请先执行 '{intent1_name}'，确认后再决定是否执行 '{intent2_name}'"
                ))
        
        return conflicts
    
    def _check_order_dependencies(self, intents: List[Dict]) -> List[IntentConflict]:
        """检查顺序依赖"""
        conflicts = []
        intent_names = [i["intent"] for i in intents]
        intent_positions = {i["intent"]: idx for idx, i in enumerate(intents)}
        
        for prereq_intent, dependent_intents in self.order_dependencies.items():
            if prereq_intent not in intent_names:
                continue
            
            prereq_pos = intent_positions[prereq_intent]
            
            for dependent in dependent_intents:
                if dependent in intent_names:
                    dependent_pos = intent_positions[dependent]
                    if prereq_pos > dependent_pos:
                        conflicts.append(IntentConflict(
                            conflict_type=ConflictType.ORDER_DEPENDENCY,
                            severity=ConflictSeverity.WARNING,
                            intent1=prereq_intent,
                            intent2=dependent,
                            description=f"意图 '{prereq_intent}' 应该在 '{dependent}' 之前执行",
                            suggestion=f"建议调整执行顺序：先执行 '{prereq_intent}'，再执行 '{dependent}'"
                        ))
        
        return conflicts
    
    def _check_parameter_conflicts(self, intents: List[Dict]) -> List[IntentConflict]:
        """检查参数冲突"""
        conflicts = []
        
        for rule in self.parameter_conflicts:
            for intent in intents:
                if intent["intent"] in rule["intents"]:
                    param_name = rule["param"]
                    if param_name in intent.get("parameters", {}):
                        value = intent["parameters"][param_name]
                        try:
                            if not rule["constraint"](value):
                                conflicts.append(IntentConflict(
                                    conflict_type=ConflictType.PARAMETER_CONFLICT,
                                    severity=ConflictSeverity.CRITICAL,
                                    intent1=intent["intent"],
                                    intent2="",
                                    description=f"意图 '{intent['intent']}' 的参数 '{param_name}' 值无效: {value}",
                                    suggestion=rule["error_msg"],
                                    params_involved=[param_name]
                                ))
                        except Exception as e:
                            conflicts.append(IntentConflict(
                                conflict_type=ConflictType.PARAMETER_CONFLICT,
                                severity=ConflictSeverity.CRITICAL,
                                intent1=intent["intent"],
                                intent2="",
                                description=f"意图 '{intent['intent']}' 的参数 '{param_name}' 验证失败: {str(e)}",
                                suggestion="请检查参数值的类型和范围",
                                params_involved=[param_name]
                            ))
        
        return conflicts
    
    def _check_resource_conflicts(self, intents: List[Dict]) -> List[IntentConflict]:
        """检查资源竞争冲突"""
        conflicts = []
        
        # 提取每个意图操作的资源（活动名称）
        resource_map = {}  # {resource_name: [intent_names]}
        
        for intent in intents:
            params = intent.get("parameters", {})
            activity_name = params.get("activity_name")
            
            if activity_name:
                if activity_name not in resource_map:
                    resource_map[activity_name] = []
                resource_map[activity_name].append(intent["intent"])
        
        # 检查同一资源是否被多个修改类意图操作
        for resource, intent_list in resource_map.items():
            if len(intent_list) > 1:
                # 检查是否有写-写冲突
                write_intents = [i for i in intent_list if self._is_write_intent(i)]
                
                if len(write_intents) > 1:
                    for i in range(len(write_intents)):
                        for j in range(i + 1, len(write_intents)):
                            conflicts.append(IntentConflict(
                                conflict_type=ConflictType.RESOURCE_CONFLICT,
                                severity=ConflictSeverity.WARNING,
                                intent1=write_intents[i],
                                intent2=write_intents[j],
                                description=f"多个意图同时修改活动 '{resource}': {write_intents[i]}, {write_intents[j]}",
                                suggestion="建议将这些操作放在一个事务中执行，或分步执行并验证中间状态",
                                params_involved=["activity_name"]
                            ))
        
        return conflicts
    
    def _check_logical_contradictions(self, intents: List[Dict]) -> List[IntentConflict]:
        """检查逻辑矛盾"""
        conflicts = []
        
        # 示例：检查概率总和是否超过1
        probability_intents = [
            i for i in intents 
            if i["intent"] == "modify_prize_probability"
        ]
        
        if len(probability_intents) > 1:
            # 如果多个意图修改同一活动的不同奖品概率，需要检查总和
            activity_probs = {}
            for intent in probability_intents:
                activity = intent["parameters"].get("activity_name")
                prob = intent["parameters"].get("new_probability")
                
                if activity and prob is not None:
                    if activity not in activity_probs:
                        activity_probs[activity] = []
                    activity_probs[activity].append({
                        "prize": intent["parameters"].get("prize_name"),
                        "probability": prob
                    })
            
            for activity, probs in activity_probs.items():
                total_prob = sum(p["probability"] for p in probs)
                if total_prob > 1.0:
                    prize_names = [p["prize"] for p in probs]
                    conflicts.append(IntentConflict(
                        conflict_type=ConflictType.LOGICAL_CONTRADICTION,
                        severity=ConflictSeverity.CRITICAL,
                        intent1="modify_prize_probability",
                        intent2="modify_prize_probability",
                        description=f"活动 '{activity}' 的奖品概率总和为 {total_prob:.2f}，超过1.0",
                        suggestion=f"涉及奖品: {', '.join(prize_names)}。请调整概率值使总和不超过1.0",
                        params_involved=["new_probability"]
                    ))
        
        return conflicts
    
    def _is_write_intent(self, intent_name: str) -> bool:
        """判断意图是否是写操作"""
        write_keywords = ["modify", "create", "delete", "update", "set", "generate", "remove"]
        return any(kw in intent_name.lower() for kw in write_keywords)
    
    def get_execution_order(self, intents: List[Dict]) -> List[Dict]:
        """
        根据依赖关系重新排序意图，返回推荐的执行顺序
        
        :param intents: 原始意图列表
        :return: 排序后的意图列表
        """
        if not intents:
            return []
        
        # 构建依赖图
        intent_positions = {i["intent"]: idx for idx, i in enumerate(intents)}
        
        # 拓扑排序
        sorted_intents = list(intents)  # 复制一份
        swapped = True
        
        while swapped:
            swapped = False
            for i in range(len(sorted_intents) - 1):
                intent1 = sorted_intents[i]["intent"]
                intent2 = sorted_intents[i + 1]["intent"]
                
                # 检查是否需要交换
                if self._should_swap(intent1, intent2):
                    sorted_intents[i], sorted_intents[i + 1] = sorted_intents[i + 1], sorted_intents[i]
                    swapped = True
        
        return sorted_intents
    
    def _should_swap(self, intent1: str, intent2: str) -> bool:
        """判断两个意图是否需要交换顺序"""
        # 如果intent1应该在intent2之后执行，则需要交换
        for prereq, dependents in self.order_dependencies.items():
            if intent2 == prereq and intent1 in dependents:
                return True
        return False


# ==================== Intent Registry ====================

class IntentRegistry:
    """意图定义注册器 - 支持从 JSON 加载和运行时动态注册"""

    def __init__(self, config_path: Optional[str] = None):
        self._definitions: Dict[str, Dict] = {}
        self._conflict_detector: Optional[ConflictDetector] = None
        if config_path:
            self.load_from_file(config_path)
        else:
            default_path = os.path.join(os.path.dirname(__file__), "intent_definitions.json")
            if os.path.exists(default_path):
                self.load_from_file(default_path)

    @property
    def conflict_detector(self) -> ConflictDetector:
        """获取冲突检测器（懒加载）"""
        if self._conflict_detector is None:
            self._conflict_detector = ConflictDetector(self)
        return self._conflict_detector

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

    def detect_conflicts(self, intents: List[Dict[str, Any]]) -> List[IntentConflict]:
        """
        检测意图列表中的冲突
        
        :param intents: 意图列表
        :return: 冲突列表
        """
        return self.conflict_detector.detect_conflicts(intents)
    
    def get_recommended_order(self, intents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        获取推荐的执行顺序
        
        :param intents: 意图列表
        :return: 排序后的意图列表
        """
        return self.conflict_detector.get_execution_order(intents)

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


def check_intent_conflicts(intents: List[Dict[str, Any]], registry: Optional[IntentRegistry] = None) -> Dict[str, Any]:
    """
    检测意图冲突并返回详细报告
    
    :param intents: 意图列表
    :param registry: 意图注册器
    :return: 冲突检测报告
    """
    if registry is None:
        registry = get_registry()
    
    conflicts = registry.detect_conflicts(intents)
    
    # 分类统计
    critical_conflicts = [c for c in conflicts if c.severity == ConflictSeverity.CRITICAL]
    warning_conflicts = [c for c in conflicts if c.severity == ConflictSeverity.WARNING]
    info_conflicts = [c for c in conflicts if c.severity == ConflictSeverity.INFO]
    
    report = {
        "has_conflicts": len(conflicts) > 0,
        "has_critical": len(critical_conflicts) > 0,
        "total_conflicts": len(conflicts),
        "critical_count": len(critical_conflicts),
        "warning_count": len(warning_conflicts),
        "info_count": len(info_conflicts),
        "conflicts": [c.to_dict() for c in conflicts],
        "can_execute": len(critical_conflicts) == 0
    }
    
    return report


def safe_execute_check(intents: List[Dict[str, Any]], registry: Optional[IntentRegistry] = None) -> Dict[str, Any]:
    """
    安全检查：验证+冲突检测+排序建议
    
    :param intents: 意图列表
    :param registry: 意图注册器
    :return: 完整的检查报告
    """
    if registry is None:
        registry = get_registry()
    
    # 1. 验证意图格式
    validated_intents = validate_and_fix_intents(intents, registry)
    
    # 2. 检测冲突
    conflict_report = check_intent_conflicts(validated_intents, registry)
    
    # 3. 获取推荐执行顺序
    recommended_order = registry.get_recommended_order(validated_intents)
    
    return {
        "validated_intents": validated_intents,
        "conflict_report": conflict_report,
        "recommended_order": recommended_order,
        "safe_to_execute": conflict_report["can_execute"] and len(validated_intents) > 0
    }

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
    
    # 冲突检测演示
    print("\n" + "=" * 60)
    print("冲突检测演示")
    print("=" * 60)
    
    # 测试1：概率总和超过1
    test_intents_1 = [
        {"intent": "modify_prize_probability", "parameters": {"activity_name": "双十一", "prize_name": "一等奖", "new_probability": 0.6}},
        {"intent": "modify_prize_probability", "parameters": {"activity_name": "双十一", "prize_name": "二等奖", "new_probability": 0.5}}
    ]
    print("\n【测试1】概率总和超过1:")
    report1 = check_intent_conflicts(test_intents_1)
    print(json.dumps(report1, indent=2, ensure_ascii=False))
    
    # 测试2：资源竞争
    test_intents_2 = [
        {"intent": "modify_prize_probability", "parameters": {"activity_name": "新年活动", "prize_name": "一等奖", "new_probability": 0.1}},
        {"intent": "generate_invitees", "parameters": {"activity_name": "新年活动", "count": 100}},
        {"intent": "set_reward_rule", "parameters": {"activity_name": "新年活动", "action": "invite", "reward_type": "points", "reward_value": 10}}
    ]
    print("\n【测试2】资源竞争检测:")
    report2 = safe_execute_check(test_intents_2)
    print(json.dumps(report2, indent=2, ensure_ascii=False))
    
    # 测试3：参数越界
    test_intents_3 = [
        {"intent": "modify_prize_probability", "parameters": {"activity_name": "活动A", "prize_name": "奖品1", "new_probability": 1.5}},
        {"intent": "generate_invitees", "parameters": {"activity_name": "活动B", "count": -10}}
    ]
    print("\n【测试3】参数越界检测:")
    report3 = check_intent_conflicts(test_intents_3)
    print(json.dumps(report3, indent=2, ensure_ascii=False))
