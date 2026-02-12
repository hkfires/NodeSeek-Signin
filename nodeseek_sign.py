# -*- coding: utf-8 -*-

import os
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from curl_cffi import requests
from yescaptcha import YesCaptchaSolver, YesCaptchaSolverError
from turnstile_solver import TurnstileSolver, TurnstileSolverError
# ---------------- 通知模块动态加载 ----------------
hadsend = False
send = None
try:
    from notify import send
    hadsend = True
except ImportError:
    print("未加载通知模块，跳过通知功能")

# ---------------- Docker Cookie 文件保存 ----------------
COOKIE_FILE_PATH = "./cookie/NS_COOKIE.txt"

def save_cookie_to_file(cookie_str: str, file_path: str):
    """将Cookie保存到文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w") as f:
            f.write(cookie_str)
        print(f"Cookie 已成功保存到文件: {file_path}")
        return True
    except Exception as e:
        print(f"保存Cookie到文件失败: {e}")
        return False

# ---------------- 登录逻辑 ----------------
def session_login(user, password, solver_type, api_base_url, client_key):
    try:
        if solver_type.lower() == "yescaptcha":
            print("正在使用 YesCaptcha 解决验证码...")
            solver = YesCaptchaSolver(
                api_base_url=api_base_url or "https://api.yescaptcha.com",
                client_key=client_key
            )
        else:  # 默认使用 turnstile_solver
            print("正在使用 TurnstileSolver 解决验证码...")
            solver = TurnstileSolver(
                api_base_url=api_base_url,
                client_key=client_key
            )

        token = solver.solve(
            url="https://www.nodeseek.com/signIn.html",
            sitekey="0x4AAAAAAAaNy7leGjewpVyR",
            verbose=True
        )
        if not token:
            print("验证码解析失败")
            return None
    except Exception as e:
        print(f"验证码错误: {e}")
        return None

    session = requests.Session(impersonate="chrome136")
    session.get("https://www.nodeseek.com/signIn.html")

    data = {
        "username": user,
        "password": password,
        "token": token,
        "source": "turnstile"
    }
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'sec-ch-ua': "\"Not A(Brand\";v=\"99\", \"Microsoft Edge\";v=\"121\", \"Chromium\";v=\"121\"",
        'sec-ch-ua-mobile': "?0",
        'sec-ch-ua-platform': "\"Windows\"",
        'origin': "https://www.nodeseek.com",
        'sec-fetch-site': "same-origin",
        'sec-fetch-mode': "cors",
        'sec-fetch-dest': "empty",
        'referer': "https://www.nodeseek.com/signIn.html",
        'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        'Content-Type': "application/json"
    }
    try:
        response = session.post("https://www.nodeseek.com/api/account/signIn", json=data, headers=headers)
        resp_json = response.json()
        if resp_json.get("success"):
            cookies = session.cookies.get_dict()
            cookie_string = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            return cookie_string
        else:
            print("登录失败:", resp_json.get("message"))
            return None
    except Exception as e:
        print("登录异常:", e)
        return None

# ---------------- 签到逻辑 ----------------
def sign(ns_cookie, ns_random):
    if not ns_cookie:
        return "invalid", "无有效Cookie"

    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': "https://www.nodeseek.com",
        'referer': "https://www.nodeseek.com/board",
        'Content-Type': 'application/json',
        'Cookie': ns_cookie
    }
    try:
        # 使用规范化后的布尔字符串 true/false 作为查询参数
        url = f"https://www.nodeseek.com/api/attendance?random={ns_random}"
        response = requests.post(url, headers=headers, impersonate="chrome136")
        if response.status_code == 403:
            print("[ERROR] 403 Forbidden - 仍被 Cloudflare 阻拦")
            print(f"[DEBUG] 响应内容: {response.text[:300]}")
            return "error", "403 Forbidden - Cloudflare 阻拦"
        data = response.json()
        msg = data.get("message", "")
        if "鸡腿" in msg or data.get("success"):
            return "success", msg
        elif "已完成签到" in msg:
            return "already", msg
        elif data.get("status") == 404:
            return "invalid", msg
        return "fail", msg
    except Exception as e:
        return "error", str(e)

# ---------------- 查询签到收益统计函数 ----------------
def get_signin_stats(ns_cookie, days=30):
    """查询前days天内的签到收益统计"""
    if not ns_cookie:
        return None, "无有效Cookie"

    if days <= 0:
        days = 1

    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': "https://www.nodeseek.com",
        'referer': "https://www.nodeseek.com/board",
        'Cookie': ns_cookie
    }

    try:
        # 使用UTC+8时区（上海时区）
        shanghai_tz = ZoneInfo("Asia/Shanghai")
        now_shanghai = datetime.now(shanghai_tz)

        # 计算查询开始时间：当前时间减去指定天数
        query_start_time = now_shanghai - timedelta(days=days)

        # 获取多页数据以确保覆盖指定天数内的所有数据
        all_records = []
        page = 1

        while page <= 20:  # 最多查询20页，防止无限循环
            url = f"https://www.nodeseek.com/api/account/credit/page-{page}"
            response = requests.get(url, headers=headers, impersonate="chrome136")
            data = response.json()

            if not data.get("success") or not data.get("data"):
                break

            records = data.get("data", [])
            if not records:
                break

            # 检查最后一条记录的时间，如果超出查询范围就停止
            last_record_time = datetime.fromisoformat(
                records[-1][3].replace('Z', '+00:00'))
            last_record_time_shanghai = last_record_time.astimezone(shanghai_tz)
            if last_record_time_shanghai < query_start_time:
                # 只添加在查询范围内的记录
                for record in records:
                    record_time = datetime.fromisoformat(
                        record[3].replace('Z', '+00:00'))
                    record_time_shanghai = record_time.astimezone(shanghai_tz)
                    if record_time_shanghai >= query_start_time:
                        all_records.append(record)
                break
            else:
                all_records.extend(records)

            page += 1
            time.sleep(0.5)

        # 筛选指定天数内的签到收益记录
        signin_records = []
        for record in all_records:
            amount, balance, description, timestamp = record
            record_time = datetime.fromisoformat(
                timestamp.replace('Z', '+00:00'))
            record_time_shanghai = record_time.astimezone(shanghai_tz)

            # 只统计指定天数内的签到收益
            if (record_time_shanghai >= query_start_time and
                    "签到收益" in description and "鸡腿" in description):
                signin_records.append({
                    'amount': amount,
                    'date': record_time_shanghai.strftime('%Y-%m-%d'),
                    'description': description
                })

        # 生成时间范围描述
        period_desc = f"近{days}天"
        if days == 1:
            period_desc = "今天"

        if not signin_records:
            return {
                'total_amount': 0,
                'average': 0,
                'days_count': 0,
                'records': [],
                'period': period_desc,
            }, f"查询成功，但没有找到{period_desc}的签到记录"

        # 统计数据
        total_amount = sum(record['amount'] for record in signin_records)
        days_count = len(signin_records)
        average = round(total_amount / days_count, 2) if days_count > 0 else 0

        stats = {
            'total_amount': total_amount,
            'average': average,
            'days_count': days_count,
            'records': signin_records,
            'period': period_desc
        }

        return stats, "查询成功"

    except Exception as e:
        return None, f"查询异常: {str(e)}"

# ---------------- 显示签到统计信息 ----------------
def print_signin_stats(stats, account_name):
    """打印签到统计信息"""
    if not stats:
        return

    print(f"\n==== {account_name} 签到收益统计 ({stats['period']}) ====")
    print(f"签到天数: {stats['days_count']} 天")
    print(f"总获得鸡腿: {stats['total_amount']} 个")
    print(f"平均每日鸡腿: {stats['average']} 个")

# ---------------- NodeSeek 执行入口 ----------------
def run_nodeseek_signins():
    print("==== NodeSeek 签到任务开始 ====")
    solver_type = os.getenv("SOLVER_TYPE", "turnstile")
    api_base_url = os.getenv("API_BASE_URL", "")
    client_key = os.getenv("CLIENTT_KEY", "")
    # 解析随机/固定签到开关，兼容大小写与多种写法
    def _bool_env(name: str, default: str = "true") -> str:
        raw = os.getenv(name, default)
        val = str(raw).strip().lower()
        return "true" if val in {"1", "true", "yes", "y", "on"} else "false"

    ns_random = _bool_env("NS_RANDOM", "true")

    print(f"NodeSeek 随机签到开关: {ns_random}")

    accounts = []

    user = os.getenv("NS_USER") or os.getenv("USER")
    password = os.getenv("NS_PASS") or os.getenv("PASS")
    if user and password:
        accounts.append({"user": user, "password": password})

    index = 1
    while True:
        user = os.getenv(f"NS_USER{index}") or os.getenv(f"USER{index}")
        password = os.getenv(f"NS_PASS{index}") or os.getenv(f"PASS{index}")
        if user and password:
            accounts.append({"user": user, "password": password})
            index += 1
        else:
            break

    all_cookies = ""
    print(f"尝试从 {COOKIE_FILE_PATH} 读取Cookie...")
    if os.path.exists(COOKIE_FILE_PATH):
        try:
            with open(COOKIE_FILE_PATH, "r") as f:
                all_cookies = f.read().strip()
            print("成功从文件加载Cookie。")
        except Exception as e:
            print(f"从文件读取Cookie失败: {e}")
    else:
        print("Cookie文件不存在，将使用空Cookie。")

    cookie_list = all_cookies.split("&")
    cookie_list = [c.strip() for c in cookie_list if c.strip()]

    print(f"共发现 {len(accounts)} 个账户配置，{len(cookie_list)} 个现有Cookie")

    if len(accounts) == 0 and len(cookie_list) > 0:
        for _ in range(len(cookie_list)):
            accounts.append({"user": "", "password": ""})

    max_count = max(len(accounts), len(cookie_list))

    while len(accounts) < max_count:
        accounts.append({"user": "", "password": ""})

    while len(cookie_list) < max_count:
        cookie_list.append("")

    cookies_updated = False

    for i in range(max_count):
        account_index = i + 1
        account = accounts[i]
        user = account["user"]
        password = account["password"]
        cookie = cookie_list[i] if i < len(cookie_list) else ""

        display_user = user if user else f"账号{account_index}"

        print(f"\n==== 账号 {display_user} 开始签到 ====")

        if cookie:
            result, msg = sign(cookie, ns_random)
        else:
            result, msg = "invalid", "无Cookie"

        if result in ["success", "already"]:
            print(f"账号 {display_user} 签到成功: {msg}")

            print("正在查询签到收益统计...")
            stats, stats_msg = get_signin_stats(cookie, 30)
            if stats:
                print_signin_stats(stats, display_user)
            else:
                print(f"统计查询失败: {stats_msg}")

            if hadsend:
                try:
                    notification_msg = f"账号 {display_user} 签到成功：{msg}"
                    if stats:
                        notification_msg += f"\n{stats['period']}已签到{stats['days_count']}天，共获得{stats['total_amount']}个鸡腿，平均{stats['average']}个/天"
                    send("NodeSeek 签到", notification_msg)
                except Exception as e:
                    print(f"发送通知失败: {e}")
        else:
            print(f"签到失败或Cookie无效: {msg}")

            if user and password:
                print("尝试重新登录获取新Cookie...")
                new_cookie = session_login(user, password, solver_type, api_base_url, client_key)
                if new_cookie:
                    print("登录成功，使用新Cookie重新签到...")
                    result, msg = sign(new_cookie, ns_random)
                    if result in ["success", "already"]:
                        print(f"账号 {display_user} 签到成功: {msg}")
                        cookies_updated = True

                        print("正在查询签到收益统计...")
                        stats, stats_msg = get_signin_stats(new_cookie, 30)
                        if stats:
                            print_signin_stats(stats, display_user)
                        else:
                            print(f"统计查询失败: {stats_msg}")

                        cookie_list[i] = new_cookie

                        if hadsend:
                            try:
                                notification_msg = f"账号 {display_user} 签到成功：{msg}"
                                if stats:
                                    notification_msg += f"\n{stats['period']}已签到{stats['days_count']}天，共获得{stats['total_amount']}个鸡腿，平均{stats['average']}个/天"
                                send("NodeSeek 签到", notification_msg)
                            except Exception as e:
                                print(f"发送通知失败: {e}")
                    else:
                        print(f"账号 {display_user} 重新签到仍然失败: {msg}")
                else:
                    print(f"账号 {display_user} 登录失败，无法获取新Cookie")
                    if hadsend:
                        try:
                            send("NodeSeek 登录失败", f"账号 {display_user} 登录失败")
                        except Exception as e:
                            print(f"发送通知失败: {e}")
            else:
                print(f"账号 {display_user} 无法重新登录: 未配置用户名或密码")

    if cookies_updated and cookie_list:
        print("\n==== 处理完毕，保存更新后的Cookie ====")
        all_cookies_new = "&".join([c for c in cookie_list if c.strip()])
        try:
            save_cookie_to_file(all_cookies_new, COOKIE_FILE_PATH)
            print("所有Cookie已成功保存")
        except Exception as e:
            print(f"保存Cookie变量异常: {e}")

# ---------------- Deepflood 登录与签到逻辑 ----------------
def df_session_login(user, password, solver_type, api_base_url, client_key):
    try:
        solver_choice = (solver_type or "turnstile").lower()
        if solver_choice == "yescaptcha":
            print("正在使用 YesCaptcha 解决验证码...")
            solver = YesCaptchaSolver(
                api_base_url=api_base_url or "https://api.yescaptcha.com",
                client_key=client_key
            )
        else:
            print("正在使用 TurnstileSolver 解决验证码...")
            solver = TurnstileSolver(
                api_base_url=api_base_url,
                client_key=client_key
            )

        token = solver.solve(
            url="https://www.deepflood.com/signIn.html",
            sitekey="0x4AAAAAAAaNy7leGjewpVyR",
            verbose=True
        )
        if not token:
            print("验证码解析失败")
            return None
    except Exception as e:
        print(f"验证码错误: {e}")
        return None

    session = requests.Session(impersonate="chrome136")
    session.get("https://www.deepflood.com/signIn.html")

    data = {
        "username": user,
        "password": password,
        "token": token,
        "source": "turnstile"
    }
    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'sec-ch-ua': "\"Not A(Brand\";v=\"99\", \"Microsoft Edge\";v=\"121\", \"Chromium\";v=\"121\"",
        'sec-ch-ua-mobile': "?0",
        'sec-ch-ua-platform': "\"Windows\"",
        'origin': "https://www.deepflood.com",
        'sec-fetch-site': "same-origin",
        'sec-fetch-mode': "cors",
        'sec-fetch-dest': "empty",
        'referer': "https://www.deepflood.com/signIn.html",
        'accept-language': "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
        'Content-Type': "application/json"
    }
    try:
        response = session.post("https://www.deepflood.com/api/account/signIn", json=data, headers=headers)
        resp_json = response.json()
        if resp_json.get("success"):
            cookies = session.cookies.get_dict()
            cookie_string = '; '.join([f"{k}={v}" for k, v in cookies.items()])
            return cookie_string
        else:
            print("登录失败:", resp_json.get("message"))
            return None
    except Exception as e:
        print("登录异常:", e)
        return None

def df_sign(df_cookie, df_random):
    if not df_cookie:
        return "invalid", "无有效Cookie"

    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': "https://www.deepflood.com",
        'referer': "https://www.deepflood.com/board",
        'Content-Type': 'application/json',
        'Cookie': df_cookie
    }
    try:
        # 使用规范化后的布尔字符串 true/false 作为查询参数
        url = f"https://www.deepflood.com/api/attendance?random={df_random}"
        response = requests.post(url, headers=headers, impersonate="chrome136")
        if response.status_code == 403:
            print("[ERROR] 403 Forbidden - 仍被 Cloudflare 阻拦")
            print(f"[DEBUG] 响应内容: {response.text[:300]}")
            return "error", "403 Forbidden - Cloudflare 阻拦"
        data = response.json()
        msg = data.get("message", "")
        if "鸡腿" in msg or data.get("success"):
            return "success", msg
        elif "已完成签到" in msg:
            return "already", msg
        elif data.get("status") == 404:
            return "invalid", msg
        return "fail", msg
    except Exception as e:
        return "error", str(e)

def df_get_signin_stats(df_cookie, days=30):
    """查询近 days 天内的签到收益统计"""
    if not df_cookie:
        return None, "无有效Cookie"

    if days <= 0:
        days = 1

    headers = {
        'User-Agent': "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
        'origin': "https://www.deepflood.com",
        'referer': "https://www.deepflood.com/board",
        'Cookie': df_cookie
    }

    try:
        shanghai_tz = ZoneInfo("Asia/Shanghai")
        now_shanghai = datetime.now(shanghai_tz)
        query_start_time = now_shanghai - timedelta(days=days)

        all_records = []
        page = 1

        while page <= 20:
            url = f"https://www.deepflood.com/api/account/credit/page-{page}"
            response = requests.get(url, headers=headers, impersonate="chrome136")
            data = response.json()

            if not data.get("success") or not data.get("data"):
                break

            records = data.get("data", [])
            if not records:
                break

            last_record_time = datetime.fromisoformat(records[-1][3].replace('Z', '+00:00')).astimezone(shanghai_tz)
            if last_record_time < query_start_time:
                for record in records:
                    record_time = datetime.fromisoformat(record[3].replace('Z', '+00:00')).astimezone(shanghai_tz)
                    if record_time >= query_start_time:
                        all_records.append(record)
                break
            else:
                all_records.extend(records)

            page += 1
            time.sleep(0.5)

        signin_records = []
        for record in all_records:
            amount, balance, description, timestamp = record
            record_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).astimezone(shanghai_tz)

            if (record_time >= query_start_time and
                    "签到收益" in description and "鸡腿" in description):
                signin_records.append({
                    'amount': amount,
                    'date': record_time.strftime('%Y-%m-%d'),
                    'description': description
                })

        period_desc = f"近{days}天"
        if days == 1:
            period_desc = "今天"

        if not signin_records:
            return {
                'total_amount': 0,
                'average': 0,
                'days_count': 0,
                'records': [],
                'period': period_desc
            }, f"查询成功，但没有找到{period_desc}的签到记录"

        total_amount = sum(record['amount'] for record in signin_records)
        days_count = len(signin_records)
        average = round(total_amount / days_count, 2) if days_count > 0 else 0

        stats = {
            'total_amount': total_amount,
            'average': average,
            'days_count': days_count,
            'records': signin_records,
            'period': period_desc
        }

        return stats, "查询成功"

    except Exception as e:
        return None, f"查询异常: {str(e)}"

def run_deepflood_signins():
    print("\n==== Deepflood 签到任务开始 ====")
    df_solver_type = os.getenv("DF_SOLVER_TYPE", os.getenv("SOLVER_TYPE", "turnstile"))
    api_base_url = os.getenv("DF_API_BASE_URL", os.getenv("API_BASE_URL", ""))
    client_key = os.getenv("DF_CLIENTT_KEY", os.getenv("CLIENTT_KEY", ""))
    # 复用上面的环境变量布尔解析
    def _bool_env(name: str, default: str = "true") -> str:
        raw = os.getenv(name, default)
        val = str(raw).strip().lower()
        return "true" if val in {"1", "true", "yes", "y", "on"} else "false"

    df_random = _bool_env("DF_RANDOM", "true")

    print(f"Deepflood 验证码模式: {df_solver_type}")
    print(f"Deepflood 随机签到开关: {df_random}")

    accounts = []

    user = os.getenv("DF_USER")
    password = os.getenv("DF_PASS")
    if user and password:
        accounts.append({"user": user, "password": password})

    index = 1
    while True:
        user = os.getenv(f"DF_USER{index}")
        password = os.getenv(f"DF_PASS{index}")
        if user and password:
            accounts.append({"user": user, "password": password})
            index += 1
        else:
            break

    df_cookie_file_path = "./cookie/DF_COOKIE.txt"
    all_cookies = ""
    print(f"尝试从 {df_cookie_file_path} 读取Cookie...")
    if os.path.exists(df_cookie_file_path):
        try:
            with open(df_cookie_file_path, "r") as f:
                all_cookies = f.read().strip()
            print("成功从文件加载Cookie。")
        except Exception as e:
            print(f"从文件读取Cookie失败: {e}")
    else:
        print("Cookie文件不存在，将使用空Cookie。")

    cookie_list = all_cookies.split("&")
    cookie_list = [c.strip() for c in cookie_list if c.strip()]

    print(f"共发现 {len(accounts)} 个账户配置，{len(cookie_list)} 个现有Cookie")

    if not accounts and not cookie_list:
        print("未检测到 Deepflood 配置，跳过执行。")
        return

    if len(accounts) == 0 and len(cookie_list) > 0:
        for _ in range(len(cookie_list)):
            accounts.append({"user": "", "password": ""})

    max_count = max(len(accounts), len(cookie_list))

    while len(accounts) < max_count:
        accounts.append({"user": "", "password": ""})

    while len(cookie_list) < max_count:
        cookie_list.append("")

    cookies_updated = False

    for i in range(max_count):
        account_index = i + 1
        account = accounts[i]
        user = account["user"]
        password = account["password"]
        cookie = cookie_list[i] if i < len(cookie_list) else ""

        display_user = user if user else f"账号{account_index}"

        print(f"\n==== Deepflood 账号 {display_user} 开始签到 ====")

        if cookie:
            result, msg = df_sign(cookie, df_random)
        else:
            result, msg = "invalid", "无Cookie"

        if result in ["success", "already"]:
            print(f"账号 {display_user} 签到成功: {msg}")

            print("正在查询签到收益统计...")
            stats, stats_msg = df_get_signin_stats(cookie, 30)
            if stats:
                print_signin_stats(stats, display_user)
            else:
                print(f"统计查询失败: {stats_msg}")

            if hadsend:
                try:
                    notification_msg = f"账号 {display_user} 签到成功：{msg}"
                    if stats:
                        notification_msg += f"\n{stats['period']}已签到{stats['days_count']}天，共获得{stats['total_amount']}个鸡腿，平均{stats['average']}个/天"
                    send("Deepflood 签到", notification_msg)
                except Exception as e:
                    print(f"发送通知失败: {e}")
        else:
            print(f"签到失败或Cookie无效: {msg}")

            if user and password:
                print("尝试重新登录获取新Cookie...")
                new_cookie = df_session_login(user, password, df_solver_type, api_base_url, client_key)
                if new_cookie:
                    print("登录成功，使用新Cookie重新签到...")
                    result, msg = df_sign(new_cookie, df_random)
                    if result in ["success", "already"]:
                        print(f"账号 {display_user} 签到成功: {msg}")
                        cookies_updated = True

                        print("正在查询签到收益统计...")
                        stats, stats_msg = df_get_signin_stats(new_cookie, 30)
                        if stats:
                            print_signin_stats(stats, display_user)
                        else:
                            print(f"统计查询失败: {stats_msg}")

                        cookie_list[i] = new_cookie

                        if hadsend:
                            try:
                                notification_msg = f"账号 {display_user} 签到成功：{msg}"
                                if stats:
                                    notification_msg += f"\n{stats['period']}已签到{stats['days_count']}天，共获得{stats['total_amount']}个鸡腿，平均{stats['average']}个/天"
                                send("Deepflood 签到", notification_msg)
                            except Exception as e:
                                print(f"发送通知失败: {e}")
                    else:
                        print(f"账号 {display_user} 重新签到仍然失败: {msg}")
                else:
                    print(f"账号 {display_user} 登录失败，无法获取新Cookie")
                    if hadsend:
                        try:
                            send("Deepflood 登录失败", f"账号 {display_user} 登录失败")
                        except Exception as e:
                            print(f"发送通知失败: {e}")
            else:
                print(f"账号 {display_user} 无法重新登录: 未配置用户名或密码")

    if cookies_updated and cookie_list:
        print("\n==== Deepflood 处理完毕，保存更新后的Cookie ====")
        all_cookies_new = "&".join([c for c in cookie_list if c.strip()])
        try:
            save_cookie_to_file(all_cookies_new, df_cookie_file_path)
            print("Deepflood Cookie 已成功保存")
        except Exception as e:
            print(f"保存Deepflood Cookie变量异常: {e}")


# ---------------- 主流程 ----------------
if __name__ == "__main__":
    run_nodeseek_signins()
    run_deepflood_signins()
