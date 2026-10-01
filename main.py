import base64, hashlib, json, os, secrets, shutil, sqlite3, time
from datetime import date,datetime
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
HOST='127.0.0.1'; PORT=8765
BASE=os.path.join(os.getenv('LOCALAPPDATA',os.path.dirname(__file__)),'DentalCareStudio'); os.makedirs(BASE,exist_ok=True)
DB=os.path.join(BASE,'clinic_runtime.db'); ENC=os.path.join(BASE,'clinic.db.enc'); AUTH=os.path.join(BASE,'auth.json'); BACKUPS=os.path.join(BASE,'backups'); os.makedirs(BACKUPS,exist_ok=True)
SESSIONS=set(); ACTIVE_PASSWORD=None
SCHEMA='''CREATE TABLE IF NOT EXISTS patients(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,phone TEXT,birth_date TEXT,gender TEXT,notes TEXT,created_at TEXT NOT NULL);CREATE TABLE IF NOT EXISTS treatment_plans(id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id INTEGER NOT NULL,tooth TEXT,treatment TEXT NOT NULL,total_amount REAL NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'Planned',notes TEXT,created_at TEXT NOT NULL,FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS appointments(id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id INTEGER NOT NULL,appt_date TEXT NOT NULL,start_time TEXT NOT NULL,end_time TEXT NOT NULL,type TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Scheduled',notes TEXT,created_at TEXT NOT NULL,FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY AUTOINCREMENT,patient_id INTEGER NOT NULL,treatment_id INTEGER,amount REAL NOT NULL,payment_date TEXT NOT NULL,method TEXT NOT NULL,note TEXT,created_at TEXT,FOREIGN KEY(patient_id) REFERENCES patients(id) ON DELETE CASCADE);CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);CREATE TABLE IF NOT EXISTS activity_log(id INTEGER PRIMARY KEY,created_at TEXT,action TEXT,details TEXT);'''
def now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def meta():
 try:
  with open(AUTH,encoding='utf8') as f:return json.load(f)
 except Exception:return None
def key(password,m):return hashlib.pbkdf2_hmac('sha256',password.encode(),base64.b64decode(m['encryption_salt']),m['iterations'],32)
def ph(password,salt,it):return base64.b64encode(hashlib.pbkdf2_hmac('sha256',password.encode(),base64.b64decode(salt),it,32)).decode()
def encrypt(password):
 if not os.path.exists(DB):return
 m=meta(); n=os.urandom(12); data=open(DB,'rb').read(); blob=b'DCS1'+n+AESGCM(key(password,m)).encrypt(n,data,b'DentalCareStudio-v1'); tmp=ENC+'.tmp';open(tmp,'wb').write(blob);os.replace(tmp,ENC)
def decrypt(password):
 m=meta(); blob=open(ENC,'rb').read();
 try:data=AESGCM(key(password,m)).decrypt(blob[4:16],blob[16:],b'DentalCareStudio-v1')
 except Exception: raise ValueError('Incorrect password or damaged database.')
 open(DB+'.tmp','wb').write(data);os.replace(DB+'.tmp',DB)
def secure_save():
 if ACTIVE_PASSWORD: encrypt(ACTIVE_PASSWORD)
def remove_runtime():
 try: os.remove(DB)
 except OSError: pass
def conn():
 if not os.path.exists(DB): raise ValueError('Database is locked.')
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');c.executescript(SCHEMA);return c
def prepare(password):
 global ACTIVE_PASSWORD
 if os.path.exists(ENC): decrypt(password)
 elif not os.path.exists(DB): sqlite3.connect(DB).close()
 c=conn();c.close();ACTIVE_PASSWORD=password;secure_save()
def rows(c,q,args=()):return [dict(x) for x in c.execute(q,args).fetchall()]
def reset_password(old,new):
 global ACTIVE_PASSWORD
 m=meta()
 if not m or ph(old,m['password_salt'],m['iterations'])!=m['password_hash']:raise ValueError('Current password is incorrect.')
 if len(new)<8:raise ValueError('New password must contain at least 8 characters.')
 encrypt(old);m['password_salt']=base64.b64encode(os.urandom(16)).decode();m['password_hash']=ph(new,m['password_salt'],m['iterations']);write_meta(m);ACTIVE_PASSWORD=new;decrypt(new);secure_save()
def write_meta(m):
 tmp=AUTH+'.tmp';json.dump(m,open(tmp,'w'),indent=2);os.replace(tmp,AUTH)
def setup(password):
 if len(password)<8:raise ValueError('Use at least 8 characters.')
 ps=base64.b64encode(os.urandom(16)).decode();es=base64.b64encode(os.urandom(16)).decode();it=390000; recovery=secrets.token_urlsafe(18)
 write_meta({'version':2,'password_salt':ps,'encryption_salt':es,'iterations':it,'password_hash':ph(password,ps,it),'recovery_hash':ph(recovery,ps,it),'created_at':now()});prepare(password);return recovery
