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
        redacted_text = text
        triggers = []
        
        if self.pii_pattern.search(redacted_text):
            redacted_text = self.pii_pattern.sub("[REDACTED_EMAIL]", redacted_text)
            triggers.append("unencrypted client contact details")
            
        if re.search(self.secret_project, redacted_text, flags=re.IGNORECASE):
            redacted_text = re.sub(self.secret_project, "[REDACTED_COMPANY_SECRET]", redacted_text, flags=re.IGNORECASE)
            triggers.append("proprietary project code")
        
        if nlp:
            doc = nlp(redacted_text)
            for ent in doc.ents:
                if ent.label_ in ["PERSON", "ORG", "GPE", "LOC", "FAC"]:
                    redacted_text = redacted_text.replace(ent.text, f"[REDACTED_{ent.label_}]")
                    if "personally identifiable information" not in triggers:
                        triggers.append("personally identifiable information")
                    
        has_sensitive = len(triggers) > 0
        return redacted_text, has_sensitive, triggers

import hashlib
import chromadb
import joblib
import os

# --- REPO 2 REFERENCE: AI Governance Framework (Risk & Ethics Agents) ---
class RiskMonitoringAgents:
    def __init__(self):
        print("Loading custom ML Classifier and ChromaDB...")
        
        # Load the custom trained LinearSVC model
        model_path = os.path.join(os.path.dirname(__file__), "custom_ethics_model.joblib")
        if os.path.exists(model_path):
            self.classifier = joblib.load(model_path)
            print("Custom LinearSVC model loaded successfully.")
        else:
            print("WARNING: custom_ethics_model.joblib not found!")
            self.classifier = None
            
        self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
        self.cache_collection = self.chroma_client.get_or_create_collection(name="prompt_cache")
        
        # Pre-warm the cache to force ChromaDB to download the 79MB embedding model now
        # instead of freezing when the user sends their first prompt!
        print("Pre-warming Semantic Cache...")
        self.cache_collection.query(query_texts=["warmup"], n_results=1)
        print("ML infrastructure ready.")

    async def evaluate_ethics_and_bias(self, text):
        # 1. Semantic Caching
        results = self.cache_collection.query(
            query_texts=[text],
            n_results=1
        )
        
        # Check if we have a match and distance is small (meaning highly similar)
        if results and results['distances'] and len(results['distances'][0]) > 0:
            distance = results['distances'][0][0]
            if distance < 0.3: # L2 distance threshold for semantic similarity
                cached_metadata = results['metadatas'][0][0]
                is_ethical = cached_metadata['is_ethical'] == "true"
                reason = cached_metadata['reason']
                triggers = ["a semantic match to a previously blocked ethical violation"]
                return is_ethical, reason, triggers

        # 2. Fast Custom ML Classifier
        if self.classifier:
            prediction = self.classifier.predict([text])[0]
            if prediction != "safe corporate request":
                is_ethical = False
                reason = f"Custom ML Classifier blocked: '{prediction}'"
                
                # Map to human readable trigger
                if "surveillance" in prediction.lower() or "monitor" in prediction.lower():
                    triggers = ["covert employee surveillance keywords"]
                elif "bias" in prediction.lower():
                    triggers = ["discriminatory or biased language"]
                else:
                    triggers = [f"content flagged as {prediction}"]
            else:
                is_ethical = True
                reason = "Custom ML Classifier: Safe"
                triggers = []
        else:
            # Fallback if model failed to load
            is_ethical = True
            reason = "Safe (No ML Model Loaded)"
            triggers = []

        # 3. Store in Cache
        doc_id = hashlib.sha256(text.encode()).hexdigest()
        self.cache_collection.add(
            documents=[text],
            metadatas=[{"is_ethical": "true" if is_ethical else "false", "reason": reason}],
            ids=[doc_id]
        )
        
        return is_ethical, reason, triggers
        return is_ethical, reason
        return is_ethical, reason
        return is_ethical, reason
        return is_ethical, reason
        return is_ethical, reason
        return is_ethical, reason

guardrail = DataProtectionGuardrail()
agents = RiskMonitoringAgents()

