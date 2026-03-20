import os
import sqlite3
import logging
from datetime import datetime
from flask import Flask, request, jsonify, render_template

# 初始化Flask应用
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 数据库连接函数
def get_db():
    db = sqlite3.connect('app.db')
    db.row_factory = sqlite3.Row
    return db

# 初始化数据库
def init_db():
    db = get_db()
    cursor = db.cursor()
    
    # 创建用户表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        phone TEXT,
        create_time INTEGER,
        is_vip BOOLEAN DEFAULT 0
    )
    ''')
    
    # 创建创作历史表
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
    
    # 创建会员套餐表
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS vip_packages (
        package_id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        cycle TEXT NOT NULL,
        desc TEXT NOT NULL  # 修正：补全字段定义，闭合括号
    )
    ''')
    
    # 插入默认会员套餐
    cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                  ('monthly', '月度会员', 19.9, '月', '无限制创作次数+更多风格选择'))
    cursor.execute('INSERT OR IGNORE INTO vip_packages VALUES (?, ?, ?, ?, ?)',
                  ('yearly', '年度会员', 199.0, '年', '全部特权+优先使用新功能'))
    
    db.commit()
    logger.info("数据库初始化完成")

# 生成自定义内容函数
def get_custom_content(req_type, prompt, platform, tone):
    if req_type == "short_video":
        return f"""
【{platform}爆款脚本-{tone}风格】
标题：{prompt} - 90%的人都不知道的秘密！
时长：30秒
脚本：
0-3秒（钩子）：家人们！今天给大家揭秘{prompt}的核心技巧，看完立省500块！
3-20秒（主体）：首先...（你的产品核心卖点）；其次...（使用场景）；最后...（优惠活动）
20-30秒（结尾）：点击下方链接，立即抢购！关注我，每天分享干货！
背景音乐：轻快的流行音乐
拍摄建议：近景+产品特写
"""
    else:
        # 办公文案的自定义内容
        return f"""
# {prompt}
## 一、文档说明
{prompt}相关的办公文档，适用于{tone}风格的商务场景。
## 二、核心内容
1. 背景：XXX
2. 目标：XXX
3. 执行方案：XXX
## 三、注意事项
1. 格式规范：XXX
2. 提交时间：XXX
"""

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

# 2. 用户注册（完整）
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

# 3. 获取创作历史（完整）
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

# 4. AI内容生成（完整，适配真实AI调用）
@app.route('/api/ai_create', methods=['POST'])
def ai_create():
    try:
        data = request.get_json()
        user_id = data.get('user_id', '').strip()
        prompt = data.get('prompt', '').strip()
        type = data.get('type', 'short_video')
        platform = data.get('platform', 'douyin')
        tone = data.get('tone', 'humorous')
        
        if not user_id or not prompt:
            return jsonify({'code': 400, 'msg': '必要参数不能为空'})
        
        # ========== 真实AI调用逻辑（替换此处即可） ==========
        # 1. 拼接AI提示词
        if type == 'short_video':
            system_prompt = f"你是{platform}平台{tone}风格的短视频创作者，根据需求生成标题+文案+拍摄建议，控制在300字内"
        else:
            system_prompt = f"你是{tone}风格的办公文案助手，根据需求生成逻辑清晰的办公文案，控制在500字内"
        
        # 2. 调用真实AI接口（示例用OpenAI，可替换为文心/通义等）
        import openai
        openai.api_key = os.getenv("API_KEY")  # 从环境变量取密钥（安全）
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content.strip()
        # ========== AI调用结束 ==========
        
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
        return jsonify({'code': 500, 'msg': f'服务器内部错误：{str(e)}'})

# 5. 获取会员套餐（完整）
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

# 6. 创建会员订单（完整）
@app.route('/api/create_vip_order', methods=['POST'])
def create_vip_order():
    try:
        data = request.get_json()
        user_id = data.get('user_id', '').strip()
        package_id = data.get('package_id', '').strip()
        
        if not user_id or not package_id:
            return jsonify({'code': 400, 'msg': '参数不能为空'})
        
        # 模拟创建订单
        order_id = f"order_{int(datetime.now().timestamp() * 1000)}"
        return jsonify({
            'code': 200,
            'data': {
                'order_id': order_id,
                'pay_url': f'https://example.com/pay?order={order_id}'
            }
        })
    
    except Exception as e:
        logger.error(f"创建订单接口异常：{str(e)}")
        return jsonify({'code': 500, 'msg': '服务器内部错误'})

# --------------------------
# 全局错误处理（完整）
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
# 启动入口（完整）
# --------------------------
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=True)  # 测试阶段开启debug
