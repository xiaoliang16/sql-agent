import json
import sqlite3
from typing import Any, Dict, List, Optional, Union

class ExecutionEngine:
    def __init__(self, db_path: str, allow_ddl: bool = False):
        """
        :param db_path: SQLite数据库文件路径
        :param allow_ddl: 是否允许执行DDL语句（如CREATE, ALTER），默认False
        """
        self.db_path = db_path
        self.allow_ddl = allow_ddl
        self.context = {}  # 上下文变量存储
        self.conn = None
        self.cursor = None

    def _connect(self):
        """建立数据库连接，开启事务"""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row  # 使查询结果可通过列名访问
        self.cursor = self.conn.cursor()

    def _close(self, commit: bool = True):
        """提交或回滚并关闭连接"""
        if self.conn:
            if commit:
                self.conn.commit()
            else:
                self.conn.rollback()
            self.conn.close()
            self.conn = None
            self.cursor = None

    def _resolve_params(self, params: List) -> List:
        """将参数中的{{变量名}}替换为上下文中的值，支持嵌套属性如intent.parameters.activity_name"""
        resolved = []
        for p in params:
            if isinstance(p, str) and p.startswith("{{") and p.endswith("}}"):
                var_path = p[2:-2].strip()
                # 支持点号路径，如 intent.parameters.activity_name
                value = self._get_nested(self.context, var_path)
                if value is None:
                    raise ValueError(f"上下文变量 {var_path} 未找到或为None")
                resolved.append(value)
            else:
                resolved.append(p)
        return resolved

    def _get_nested(self, data: dict, path: str):
        """从嵌套字典中通过点号路径取值"""
        keys = path.split('.')
        value = data
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    def _check_sql_safe(self, sql: str):
        """简单的安全检查：禁止DDL（除非允许）和删除所有数据等危险操作"""
        sql_upper = sql.strip().upper()
        if not self.allow_ddl:
            ddl_keywords = ["CREATE", "DROP", "ALTER", "TRUNCATE", "RENAME"]
            for kw in ddl_keywords:
                if sql_upper.startswith(kw):
                    raise PermissionError(f"禁止执行DDL语句: {sql}")
        # 可扩展更多检查，如禁止不带WHERE的DELETE
        if sql_upper.startswith("DELETE") and "WHERE" not in sql_upper:
            raise PermissionError("禁止执行不带WHERE条件的DELETE语句")
        return True

    def execute_plan(self, plan: Dict, initial_context: Optional[Dict] = None):
        """
        执行计划
        :param plan: 包含steps的字典
        :param initial_context: 初始上下文，例如意图参数
        :return: 执行结果列表
        """
        if initial_context:
            self.context.update(initial_context)
        steps = plan.get("steps", [])
        if not steps:
            return []

        self._connect()
        results = []
        try:
            for step in steps:
                result = self._execute_step(step)
                results.append(result)
                if "result_var" in step:
                    self.context[step["result_var"]] = result
            self._close(commit=True)
        except Exception as e:
            self._close(commit=False)
            raise e
        return results

    def _execute_step(self, step: Dict) -> Any:
        """执行单个步骤，根据type分发"""
        step_type = step.get("type")
        if step_type == "query":
            return self._execute_query(step)
        elif step_type == "update":
            return self._execute_update(step)
        elif step_type == "transaction":
            return self._execute_transaction(step)
        elif step_type == "user_confirmation":
            return self._execute_user_confirmation(step)
        elif step_type == "condition":
            return self._execute_condition(step)
        else:
            raise ValueError(f"未知步骤类型: {step_type}")

    def _execute_query(self, step: Dict) -> List[Dict]:
        sql = step["sql"]
        params = self._resolve_params(step.get("params", []))
        self._check_sql_safe(sql)
        self.cursor.execute(sql, params)
        rows = self.cursor.fetchall()
        # 将sqlite3.Row对象转为字典
        return [dict(row) for row in rows]

    def _execute_update(self, step: Dict) -> Dict:
        sql = step["sql"]
        params = self._resolve_params(step.get("params", []))
        self._check_sql_safe(sql)
        self.cursor.execute(sql, params)
        return {"affected_rows": self.cursor.rowcount}

    def _execute_transaction(self, step: Dict) -> List:
        """事务步骤：对其子步骤顺序执行，若失败则整体回滚（由外层事务统一控制，这里不单独处理）"""
        # 简单实现：直接递归执行子步骤，如果其中失败，异常会抛出，外层回滚
        sub_steps = step.get("steps", [])
        results = []
        for sub_step in sub_steps:
            results.append(self._execute_step(sub_step))
        return results

    def _execute_user_confirmation(self, step: Dict) -> Dict:
        message = step.get("message", "是否继续执行？")
        print(f"[需要确认] {message}")
        # 实际应用中可集成对话系统，这里简单用input模拟
        while True:
            resp = input("请输入 y(确认)/n(取消): ").strip().lower()
            if resp == 'y':
                return {"confirmed": True}
            elif resp == 'n':
                raise Exception("用户取消了操作")
            else:
                print("输入错误，请重试。")

    def _execute_condition(self, step: Dict) -> Any:
        condition_sql = step["condition_sql"]
        params = self._resolve_params(step.get("params", []))
        self._check_sql_safe(condition_sql)
        self.cursor.execute(condition_sql, params)
        row = self.cursor.fetchone()
        condition_true = bool(row[0]) if row else False
        if condition_true:
            # if_true_steps 可以是一个步骤对象或步骤数组
            true_steps = step["if_true_steps"]
            return self._execute_step(true_steps) if isinstance(true_steps, dict) else [self._execute_step(s) for s in true_steps]
        else:
            false_steps = step["if_false_steps"]
            return self._execute_step(false_steps) if isinstance(false_steps, dict) else [self._execute_step(s) for s in false_steps]