class OutputExplainer:
    def __init__(self):
        print("Loading Heuristic Explainer Engine...")
        # A robust set of heuristics to accurately match the context of the LLM output
        self.patterns = {
            'rejection': {
                'keywords': ['reject', 'unfortunately', 'other candidates', 'careful consideration', 'not selected', 'future endeavors', 'regret to inform'],
                'intent': 'drafting a professional rejection communication',
                'analysis': 'The AI adopted a formal, polite tone anchoring on standard HR practices. It deliberately kept the reasoning generalized to minimize corporate liability while maintaining a respectful employer brand.'
            },
            'summary': {
                'keywords': ['summary', 'brief', 'overview', 'conclusion', 'key points', 'data', 'metrics', 'in short'],
                'intent': 'summarizing internal data or discussions',
                'analysis': 'The AI structured the output to highlight key metrics and actionable takeaways. It omitted granular data points to ensure the summary remains concise and easily digestible for executive review.'
            },
            'code': {
                'keywords': ['def ', 'import ', 'function', 'class ', 'return', 'script', 'const ', 'let ', 'var '],
                'intent': 'generating technical code or scripts',
                'analysis': 'The AI generated functional programming constructs. It focused on syntactical correctness and standard engineering paradigms while ensuring the code aligns with standard software practices.'
            },
            'instructions': {
                'keywords': ['step 1', 'first', 'then', 'finally', 'how to', 'guide', 'instructions', 'ensure that'],
                'intent': 'providing technical or procedural instructions',
                'analysis': 'The AI broke down the requested task into a sequential, actionable guide. It prioritized clarity and logical flow to ensure the user can follow the steps without ambiguity.'
            }
        }
        print("Heuristic Explainer Engine loaded.")
        
    def explain(self, text):
        text_lower = text.lower()
        matched_category = None
        max_matches = 0
        
        for cat, data in self.patterns.items():
            matches = sum(1 for kw in data['keywords'] if kw in text_lower)
            if matches > max_matches:
                max_matches = matches
                matched_category = cat
                
        if matched_category:
            intent = self.patterns[matched_category]['intent']
            analysis = self.patterns[matched_category]['analysis']
        else:
            intent = 'general professional assistance'
            analysis = 'The AI processed the request using standard corporate communication protocols. It focused on delivering clear, neutral, and actionable information tailored to the prompt.'
            
        return f"Governance Analysis: The intent of the AI's response was categorized as '{intent}'.\n\nDetailed Reasoning: {analysis}"

explainer_agent = OutputExplainer()

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

class ExplainRequest(BaseModel):
    text: str

def generate_plain_explanation(action, triggers):
    if not triggers:
        return f"This request was {action}."
    
    if len(triggers) == 1:
        trigger_str = triggers[0]
    elif len(triggers) == 2:
        trigger_str = f"{triggers[0]} and {triggers[1]}"
    else:
        trigger_str = ", ".join(triggers[:-1]) + f", and {triggers[-1]}"
        
    return f"This request was {action} because it contained {trigger_str}."

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
    is_ethical, agent_reason, ethics_triggers = await agents.evaluate_ethics_and_bias(req.text)
    if not is_ethical:
        log = AuditLog(timestamp=str(datetime.datetime.now()), user_id=req.user_id, url=req.url, prompt_text=req.text, status="blocked_ethics")
        db.add(log)
        db.commit()
        
        nlg_reason = generate_plain_explanation("blocked", ethics_triggers)
        return {"status": "blocked", "reason": nlg_reason, "safe_prompt": "", "prompt_id": log.id}

    # 3. Granular Data Routing
    safe_text, has_sensitive, data_triggers = guardrail.redact_prompt(req.text)
    
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
            
            nlg_reason = generate_plain_explanation("altered", data_triggers)
            return {
                "status": "warning", 
                "reason": nlg_reason, 
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

@app.post("/api/v1/explain-output")
async def explain_output_endpoint(req: ExplainRequest):
    explanation = explainer_agent.explain(req.text)
    return {"explanation": explanation}

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