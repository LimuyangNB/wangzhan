# 导入必要的库
from flask import Flask, request, jsonify
import pymysql
import hashlib

# 初始化 Flask 应用
app = Flask(__name__)

# 数据库配置
DB_CONFIG = {
    'host': postgres.railway.internal,
    'user': postgres,
    'password': UDqEjxjaXGyXTdCyXTmWjneXNGAGnJXx,
    'database': railway,
    'port': 5432,
    'client_encoding': 'utf8'
}

# -------------------------- 核心接口 --------------------------
# 1. 根路由（解决 404 关键！）
@app.route('/')
def index():
    return jsonify({
        "status": "success",
        "message": "服务运行正常✅",
        "available_endpoints": {
            "GET /": "检查服务状态",
            "GET /api/get_vip_packages": "获取VIP套餐列表",
            "POST /api/login": "用户登录",
            "POST /api/register": "用户注册"
        }
    })

# 2. 获取VIP套餐接口
@app.route('/api/get_vip_packages', methods=['GET'])
def get_vip_packages():
    try:
        # 连接数据库
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        # 查询套餐数据
        cursor.execute("SELECT id, name, price, duration, description FROM vip_packages WHERE is_active = 1")
        packages = cursor.fetchall()
        
        # 关闭连接
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "data": packages
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取套餐失败：{str(e)}"
        }), 500

# 3. 用户登录接口
@app.route('/api/login', methods=['POST'])
def login():
    try:
        # 获取请求参数
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                "status": "error",
                "message": "用户名和密码不能为空"
            }), 400
        
        # 密码加密（和注册时保持一致）
        encrypted_pwd = hashlib.md5(password.encode()).hexdigest()
        
        # 连接数据库验证
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        
        cursor.execute("SELECT id, username, is_vip FROM users WHERE username = %s AND password = %s", 
                      (username, encrypted_pwd))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            return jsonify({
                "status": "success",
                "message": "登录成功",
                "data": user
            })
        else:
            return jsonify({
                "status": "error",
                "message": "用户名或密码错误"
            }), 401
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"登录失败：{str(e)}"
        }), 500

# 4. 用户注册接口
@app.route('/api/register', methods=['POST'])
def register():
    try:
        # 获取请求参数
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        
        if not username or not password or not email:
            return jsonify({
                "status": "error",
                "message": "用户名、密码、邮箱不能为空"
            }), 400
        
        # 密码加密
        encrypted_pwd = hashlib.md5(password.encode()).hexdigest()
        
        # 连接数据库
        conn = pymysql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 检查用户名是否已存在
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({
                "status": "error",
                "message": "用户名已存在"
            }), 409
        
        # 插入新用户
        cursor.execute(
            "INSERT INTO users (username, password, email, is_vip, create_time) VALUES (%s, %s, %s, 0, NOW())",
            (username, encrypted_pwd, email)
        )
        conn.commit()
        
        # 获取新用户ID
        user_id = cursor.lastrowid
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": "注册成功",
            "data": {"user_id": user_id, "username": username}
        }), 201
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"注册失败：{str(e)}"
        }), 500

# -------------------------- 启动配置 --------------------------
# 适配 Railway 部署（必须用 0.0.0.0 和环境变量端口）
if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)  # 生产环境关闭 debug
