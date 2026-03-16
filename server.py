import os
import json
import time
import sqlite3
import hashlib
import logging
import requests
from logging.handlers import TimedRotatingFileHandler
from flask import Flask, request, jsonify, g
import secrets

# ====================== 核心配置（请在这里填写你的内测API信息） ======================
# 你的内测API Key
API_KEY = "sk-e3xlGOKCvkFCik0X9c0eHukXNs1ZEtdrsA8fwcsKLRFEH4Wv"
# API Host：国内用 api.chatanywhere.tech ，国外用 api.chatanywhere.org
API_HOST = "api.chatanywhere.tech"
# 固定使用GPT-4o模型
MODEL_NAME = "gpt-4o"
# API超时时间（秒）
API_TIMEOUT = 60
# ======================================================================================

# ========== 1. 日志配置 ==========
def setup_logger():
    """初始化日志配置：按天分割，保留7天日志"""
    if not os.path.exists("logs"):
        os.makedirs("logs")
    
    log_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(module)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    log_handler = TimedRotatingFileHandler(
        filename='logs/server.log',
        when='midnight',
        interval=1,
        backupCount=7,
        encoding='utf-8'
    )
    log_handler.suffix = '%Y%m%d.log'
    log_handler.setFormatter(log_formatter)
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    logger = logging.getLogger('ai_creator')
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logger()

# ========== 2. 基础配置 ==========
# 基础配置
app = Flask(__name__)

# 自动管理SECRET_KEY，重启不失效
SECRET_KEY_FILE = '.secret_key'
if os.path.exists(SECRET_KEY_FILE):
    # 已有密钥，直接读取
    with open(SECRET_KEY_FILE, 'r', encoding='utf-8') as f:
        app.config['SECRET_KEY'] = f.read().strip()
else:
    # 首次运行，生成新密钥并保存
    new_key = secrets.token_hex(32)
    with open(SECRET_KEY_FILE, 'w', encoding='utf-8') as f:
        f.write(new_key)
    app.config['SECRET_KEY'] = new_key
    # 把密钥文件加入.gitignore，避免泄露
    if not os.path.exists('.gitignore'):
        with open('.gitignore', 'w', encoding='utf-8') as f:
            f.write('.secret_key\nai_creator.db\nlogs/\n__pycache__/\n')

DATABASE = 'ai_creator.db'

# ========== 3. 数据库操作 ==========
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """初始化数据库"""
    with app.app_context():
        db = get_db()
        cursor = db.cursor()
        
        # 用户表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            vip_type INTEGER DEFAULT 0,
            vip_expire_time INTEGER DEFAULT 0,
            free_count INTEGER DEFAULT 3,
            create_time INTEGER DEFAULT (strftime('%s', 'now'))
        )
        ''')
        
        # VIP套餐表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS vip_packages (
            package_id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            duration INTEGER NOT NULL
        )
        ''')
        
        # 订单表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            package_id INTEGER NOT NULL,
            order_no TEXT UNIQUE NOT NULL,
            status INTEGER DEFAULT 0,
            create_time INTEGER DEFAULT (strftime('%s', 'now')),
            pay_time INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (package_id) REFERENCES vip_packages(package_id)
        )
        ''')
        
        # 生成记录
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS create_records (
            record_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            req_type TEXT NOT NULL,
            prompt TEXT NOT NULL,
            content TEXT NOT NULL,
            create_time INTEGER DEFAULT (strftime('%s', 'now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        ''')
        
        # 初始化VIP套餐
        cursor.execute('SELECT COUNT(*) FROM vip_packages')
        if cursor.fetchone()[0] == 0:
            packages = [
                (1, '月会员', 19.9, 30*24*3600),
                (2, '季会员', 49.9, 90*24*3600),
                (3, '年会员', 199.0, 365*24*3600)
            ]
            cursor.executemany('INSERT INTO vip_packages VALUES (?,?,?,?)', packages)
        
        db.commit()
        logger.info("数据库初始化完成")

# ========== 4. 工具函数 ==========
def generate_order_no(user_id):
    """生成唯一订单号"""
    timestamp = str(int(time.time()))
    random_str = hashlib.md5(f"{user_id}{timestamp}".encode()).hexdigest()[:8]
    return f"VIP{user_id}{timestamp}{random_str}"

