"""Google sign-in and opaque server sessions for the public viewer boundary."""
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

ROOT=Path(__file__).resolve().parents[1]
SESSION_COOKIE='__Host-mapwalker_session'
LOGIN_COOKIE='__Host-mapwalker_login'
SESSION_SECONDS=8*3600


@dataclass(frozen=True)
class AccessConfig:
    enabled: bool=False
    origin: str=''
    client_id: str=''
    emails: tuple=()
    subjects: tuple=()
    mode: str='google'
    code_hash: str=''
    code_expires: float=0

    @classmethod
    def load(cls,required=False):
        if not required:return cls()
        path=Path(os.environ.get('MAPWALKER_ACCESS_CONFIG',ROOT/'.mapwalker-access.json'))
        values=json.loads(path.read_text('utf-8')) if path.exists() else {}
        emails=os.environ.get('MAPWALKER_ALLOWED_EMAILS')
        config=cls(True,os.environ.get('MAPWALKER_PUBLIC_ORIGIN',values.get('public_origin','')),
                   os.environ.get('MAPWALKER_GOOGLE_CLIENT_ID',values.get('google_client_id','')),
                   tuple(emails.split(',')) if emails is not None else tuple(values.get('allowed_emails',[])),
                   tuple(values.get('allowed_google_subjects',[])),values.get('auth_mode','google'),
                   values.get('access_code_hash',''),values.get('access_code_expires',0))
        config.validate();return config

    def validate(self):
        if not self.enabled:return
        if not isinstance(self.origin,str) or not isinstance(self.client_id,str):
            raise ValueError('Public origin and Google client ID must be strings.')
        url=urlsplit(self.origin)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.path not in ('','/') or url.query or url.fragment or self.origin.endswith('/'):
            raise ValueError('Public access requires an exact HTTPS origin without a trailing slash.')
        if self.mode not in ('google','access-code'):raise ValueError('Unknown authentication mode.')
        if self.mode=='access-code':
            if not isinstance(self.code_hash,str) or len(self.code_hash)!=64 or any(c not in '0123456789abcdef' for c in self.code_hash):
                raise ValueError('Temporary access requires a generated access-code hash.')
            if not isinstance(self.code_expires,(int,float)) or not time.time()<self.code_expires<=time.time()+31*86400:
                raise ValueError('Temporary access must expire within 31 days.')
            return
        if not self.client_id.endswith('.apps.googleusercontent.com') or any(c.isspace() for c in self.client_id):
            raise ValueError('Configure a Google Web application client ID before starting public access.')
        if not self.emails and not self.subjects:raise ValueError('At least one allowed Google account is required.')
        if any(not isinstance(e,str) or '@' not in e or '*' in e for e in self.emails):
            raise ValueError('Allowed emails must be explicit addresses, not wildcards.')
        if any(not isinstance(s,str) or not s.isdigit() for s in self.subjects):
            raise ValueError('Allowed Google subjects must be explicit numeric account IDs.')

    def allowed(self,email,subject,authoritative=True):
        if self.mode=='access-code':return time.time()<self.code_expires and hmac.compare_digest(subject,'access-code:'+self.code_hash)
        return subject in self.subjects or (authoritative and email.lower() in {e.strip().lower() for e in self.emails})


def digest(value):return hashlib.sha256(value.encode()).hexdigest()


