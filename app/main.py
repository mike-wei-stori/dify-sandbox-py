from fastapi import FastAPI, Header, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware  
from pydantic import BaseModel
from typing import Optional
import asyncio
from .executor import CodeExecutor
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# 配置
API_KEY = os.getenv("API_KEY", "dify-sandbox")
MAX_REQUESTS = int(os.getenv("MAX_REQUESTS", "1000"))
# 根据 CPU 核心数动态设置工作线程数，避免过多进程导致 CPU 争抢
# 默认公式: min(32, (cpu_count * 4))，确保至少有 4 个 worker
import multiprocessing
try:
    cpu_count = multiprocessing.cpu_count()
except Exception:
    cpu_count = 1
default_workers = min(32, cpu_count * 4)
MAX_WORKERS = int(os.getenv("MAX_WORKERS", str(default_workers)))
WORKER_TIMEOUT = int(os.getenv("WORKER_TIMEOUT", "10000"))

logger.info("=" * 80)
logger.info("沙箱服务初始化")
logger.info("配置信息:")
logger.info("  - 最大请求数: %d", MAX_REQUESTS)
logger.info("  - 最大工作线程数: %d", MAX_WORKERS)
logger.info("  - 工作线程超时: %d 秒", WORKER_TIMEOUT)
logger.info("=" * 80)

app = FastAPI()
executor = CodeExecutor(timeout=WORKER_TIMEOUT, max_workers=MAX_WORKERS)

# 请求模型
class CodeRequest(BaseModel):
    language: str
    code: str
    preload: Optional[str] = ""
    enable_network: Optional[bool] = False

# 认证中间件
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/v1/sandbox"):
            api_key = request.headers.get("X-Api-Key")
            if not api_key or api_key != API_KEY:
                # 修改这里：返回 JSONResponse 而不是直接返回 HTTPException
                from fastapi.responses import JSONResponse
                return JSONResponse(
                    status_code=401,
                    content={
                        "code": -401,
                        "message": "Unauthorized",
                        "data": None
                    }
                )
        return await call_next(request)

# 并发控制中间件
class ConcurrencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.semaphore = asyncio.Semaphore(MAX_WORKERS)
        self.current_requests = 0

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/v1/sandbox/run"):
            if self.current_requests >= MAX_REQUESTS:
                return {
                    "code": -503,
                    "message": "Too many requests",
                    "data": None
                }
            
            self.current_requests += 1
            try:
                async with self.semaphore:
                    response = await call_next(request)
                return response
            finally:
                self.current_requests -= 1
        return await call_next(request)

# 添加中间件
app.add_middleware(AuthMiddleware)
app.add_middleware(ConcurrencyMiddleware)

@app.get("/health")
async def health_check():
    return "ok"

@app.post("/v1/sandbox/run")
async def execute_code(request: CodeRequest):
    logger.info("*" * 80)
    logger.info("收到代码执行请求")
    logger.info("语言: %s", request.language)
    logger.info("启用网络: %s", request.enable_network)
    if request.preload:
        logger.info("预加载代码: %s", request.preload[:100] + "..." if len(request.preload) > 100 else request.preload)
    logger.info("*" * 80)
    
    if request.language not in ["python3", "nodejs"]:
        logger.warning("不支持的语言: %s", request.language)
        return {
            "code": -400,
            "message": "unsupported language",
            "data": None
        }

    result = await executor.execute(request.code, request.language)
    
    logger.info("-" * 80)
    logger.info("API 响应:")
    logger.info("成功: %s", result.get("success", False))
    if result.get("output"):
        output_preview = result["output"][:1000] + "..." if len(result["output"]) > 1000 else result["output"]
        logger.info("输出 (truncated):\n%s", output_preview)
    if result.get("error"):
        error_preview = result["error"][:1000] + "..." if len(result["error"]) > 1000 else result["error"]
        logger.warning("错误 (truncated):\n%s", error_preview)
    logger.info("*" * 80)
    
    return {
        "code": 0,
        "message": "success",
        "data": {
            "error": result["error"] or "",
            "stdout": result["output"] or "",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8194)