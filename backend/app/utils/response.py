from fastapi.responses import JSONResponse


def _default_http_status(code: int) -> int:
    if 400 <= int(code) <= 599:
        return int(code)
    if int(code) >= 500000 or int(code) == 500:
        return 500
    return 400


class ResponseWrapper:
    @staticmethod
    def success(data=None, msg="success", code=0, status_code: int = 200):
        return JSONResponse(content={
            "code": code,
            "msg": msg,
            "data": data
        }, status_code=status_code)

    @staticmethod
    def error(msg="error", code=500, data=None, status_code: int | None = None):
        return JSONResponse(content={
            "code": code,
            "msg": str(msg),
            "data": data
        }, status_code=status_code or _default_http_status(code))