class Access:
    def __init__(self,data,config):
        config.validate();self.config=config;self.path=Path(data)/'access.sqlite3'
        self.transport=None;self.verify_lock=threading.Lock()
        if config.enabled:
            with self.connect() as db:
                db.executescript('''CREATE TABLE IF NOT EXISTS sessions (
                    token TEXT PRIMARY KEY,subject TEXT NOT NULL,email TEXT NOT NULL,
                    authoritative INTEGER NOT NULL,csrf TEXT NOT NULL,expires REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS challenges (token TEXT PRIMARY KEY,expires REAL NOT NULL);
                    CREATE TABLE IF NOT EXISTS limits (key TEXT PRIMARY KEY,started REAL NOT NULL,count INTEGER NOT NULL);''')

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()

    def throttle(self,bucket,maximum,period=60):
        now=time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE started<?',(now-period,))
            db.execute('INSERT INTO limits VALUES(?,?,1) ON CONFLICT(key) DO UPDATE SET count=count+1',(bucket,now))
            count=db.execute('SELECT count FROM limits WHERE key=?',(bucket,)).fetchone()[0]
        if count>maximum:raise HTTPException(429,'Too many sign-in attempts. Please wait a minute.')

    def challenge(self):
        nonce=secrets.token_urlsafe(32);now=time.time()
        with self.connect() as db:
            db.execute('DELETE FROM challenges WHERE expires<?',(now,))
            db.execute('DELETE FROM sessions WHERE expires<?',(now,))
            db.execute('INSERT INTO challenges VALUES(?,?)',(digest(nonce),now+600))
        return nonce

    def consume_challenge(self,nonce):
        with self.connect() as db:
            count=db.execute('DELETE FROM challenges WHERE token=? AND expires>?',(digest(nonce),time.time())).rowcount
        if not count:raise HTTPException(401,'This sign-in request expired or was already used. Reload the sign-in page.')

    def verify(self,credential):
        from google.oauth2 import id_token
        from google.auth.transport.requests import Request as GoogleRequest
        import requests
        from cachecontrol import CacheControl
        def transport(*args,**kwargs):
            kwargs['timeout']=10
            return self.transport(*args,**kwargs)
        with self.verify_lock:
            if self.transport is None:self.transport=GoogleRequest(session=CacheControl(requests.Session()))
            return id_token.verify_oauth2_token(credential,transport,self.config.client_id)

    def login(self,credential,nonce):
        if self.config.mode!='google':raise HTTPException(404,'Google sign-in is not configured.')
        from google.auth.exceptions import GoogleAuthError, TransportError
        self.consume_challenge(nonce)
        try:claims=self.verify(credential)
        except TransportError as exc:raise HTTPException(503,'Google verification is temporarily unavailable. Please try again.') from exc
        except (ValueError,GoogleAuthError) as exc:raise HTTPException(401,'Google could not verify this sign-in. Please try again.') from exc
        except Exception as exc:raise HTTPException(503,'Google verification is temporarily unavailable. Please try again.') from exc
        if not isinstance(claims.get('exp'),(int,float)) or claims.get('aud')!=self.config.client_id or claims.get('iss') not in ('accounts.google.com','https://accounts.google.com') or claims['exp']<=time.time():
            raise HTTPException(401,'Invalid Google identity.')
        if not isinstance(claims.get('nonce'),str) or not hmac.compare_digest(claims['nonce'],nonce):
            raise HTTPException(401,'Sign-in does not belong to this browser request.')
        email=claims.get('email','');subject=claims.get('sub','')
        if not isinstance(email,str) or not isinstance(subject,str) or not subject.isdigit():
            raise HTTPException(401,'Invalid Google identity.')
        email=email.lower()
        authoritative=email.endswith('@gmail.com') or bool(claims.get('hd'))
        if claims.get('email_verified') is not True or not subject or not self.config.allowed(email,subject,authoritative):
            raise HTTPException(403,'This Google account has not been granted access to Mapwalker.')
        return self.issue_session(subject,email,authoritative)

    def login_code(self,code,nonce):
        if self.config.mode!='access-code':raise HTTPException(404,'Access-code sign-in is not enabled.')
        self.consume_challenge(nonce)
        if time.time()>=self.config.code_expires or not hmac.compare_digest(digest(code.strip()),self.config.code_hash):
            raise HTTPException(401,'Invalid or expired access code.')
        return self.issue_session('access-code:'+self.config.code_hash,'Private access',False)

    def issue_session(self,subject,email,authoritative):
        token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(32)
        expires=time.time()+SESSION_SECONDS
        if self.config.mode=='access-code':expires=min(expires,self.config.code_expires)
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?)',(digest(token),subject,email,int(authoritative),csrf,expires))
        return token

    def session(self,token):
        if not token or len(token)>200:return None
        with self.connect() as db:
            row=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(digest(token),time.time())).fetchone()
        if row and self.config.allowed(row['email'],row['subject'],bool(row['authoritative'])):return dict(row)

    def logout(self,token):
        if self.config.enabled and token:
            with self.connect() as db:db.execute('DELETE FROM sessions WHERE token=?',(digest(token),))


class Credential(BaseModel):
    credential: str=Field(min_length=1,max_length=16000)


