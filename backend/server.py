from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import re
import datetime
import spacy
import httpx
import json

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    nlp = None

# --- Database Setup (SQLAlchemy) ---
SQLALCHEMY_DATABASE_URL = "sqlite:///./aigov.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String)
    user_id = Column(String)
    url = Column(String)
    prompt_text = Column(String)
    status = Column(String)
    department = Column(String, default="Engineering")

class ToolRegistry(Base):
    __tablename__ = "tool_registry"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String, unique=True, index=True)
    status = Column(String) # approved, pending, blocked
    justification = Column(String)
    clearance_level = Column(String, default="PUBLIC") # PUBLIC, INTERNAL, CONFIDENTIAL

class OutputLog(Base):
    __tablename__ = "output_logs"
    id = Column(Integer, primary_key=True, index=True)
    prompt_id = Column(Integer, ForeignKey("audit_logs.id"))
    ai_response_text = Column(String)
    timestamp = Column(String)

Base.metadata.create_all(bind=engine)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="Enterprise AI Governance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

# --- Plain-Language Exception Handler ---
@app.exception_handler(Exception)
async def simple_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=400,
        content={"message": "We couldn't process your request to use this tool. Please check the web address and try again. If this persists, contact IT support."}
    )

# --- REPO 1 REFERENCE: NeMo Guardrails (Data Protection) ---
class DataProtectionGuardrail:
    def __init__(self):
        self.pii_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.secret_project = "project titan"

    def redact_prompt(self, text):
        redacted_text = self.pii_pattern.sub("[REDACTED_EMAIL]", text)
        redacted_text = re.sub(self.secret_project, "[REDACTED_COMPANY_SECRET]", redacted_text, flags=re.IGNORECASE)
        
        has_sensitive = (redacted_text != text)
        
        if nlp:
            doc = nlp(redacted_text)
            for ent in doc.ents:
                if ent.label_ in ["PERSON", "ORG", "GPE", "LOC", "FAC"]:
                    redacted_text = redacted_text.replace(ent.text, f"[REDACTED_{ent.label_}]")
                    has_sensitive = True
                    
        return redacted_text, has_sensitive

# --- REPO 2 REFERENCE: AI Governance Framework (Risk & Ethics Agents) ---
class RiskMonitoringAgents:
    async def evaluate_ethics_and_bias(self, text):
        system_prompt = """Evaluate the user's input for bias, unethical behavior, or covert monitoring. 
        Strictly return a JSON object: {"is_ethical": boolean, "reason": "string"}."""
        
        fallback_keywords = ["monitor employees covertly", "bypass security", "steal data", "hack"]
        def check_fallback():
            if any(keyword in text.lower() for keyword in fallback_keywords):
                return False, "Offline Fallback: Unethical keywords detected while AI Ethics Agent is offline."
            return True, "Safe (Ollama fallback)"
            
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "http://127.0.0.1:11434/api/generate",
                    json={
                        "model": "llama3", # default ollama model assumption
                        "prompt": f"System: {system_prompt}\n\nUser: {text}",
                        "stream": False,
                        "format": "json"
                    },
                    timeout=60.0
                )
                if response.status_code == 200:
                    data = response.json().get("response", "")
                    parsed = json.loads(data)
                    
                    is_ethical = parsed.get("is_ethical", True)
                    # Correctly handle if the LLM hallucinated a string instead of a true boolean
                    if isinstance(is_ethical, str):
                        is_ethical = is_ethical.lower() != "false"
                        
                    return is_ethical, parsed.get("reason", "Safe")
                else:
                    return check_fallback()
        except Exception as e:
            print(f"Ollama error: {e}")
            return check_fallback()

guardrail = DataProtectionGuardrail()
agents = RiskMonitoringAgents()

class PromptRequest(BaseModel):
    user_id: str
    url: str
    text: str

class ToolRequest(BaseModel):
    url: str
    justification: str

class OutputRequest(BaseModel):
    prompt_id: int
    response_text: str

