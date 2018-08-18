from kagerofu.database import get_pg_connection, json_wrapper

def write_log(type, operator, comment):
    cnx = get_pg_connection()
    try:
        cursor = cnx.cursor()
        cursor.execute("INSERT INTO log (type, operator, datetime, data) "
                       "VALUES (%s, %s, NOW(), %s)",
                       (type, operator, json_wrapper(comment)))
        cnx.commit()
    finally:
        cnx.close()

def log_type_to_string(log_type):
    names = {
        "dashboard_access": "大本营访问",
        "login": "登录",
        "logout": "注销",
        "registration": "注册",
        "new_thread": "发表主题",
        "new_reply": "回复主题",
        "edit": "编辑",
        "update_userinfo": "更新用户信息",
        "update_profile": "更新用户档案",
        "category_merge": "分类合并",
        "category_new": "分类创建",
        "delete": "删除",
        "restore": "恢复"
    }

    ret = names.get(log_type)
    if ret == None:
        ret = log_type
    return ret

def log_data_simple(log_type, data):
    if log_type == "dashboard_access":
        return "成功" if data["success"] else "失败"
    elif log_type == "login":
        return "成功" if data["success"] else "失败"
    elif log_type == "logout":
        return ""
    elif log_type == "registration":
        return "成功" if data["success"] else "失败"
    elif log_type == "new_thread":
        return "成功" if data["success"] else "失败"
    elif log_type == "new_reply":
        return "成功" if data["success"] else "失败"
    elif log_type == "edit":
        return "成功" if data["success"] else "失败"
    elif log_type == "update_userinfo":
        return ""
    elif log_type == "update_profile":
        return ""
    elif log_type == "category_merge":
        return "{} -> {}".format(data["src"]["name"], data["dst"]["name"])
    elif log_type == "category_new":
        return data["category"]
    elif log_type in ["delete", "restore"]:
        type = "主题" if data["type"] == "thread" else "回复"
        return "{}: {}".format(type, data["id"])
