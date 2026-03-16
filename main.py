from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import random
import string

app = Flask(__name__)
CORS(app)

# 模拟数据库
users = {}
vip_packages = {
    1: {"name": "月会员", "price": 19.9, "duration": 30 * 24 * 3600},
    2: {"name": "季会员", "price": 49.9, "duration": 90 * 24 * 3600},
    3: {"name": "年会员", "price": 159.9, "duration": 365 * 24 * 3600}
}
orders = {}
history = []

def generate_id(prefix="user"):
    return f"{prefix}_{int(time.time())}_{random.randint(1000, 9999)}"

def generate_order_no():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=16))

# 登录
@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')

    for uid, info in users.items():
        if info['username'] == username and info['password'] == password:
            return jsonify({
                "code": 0,
                "msg": "登录成功",
                "data": {
                    "user_id": uid,
                    "username": username,
                    "vip_type": info['vip_type'],
                    "vip_expire_time": info['vip_expire_time']
                }
            })
    return jsonify({"code": 1, "msg": "用户名或密码错误"})

# 注册
@app.route('/api/register', methods=['POST'])
def api_register():
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    phone = data.get('phone', '')

    for uid, info in users.items():
        if info['username'] == username:
            return jsonify({"code": 1, "msg": "用户名已存在"})

    user_id = generate_id()
    users[user_id] = {
        "username": username,
        "password": password,
        "phone": phone,
        "vip_type": 0,
        "vip_expire_time": 0,
        "free_count": 3,
        "create_time": int(time.time())
    }
    return jsonify({"code": 0, "msg": "注册成功"})

# 获取用户信息
@app.route('/api/get_user_info', methods=['POST'])
def api_get_user_info():
    data = request.get_json()
    user_id = data.get('user_id')
    user = users.get(user_id)
    if not user:
        return jsonify({"code": 404, "msg": "用户不存在"})

    return jsonify({
        "code": 0,
        "data": {
            "free_count": user['free_count'],
            "vip_type": user['vip_type'],
            "vip_expire_time": user['vip_expire_time']
        }
    })

# AI 生成
@app.route('/api/ai_create', methods=['POST'])
def api_ai_create():
    data = request.get_json()
    user_id = data.get('user_id')
    prompt = data.get('prompt')
    req_type = data.get('req_type')

    user = users.get(user_id)
    if not user:
        return jsonify({"code": 404, "msg": "用户不存在"})

    if user['vip_type'] == 0:
        if user['free_count'] <= 0:
            return jsonify({"code": 403, "msg": "免费次数已用完，请开通VIP"})
        user['free_count'] -= 1

    fake_content = f"【AI 生成结果】\n需求：{prompt}\n\n这是一段自动生成的演示内容，替换成你自己的模型接口即可。"

    history.append({
        "user_id": user_id,
        "type": req_type,
        "prompt": prompt,
        "content": fake_content,
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    })

    return jsonify({"code": 0, "data": {"content": fake_content}})

# 获取VIP套餐
@app.route('/api/get_vip_packages', methods=['GET'])
def api_get_vip_packages():
    return jsonify({"code": 0, "data": vip_packages})

# 创建订单
@app.route('/api/create_vip_order', methods=['POST'])
def api_create_vip_order():
    data = request.get_json()
    user_id = data.get('user_id')
    package_id = int(data.get('package_id'))

    if package_id not in vip_packages:
        return jsonify({"code": 1, "msg": "套餐不存在"})

    order_no = generate_order_no()
    orders[order_no] = {
        "user_id": user_id,
        "package_id": package_id,
        "status": 0,
        "create_time": int(time.time()),
        "pay_time": 0
    }
    return jsonify({"code": 0, "data": {"order_no": order_no}})

# 查询订单状态（模拟支付成功）
@app.route('/api/query_order_status', methods=['POST'])
def api_query_order_status():
    data = request.get_json()
    order_no = data.get('order_no')
    order = orders.get(order_no)

    if not order:
        return jsonify({"code": 1, "msg": "订单不存在"})

    user = users.get(order['user_id'])
    pkg = vip_packages[order['package_id']]
    now = int(time.time())

    user['vip_type'] = 1
    user['vip_expire_time'] = now + pkg['duration']
    order['status'] = 1
    order['pay_time'] = now

    return jsonify({"code": 0, "data": {"status": 1}})

# 获取历史记录
@app.route('/api/get_history', methods=['POST'])
def api_get_history():
    data = request.get_json()
    user_id = data.get('user_id')
    user_history = [h for h in history if h['user_id'] == user_id]
    return jsonify({"code": 0, "data": user_history})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
