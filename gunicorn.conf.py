import os

# 绑定地址和端口（优先使用Railway的PORT环境变量）
bind = f"0.0.0.0:{os.environ.get('PORT', 8080)}"
# 工作进程数（Railway免费版建议1）
workers = 1
# 工作模式
worker_class = "sync"
# 超时时间（AI调用可能需要较长时间）
timeout = 60
# 日志配置
accesslog = "-"  # 输出到控制台
errorlog = "-"
loglevel = "info"
