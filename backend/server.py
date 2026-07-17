from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import re
import datetime
import spacy

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
    allow_origins=["*"], # For hackathon purposes
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
        
        if nlp:
            doc = nlp(redacted_text)
            for ent in doc.ents:
                if ent.label_ in ["PERSON", "ORG", "GPE", "LOC", "FAC"]:
                    redacted_text = redacted_text.replace(ent.text, f"[REDACTED_{ent.label_}]")
                    
        return redacted_text

# --- REPO 2 REFERENCE: AI Governance Framework (Risk & Ethics Agents) ---
class RiskMonitoringAgents:
    def evaluate_ethics_and_bias(self, text):
        text_lower = text.lower()
        if "hire only men" in text_lower or "filter out minorities" in text_lower:
            return False, "SafetyAgent: Prompt violates anti-discrimination policies."
        if "monitor employees covertly" in text_lower or "track keystrokes without telling" in text_lower:
            return False, "EthicsAgent: Covert employee monitoring violates enterprise ethical boundaries."
        return True, "Safe"

guardrail = DataProtectionGuardrail()
agents = RiskMonitoringAgents()

class PromptRequest(BaseModel):
    user_id: str
    url: str
    text: str

class ToolRequest(BaseModel):
    url: str
    justification: str

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
            # Auto-register the shadow AI tool so it appears on the admin dashboard
            new_tool = ToolRegistry(url=req.url, status="pending", justification="Auto-detected Shadow AI usage")
            db.add(new_tool)
            db.commit()
            return {"status": "blocked", "reason": f"Tool at {req.url} is not registered. It has been flagged as Shadow AI and is pending IT review.", "safe_prompt": ""}
        elif tool.status == "pending":
            return {"status": "blocked", "reason": f"Tool at {req.url} is currently pending IT approval.", "safe_prompt": ""}
        else:
            return {"status": "blocked", "reason": f"Tool at {req.url} has been explicitly blocked by IT.", "safe_prompt": ""}

    # 2. Evaluate Ethics
    is_ethical, agent_reason = agents.evaluate_ethics_and_bias(req.text)
    if not is_ethical:
        log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="blocked_ethics")
        db.add(log)
        db.commit()
        return {"status": "blocked", "reason": agent_reason, "safe_prompt": ""}

    # 3. Data Protection
    safe_text = guardrail.redact_prompt(req.text)
    
    if safe_text != req.text:
        log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="redacted_data")
        db.add(log)
        db.commit()
        return {
            "status": "warning", 
            "reason": "Data Leakage Guardrail: Sensitive enterprise data detected and redacted.", 
            "safe_prompt": safe_text
        }

    log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="approved")
    db.add(log)
    db.commit()
    return {"status": "approved", "reason": "Passed all governance checks.", "safe_prompt": req.text}

@app.post("/api/v1/request-tool")
async def request_tool(req: ToolRequest, db: Session = Depends(get_db)):
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == req.url).first()
    if tool:
        return {"message": "Tool already exists in the registry.", "status": tool.status}
        
    new_tool = ToolRegistry(url=req.url, status="pending", justification=req.justification)
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
    # 1. Check explicit registry
    tool = db.query(ToolRegistry).filter(ToolRegistry.url == url).first()
    if tool:
        return {"is_ai_tool": True, "status": tool.status}
        
    # 2. Heuristic check for common AI domains to catch Shadow AI dynamically
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