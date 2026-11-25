import os,json,secrets,subprocess,threading,time
from pathlib import Path
from functools import wraps
from flask import Flask,render_template,request,jsonify,session,redirect,url_for
from dotenv import load_dotenv
import requests
load_dotenv()
BASE=Path(__file__).parent
DATA=BASE/"data"; DATA.mkdir(parents=True, exist_ok=True)
HOME_DIR=Path(os.getenv("HOME", "/home/appuser"))
OPENCODE_BIN=HOME_DIR/".opencode"/"bin"/"opencode"
LEGACY_BIN=Path("/root/.opencode/bin/opencode")
OPENCODE_LOG=DATA/"opencode-server.log"
OPENCODE_CONFIG_DIR=HOME_DIR/".config"/"opencode"
OPENCODE_CONFIG=OPENCODE_CONFIG_DIR/"opencode.json"
DEFAULT_MODEL="opencode/big-pickle"
SERVER_PROC=None
SERVER_LOCK=threading.Lock()
SF=DATA/"settings.json"
app=Flask(__name__); app.secret_key=os.getenv("FLASK_SECRET_KEY") or secrets.token_hex(32)
def cfg():
    try:return json.loads(SF.read_text())
    except:return {"opencode_url":os.getenv("OPENCODE_URL","http://127.0.0.1:4096"),"project_dir":"/workspace","default_model":DEFAULT_MODEL,"github_username":"","github_token":"","github_repo":"","github_branch":"main"}
def save(s):
    SF.write_text(json.dumps(s,indent=2)); SF.chmod(0o600)
def write_opencode_config(model=None):
    """Persist OpenCode's global default model in its home volume."""
    OPENCODE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    current = {}
    if OPENCODE_CONFIG.exists():
        try:
            current = json.loads(OPENCODE_CONFIG.read_text())
        except Exception:
            backup = OPENCODE_CONFIG.with_suffix(".json.bak")
            if not backup.exists(): backup.write_text(OPENCODE_CONFIG.read_text(errors="replace"))
            current = {}
    current["$schema"] = "https://opencode.ai/config.json"
    current["model"] = model or cfg().get("default_model") or DEFAULT_MODEL
    tmp = OPENCODE_CONFIG.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(current, indent=2) + "\n")
    tmp.replace(OPENCODE_CONFIG)
    OPENCODE_CONFIG.chmod(0o600)
    return current["model"]
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
    return jsonify({"installed":installed,"version":None,"running":running,"binary":str(OPENCODE_BIN),"home":str(HOME_DIR),"default_model":cfg().get("default_model",DEFAULT_MODEL)})
@app.post("/api/manager/install")
@auth
def manager_install():
    try:
        HOME_DIR.mkdir(parents=True, exist_ok=True)
        install_dir = HOME_DIR/".opencode"/"bin"
        install_dir.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "HOME": str(HOME_DIR),
            "XDG_CONFIG_HOME": str(HOME_DIR/".config"),
            "XDG_DATA_HOME": str(HOME_DIR/".local/share"),
            "PATH": str(install_dir) + os.pathsep + os.environ.get("PATH", ""),
        }
        # Use non-login bash: bash -l can reset HOME to /root when the container runs as root.
        proc = subprocess.run(
            ["bash", "-c", "curl -fsSL https://opencode.ai/install | bash"],
            capture_output=True, text=True, timeout=300, env=env
        )
        if proc.returncode:
            return jsonify({"error":("OpenCode installer failed. "+(proc.stderr or proc.stdout or ""))[-5000:]}),500
        if not OPENCODE_BIN.exists() and LEGACY_BIN.exists():
            # Migrate an older root-home installation into the persistent named volume.
            import shutil
            shutil.copy2(LEGACY_BIN, OPENCODE_BIN)
            OPENCODE_BIN.chmod(0o755)
        if not OPENCODE_BIN.exists():
            return jsonify({"error":"Installer finished but binary is missing at "+str(OPENCODE_BIN)+". Installer output: "+(proc.stdout or "")[-2500:]}),500
        OPENCODE_BIN.chmod(0o755)
        model=write_opencode_config()
        return jsonify({"ok":True,"message":"OpenCode installed in persistent storage. Default model: "+model+"."})
    except Exception as e:
        return jsonify({"error":"OpenCode installation error: "+str(e)}),500
