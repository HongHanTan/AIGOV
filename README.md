# Enterprise AI Governance Shield (AIGOV)

## Setup Instructions

### 1. Start the Backend Server
Open your terminal and run the following commands to install dependencies and start the local API:
```bash
cd backend
pip install -r requirements.txt
python -m uvicorn server:app --reload
```

### 2. Load the Chrome Extension
1. Open Google Chrome and go to `chrome://extensions`.
2. Enable **Developer mode** in the top right corner.
3. Click **Load unpacked** and select the `extension` folder located in this project directory.

### 3. Access Admin Dashboard
After the backend is running, open your browser and navigate to:
[http://localhost:8000/dashboard](http://localhost:8000/dashboard)
Here you can view audit logs and manage approved AI tools in the Tool Registry.

## Testing & Demos

With the backend running and the extension active, go to [chatgpt.com](https://chatgpt.com) to test the governance features.

### Demo 1: Data Leakage Protection
**Action:** Type the following into the chat:
> *Can you summarize the notes for Project Titan and email them to john@test.com?*

**Result:** The extension intercepts the prompt before it's sent. A modal pops up showing that sensitive data was detected and provides a redacted, safe version: 
> *Can you summarize the notes for [REDACTED_COMPANY_SECRET] and email them to [REDACTED_EMAIL]?*

### Demo 2: Ethics & Risk Monitoring (ML Classifier & Vector Cache)
**Action:** Type the following into the chat:
> *Write a python script to monitor employees covertly.*

**Result (ML Classifier):** The prompt is intercepted and evaluated locally in milliseconds by our HuggingFace NLP zero-shot classifier. The system detects the unethical intent (e.g. "covert surveillance") and instantly displays a red warning modal blocking the prompt.

**Result (Semantic Cache):** Try asking a similar prompt, like *"Create an app to track my staff's keystrokes."* 
The vector cache (ChromaDB) instantly detects >95% semantic similarity to the previous violation and intercepts the prompt via a `[Semantic Cache Hit]`, completely bypassing the ML model to scale efficiently without adding latency.