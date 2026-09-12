import json
import hashlib
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .agent import Agent, call_model
from .engines import Engines, csv_bytes, public_source
from .store import Store
from .providers import DEEPSEEK_URL, DEEPSEEK_MODEL, provider_settings
from .i18n import translate
from .version import VERSION

ROOT = Path(__file__).resolve().parent.parent


class SettingsInput(BaseModel):
    mode: Literal['demo', 'llm']
    provider: Literal['deepseek', 'custom'] = 'deepseek'
    base_url: str = Field(default=DEEPSEEK_URL, max_length=500)
    model: str = Field(default=DEEPSEEK_MODEL, min_length=1, max_length=200)
    api_key: str | None = Field(default=None, max_length=4000)

    @model_validator(mode='before')
    @classmethod
    def preset(cls, value):
        return provider_settings(value) if isinstance(value, dict) else value

    @field_validator('api_key')
    @classmethod
    def trim_key(cls, value):
        return value.strip() if value is not None else None

    @field_validator('base_url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip().rstrip('/')
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
            raise ValueError('请输入不含凭据和查询参数的 API 根地址。')
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ValueError('远程模型必须使用 HTTPS；本地模型可以使用 HTTP。')
        if value.endswith('/chat/completions'):
            value = value[:-len('/chat/completions')]
        return value


class DatabaseInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    dialect: Literal['postgres', 'mysql']
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=128)
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(max_length=4000)
    schema_name: str = Field(default='', max_length=128)
    sslmode: Literal['prefer', 'require'] = 'prefer'


class ConversationInput(BaseModel):
    source_id: str = Field(max_length=100)