@app.post("/api/manager/start")
@auth
def manager_start():
    global SERVER_PROC
    if not OPENCODE_BIN.is_file():
        return jsonify({"error":"OpenCode binary is not installed in persistent storage at "+str(OPENCODE_BIN)+". The dashboard will install it automatically on page load; otherwise click Install."}),400
    if not os.access(OPENCODE_BIN, os.X_OK):
        try: OPENCODE_BIN.chmod(0o755)
        except OSError as e: return jsonify({"error":"OpenCode binary is not executable: "+str(e)}),500
    try:
        r=requests.get("http://127.0.0.1:4096/global/health",timeout=1)
        if r.ok:return jsonify({"ok":True,"message":"OpenCode server is already running."})
    except Exception:pass
    try:
        project=Path(cfg().get("project_dir","/workspace")).expanduser()
        project.mkdir(parents=True,exist_ok=True)
        # Verify write access before starting OpenCode, and report a useful error.
        probe=project/".opencode-write-test"
        try:
            probe.write_text("ok")
            probe.unlink()
        except OSError as e:
            return jsonify({"error":f"Project folder is not writable: {project}. Check that the host folder is not mounted read-only. Details: {e}"}),500
        DATA.mkdir(parents=True, exist_ok=True)
        write_opencode_config()
        env={**os.environ,"HOME":str(HOME_DIR),"XDG_CONFIG_HOME":str(HOME_DIR/".config")}
        provider_env={"groq":"GROQ_API_KEY","openai":"OPENAI_API_KEY","anthropic":"ANTHROPIC_API_KEY","google":"GOOGLE_GENERATIVE_AI_API_KEY","openrouter":"OPENROUTER_API_KEY"}
        for provider,key in cfg().get("provider_keys",{}).items():
            if provider in provider_env and key: env[provider_env[provider]]=key
        with OPENCODE_LOG.open("a", encoding="utf-8") as log:
            SERVER_PROC=subprocess.Popen([str(OPENCODE_BIN),"serve","--hostname","127.0.0.1","--port","4096"],cwd=str(project),stdout=log,stderr=subprocess.STDOUT,env=env,start_new_session=True)
        for _ in range(30):
            time.sleep(1)
            try:
                r=requests.get("http://127.0.0.1:4096/global/health",timeout=1)
                if r.ok:return jsonify({"ok":True,"message":"OpenCode server started."})
            except Exception:pass
            if SERVER_PROC.poll() is not None:break
        detail=OPENCODE_LOG.read_text(errors="replace")[-2500:] if OPENCODE_LOG.exists() else ""
        return jsonify({"error":"OpenCode did not become healthy. "+("Process exit code: "+str(SERVER_PROC.poll())+". " if SERVER_PROC else "")+detail}),500
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
    env_names={"groq":"GROQ_API_KEY","openai":"OPENAI_API_KEY","anthropic":"ANTHROPIC_API_KEY","google":"GOOGLE_GENERATIVE_AI_API_KEY","openrouter":"OPENROUTER_API_KEY"}
    if provider not in env_names or not key:
        return jsonify({"error":"Choose a supported provider and enter its API key."}),400
    st=cfg(); keys=st.get("provider_keys",{}); keys[provider]=key; st["provider_keys"]=keys; save(st)
    global SERVER_PROC
    if SERVER_PROC and SERVER_PROC.poll() is None:
        SERVER_PROC.terminate()
        try: SERVER_PROC.wait(timeout=8)
        except subprocess.TimeoutExpired: SERVER_PROC.kill(); SERVER_PROC.wait(timeout=3)
        SERVER_PROC=None
    return jsonify({"ok":True,"message":provider+" key saved securely. Start OpenCode again to activate it."})
@app.post("/api/model")
@auth
def set_default_model():
    global SERVER_PROC
    b=request.get_json(force=True); model=(b.get("model") or "").strip()
    if not model or "/" not in model or len(model)>180 or any(c.isspace() for c in model):
        return jsonify({"error":"Enter a model ID in provider/model format, e.g. opencode/big-pickle."}),400
    st=cfg(); st["default_model"]=model; save(st)
    try:
        write_opencode_config(model)
        if SERVER_PROC and SERVER_PROC.poll() is None:
            SERVER_PROC.terminate()
            try: SERVER_PROC.wait(timeout=8)
            except subprocess.TimeoutExpired: SERVER_PROC.kill(); SERVER_PROC.wait(timeout=3)
            SERVER_PROC=None
        return jsonify({"ok":True,"model":model,"message":"Default model saved. Start OpenCode again to apply it."})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.get("/api/status")
