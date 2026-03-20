import os
bind = f"0.0.0.0:{os.environ.get('PORT', 8080)}"  # 优先用Railway的PORT变量
workers = 1
worker_class = "sync"
timeout = 60  # 延长超时时间
accesslog = "-"
errorlog = "-"
loglevel = "info"