def install_access(app,data,config):
    access=Access(data,config);app.state.access=access
    public_paths={'/auth/login','/auth/login.css','/auth/login.js','/auth/config','/auth/google','/auth/access-code','/healthz'}

    @app.middleware('http')
    async def access_boundary(request:Request,call_next):
        path=request.url.path
        if config.enabled:
            # Never accept identity headers or a localhost bypass behind a tunnel.
            session=access.session(request.cookies.get(SESSION_COOKIE))
            request.state.session=session
            if path not in public_paths and not session:
                if request.method=='GET' and 'text/html' in request.headers.get('accept','') and not path.startswith('/api/'):
                    return RedirectResponse('/auth/login?next='+quote(path,safe=''),status_code=303,headers={'Cache-Control':'no-store'})
                return JSONResponse({'detail':'Sign in to access Mapwalker.'},401,headers={'Cache-Control':'no-store'})
            if request.method in ('POST','PUT','PATCH','DELETE'):
                if request.headers.get('origin')!=config.origin:
                    return JSONResponse({'detail':'Cross-origin writes are disabled.'},403)
                if path not in ('/auth/google','/auth/access-code'):
                    csrf=request.headers.get('x-csrf-token','')
                    if not session or not hmac.compare_digest(csrf,session['csrf']):
                        return JSONResponse({'detail':'Refresh this page before making changes.'},403)
        else:
            # A local-only listener is never an acceptable public tunnel target.
            if any(request.headers.get(h) for h in ('forwarded','x-forwarded-for','x-forwarded-host','cf-connecting-ip')):
                return JSONResponse({'detail':'This listener is local-only. Use the authenticated public listener.'},403)
        response=await call_next(request)
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['Cross-Origin-Opener-Policy']='same-origin-allow-popups'
        if config.enabled:
            response.headers['Cache-Control']='private, no-store'
            response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.get('/healthz')
    def health():return {'status':'ok','authentication_required':config.enabled}

    @app.get('/auth/login')
    def login_page():
        if not config.enabled:return RedirectResponse('/')
        return FileResponse(ROOT/'web/login.html')

    @app.get('/auth/login.css')
    def login_css():return FileResponse(ROOT/'web/login.css',media_type='text/css')

    @app.get('/auth/login.js')
    def login_js():return FileResponse(ROOT/'web/login.js',media_type='application/javascript')

    @app.get('/auth/config')
    def auth_config():
        if not config.enabled:return {'enabled':False}
        access.throttle('challenge',60)
        nonce=access.challenge()
        response=JSONResponse({'enabled':True,'mode':config.mode,'client_id':config.client_id if config.mode=='google' else '', 'nonce':nonce})
        response.set_cookie(LOGIN_COOKIE,nonce,max_age=600,secure=True,httponly=True,samesite='lax',path='/')
        return response

    def sign_in(request,payload,mode):
        if not config.enabled:raise HTTPException(404,'Sign-in is not enabled on this local listener.')
        if config.mode!=mode:raise HTTPException(404,'This sign-in method is not enabled.')
        access.throttle('sign-in',20)
        nonce=request.cookies.get(LOGIN_COOKIE,'');csrf=request.headers.get('x-csrf-token','')
        if not nonce or len(nonce)>200 or not hmac.compare_digest(nonce,csrf):raise HTTPException(403,'Invalid sign-in request. Reload this page.')
        token=access.login(payload.credential,nonce) if mode=='google' else access.login_code(payload.credential,nonce)
        access.logout(request.cookies.get(SESSION_COOKIE))
        response=JSONResponse({'signed_in':True})
        response.set_cookie(SESSION_COOKIE,token,max_age=SESSION_SECONDS,secure=True,httponly=True,samesite='lax',path='/')
        response.delete_cookie(LOGIN_COOKIE,secure=True,httponly=True,samesite='lax',path='/')
        return response

    @app.post('/auth/google')
    def google_login(request:Request,payload:Credential):return sign_in(request,payload,'google')

    @app.post('/auth/access-code')
    def code_login(request:Request,payload:Credential):return sign_in(request,payload,'access-code')

    @app.get('/auth/me')
    def me(request:Request):
        if not config.enabled:return {'enabled':False}
        session=request.state.session
        return {'enabled':True,'email':session['email'],'csrf':session['csrf'],'expires':session['expires']}

    @app.post('/auth/logout')
    def logout(request:Request):
        access.logout(request.cookies.get(SESSION_COOKIE))
        response=JSONResponse({'signed_out':True});response.delete_cookie(SESSION_COOKIE,secure=True,httponly=True,samesite='lax',path='/')
        return response