@auth
def status():
    s=cfg(); u=s["opencode_url"].rstrip("/")
    try:r=requests.get(u+"/global/health",timeout=3);r.raise_for_status();return jsonify({"ok":True,"health":r.json(),"url":u})
    except Exception as e:return jsonify({"ok":False,"error":str(e),"url":u})
@app.get("/api/settings")
@auth
def getsettings():
    s=cfg();s.pop("github_token",None);s.pop("provider_keys",None);s["default_model"]=s.get("default_model",DEFAULT_MODEL);s["github_token_saved"]=bool(cfg().get("github_token"));return jsonify(s)
@app.post("/api/settings")
@auth
def setsettings():
    s=cfg(); b=request.get_json(force=True)
    for k in ["opencode_url","project_dir","default_model","github_username","github_repo","github_branch"]:
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
def opencode_unavailable_error(exc):
    return ("OpenCode server is not running at 127.0.0.1:4096. "
            "The dashboard will try to start it automatically when the page loads. "
            "If it still fails, open Advanced tools → Server logs. Details: " + str(exc))

@app.get("/api/models")
@auth
def models():
    try:return jsonify(oc("/provider",timeout=10))
    except Exception as e:return jsonify({"error":opencode_unavailable_error(e)}),503
@app.get("/api/sessions")
@auth
def sessions():
    try:return jsonify(oc("/session",timeout=10))
    except Exception as e:return jsonify({"error":opencode_unavailable_error(e)}),503
@app.post("/api/sessions")
@auth
def new_session():
    try:return jsonify(oc("/session","POST",{},15))
    except Exception as e:return jsonify({"error":opencode_unavailable_error(e)}),503
def text_only_parts(payload):
    """Return only user-visible text parts; never expose reasoning/tool/internal parts."""
    if isinstance(payload, dict):
        parts = payload.get("parts")
        if parts is None and isinstance(payload.get("message"), dict):
            parts = payload["message"].get("parts")
    elif isinstance(payload, list):
        parts = []
        for item in payload:
            if isinstance(item, dict):
                item_parts = item.get("parts") or []
                parts.extend(item_parts)
    else:
        parts = []
    visible = []
    for part in parts or []:
        if not isinstance(part, dict):
            continue
        if part.get("type") != "text":
            continue
        value = part.get("text")
        if isinstance(value, str) and value.strip():
            visible.append(value)
    return visible

@app.get("/api/sessions/<sid>/messages")
@auth
def messages(sid):
    try:
        raw=oc(f"/session/{sid}/message",timeout=20)
        items=raw if isinstance(raw,list) else raw.get("messages",[]) if isinstance(raw,dict) else []
        safe=[]
        for item in items:
            if not isinstance(item,dict):
                continue
            info=item.get("info") if isinstance(item.get("info"),dict) else {}
            role=info.get("role") or item.get("role") or "assistant"
            safe.append({
                "id": info.get("id") or item.get("id"),
                "role": role if role in ("user","assistant") else "assistant",
                "text": "\\n".join(text_only_parts(item))
            })
        return jsonify({"messages":safe})
    except Exception as e:
        return jsonify({"error":opencode_unavailable_error(e)}),503

@app.post("/api/sessions/<sid>/command")
@auth
def session_command(sid):
    """Execute a native OpenCode slash command through the server HTTP API."""
    b=request.get_json(force=True)
    command=(b.get("command") or "").strip().lstrip("/")
    arguments=(b.get("arguments") or "").strip()
    allowed={"init","undo","redo","compact","share","help"}
    if command not in allowed:
        return jsonify({"error":"Unsupported OpenCode command: /"+command}),400
    try:
        raw=oc(f"/session/{sid}/command","POST",{"command":command,"arguments":arguments},240)
        visible="\n".join(text_only_parts(raw))
        info=raw.get("info",{}) if isinstance(raw,dict) else {}
        return jsonify({"ok":True,"text":visible,"result":info})
    except Exception as e:
        return jsonify({"error":"OpenCode command /"+command+" failed: "+str(e)}),502

@app.post("/api/sessions/<sid>/prompt")
@auth
def prompt(sid):
    b=request.get_json(force=True); t=(b.get("prompt") or "").strip()
    if not t:return jsonify({"error":"Prompt required"}),400
    try:
        raw=oc(f"/session/{sid}/message","POST",{"parts":[{"type":"text","text":t}]},180)
        visible="\\n".join(text_only_parts(raw))
        if not visible:
            return jsonify({"error":"OpenCode returned no user-visible text. Check Server logs for provider/model errors."}),502
        return jsonify({"text":visible})
    except Exception as e:
        return jsonify({"error":opencode_unavailable_error(e)}),503
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
