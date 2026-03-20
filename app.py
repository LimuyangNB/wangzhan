from flask import (
    Flask, render_template, g,
    request, session, redirect, url_for,
    jsonify  # 关键修复：导入jsonify
)
import sqlite3
import logging
from datetime import datetime
import os

# 初始化日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ai-creator-2026')  # 兼容环境变量
app.config['DATABASE'] = 'app.db'

# --------------------------
# 跨域配置（关键！前端能正常调用）
# --------------------------
@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    return response

# --------------------------
# 数据库操作
# --------------------------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(app.config['DATABASE'])
        db.row_factory = sqlite3.Row  # 支持字段名访问
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

# 初始化数据库（首次运行自动创建表）
def init_db():
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # 1. 用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                phone TEXT,
                is_vip INTEGER DEFAULT 0,
                create_time INTEGER NOT NULL
            )
        ''')
        
        # 2. 创作历史表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                prompt TEXT NOT NULL,
                content TEXT NOT NULL,
                create_time INTEGER NOT NULL
            )
        ''')
        
        # 3. 会员套餐表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vip_packages (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                price REAL NOT NULL,
                cycle TEXT NOT NULL,
                desc TEXT
            )
        ''')
        
        # 插入默认会员套餐
        cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                      ('monthly', '月度会员', 19.9, '月', '无限制创作次数+更多风格选择'))
        cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                      ('yearly', '年度会员', 199.0, '年', '全部特权+优先使用新功能'))
        
        db.commit()
        logger.info("数据库初始化完成")

# --------------------------
# 页面路由
# --------------------------
@app.route('/')
def index():
    return render_template('index.html')

# --------------------------
# API接口（核心功能）
# --------------------------

# 1. 用户登录
@app.route('/api/login', methods=['POST'])
def login():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', 
                      (username, password))
        user = cursor.fetchone()
        
        if user:
            # 生成简单token（实际项目建议用JWT）
            token = f"token_{user['user_id']}_{datetime.now().timestamp()}"
            return jsonify({
                'code': 200,
                'data': {
                    'user_id': user['user_id'],
                    'username': user['username'],
                    'is_vip': bool(user['is_vip']),
                    'token': token
                }
            })
        else:
            return jsonify({'code': 401, 'msg': '用户名或密码错误'})
    
    except Exception as e:
        logger.error(f"登录接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# 2. 用户注册
@app.route('/api/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        phone = data.get('phone', '').strip()
        
        if not username or not password:
            return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
        
        # 生成唯一user_id
        user_id = str(int(datetime.now().timestamp() * 1000))
        create_time = int(datetime.now().timestamp())
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO users (user_id, username, password, phone, create_time) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, password, phone, create_time)
        )
        db.commit()
        
        return jsonify({'code': 200, 'msg': '注册成功，请登录'})
    
    except sqlite3.IntegrityError:
        return jsonify({'code': 400, 'msg': '用户名已存在'})
    except Exception as e:
        logger.error(f"注册接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# 3. 获取创作历史（POST方法，修复405错误）
@app.route('/api/get_history', methods=['POST'])
def get_history():
    try:
        data = request.get_json()
        user_id = data.get('user_id', '').strip()
        
        if not user_id:
            return jsonify({'code': 400, 'msg': 'user_id不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM history WHERE user_id = ? ORDER BY create_time DESC', 
                      (user_id,))
        history_list = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({'code': 200, 'data': history_list})
    
    except Exception as e:
        logger.error(f"获取历史接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# 4. AI内容生成
@app.route('/api/ai_create', methods=['POST'])
def ai_create():
    try:
        data = request.get_json()
        user_id = data.get('user_id', '').strip()
        prompt = data.get('prompt', '').strip()
        type = data.get('type', 'short_video')
        
        if not user_id or not prompt:
            return jsonify({'code': 400, 'msg': '必要参数不能为空'})
        
        # 模拟AI生成（实际项目替换为真实大模型调用）
        if type == 'short_video':
            content = f"""【短视频创作结果】
需求：{prompt}
生成内容：
1. 标题：{prompt[:10]}+趣味吸睛后缀
2. 文案：{prompt}，用生动有趣的语言扩展至200字左右
3. 拍摄建议：搭配相关画面，语速适中，结尾引导互动
（注：实际部署请对接真实AI接口）"""
        else:
            content = f"""【办公创作结果】
需求：{prompt}
生成内容：
{prompt}，用正式/简洁的语言扩展至300字左右，逻辑清晰，重点突出
（注：实际部署请对接真实AI接口）"""
        
        # 保存到历史记录
        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            'INSERT INTO history (user_id, type, prompt, content, create_time) VALUES (?, ?, ?, ?, ?)',
            (user_id, type, prompt, content, int(datetime.now().timestamp()))
        )
        db.commit()
        
        return jsonify({
            'code': 200,
            'data': {'content': content}
        })
    
    except Exception as e:
        logger.error(f"AI生成接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# 5. 获取会员套餐
@app.route('/api/get_vip_packages', methods=['GET'])
def get_vip_packages():
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM vip_packages')
        packages = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({'code': 200, 'data': packages})
    
    except Exception as e:
        logger.error(f"获取套餐接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# 6. 创建会员订单
@app.route('/api/create_vip_order', methods=['POST'])
def create_vip_order():
    try:
        data = request.get_json()
        user_id = data.get('user_id', '').strip()
        package_id = data.get('package_id', '').strip()
        
        if not user_id or not package_id:
            return jsonify({'code': 400, 'msg': '参数不能为空'})
        
        # 模拟创建订单（实际项目对接支付网关）
        order_id = f"order_{int(datetime.now().timestamp() * 1000)}"
        return jsonify({
            'code': 200,
            'data': {
                'order_id': order_id,
                'pay_url': f'https://example.com/pay?order={order_id}'  # 模拟支付链接
            }
        })
    
    except Exception as e:
        logger.error(f"创建订单接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# --------------------------
# 全局错误处理
# --------------------------
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({'code': 404, 'msg': '接口不存在'}), 404

@app.errorhandler(405)
def method_not_allowed(e):
    return jsonify({'code': 405, 'msg': '请求方法不允许'}), 405

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({'code': 500, 'msg': '服务器内部错误'}), 500

# --------------------------
# 启动入口
# --------------------------
if __name__ == '__main__':
    init_db()  # 初始化数据库
    port = int(os.environ.get('PORT', 8080))  # 兼容Railway端口
    app.run(host='0.0.0.0', port=port, debug=False)  # 生产环境关闭debug
