import os
import sqlite3
import logging
import time
from datetime import datetime
from flask import Flask, request, jsonify, render_template
import openai  # 用于AI调用，需配置API_KEY

# ===================== 基础配置 =====================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# OpenAI配置（从Railway环境变量读取，安全且无需硬编码）
openai.api_key = os.getenv("OPENAI_API_KEY")
# 备用AI接口地址（可选，用于国内访问）
openai.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")

# ===================== 数据库操作 =====================
def init_db():
    """初始化数据库，确保所有表存在"""
    # Railway可写目录：/app
    db_path = os.path.join('/app', 'app.db')
    # 确保目录存在
    if not os.path.exists('/app'):
        os.makedirs('/app')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 1. 用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT,
        create_time INTEGER NOT NULL,
        is_vip BOOLEAN DEFAULT 0,
        vip_expire_time INTEGER DEFAULT 0
    )
    ''')
    
    # 2. 创作历史表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS creation_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        type TEXT NOT NULL,  # short_video / office_doc
        platform TEXT,       # 抖音/小红书/微信等
        tone TEXT,           # 幽默/正式/温馨等
        prompt TEXT NOT NULL,
        content TEXT NOT NULL,
        create_time INTEGER NOT NULL
    )
    ''')
    
    # 3. 会员套餐表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS vip_packages (
        package_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        cycle_days INTEGER NOT NULL,  # 有效期（天）
        desc TEXT NOT NULL
    )
    ''')
    
    # 插入默认会员套餐（不存在则插入）
    cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                  ('monthly', '月度会员', 19.9, 30, '无限制AI创作次数+全风格支持'))
    cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                  ('quarterly', '季度会员', 49.9, 90, '月度会员特权+优先使用新功能'))
    cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?)',
                  ('yearly', '年度会员', 199.0, 365, '全部特权+专属客服'))
    
    conn.commit()
    conn.close()
    logger.info("数据库初始化完成")

def get_db():
    """获取数据库连接"""
    db_path = os.path.join('/app', 'app.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # 支持字典式访问
    return conn

# ===================== AI创作核心功能 =====================
def generate_content(prompt, content_type, platform, tone):
    """
    调用OpenAI生成内容
    :param prompt: 用户创作需求
    :param content_type: 内容类型（short_video/office_doc）
    :param platform: 发布平台
    :param tone: 风格语气
    :return: 生成的内容字符串
    """
    # 根据内容类型拼接提示词
    if content_type == "short_video":
        system_prompt = f"""你是一名专业的{platform}内容创作者，擅长{tone}风格的短视频文案创作。
要求：
1. 标题吸引眼球，符合{platform}平台调性；
2. 文案简洁易懂，控制在300字以内；
3. 包含拍摄建议（1-2句即可）；
4. 语气符合{tone}风格。"""
    else:
        system_prompt = f"""你是一名专业的办公文案助手，擅长{tone}风格的文案创作。
要求：
1. 逻辑清晰，符合办公场景使用；
2. 语言简洁，控制在500字以内；
3. 语气符合{tone}风格。"""
    
    # 调用OpenAI API
    try:
        response = openai.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,  # 创意度
            timeout=30  # 超时时间
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"AI生成失败：{str(e)}")
        raise Exception(f"AI调用失败：{str(e)}")

# ===================== API接口 =====================
@app.route('/api/register', methods=['POST'])
def register():
    """用户注册"""
    try:
        data = request.get_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        phone = str(data.get('phone', '')).strip()
        
        if not username or not password:
            return jsonify({"code": 400, "msg": "用户名和密码不能为空"})
        
        # 生成唯一user_id
        user_id = f"user_{int(time.time() * 1000)}"
        create_time = int(time.time())
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 检查用户名是否已存在
        cursor.execute('SELECT 1 FROM users WHERE username = ?', (username,))
        if cursor.fetchone():
            return jsonify({"code": 400, "msg": "用户名已存在"})
        
        # 插入用户数据
        cursor.execute(
            'INSERT INTO users (user_id, username, password, phone, create_time) VALUES (?, ?, ?, ?, ?)',
            (user_id, username, password, phone, create_time)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            "code": 200,
            "msg": "注册成功",
            "data": {"user_id": user_id, "username": username}
        })
    except Exception as e:
        logger.error(f"注册失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"注册失败：{str(e)}"})

@app.route('/api/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.get_json()
        username = str(data.get('username', '')).strip()
        password = str(data.get('password', '')).strip()
        
        if not username or not password:
            return jsonify({"code": 400, "msg": "用户名和密码不能为空"})
        
        conn = get_db()
        cursor = conn.cursor()
        
        # 验证用户
        cursor.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({"code": 401, "msg": "用户名或密码错误"})
        
        # 生成简单token（生产环境建议用JWT）
        token = f"token_{user['user_id']}_{int(time.time())}"
        
        return jsonify({
            "code": 200,
            "msg": "登录成功",
            "data": {
                "user_id": user['user_id'],
                "username": user['username'],
                "is_vip": bool(user['is_vip']),
                "token": token
            }
        })
    except Exception as e:
        logger.error(f"登录失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"登录失败：{str(e)}"})

@app.route('/api/ai_create', methods=['POST'])
def ai_create():
    """AI内容生成（核心接口）"""
    try:
        data = request.get_json()
        user_id = str(data.get('user_id', '')).strip()
        prompt = str(data.get('prompt', '')).strip()
        content_type = str(data.get('type', 'short_video')).strip()
        platform = str(data.get('platform', 'douyin')).strip()
        tone = str(data.get('tone', 'humorous')).strip()
        
        # 参数校验
        if not user_id or not prompt:
            return jsonify({"code": 400, "msg": "user_id和创作需求不能为空"})
        
        # 调用AI生成内容
        content = generate_content(prompt, content_type, platform, tone)
        
        # 保存创作历史
        create_time = int(time.time())
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            '''INSERT INTO creation_history 
               (user_id, type, platform, tone, prompt, content, create_time) 
               VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (user_id, content_type, platform, tone, prompt, content, create_time)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            "code": 200,
            "msg": "生成成功",
            "data": {
                "content": content,
                "create_time": create_time
            }
        })
    except Exception as e:
        logger.error(f"AI生成失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"生成失败：{str(e)}"})

@app.route('/api/get_history', methods=['POST'])
def get_history():
    """获取创作历史"""
    try:
        data = request.get_json()
        user_id = str(data.get('user_id', '')).strip()
        
        if not user_id:
            return jsonify({"code": 400, "msg": "user_id不能为空"})
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT * FROM creation_history WHERE user_id = ? ORDER BY create_time DESC',
            (user_id,)
        )
        history = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": history
        })
    except Exception as e:
        logger.error(f"获取历史失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"获取失败：{str(e)}"})

@app.route('/api/get_vip_packages', methods=['GET'])
def get_vip_packages():
    """获取会员套餐"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM vip_packages')
        packages = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return jsonify({
            "code": 200,
            "msg": "获取成功",
            "data": packages
        })
    except Exception as e:
        logger.error(f"获取套餐失败：{str(e)}")
        return jsonify({"code": 500, "msg": f"获取失败：{str(e)}"})

# ===================== 页面路由 =====================
@app.route('/')
def index():
    """前端页面入口"""
    return render_template('index.html')

# ===================== 全局配置 =====================
@app.errorhandler(404)
def page_not_found(e):
    return jsonify({"code": 404, "msg": "接口不存在"}), 404

@app.errorhandler(500)
def internal_server_error(e):
    return jsonify({"code": 500, "msg": "服务器内部错误"}), 500

# ===================== 启动入口 =====================
if __name__ == '__main__':
    # 初始化数据库
    init_db()
    # 启动服务（适配Railway端口）
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)  # 生产环境关闭debug
