from fastapi import FastAPI
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import re
import datetime
import spacy

try:
    nlp = spacy.load("en_core_web_sm")
except OSError:
    # Fallback if the model hasn't been downloaded yet
    nlp = None

app = FastAPI(title="Enterprise AI Governance API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For hackathon purposes
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- REPO 3 REFERENCE: FINOS Approval Workflow & Tracking Dashboard ---
class ApprovalWorkflowHub:
    def __init__(self):
        self.audit_log = []
        # Simulate a database of approved/unapproved AI tools
        self.approved_tools = {
            "chatgpt.com": "approved",
            "claude.ai": "approved",
            "untrusted-ai.com": "blocked"
        }

    def track_usage(self, user_id, tool_url, prompt, status):
        log_entry = {
            "timestamp": str(datetime.datetime.now()),
            "user": user_id,
            "tool": tool_url,
            "status": status,
            "shadow_ai_flag": self.approved_tools.get(tool_url, "unknown") != "approved"
        }
        self.audit_log.append(log_entry)
        return log_entry["shadow_ai_flag"]

# --- REPO 1 REFERENCE: NeMo Guardrails (Data Protection) ---
class DataProtectionGuardrail:
    def __init__(self):
        # Regex for emails and specific company secrets
        self.pii_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        self.secret_project = "project titan"

    def redact_prompt(self, text):
        # 1. Regex fallback for emails and secrets
        redacted_text = self.pii_pattern.sub("[REDACTED_EMAIL]", text)
        redacted_text = re.sub(self.secret_project, "[REDACTED_COMPANY_SECRET]", redacted_text, flags=re.IGNORECASE)
        
        # 2. ML-based extraction using spaCy (if model is loaded)
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
        # Simulate SafetyControlAgent (Bias)
        if "hire only men" in text_lower or "filter out minorities" in text_lower:
            return False, "SafetyAgent: Prompt violates anti-discrimination policies."
        
        # Simulate EthicsAgent (Covert Monitoring - straight from case study)
        if "monitor employees covertly" in text_lower or "track keystrokes without telling" in text_lower:
            return False, "EthicsAgent: Covert employee monitoring violates enterprise ethical boundaries."
            
        return True, "Safe"

# --- Initialize Modules ---
tracker = ApprovalWorkflowHub()
guardrail = DataProtectionGuardrail()
agents = RiskMonitoringAgents()

class PromptRequest(BaseModel):
    user_id: str
    url: str
    text: str

@app.post("/api/v1/evaluate-prompt")
async def evaluate_prompt(req: PromptRequest):
    # 1. Track Shadow AI (FINOS Repo)
    is_shadow_ai = tracker.track_usage(req.user_id, req.url, req.text, "pending")
    if is_shadow_ai:
        return {"status": "blocked", "reason": f"Tool at {req.url} is not IT-approved.", "safe_prompt": ""}

    # 2. Evaluate Ethics and Bias (AI Gov Framework Repo)
    is_ethical, agent_reason = agents.evaluate_ethics_and_bias(req.text)
    if not is_ethical:
        tracker.track_usage(req.user_id, req.url, req.text, "blocked_ethics")
        return {"status": "blocked", "reason": agent_reason, "safe_prompt": ""}

    # 3. Data Protection and Redaction (NeMo Guardrails Repo)
    safe_text = guardrail.redact_prompt(req.text)
    
    if safe_text != req.text:
        tracker.track_usage(req.user_id, req.url, req.text, "redacted_data")
        return {
            "status": "warning", 
            "reason": "Data Leakage Guardrail: Sensitive enterprise data detected and redacted.", 
            "safe_prompt": safe_text
        }

    tracker.track_usage(req.user_id, req.url, req.text, "approved")
    return {"status": "approved", "reason": "Passed all governance checks.", "safe_prompt": req.text}

# Run with: uvicorn server:app --reload