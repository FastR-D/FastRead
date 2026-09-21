"""Keep PDF byte offsets intact while compressing JSON and other responses."""
import re
from starlette.middleware.gzip import GZipMiddleware


class ReaderGZipMiddleware(GZipMiddleware):
    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http' and re.fullmatch(r'/api/papers/[^/]+/file', scope['path']):
            await self.app(scope, receive, send)
        else:
            await super().__call__(scope, receive, send)