def call_gpt4o_api(system_prompt, user_prompt):
    """调用GPT-4o API，返回生成的内容"""
    # 拼接完整的API地址
    api_url = f"https://{API_HOST}/v1/chat/completions"
    # 请求头
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }
    # 请求体
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.7,
        "stream": False
    }

    try:
        logger.info(f"开始调用GPT-4o API | 模型：{MODEL_NAME} | Host：{API_HOST}")
        # 发送请求
        response = requests.post(
            url=api_url,
            headers=headers,
            json=payload,
            timeout=API_TIMEOUT
        )
        # 处理响应
        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            logger.info(f"GPT-4o API调用成功 | 响应长度：{len(content)}")
            return True, content
        else:
            error_msg = f"API调用失败，状态码：{response.status_code}，响应：{response.text}"
            logger.error(error_msg)
            return False, f"生成失败：{error_msg}"
    except requests.exceptions.Timeout:
        error_msg = "API请求超时，请重试"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"API调用异常：{str(e)}"
        logger.error(error_msg, exc_info=True)
        return False, error_msg

# ========== 5. API接口 ==========
@app.route('/api/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        phone = data.get('phone', '').strip()
        
        if not username or not password:
            logger.warn(f"注册失败：用户名/密码为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
        
        pwd_hash = hashlib.md5(password.encode()).hexdigest()
        
        db = get_db()
        cursor = db.cursor()
        
        try:
            cursor.execute(
                'INSERT INTO users (username, password, phone) VALUES (?,?,?)',
                (username, pwd_hash, phone)
            )
            db.commit()
            logger.info(f"用户注册成功 | 用户名：{username} | 手机号：{phone}")
            return jsonify({'code': 200, 'msg': '注册成功'})
        except sqlite3.IntegrityError:
            logger.warn(f"注册失败：用户名已存在 | 用户名：{username}")
            return jsonify({'code': 409, 'msg': '用户名已存在'})
    except Exception as e:
        logger.error(f"注册接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json() or {}
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            logger.warn(f"登录失败：用户名/密码为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
        
        pwd_hash = hashlib.md5(password.encode()).hexdigest()
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(
            'SELECT user_id, username, vip_type, vip_expire_time FROM users WHERE username=? AND password=?',
            (username, pwd_hash)
        )
        user = cursor.fetchone()
        
        if user:
            logger.info(f"用户登录成功 | 用户名：{username} | 用户ID：{user['user_id']}")
            return jsonify({
                'code': 200,
                'msg': '登录成功',
                'data': {
                    'user_id': user['user_id'],
                    'username': user['username'],
                    'vip_type': user['vip_type'],
                    'vip_expire_time': user['vip_expire_time']
                }
            })
        else:
            logger.warn(f"登录失败：用户名/密码错误 | 用户名：{username}")
            return jsonify({'code': 401, 'msg': '用户名或密码错误'})
    except Exception as e:
        logger.error(f"登录接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/get_user_info', methods=['POST'])
def get_user_info():
    """获取用户信息"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        
        if not user_id:
            logger.warn(f"获取用户信息失败：用户ID为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '用户ID不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(
            'SELECT vip_type, vip_expire_time, free_count FROM users WHERE user_id=?',
            (user_id,)
        )
        user = cursor.fetchone()
        
        if user:
            current_time = int(time.time())
            vip_type = user['vip_type'] if (user['vip_expire_time'] > current_time) else 0
            
            logger.info(f"获取用户信息成功 | 用户ID：{user_id} | VIP类型：{vip_type}")
            return jsonify({
                'code': 200,
                'data': {
                    'vip_type': vip_type,
                    'vip_expire_time': user['vip_expire_time'],
                    'free_count': user['free_count']
                }
            })
        else:
            logger.warn(f"获取用户信息失败：用户不存在 | 用户ID：{user_id}")
            return jsonify({'code': 404, 'msg': '用户不存在'})
    except Exception as e:
        logger.error(f"获取用户信息接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/get_vip_packages', methods=['GET'])
def get_vip_packages():
    """获取VIP套餐列表"""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT package_id, name, price, duration FROM vip_packages')
        packages = cursor.fetchall()
        
        package_dict = {}
        for pkg in packages:
            package_dict[pkg['package_id']] = {
                'name': pkg['name'],
                'price': pkg['price'],
                'duration': pkg['duration']
            }
        
        logger.info("获取VIP套餐列表成功")
        return jsonify({'code': 200, 'data': package_dict})
    except Exception as e:
        logger.error(f"获取VIP套餐接口异常：{str(e)}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/create_vip_order', methods=['POST'])
def create_vip_order():
    """创建VIP订单"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        package_id = data.get('package_id')
        
        if not user_id or not package_id:
            logger.warn(f"创建订单失败：参数为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '用户ID和套餐ID不能为空'})
        
        order_no = generate_order_no(user_id)
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('SELECT package_id FROM vip_packages WHERE package_id=?', (package_id,))
        if not cursor.fetchone():
            logger.warn(f"创建订单失败：套餐不存在 | 套餐ID：{package_id} | 用户ID：{user_id}")
            return jsonify({'code': 404, 'msg': '套餐不存在'})
        
        cursor.execute(
            'INSERT INTO orders (user_id, package_id, order_no) VALUES (?,?,?)',
            (user_id, package_id, order_no)
        )
        db.commit()
        
        logger.info(f"创建VIP订单成功 | 订单号：{order_no} | 用户ID：{user_id} | 套餐ID：{package_id}")
        return jsonify({
            'code': 200,
            'msg': '订单创建成功',
            'data': {'order_no': order_no}
        })
    except Exception as e:
        logger.error(f"创建VIP订单接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/query_order_status', methods=['POST'])
def query_order_status():
    """查询订单状态"""
    try:
        data = request.get_json() or {}
        order_no = data.get('order_no', '').strip()
        
        if not order_no:
            logger.warn(f"查询订单失败：订单号为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '订单号不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(
            'SELECT order_id, user_id, package_id, status, pay_time FROM orders WHERE order_no=?',
            (order_no,)
        )
        order = cursor.fetchone()
        
        if not order:
            logger.warn(f"查询订单失败：订单不存在 | 订单号：{order_no}")
            return jsonify({'code': 404, 'msg': '订单不存在'})
        
        if order['status'] == 0:
            pay_time = int(time.time())
            cursor.execute(
                'UPDATE orders SET status=1, pay_time=? WHERE order_no=?',
                (pay_time, order_no)
            )
            
            cursor.execute('SELECT duration FROM vip_packages WHERE package_id=?', (order['package_id'],))
            duration = cursor.fetchone()['duration']
            
            current_time = int(time.time())
            cursor.execute(
                'UPDATE users SET vip_type=?, vip_expire_time=? WHERE user_id=?',
                (order['package_id'], current_time + duration, order['user_id'])
            )
            
            db.commit()
            logger.info(f"订单支付成功 | 订单号：{order_no} | 用户ID：{order['user_id']}")
        
        logger.info(f"查询订单状态成功 | 订单号：{order_no} | 状态：{order['status']}")
        return jsonify({
            'code': 200,
            'data': {
                'status': 1,
                'pay_time': pay_time if 'pay_time' in locals() else order['pay_time']
            }
        })
    except Exception as e:
        logger.error(f"查询订单状态接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/ai_create', methods=['POST'])
def ai_create():
    """AI内容生成（对接真实GPT-4o）"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        req_type = data.get('req_type', '').strip()
        prompt = data.get('prompt', '').strip()
        platform = data.get('platform', '').strip()
        tone = data.get('tone', '').strip()
        
        if not user_id or not req_type or not prompt:
            logger.warn(f"AI生成失败：参数为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '必要参数不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute(
            'SELECT vip_type, vip_expire_time, free_count FROM users WHERE user_id=?',
            (user_id,)
        )
        user = cursor.fetchone()
        
        if not user:
            logger.warn(f"AI生成失败：用户不存在 | 用户ID：{user_id}")
            return jsonify({'code': 404, 'msg': '用户不存在'})
        
        current_time = int(time.time())
        is_vip = user['vip_type'] > 0 and user['vip_expire_time'] > current_time
        
        # 非VIP检查免费次数
        if not is_vip:
            if user['free_count'] <= 0:
                logger.warn(f"AI生成失败：免费次数用尽 | 用户ID：{user_id}")
                return jsonify({'code': 403, 'msg': '今日免费次数已用尽，请开通VIP'})
            
            # 扣减免费次数
            cursor.execute(
                'UPDATE users SET free_count = free_count - 1 WHERE user_id=?',
                (user_id,)
            )
            db.commit()
        
        # ========== 构建GPT-4o Prompt ==========
        if req_type == "short_video":
            system_prompt = f"""
            你是一个专业的短视频内容创作专家，擅长{platform}平台的{tone}风格内容创作。
            要求：
            1. 内容完全贴合用户的创作需求，符合{platform}平台的流量规则和用户喜好
            2. 风格严格按照{tone}来创作，语言口语化、有网感，符合短视频的节奏
            3. 结构清晰，有开头钩子、主体内容、结尾引导，适合口播拍摄
            4. 内容原创、合规，不涉及违规内容
            """
            user_prompt = f"创作需求：{prompt}"
        else:
            system_prompt = f"""
            你是一个专业的办公文案创作专家，擅长{tone}风格的办公文档、文案创作。
            要求：
            1. 内容完全贴合用户的创作需求，逻辑清晰、结构严谨
            2. 风格严格按照{tone}来创作，符合职场办公的规范
            3. 内容专业、得体，符合商务场景的使用要求
            4. 内容原创、合规，不涉及违规内容
            """
            user_prompt = f"创作需求：{prompt}"
        
        # 调用GPT-4o API
        success, content = call_gpt4o_api(system_prompt, user_prompt)
        if not success:
            # 生成失败，回退扣减的免费次数
            if not is_vip:
                cursor.execute(
                    'UPDATE users SET free_count = free_count + 1 WHERE user_id=?',
                    (user_id,)
                )
                db.commit()
            return jsonify({'code': 500, 'msg': content})
        
        # 保存生成记录
        cursor.execute(
            'INSERT INTO create_records (user_id, req_type, prompt, content) VALUES (?,?,?,?)',
            (user_id, req_type, prompt, content)
        )
        db.commit()
        
        logger.info(f"AI生成成功 | 用户ID：{user_id} | 类型：{req_type} | 需求：{prompt[:20]}...")
        return jsonify({
            'code': 200,
            'data': {'content': content}
        })
    except Exception as e:
        logger.error(f"AI生成接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

@app.route('/api/get_history', methods=['POST'])
def get_history():
    """获取生成历史"""
    try:
        data = request.get_json() or {}
        user_id = data.get('user_id')
        
        if not user_id:
            logger.warn(f"获取历史失败：用户ID为空 | 请求数据：{data}")
            return jsonify({'code': 400, 'msg': '用户ID不能为空'})
        
        db = get_db()
        cursor = db.cursor()
        
        cursor.execute('''
        SELECT req_type, prompt, content, create_time 
        FROM create_records 
        WHERE user_id=? 
        ORDER BY create_time DESC
        LIMIT 20
        ''', (user_id,))
        
        records = cursor.fetchall()
        history = []
        for record in records:
            create_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(record['create_time']))
            history.append({
                'type': record['req_type'],
                'prompt': record['prompt'],
                'content': record['content'],
                'time': create_time
            })
        
        logger.info(f"获取生成历史成功 | 用户ID：{user_id} | 记录数：{len(history)}")
        return jsonify({'code': 200, 'data': history})
    except Exception as e:
        logger.error(f"获取历史接口异常：{str(e)} | 请求数据：{request.get_json()}", exc_info=True)
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# ========== 6. 跨域支持 ==========
@app.after_request
def after_request(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

# ========== 7. 启动服务（适配Railway） ==========
if __name__ == '__main__':
    # 启动前校验API配置
    if API_KEY == "这里填写你的内测API_KEY" or not API_KEY:
        logger.error("请先配置你的内测API_KEY！")
        print("❌ 错误：请先配置你的内测API_KEY，再启动服务")
        exit(1)
    init_db()
    logger.info(f"AI内容创作工具服务启动")
    logger.info(f"GPT-4o配置 | Host：{API_HOST} | 模型：{MODEL_NAME}")
    
    # 关键修改：用Railway的PORT环境变量，默认8080
    port = int(os.environ.get('PORT', 8080))
    # 生产环境用0.0.0.0监听所有网卡
    app.run(host='0.0.0.0', port=port, debug=False)