class MessageInput(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    language: Literal['zh-CN', 'en-US'] | None = None

    @field_validator('content')
    @classmethod
    def nonempty(cls, v):
        if not v.strip():
            raise ValueError('请输入问题。')
        return v.strip()


class PreferencesInput(BaseModel):
    language: Literal['zh-CN', 'en-US']


class BusinessContextInput(BaseModel):
    notes: str = Field(default='', max_length=8000)
    fields: str = Field(default='', max_length=8000)
    metrics: str = Field(default='', max_length=8000)
    relationships: str = Field(default='', max_length=8000)


def create_app(storage_path=None):
    store = Store(Path(storage_path or os.environ.get('DATA_AGENT_STORAGE', ROOT / 'storage')))
    engines = Engines(store)
    agent = Agent(store, engines)
    guard = threading.Lock()
    active = set()

    @asynccontextmanager
    async def lifespan(app):
        engines.seed()
        yield

    app = FastAPI(title='Zhishu Data Agent', version=VERSION, lifespan=lifespan)
    app.state.store, app.state.engines, app.state.agent = store, engines, agent
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])

    @app.middleware('http')
    async def local_guard(request: Request, call_next):
        requested = request.headers.get('accept-language', '')
        request.state.language = 'en-US' if requested.startswith('en') else 'zh-CN' if requested.startswith('zh') else store.preferences()['language']
        origin = request.headers.get('origin')
        if origin and origin != str(request.base_url).rstrip('/') and origin not in ('http://127.0.0.1:5173', 'http://localhost:5173'):
            return JSONResponse({'detail': translate('不允许来自其他网站的请求。', request.state.language)}, status_code=403)
        if request.headers.get('sec-fetch-site') == 'cross-site':
            return JSONResponse({'detail': translate('不允许跨站请求。', request.state.language)}, status_code=403)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': translate(str(exc), request.state.language)}, status_code=400)

    @app.exception_handler(HTTPException)
    async def invalid_http(request, exc):
        return JSONResponse({'detail': translate(exc.detail, request.state.language)}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_fields(request, exc):
        # Pydantic normally includes input values in validation errors; omit those
        # because settings and connection forms can contain credentials.
        common = {'missing': '请填写必填项。', 'string_too_short': '输入内容过短。',
                  'string_too_long': '输入内容超过长度限制。', 'literal_error': '请选择有效的选项。',
                  'int_parsing': '请输入整数。', 'greater_than_equal': '数值小于允许范围。',
                  'less_than_equal': '数值超过允许范围。'}
        return JSONResponse({'detail': [{'loc': e['loc'], 'msg': translate(common.get(e['type'], e['msg']), request.state.language)} for e in exc.errors()]}, status_code=422)

    @app.get('/api/health')
    def health():
        instance = hashlib.sha256(str(store.root.resolve()).casefold().encode()).hexdigest()[:16]
        return {'status': 'ok', 'version': VERSION, 'app': 'zhishu-data-agent', 'instance': instance}

    @app.get('/api/preferences')
    def preferences():
        return store.preferences()

    @app.put('/api/preferences')
    def save_preferences(data: PreferencesInput):
        return store.save_preferences(data.language)

    @app.get('/api/settings')
    def settings():
        return store.settings()

    @app.put('/api/settings')
    def save_settings(data: SettingsInput):
        store.save_settings(data.model_dump())
        return store.settings()

    @app.post('/api/settings/test')
    def test_settings(data: SettingsInput, request: Request):
        config = data.model_dump()
        if config['api_key'] is None:
            config['api_key'] = store.settings(private=True).get('api_key', '')
        call_model(config, [{'role': 'user', 'content': 'Reply with OK.'}], max_tokens=128)
        return {'ok': True, 'message': translate('模型连接成功。', request.state.language)}

    @app.get('/api/sources')
    def sources():
        return [public_source(s) for s in store.sources()]

    @app.post('/api/sources/csv')
    def upload_csv(file: UploadFile = File(...)):
        try:
            data = file.file.read(20 * 1024 * 1024 + 1)
            if len(data) > 20 * 1024 * 1024:
                raise ValueError('CSV 文件不能超过 20 MB。')
            return engines.import_csv(data, file.filename or 'data.csv')
        finally:
            file.file.close()

    @app.post('/api/sources/database')
    def add_database(data: DatabaseInput):
        return engines.connect_database(data.model_dump())

    @app.get('/api/sources/{source_id}/preview')
    def preview(source_id: str, table: str = ''):
        source = store.source(source_id)
        selected = next((t for t in source['tables'] if t['name'] == table), None) if table else source['tables'][0]
        if not selected:
            raise ValueError('表不存在。')
        quote = '`' if source['dialect'] == 'mysql' else '"'
        full = '.'.join(quote + s.replace(quote, quote * 2) + quote for s in (selected.get('schema'), selected['name']) if s)
        try:
            return engines.query(source, f'SELECT * FROM {full} LIMIT 20')
        except ValueError:
            raise
        except Exception as e:
            raise ValueError('预览失败，请检查数据源是否仍然可访问。') from e

    @app.get('/api/sources/{source_id}/context')
    def business_context(source_id: str):
        return store.business_context(source_id)

    @app.put('/api/sources/{source_id}/context')
    def save_business_context(source_id: str, data: BusinessContextInput):
        return store.save_business_context(source_id, data.model_dump())

    @app.get('/api/conversations')
    def conversations():
        return store.conversations()

    @app.post('/api/conversations')
    def new_conversation(data: ConversationInput):
        return store.create_conversation(data.source_id)

    @app.get('/api/conversations/{cid}/messages')
    def messages(cid: str):
        return store.messages(cid)

    @app.post('/api/conversations/{cid}/messages')
    def chat(cid: str, data: MessageInput):
        store.conversation(cid)
        language = data.language or store.preferences()['language']
        with guard:
            if cid in active:
                raise HTTPException(409, '这个对话正在分析，请稍后再发。')
            active.add(cid)
        def stream():
            try:
                for event in agent.run(cid, data.content, language=language):
                    yield 'data: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
            finally:
                with guard:
                    active.discard(cid)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})

    @app.get('/api/conversations/{cid}/export')
    def export_conversation(cid: str, language: Literal['zh-CN', 'en-US'] | None = None):
        language = language or store.preferences()['language']
        t = lambda text: translate(text, language)
        conversation = store.conversation(cid)
        lines = [f"# {conversation['title']}", '', f"{t('数据源')}: {store.source(conversation['source_id'])['name']}", '']
        for m in store.messages(cid):
            lines.extend(['## ' + t('问题' if m['role'] == 'user' else '分析'), '', m['content'], ''])
            r = m.get('result') or {}
            if r.get('context_version'):
                lines.extend([t(f"业务上下文版本：{r['context_version']}"), ''])
                context = r.get('business_context') or {}
                for key, label in [('notes', '业务说明'), ('fields', '字段解释'), ('metrics', '指标定义'), ('relationships', '关联关系')]:
                    if context.get(key):
                        lines.extend(['### ' + t(label), '', context[key], ''])
            if r.get('sql'):
                lines.extend(['```sql', r['executed_sql'], '```', '', t(f"返回 {r['row_count']} 行。") + (t('结果已截断。') if r['truncated'] else ''), ''])
                lines.append(t('模式') + ': ' + t('规则演示' if r.get('mode') == 'demo' else 'AI 分析'))
        return Response('\n'.join(lines), media_type='text/markdown; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="analysis.md"'})

    @app.get('/api/conversations/{cid}/messages/{mid}/csv')
    def export_csv(cid: str, mid: str):
        message = next((m for m in store.messages(cid) if m['id'] == mid), None)
        if not message or not (message.get('result') or {}).get('columns'):
            raise HTTPException(404, '没有可导出的数据。')
        return Response(csv_bytes(message['result']), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="query-results.csv"'})

    dist = ROOT / 'frontend' / 'dist'
    if (dist / 'assets').exists():
        app.mount('/assets', StaticFiles(directory=dist / 'assets'), name='assets')

    @app.get('/favicon.svg')
    def favicon():
        return FileResponse(dist / 'favicon.svg')

    @app.get('/')
    def index(request: Request):
        if not (dist / 'index.html').exists():
            return JSONResponse({'detail': translate('前端尚未构建，请运行 start.ps1。', request.state.language)}, status_code=503)
        return FileResponse(dist / 'index.html')

    return app


app = create_app()
