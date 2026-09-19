"""
测试数据清理的公用逻辑。

为什么单独抽成一个模块，而不是在各模块 conftest 里各写一遍：
    孤儿行清理必须在「所有会用到 at_ 测试数据的模块」里**完全一致**。
    分散在 4 个 conftest 里各写一份，很容易漏掉其中一个——
    而漏掉的那个模块会在下一次跑批时随机撞主键冲突，且很难归因。
    所以把这段逻辑收成一个函数，4 个模块各自调用同一份实现。
"""

from utils.recordlog import logs


def delete_orphan_relations(db):
    """
    清理关联表里「主体已经不在了」的孤儿行。

    ── 为什么需要 ──
    各模块 conftest 的 _delete_at_users / _delete_at_roles 是这么写的：
        DELETE FROM sys_user_role WHERE user_id IN
          (SELECT user_id FROM sys_user WHERE user_name LIKE 'at\\_%')
    它是靠 sys_user / sys_role 的**子查询先找到主体、再删关联**。
    所以「用户（或角色）已经被删掉、关联行却还留着」的孤儿行，
    对这段清理逻辑是**完全隐形**的——永远选不中，也就永远删不掉。

    ── 为什么危险 ──
    sys_user_role / sys_user_post / sys_role_menu / sys_role_dept 都是**复合主键**，
    孤儿行会一直占着 (id, id) 这个坑位。一旦自增 ID 被回收
    （人工物理删过数据、或服务重启后 MySQL 按 MAX(id)+1 重算自增），
    再建用户/角色就会撞主键：

        实测踩到过 —— Duplicate entry '157-2' for key 'PRIMARY'
        （sys_user_role 里残留 (157, 2)，sys_user 里已无 157，自增又把 157 发了出去）

    而且这个失败是**随机出现**的：只有当自增刚好回到那个被占用的 ID 时才复现，
    排查起来非常容易被带偏成"接口偶发 500"。

    ── 为什么安全 ──
    关联行找不到主体就是无意义数据（RuoYi 的逻辑删除只把 del_flag 置 '2'，
    行还在；行彻底没了说明是物理删除），删掉不影响任何正常业务。

    :param db: ConnectMysql 实例
    """
    # 用户侧关联：主体是 sys_user
    db.execute(
        "DELETE ur FROM sys_user_role ur "
        "LEFT JOIN sys_user u ON u.user_id = ur.user_id "
        "WHERE u.user_id IS NULL"
    )
    db.execute(
        "DELETE up FROM sys_user_post up "
        "LEFT JOIN sys_user u ON u.user_id = up.user_id "
        "WHERE u.user_id IS NULL"
    )

    # 角色侧关联：主体是 sys_role
    db.execute(
        "DELETE rm FROM sys_role_menu rm "
        "LEFT JOIN sys_role r ON r.role_id = rm.role_id "
        "WHERE r.role_id IS NULL"
    )
    db.execute(
        "DELETE rd FROM sys_role_dept rd "
        "LEFT JOIN sys_role r ON r.role_id = rd.role_id "
        "WHERE r.role_id IS NULL"
    )

    logs.info("已清理关联表孤儿行（sys_user_role / sys_user_post / sys_role_menu / sys_role_dept）")
