# 表名: activity

## 表描述
活动信息主表，存储所有营销活动的基本信息和状态。

## 字段说明
| 字段名 | 类型 | 必填 | 说明 | 示例 |
|--------|------|------|------|------|
| id | INTEGER | 是 | 活动ID，主键自增 | 1 |
| name | VARCHAR(100) | 是 | 活动名称 | "双十一大促" |
| start_time | DATETIME | 否 | 活动开始时间 | "2024-11-01 00:00:00" |
| end_time | DATETIME | 否 | 活动结束时间 | "2024-11-30 23:59:59" |
| status | TINYINT | 是 | 状态：0-未开始，1-进行中，2-已结束 | 1 |

## 业务规则
- 活动必须在有效期内才能进行操作
- 修改活动状态需要记录操作日志
- 删除活动前必须先删除关联的奖品和邀请码

## 关联关系
- 一对多关联 `prize_config` 表（通过 activity_id）
- 一对多关联 `invitation_code` 表（通过 activity_id）

## 常用SQL示例

### 查询活动基本信息

SELECT id, name, start_time, end_time, status FROM activity WHERE name = ?;

### 查询进行中的活动

SELECT * FROM activity WHERE status = 1 AND start_time <= datetime('now') AND end_time >= datetime('now');

### 创建活动

INSERT INTO activity (name, start_time, end_time, status) VALUES (?, ?, ?, 0);

### 更新活动状态

UPDATE activity SET status = ? WHERE id = ?;

## 常见查询场景
- 根据活动名称查找活动ID
- 检查活动是否在有效期内
- 获取活动当前状态
