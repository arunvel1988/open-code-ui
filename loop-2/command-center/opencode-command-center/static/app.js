
const $=x=>document.getElementById(x);let sid=null;
async function api(p,o={}){let r=await fetch(p,{headers:{"Content-Type":"application/json"},...o}),d=await r.json();if(!r.ok)throw Error(d.error||"Request failed");return d}
function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]))}
async function status(){let d=await api("/api/status");$("server").textContent=d.ok?"Online":"Offline";$("status").textContent=d.ok?"● OpenCode connected":"● OpenCode unavailable";$("project").textContent=$("projectdir").value||"Workspace"}
async function loadSettings(){let d=await api("/api/settings");$("ocurl").value=d.opencode_url;$("projectdir").value=d.project_dir;$("ghuser").value=d.github_username||"";$("repo").value=d.github_repo||""}
async function save(test){try{await api("/api/settings",{method:"POST",body:JSON.stringify({opencode_url:$("ocurl").value,project_dir:$("projectdir").value,github_username:$("ghuser").value,github_repo:$("repo").value,github_token:$("ghtoken").value})});$("ghtoken").value="";$("settingsmsg").textContent="Settings saved";$("ghmsg").textContent="Settings saved";await loadSettings();if(test){let d=await api("/api/github/test",{method:"POST",body:"{}"});$("ghmsg").textContent="Connected as "+d.login}}catch(e){$("ghmsg").textContent=e.message;$("settingsmsg").textContent=e.message}}
async function loadFiles(){try{let d=await api("/api/files");$("root").textContent=d.root;$("filelist").innerHTML=d.items.map(x=>`<div class="line"><b>${x.dir?"▣":"▤"} ${esc(x.name)}</b><small>${x.dir?"Folder":x.size+" bytes"}</small></div>`).join("")||"No files"}catch(e){$("filelist").textContent=e.message}}
async function loadSessions(){try{let d=await api("/api/sessions"),a=Array.isArray(d)?d:d.sessions||[];$("sessionlist").innerHTML=a.slice(0,40).map(x=>`<button class="line clickable" onclick="selectSession('${esc(x.id)}')"><b>${esc(x.title||"Untitled session")}</b><small>${esc(x.id)}</small></button>`).join("")||"No sessions yet"}catch(e){$("sessionlist").textContent=e.message}}
async function newSession(){try{let d=await api("/api/sessions",{method:"POST",body:"{}"});sid=d.id;$("sid").textContent=sid;$("chat").innerHTML='<div class="empty">New session ready. What are we building?</div>';loadSessions()}catch(e){alert(e.message)}}
function renderBubble(role,text){
  const box=document.createElement("div");
  box.className="bubble";
  const label=document.createElement("small");
  label.textContent=String(role||"assistant").toUpperCase();
  const body=document.createElement("p");
  body.textContent=String(text||"");
  box.append(label,body);
  return box;
}
function scrollChat(){const chat=$("chat");chat.scrollTop=chat.scrollHeight;}
async function selectSession(id){
  sid=id;
  $("sid").textContent=id;
  try{
    const d=await api("/api/sessions/"+encodeURIComponent(id)+"/messages");
    const items=Array.isArray(d.messages)?d.messages:[];
    $("chat").replaceChildren();
    for(const item of items){
      if(item.text) $("chat").appendChild(renderBubble(item.role,item.text));
    }
    if(!items.length) $("chat").innerHTML='<div class="welcome"><div class="welcome-icon">O</div><h3>Session ready</h3><p>Send a message to continue.</p></div>';
    scrollChat();
  }catch(e){$("chat").textContent=e.message;}
}
const COMMANDS=[
  {name:"help",description:"Show available dashboard and OpenCode commands",local:true},
  {name:"new",description:"Create a fresh session",local:true},
  {name:"sessions",description:"Show recent sessions",local:true},
  {name:"models",description:"Show configured providers and models",local:true},
  {name:"connect",description:"Open provider connection settings",local:true},
  {name:"init",description:"Analyze project and create AGENTS.md"},
  {name:"undo",description:"Undo the previous OpenCode turn and file changes"},
  {name:"redo",description:"Restore the changes staged by undo"},
  {name:"compact",description:"Summarize and compact this session"},
  {name:"share",description:"Create a share link for this session"}
];
let paletteIndex=0;
function updateCommandPalette(){
  const input=$("prompt"), palette=$("commandPalette"), value=input.value;
  const match=value.match(/^\/([a-zA-Z-]*)$/);
  if(!match){palette.hidden=true;return;}
  const q=match[1].toLowerCase();
  const found=COMMANDS.filter(c=>c.name.startsWith(q));
  paletteIndex=Math.min(paletteIndex,Math.max(0,found.length-1));
  palette.replaceChildren();
  if(!found.length){const empty=document.createElement("div");empty.className="command-empty";empty.textContent="No matching commands";palette.append(empty);}
  found.forEach((c,i)=>{const b=document.createElement("button");b.type="button";b.className="command-option"+(i===paletteIndex?" active":"");const name=document.createElement("strong"),desc=document.createElement("small");name.textContent="/"+c.name;desc.textContent=c.description;b.append(name,desc);b.addEventListener("mousedown",e=>e.preventDefault());b.addEventListener("click",()=>{input.value="/"+c.name+(c.local?" ":" ");palette.hidden=true;input.focus();});palette.append(b);});
  palette.hidden=false;
}
function showCommandHelp(){
  const lines=COMMANDS.map(c=>"/"+c.name+" — "+c.description).join("\n");
  $("chat").appendChild(renderBubble("commands",lines));scrollChat();
}
async function runSlashCommand(raw){
  const match=raw.match(/^\/([a-zA-Z-]+)(?:\s+(.*))?$/s);
  if(!match)return false;
  const name=match[1].toLowerCase(),args=(match[2]||"").trim();
  if(name==="help"){showCommandHelp();return true;}
  if(name==="new"){await newSession();return true;}
  if(name==="sessions"){$("sessionlist").scrollIntoView({behavior:"smooth",block:"center"});await loadSessions();return true;}
  if(name==="models"){$("modellist").scrollIntoView({behavior:"smooth",block:"center"});await loadModels();return true;}
  if(name==="connect"){$("providerId").scrollIntoView({behavior:"smooth",block:"center"});$("providerKey").focus({preventScroll:true});return true;}
  if(!["init","undo","redo","compact","share"].includes(name))return false;
  if(!sid){const created=await api("/api/sessions",{method:"POST",body:"{}"});sid=created.id||created.session?.id;if(!sid)throw Error("Could not create an OpenCode session.");$("sid").textContent=sid;}
  const label="/"+name+(args?" "+args:"");
  $("chat").appendChild(renderBubble("you",label));
  const pending=renderBubble("opencode","Running "+label+"…");$("chat").appendChild(pending);scrollChat();
  try{
    const result=await api("/api/sessions/"+encodeURIComponent(sid)+"/command",{method:"POST",body:JSON.stringify({command:name,arguments:args})});
    pending.remove();
    if(result.text)$("chat").appendChild(renderBubble("opencode",result.text));
    else $("chat").appendChild(renderBubble("system","Command /"+name+" completed."));
    if(name==="share"&&result.result?.share?.url)$("chat").appendChild(renderBubble("system","Share URL: "+result.result.share.url));
    if(name==="undo"||name==="redo")await selectSession(sid);
    scrollChat();
  }catch(e){pending.remove();$("chat").appendChild(renderBubble("error",e.message));scrollChat();}
  return true;
}
async function send(){
  const promptText=$("prompt").value.trim();
  if(!promptText)return;
  if(promptText.startsWith("/") && await runSlashCommand(promptText)){ $("prompt").value="";$("commandPalette").hidden=true;return; }
  const sendButton=document.querySelector(".send-button");
  if(sendButton)sendButton.disabled=true;
  try{
    if(!sid){
      const created=await api("/api/sessions",{method:"POST",body:"{}"});
      sid=created.id || created.session?.id;
      if(!sid)throw Error("OpenCode did not return a session ID. Check the server logs.");
      $("sid").textContent=sid;
      $("chat").replaceChildren();
      loadSessions();
    }
    $("chat").appendChild(renderBubble("you",promptText));
    const pending=renderBubble("opencode","Thinking…");
    $("chat").appendChild(pending);
    $("prompt").value="";
    scrollChat();
    const result=await api("/api/sessions/"+encodeURIComponent(sid)+"/prompt",{
      method:"POST",body:JSON.stringify({prompt:promptText})
    });
    pending.remove();
    if(result.text) $("chat").appendChild(renderBubble("opencode",result.text));
    else $("chat").appendChild(renderBubble("system","No text response was returned."));
    scrollChat();
  }catch(e){
    $("chat").appendChild(renderBubble("error",e.message));
    scrollChat();
  }finally{
    if(sendButton)sendButton.disabled=false;
  }
}
async function loadModels(){try{let d=await api("/api/models");$("modellist").textContent=JSON.stringify(d,null,2)}catch(e){$("modellist").textContent=e.message}}
async function repos(){try{let a=await api("/api/github/repos",{method:"POST",body:"{}"});$("repos").innerHTML=a.map(x=>`<div class="line"><b>${esc(x.full_name)}</b><small>${x.private?"Private":"Public"}</small></div>`).join("")}catch(e){$("repos").textContent=e.message}}
async function createRepo(){try{let d=await api("/api/github/create",{method:"POST",body:JSON.stringify({name:$("repo").value,private:$("private").value==="true"})});$("ghmsg").textContent="Created "+d.repo;repos()}catch(e){$("ghmsg").textContent=e.message}}
async function push(){if(!confirm("Commit all changes in the selected project and push to origin? Review your files first."))return;try{let d=await api("/api/git/push",{method:"POST",body:JSON.stringify({message:$("commit").value})});$("gitmsg").textContent=d.commit+" "+d.push}catch(e){$("gitmsg").textContent=e.message}}
$("prompt").addEventListener("input",()=>{paletteIndex=0;updateCommandPalette();});
$("prompt").addEventListener("keydown",e=>{
  const palette=$("commandPalette");
  if(!palette.hidden){
    const options=[...palette.querySelectorAll(".command-option")];
    if(e.key==="ArrowDown"&&options.length){e.preventDefault();paletteIndex=(paletteIndex+1)%options.length;updateCommandPalette();return;}
    if(e.key==="ArrowUp"&&options.length){e.preventDefault();paletteIndex=(paletteIndex-1+options.length)%options.length;updateCommandPalette();return;}
    if(e.key==="Tab"&&options.length){e.preventDefault();options[paletteIndex].click();return;}
    if(e.key==="Escape"){palette.hidden=true;return;}
    if(e.key==="Enter"&&!e.shiftKey&&options.length){e.preventDefault();options[paletteIndex].click();return;}
  }
  if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}
});
document.addEventListener("click",e=>{if(!e.target.closest(".composer-wrap"))$("commandPalette").hidden=true;});
async function bootstrap(){
  // Load saved project/provider settings first, then ensure the engine is online
  // before requesting sessions/models. This prevents the initial connection-refused race.
  try {
    await loadSettings();
    let engine = await checkEngine();
    if (engine && !engine.installed) {
      $("engineDetail").textContent = "OpenCode is not installed. Installing into persistent Docker storage…";
      try {
        const installed = await api("/api/manager/install", {method:"POST", body:"{}"});
        $("engineDetail").textContent = installed.message;
        engine = await checkEngine();
      } catch (e) {
        $("engineDetail").textContent = "Automatic installation failed: " + e.message + " — use Install and check Server logs.";
      }
    }
    if (engine && engine.installed && !engine.running) {
      $("engineDetail").textContent = "Starting OpenCode automatically…";
      await startOpenCode();
    }
    await Promise.allSettled([status(), loadFiles(), loadSessions(), loadModels()]);
  } catch (e) {
    $("engineDetail").textContent = "Startup check failed: " + e.message;
  }
}
bootstrap();
setInterval(status,15000);

