# 导入必要的库（修复：新增 request 导入，替换 psycopg2 驱动）
from flask import Flask, jsonify, render_template, request
import psycopg2  # PostgreSQL 驱动（替换 pymysql）
import psycopg2.extras  # 用于 DictCursor
import hashlib
import os

# 初始化 Flask 应用
app = Flask(__name__)

# 数据库配置（修复：适配 PostgreSQL 格式）
DB_CONFIG = {
    'host': "postgres.railway.internal",
    'user': "postgres",
    'password': "UDqEjxjaXGyXTdCyXTmWjneXNGAGnJXx",
    'database': "railway",
    'port': 5432,  # PostgreSQL 默认端口是 5432（不是 7030）
    'options': '-c client_encoding=utf8'  # PostgreSQL 编码配置（替换 client_encoding）
}

# -------------------------- 核心接口 --------------------------
# 1. 根路由
@app.route('/')
def index():
    return render_template('index.html')

# 2. 获取VIP套餐接口（修复：适配 PostgreSQL 语法）
@app.route('/api/get_vip_packages', methods=['GET'])
def get_vip_packages():
    try:
        # 连接 PostgreSQL 数据库
        conn = psycopg2.connect(**DB_CONFIG)
        # 使用 DictCursor 让返回结果是字典格式
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # 查询套餐数据（SQL 语法和 MySQL 一致，无需修改）
        cursor.execute("SELECT id, name, price, duration, description FROM vip_packages WHERE is_active = 1")
        packages = cursor.fetchall()
        
        # 转换为普通列表（适配 JSON 序列化）
        packages_list = [dict(pkg) for pkg in packages]
        
        # 关闭连接
        cursor.close()
        conn.close()
        
        return jsonify({
            "status": "success",
            "data": packages_list
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": f"获取套餐失败：{str(e)}"
        }), 500

# 3. 用户登录接口（修复：适配 PostgreSQL 语法 + 补全 request 导入）
@app.route('/api/login', methods=['POST'])
def login():
    try:
        # 获取请求参数（修复：新增 request 导入后可正常使用）
        data = request.get_json()
        if not data:  # 新增：容错空请求
            return jsonify({
                "status": "error",
                "message": "请求格式错误，请传递 JSON 数据"
            }), 400
        
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({
                "status": "error",
                "message": "用户名和密码不能为空"
            }), 400
        
        # 密码加密（逻辑不变）
        encrypted_pwd = hashlib.md5(password.encode()).hexdigest()
        
        # 连接 PostgreSQL 验证
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # PostgreSQL 参数占位符是 %s（和 MySQL 一致，无需改）
        cursor.execute("SELECT id, username, is_vip FROM users WHERE username = %s AND password = %s", 
                      (username, encrypted_pwd))
        user = cursor.fetchone()
        
        cursor.close()
        conn.close()
        
        if user:
            return jsonify({
                "status": "success",
                "message": "登录成功",
                "data": dict(user)  # 转换为字典
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

# 4. 用户注册接口（修复：适配 PostgreSQL 语法 + 补全容错）
@app.route('/api/register', methods=['POST'])
def register():
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:  # 新增：容错空请求
            return jsonify({
                "status": "error",
                "message": "请求格式错误，请传递 JSON 数据"
            }), 400
        
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        
        if not username or not password or not email:
            return jsonify({
                "status": "error",
                "message": "用户名、密码、邮箱不能为空"
            }), 400
        
        # 密码加密（逻辑不变）
        encrypted_pwd = hashlib.md5(password.encode()).hexdigest()
        
        # 连接 PostgreSQL
        conn = psycopg2.connect(**DB_CONFIG)
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
        
        # 插入新用户（修复：PostgreSQL 用 CURRENT_TIMESTAMP 替换 NOW()）
        cursor.execute(
            "INSERT INTO users (username, password, email, is_vip, create_time) VALUES (%s, %s, %s, 0, CURRENT_TIMESTAMP)",
            (username, encrypted_pwd, email)
        )
        conn.commit()
        
        # 获取新用户ID（修复：PostgreSQL 获取自增ID的方式）
        cursor.execute("SELECT currval(pg_get_serial_sequence('users', 'id'))")
        user_id = cursor.fetchone()[0]
        
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
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