@app.post("/api/v1/evaluate-prompt")
async def evaluate_prompt(req: PromptRequest, db: Session = Depends(get_db)):
    # 1. Check ToolRegistry
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == req.url).first()
    
    if not tool or tool.status != "approved":
        status = "blocked_shadow_ai"
        log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status=status)
        db.add(log)
        db.commit()
        if not tool:
            new_tool = ToolRegistry(url=req.url, status="pending", justification="Auto-detected Shadow AI usage", clearance_level="PUBLIC")
            db.add(new_tool)
            db.commit()
            return {"status": "blocked", "reason": f"Tool at {req.url} is not registered. It has been flagged as Shadow AI and is pending IT review.", "safe_prompt": "", "prompt_id": log.id}
        elif tool.status == "pending":
            return {"status": "blocked", "reason": f"Tool at {req.url} is currently pending IT approval.", "safe_prompt": "", "prompt_id": log.id}
        else:
            return {"status": "blocked", "reason": f"Tool at {req.url} has been explicitly blocked by IT.", "safe_prompt": "", "prompt_id": log.id}

    # 2. Evaluate Ethics (Offline LLM)
    is_ethical, agent_reason = await agents.evaluate_ethics_and_bias(req.text)
    if not is_ethical:
        log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="blocked_ethics")
        db.add(log)
        db.commit()
        return {"status": "blocked", "reason": f"Ethics Agent: {agent_reason}", "safe_prompt": "", "prompt_id": log.id}

    # 3. Granular Data Routing
    safe_text, has_sensitive = guardrail.redact_prompt(req.text)
    
    if has_sensitive:
        if tool.clearance_level == "CONFIDENTIAL":
            # Tool is allowed to see sensitive data. Let it pass unredacted.
            log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="approved_confidential")
            db.add(log)
            db.commit()
            return {"status": "approved", "reason": "Passed all checks. Sensitive data allowed for CONFIDENTIAL tool.", "safe_prompt": req.text, "prompt_id": log.id}
        else:
            # Tool is PUBLIC. We must offer the redacted version.
            log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="redacted_data")
            db.add(log)
            db.commit()
            return {
                "status": "warning", 
                "reason": "Data Routing Guardrail: Sensitive enterprise data detected. This tool is only cleared for PUBLIC data. Please use the redacted prompt.", 
                "safe_prompt": safe_text,
                "prompt_id": log.id
            }

    # 4. Safe Public Prompt
    log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="approved")
    db.add(log)
    db.commit()

    return {
        "status": "approved", 
        "reason": "Passed all governance checks.", 
        "safe_prompt": req.text,
        "prompt_id": log.id
    }

@app.post("/api/v1/log-output")
async def log_output(req: OutputRequest, db: Session = Depends(get_db)):
    out_log = OutputLog(
        prompt_id=req.prompt_id,
        ai_response_text=req.response_text,
        timestamp=str(datetime.datetime.now())
    )
    db.add(out_log)
    db.commit()
    return {"message": "Output logged successfully"}

@app.get("/api/v1/get-output/{prompt_id}")
async def get_output(prompt_id: int, db: Session = Depends(get_db)):
    output = db.query(OutputLog).filter(OutputLog.prompt_id == prompt_id).first()
    if output:
        return {"response_text": output.ai_response_text}
    else:
        return {"response_text": "No output recorded for this prompt."}

@app.post("/api/v1/request-tool")
async def request_tool(req: ToolRequest, db: Session = Depends(get_db)):
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == req.url).first()
    if tool:
        return {"message": "Tool already exists in the registry.", "status": tool.status}
        
    new_tool = ToolRegistry(url=req.url, status="pending", justification=req.justification, clearance_level="PUBLIC")
    db.add(new_tool)
    db.commit()
    return {"message": "We have received your request to use this AI tool. The IT team will review it shortly."}

@app.post("/api/v1/update-tool-status")
async def update_tool_status(url: str = Form(...), status: str = Form(...), db: Session = Depends(get_db)):
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == url).first()
    if not tool:
        return {"error": "Tool not found"}
    tool.status = status
    db.commit()
    return {"message": "Successfully updated tool status"}

@app.get("/api/v1/check-tool")
async def check_tool(url: str, db: Session = Depends(get_db)):
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == url).first()
    if tool:
        return {"is_ai_tool": True, "status": tool.status}
        
    ai_keywords = ["chatgpt", "openai", "claude", "anthropic", "perplexity", "gemini", "poe", "huggingface", "copilot"]
    if any(keyword in url.lower() for keyword in ai_keywords):
        return {"is_ai_tool": True, "status": "unregistered"}
        
    return {"is_ai_tool": False}

@app.post("/api/v1/delete-tool")
async def delete_tool(url: str = Form(...), db: Session = Depends(get_db)):
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == url).first()
    if tool:
        db.delete(tool)
        db.commit()
    return {"message": "Tool deleted"}

@app.post("/api/v1/clear-tools")
async def clear_tools(db: Session = Depends(get_db)):
    db.query(ToolRegistry).delete()
    db.commit()
    return {"message": "All tools cleared"}

@app.post("/api/v1/delete-log")
async def delete_log(log_id: int = Form(...), db: Session = Depends(get_db)):
    log = db.query(AuditLog).filter(AuditLog.id == log_id).first()
    if log:
        db.delete(log)
        db.commit()
    return {"message": "Log deleted"}

@app.post("/api/v1/clear-logs")
async def clear_logs(db: Session = Depends(get_db)):
    db.query(AuditLog).delete()
    db.commit()
    return {"message": "All logs cleared"}

@app.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(50).all()
    tools = db.query(ToolRegistry).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "logs": logs, "tools": tools})