def recover(code,new):
 global ACTIVE_PASSWORD
 m=meta()
 if not m or ph(code,m['password_salt'],m['iterations'])!=m.get('recovery_hash',''):raise ValueError('Invalid recovery code.')
 old=ACTIVE_PASSWORD
 if not os.path.exists(DB):
  if not os.path.exists(ENC):raise ValueError('No encrypted database found.')
  raise ValueError('Recovery requires the application to be unlocked or an emergency recovery package.')
 ps=base64.b64encode(os.urandom(16)).decode();m['password_salt']=ps;m['password_hash']=ph(new,ps,m['iterations']);newcode=secrets.token_urlsafe(18);m['recovery_hash']=ph(newcode,ps,m['iterations']);encrypt(old);write_meta(m);ACTIVE_PASSWORD=new;decrypt(new);return newcode
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def sendj(self,x,code=200,headers={}):
  d=json.dumps(x).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(d)));[self.send_header(k,v) for k,v in headers.items()];self.end_headers();self.wfile.write(d)
 def body(self):return json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')) or 2) or b'{}')
 def auth(self):
  return next((x.split('=',1)[1] for x in self.headers.get('Cookie','').split(';') if x.strip().startswith('dc=' ) and x.split('=',1)[1] in SESSIONS),None)
 def do_GET(self):
  try:
   p=urlparse(self.path)
   if p.path=='/':data=open(os.path.join(getattr(__import__('sys'),'_MEIPASS',os.path.dirname(__file__)),'static','index.html'),'rb').read();self.send_response(200);self.send_header('Content-Type','text/html');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
   if p.path.startswith('/static/'):
    root=os.path.realpath(os.path.join(os.path.dirname(__file__),'static'));fp=os.path.realpath(os.path.join(root,p.path[8:]));
    if fp.startswith(root+os.sep) and os.path.isfile(fp): data=open(fp,'rb').read();self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data);return
   if p.path=='/api/auth/status':return self.sendj({'setup_required':not bool(meta()),'authenticated':bool(self.auth())})
   if not self.auth():return self.sendj({'error':'Authentication required'},401)
   c=conn();out={}
   if p.path=='/api/bootstrap':out={'patients':rows(c,'select * from patients order by name'),'treatments':rows(c,'select t.*,p.name patient_name from treatment_plans t join patients p on p.id=t.patient_id order by t.id desc'),'appointments':rows(c,'select a.*,p.name patient_name from appointments a join patients p on p.id=a.patient_id order by appt_date,start_time'),'payments':rows(c,'select * from payments order by id desc')}
   elif p.path=='/api/patients':out=rows(c,'select * from patients order by name')
   elif p.path=='/api/treatments':out=rows(c,'select t.*,p.name patient_name from treatment_plans t join patients p on p.id=t.patient_id order by t.id desc')
   else:return self.sendj({'error':'Not found'},404)
   c.close();self.sendj(out)
  except Exception as e:self.sendj({'error':str(e)},500)
 def do_POST(self):
  try:
   p=urlparse(self.path);b=self.body()
   if p.path=='/api/auth/setup':r=setup(str(b.get('password','')));return self.sendj({'ok':True,'recovery_code':r},200,{'Set-Cookie':'dc=x; Path=/; HttpOnly'})
   if p.path=='/api/auth/login':
    m=meta();pw=str(b.get('password',''))
    if not m or ph(pw,m['password_salt'],m['iterations'])!=m['password_hash']:return self.sendj({'error':'Incorrect password.'},401)
    prepare(pw);t=secrets.token_urlsafe(24);SESSIONS.add(t);return self.sendj({'ok':True},200,{'Set-Cookie':f'dc={t}; Path=/; HttpOnly'})
   if p.path=='/api/auth/recover':r=recover(str(b.get('recovery_code','')),str(b.get('new_password','')));return self.sendj({'ok':True,'recovery_code':r})
   if not self.auth():return self.sendj({'error':'Authentication required'},401)
   c=conn();
   if p.path in ('/api/patients','/api/patients/update'):
    if p.path.endswith('update'):c.execute('update patients set name=?,phone=?,birth_date=?,gender=?,notes=? where id=?',(b['name'],b.get('phone',''),b.get('birth_date',''),b.get('gender',''),b.get('notes',''),b['id']))
    else:c.execute('insert into patients(name,phone,birth_date,gender,notes,created_at) values(?,?,?,?,?,?)',(b['name'],b.get('phone',''),b.get('birth_date',''),b.get('gender',''),b.get('notes',''),now()))
   elif p.path=='/api/patients/delete':c.execute('delete from patients where id=?',(b['id'],))
   elif p.path in ('/api/treatments','/api/treatments/update'):
    v=(b['patient_id'],b.get('tooth',''),b['treatment'],float(b.get('total_amount',0)),b.get('status','Planned'),b.get('notes',''))
    c.execute('update treatment_plans set patient_id=?,tooth=?,treatment=?,total_amount=?,status=?,notes=? where id=?',v+(b['id'],)) if p.path.endswith('update') else c.execute('insert into treatment_plans(patient_id,tooth,treatment,total_amount,status,notes,created_at) values(?,?,?,?,?,?,?)',v+(now(),))
   elif p.path=='/api/treatments/delete':c.execute('delete from treatment_plans where id=?',(b['id'],))
   else:return self.sendj({'error':'Not found'},404)
   c.commit();c.close();secure_save();self.sendj({'ok':True})
  except Exception as e:self.sendj({'error':str(e)},400)
if __name__=='__main__':ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
