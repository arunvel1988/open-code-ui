import os,json,secrets,subprocess,threading,time
from pathlib import Path
from functools import wraps
from flask import Flask,render_template,request,jsonify,session,redirect,url_for
from dotenv import load_dotenv
import requests
load_dotenv()
BASE=Path(__file__).parent
DATA=BASE/"data"; DATA.mkdir(exist_ok=True)
HOME_DIR=Path(os.getenv("HOME", "/home/appuser"))
OPENCODE_BIN=HOME_DIR/".opencode"/"bin"/"opencode"
OPENCODE_LOG=DATA/"opencode-server.log"
SERVER_PROC=None
SERVER_LOCK=threading.Lock()
SF=DATA/"settings.json"
app=Flask(__name__); app.secret_key=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
def cfg():
    try:return json.loads(SF.read_text())
    except:return {"opencode_url":os.getenv("OPENCODE_URL","http://127.0.0.1:4096"),"project_dir":"/workspace","github_username":"","github_token":"","github_repo":"","github_branch":"main"}
def save(s):
    SF.write_text(json.dumps(s,indent=2)); SF.chmod(0o600)
def auth(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("ok"):return redirect(url_for("login"))
        return f(*a,**k)
    return w
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        if secrets.compare_digest(request.form.get("password",""),os.getenv("DASHBOARD_PASSWORD","change-me-now")):
            session["ok"]=True; return redirect("/")
        return render_template("login.html",error="Incorrect password")
    return render_template("login.html",error="")
@app.post("/logout")
def logout():session.clear();return redirect("/login")
@app.get("/")
@auth
def home():return render_template("index.html")
@app.get("/api/manager")
@auth
def manager_status():
    installed=OPENCODE_BIN.exists()
    running=False
    try:
        r=requests.get("http://127.0.0.1:4096/global/health",timeout=1); running=r.ok
    except Exception: pass
    return jsonify({"installed":installed,"version":None,"running":running,"binary":str(OPENCODE_BIN)})
@app.post("/api/manager/install")
@auth
def manager_install():
    if OPENCODE_BIN.exists(): return jsonify({"ok":True,"message":"OpenCode is already installed in the Command Center container."})
    try:
        curl=subprocess.Popen(["curl","-fsSL","https://opencode.ai/install"],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        proc=subprocess.run(["bash"],stdin=curl.stdout,capture_output=True,text=True,timeout=240,env={**os.environ,"HOME":str(HOME_DIR)})
        curl.stdout.close(); curl_err=curl.stderr.read().decode(errors="replace") if curl.stderr else ""
        if proc.returncode: return jsonify({"error":(proc.stderr or curl_err or "Installer failed")[-3000:]}),500
        if not OPENCODE_BIN.exists(): return jsonify({"error":"Installer finished but expected binary was not found at "+str(OPENCODE_BIN)+". Installer output: "+proc.stdout[-1500:]}),500
        return jsonify({"ok":True,"message":"OpenCode installed successfully inside the Command Center."})
    except Exception as e:return jsonify({"error":str(e)}),500
@app.post("/api/manager/start")
@auth
def manager_start():
    global SERVER_PROC
    if not OPENCODE_BIN.exists(): return jsonify({"error":"Install OpenCode first using the Install button."}),400
    try:
        r=requests.get("http://127.0.0.1:4096/global/health",timeout=1)
        if r.ok:return jsonify({"ok":True,"message":"OpenCode server is already running."})
    except Exception:pass
    try:
        project=Path(cfg().get("project_dir","/workspace")).expanduser(); project.mkdir(parents=True,exist_ok=True)
        log=OPENCODE_LOG.open("a")
        SERVER_PROC=subprocess.Popen([str(OPENCODE_BIN),"serve","--hostname","127.0.0.1","--port","4096"],cwd=str(project),stdout=log,stderr=subprocess.STDOUT,env={**os.environ,"HOME":str(HOME_DIR)},start_new_session=True)
        for _ in range(30):
            time.sleep(1)
            try:
                r=requests.get("http://127.0.0.1:4096/global/health",timeout=1)
                if r.ok:return jsonify({"ok":True,"message":"OpenCode server started."})
            except Exception:pass
            if SERVER_PROC.poll() is not None:break
        return jsonify({"error":"OpenCode did not become healthy. Check server logs in Activity."}),500
    except Exception as e:return jsonify({"error":str(e)}),500
@app.post("/api/manager/stop")
@auth
def manager_stop():
    global SERVER_PROC
    try:
        if SERVER_PROC and SERVER_PROC.poll() is None: SERVER_PROC.terminate(); SERVER_PROC.wait(timeout=8)
        SERVER_PROC=None
        return jsonify({"ok":True,"message":"Stop request sent."})
    except Exception as e:return jsonify({"error":str(e)}),500
@app.get("/api/manager/logs")
@auth
def manager_logs():
    try:return jsonify({"logs":OPENCODE_LOG.read_text(errors="replace")[-12000:] if OPENCODE_LOG.exists() else "No server logs yet."})
    except Exception as e:return jsonify({"error":str(e)}),500
@app.post("/api/providers/connect")
@auth
def connect_provider():
    b=request.get_json(force=True); provider=(b.get("provider") or "").strip().lower(); key=(b.get("key") or "").strip()
    if not provider or not key:return jsonify({"error":"Provider and API key are required"}),400
    if not provider.replace("-","").isalnum():return jsonify({"error":"Invalid provider ID"}),400
    try:
        r=requests.put("http://127.0.0.1:4096/auth/"+provider,json={"type":"api","key":key},timeout=15)
        r.raise_for_status()
        return jsonify({"ok":True,"message":provider+" credentials saved by OpenCode."})
    except Exception as e:return jsonify({"error":str(e)}),502
@app.get("/api/status")
@auth
def status():
    s=cfg(); u=s["opencode_url"].rstrip("/")
    try:r=requests.get(u+"/global/health",timeout=3);r.raise_for_status();return jsonify({"ok":True,"health":r.json(),"url":u})
    except Exception as e:return jsonify({"ok":False,"error":str(e),"url":u})
@app.get("/api/settings")
@auth
def getsettings():
    s=cfg();s.pop("github_token",None);s["github_token_saved"]=bool(cfg().get("github_token"));return jsonify(s)
@app.post("/api/settings")
@auth
def setsettings():
    s=cfg(); b=request.get_json(force=True)
    for k in ["opencode_url","project_dir","github_username","github_repo","github_branch"]:
        if k in b:s[k]=str(b[k]).strip()
    if b.get("github_token"):s["github_token"]=b["github_token"]
    save(s);return jsonify({"ok":True,"token_saved":bool(s.get("github_token"))})
@app.get("/api/files")
@auth
def files():
    p=Path(cfg().get("project_dir","/workspace")).expanduser().resolve()
    try:
        p.mkdir(parents=True,exist_ok=True)
        return jsonify({"root":str(p),"items":[{"name":x.name,"dir":x.is_dir(),"size":x.stat().st_size if x.is_file() else None} for x in sorted(p.iterdir(),key=lambda x:(not x.is_dir(),x.name.lower()))[:250]]})
    except Exception as e:return jsonify({"error":str(e)}),400
def oc(path,method="GET",data=None,timeout=180):
    u=cfg()["opencode_url"].rstrip("/")+"/"+path.lstrip("/")
    r=requests.request(method,u,json=data,timeout=timeout);r.raise_for_status();return r.json() if r.content else {}
@app.get("/api/models")
@auth
def models():
    try:return jsonify(oc("/provider",timeout=10))
    except Exception as e:return jsonify({"error":str(e)}),502
@app.get("/api/sessions")
@auth
def sessions():
    try:return jsonify(oc("/session",timeout=10))
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/sessions")
@auth
def new_session():
    try:return jsonify(oc("/session","POST",{},15))
    except Exception as e:return jsonify({"error":str(e)}),502
@app.get("/api/sessions/<sid>/messages")
@auth
def messages(sid):
    try:return jsonify(oc(f"/session/{sid}/message",timeout=20))
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/sessions/<sid>/prompt")
@auth
def prompt(sid):
    b=request.get_json(force=True); t=(b.get("prompt") or "").strip()
    if not t:return jsonify({"error":"Prompt required"}),400
    try:return jsonify(oc(f"/session/{sid}/message","POST",{"parts":[{"type":"text","text":t}]},180))
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/github/test")
@auth
def gh_test():
    s=cfg();token=s.get("github_token")
    if not token:return jsonify({"error":"Save a token first"}),400
    try:
        r=requests.get("https://api.github.com/user",headers={"Authorization":"Bearer "+token,"Accept":"application/vnd.github+json"},timeout=12);r.raise_for_status()
        return jsonify({"ok":True,"login":r.json().get("login")})
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/github/repos")
@auth
def gh_repos():
    s=cfg()
    try:
        r=requests.get("https://api.github.com/user/repos?per_page=100&sort=updated",headers={"Authorization":"Bearer "+s["github_token"],"Accept":"application/vnd.github+json"},timeout=15);r.raise_for_status()
        return jsonify([{"full_name":x["full_name"],"private":x["private"],"url":x["html_url"]} for x in r.json()])
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/github/create")
@auth
def gh_create():
    s=cfg();b=request.get_json(force=True)
    try:
        r=requests.post("https://api.github.com/user/repos",headers={"Authorization":"Bearer "+s["github_token"],"Accept":"application/vnd.github+json"},json={"name":b.get("name"),"private":bool(b.get("private",True)),"auto_init":True},timeout=15);r.raise_for_status()
        return jsonify({"ok":True,"repo":r.json()["full_name"],"url":r.json()["html_url"]})
    except Exception as e:return jsonify({"error":str(e)}),502
@app.post("/api/git/push")
@auth
def gitpush():
    p=Path(cfg()["project_dir"]).expanduser().resolve()
    def run(args):return subprocess.run(["git"]+args,cwd=p,capture_output=True,text=True,timeout=45)
    try:
        if run(["rev-parse","--is-inside-work-tree"]).returncode:return jsonify({"error":"Folder is not a Git repository"}),400
        if not run(["status","--porcelain"]).stdout.strip():return jsonify({"error":"No changes to commit"}),400
        b=request.get_json(force=True);a=run(["add","-A"])
        if a.returncode:return jsonify({"error":a.stderr}),400
        c=run(["commit","-m",b.get("message") or "Update from OpenCode Command Center"])
        if c.returncode:return jsonify({"error":c.stderr}),400
        q=run(["push","-u","origin",cfg().get("github_branch","main")])
        if q.returncode:return jsonify({"error":"Commit created, push failed: "+q.stderr}),502
        return jsonify({"ok":True,"commit":c.stdout,"push":q.stdout})
    except Exception as e:return jsonify({"error":str(e)}),400
if __name__=="__main__":app.run(host="0.0.0.0",port=5000)