async function checkEngine(){try{let d=await api("/api/manager");$("installState").textContent=d.installed?"Installed":"Not installed";$("engineRunState").textContent=d.running?"Running":"Stopped";$("engineDetail").textContent=d.installed?"OpenCode binary: "+d.binary:"Use Install OpenCode to install it into the persistent application volume.";$("installBtn").disabled=false;$("installBtn").textContent=d.installed?"Update / Repair":"Install OpenCode";if($("defaultModel")&&!$("defaultModel").dataset.userEdited)$("defaultModel").value=d.default_model||"opencode/big-pickle";return d;}catch(e){$("engineDetail").textContent=e.message;return null}}
async function installOpenCode(){if(!confirm("Install OpenCode inside the Command Center container? This downloads the official installer and persists the binary in a Docker volume."))return;let b=$("installBtn");b.disabled=true;b.textContent="Installing…";try{let d=await api("/api/manager/install",{method:"POST",body:"{}"});$("engineDetail").textContent=d.message;await checkEngine()}catch(e){$("engineDetail").textContent="Installation failed: "+e.message;b.disabled=false;b.textContent="Retry installation"}}
async function startOpenCode(){try{let d=await api("/api/manager/start",{method:"POST",body:"{}"});$("engineDetail").textContent=d.message;await checkEngine();await status()}catch(e){$("engineDetail").textContent="Start failed: "+e.message}}
async function stopOpenCode(){try{let d=await api("/api/manager/stop",{method:"POST",body:"{}"});$("engineDetail").textContent=d.message;await checkEngine()}catch(e){$("engineDetail").textContent=e.message}}
async function connectProvider(){let provider=$("providerId").value,key=$("providerKey").value.trim();if(!key){$("providerMsg").textContent="Enter an API key first.";return}try{let d=await api("/api/providers/connect",{method:"POST",body:JSON.stringify({provider,key})});$("providerKey").value="";$("providerMsg").textContent=d.message;loadModels()}catch(e){$("providerMsg").textContent="Connection failed: "+e.message}}

async function saveModel(){try{let d=await api("/api/model",{method:"POST",body:JSON.stringify({model:$("defaultModel").value.trim()})});$("modelMsg").textContent=d.message;await checkEngine()}catch(e){$("modelMsg").textContent=e.message}}
if($("defaultModel"))$("defaultModel").addEventListener("input",()=>{$("defaultModel").dataset.userEdited="1"});
