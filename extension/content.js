// Function to create a stylish popup modal
function showGovernanceModal(title, message, safePrompt, chatInput) {
    const modal = document.createElement("div");
    modal.style.cssText = `
        position: fixed; top: 20px; right: 20px; z-index: 999999;
        background: #1e1e2f; color: white; padding: 20px; border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3); border-left: 5px solid #ff4757;
        font-family: sans-serif; width: 350px;
    `;
    modal.innerHTML = `
        <h3 style="margin-top: 0; color: #ff4757;">${title}</h3>
        <p style="font-size: 14px;">${message}</p>
        <p style="font-size: 12px; color: #a4b0be; margin-bottom: 5px;">Suggested Safe Prompt:</p>
        <div style="background: #2f3542; padding: 10px; border-radius: 4px; font-size: 13px; font-style: italic;">
            ${safePrompt}
        </div>
        <button id="acceptSafePrompt" style="margin-top: 15px; padding: 8px 12px; background: #2ed573; border: none; border-radius: 4px; color: white; cursor: pointer; font-weight: bold;">
            Accept & Send
        </button>
        <button id="appealDecision" style="margin-top: 15px; margin-left: 10px; padding: 8px 12px; background: #747d8c; border: none; border-radius: 4px; color: white; cursor: pointer;">
            Appeal to Admin
        </button>
    `;
    document.body.appendChild(modal);

    // If user clicks Accept, replace text and close modal
    document.getElementById("acceptSafePrompt").addEventListener("click", () => {
        if (chatInput.value !== undefined) {
            chatInput.value = safePrompt;
        } else {
            // It's a contenteditable div, so we must set innerText and also create an input event to notify React
            chatInput.innerText = safePrompt;
            chatInput.dispatchEvent(new Event('input', { bubbles: true }));
        }
        modal.remove();
        // Give the user a brief visual cue before they can hit enter again
        chatInput.style.border = "2px solid #2ed573";
        setTimeout(() => chatInput.style.border = "", 2000);
    });

    // Handle Human-in-the-loop Redressal Requirement
    document.getElementById("appealDecision").addEventListener("click", () => {
        alert("Sent to Human Auditor. Your HumanCollaborationAgent workflow has been triggered.");
        modal.remove();
    });
}

// Listen for "Enter" key on the ChatGPT chatbox
document.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey) {
        // ChatGPT uses a div with id="prompt-textarea" now, but fallback to textarea just in case
        const chatInput = document.querySelector('#prompt-textarea') || document.querySelector('textarea');

        if (chatInput && (document.activeElement === chatInput || chatInput.contains(document.activeElement))) {
            const promptText = chatInput.value !== undefined ? chatInput.value : chatInput.innerText;

            if (promptText.trim().length > 0) {
                event.preventDefault(); // Stop prompt from sending
                event.stopPropagation();

                if (chatInput.tagName.toLowerCase() === 'textarea') {
                    chatInput.disabled = true;
                } else {
                    chatInput.setAttribute('contenteditable', 'false');
                }

                chrome.runtime.sendMessage({ action: "evaluatePrompt", text: promptText }, function (response) {
                    if (chatInput.tagName.toLowerCase() === 'textarea') {
                        chatInput.disabled = false;
                    } else {
                        chatInput.setAttribute('contenteditable', 'true');
                        chatInput.focus();
                    }

                    if (response.status === "warning" || response.status === "blocked") {
                        showGovernanceModal("🛑 Policy Violation", response.reason, response.safe_prompt, chatInput);
                    } else if (response.status === "approved") {
                        // Let it pass
                        if (chatInput.value !== undefined) {
                            chatInput.value = promptText;
                        } else {
                            chatInput.innerText = promptText;
                        }
                        chatInput.style.border = "2px solid #1dd1a1";
                        alert("✅ Prompt Approved by Governance Engine.");
                    }
                });
            }
        }
    }
}, true); // Capture phase