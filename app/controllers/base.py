from fastapi import Request

from app.config import config
from app.models.exception import HttpException
from app.utils import utils


def get_task_id(request: Request):
    task_id = request.headers.get("x-task-id")
    if not task_id:
        task_id = utils.get_uuid()  # 使用修改后的函数，返回日期格式的ID
    return str(task_id)


def get_api_key(request: Request):
    api_key = request.headers.get("x-api-key")
    return api_key


def verify_token(request: Request):
    token = get_api_key(request)
    if token != config.app.get("api_key", ""):
        request_id = get_task_id(request)
        request_url = request.url
        user_agent = request.headers.get("user-agent")
        raise HttpException(
            task_id=request_id,
            status_code=401,
            message=f"invalid token: {request_url}, {user_agent}",
        )
