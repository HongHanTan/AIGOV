chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "evaluatePrompt") {
        // Send the intercepted prompt to your local FastAPI Governance Engine
        fetch("http://localhost:8000/api/v1/evaluate-prompt", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                user_id: "emp_1042", // Mock employee ID
                url: new URL(sender.tab.url).hostname,
                text: request.text
            })
        })
            .then(response => response.json())
            .then(data => sendResponse(data))
            .catch(error => sendResponse({ status: "error", reason: "Governance API unreachable." }));

        return true; // Keep channel open for async fetch
    }
});