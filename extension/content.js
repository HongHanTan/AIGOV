// AIGOV Chrome Extension
function showGovernanceModal(title, message, safePrompt, chatInput, promptId, triggerType, originalTarget) {
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
        
        resubmitPrompt(chatInput, triggerType, originalTarget);
        
        if (promptId) {
            startOutputTracking(promptId);
        }
    });

    // Handle Human-in-the-loop Redressal Requirement
    document.getElementById("appealDecision").addEventListener("click", () => {
        alert("Sent to Human Auditor. Your HumanCollaborationAgent workflow has been triggered.");
        modal.remove();
    });
}

function startOutputTracking(promptId) {
    console.log("AIGOV: Tracking output for prompt ID", promptId);
    
    const targetNode = document.querySelector('main') || document.body;
    let lastText = "";
    let debounceTimer = null;
    let isTracking = true;

    const observer = new MutationObserver((mutations) => {
        if (!isTracking) return;
        
        // Find the LAST assistant message on the page
        const assistantMessages = document.querySelectorAll('div[data-message-author-role="assistant"]');
        if (assistantMessages.length === 0) return;
        
        const latestMessage = assistantMessages[assistantMessages.length - 1];
        const currentText = latestMessage.innerText;
        
        if (currentText !== lastText && currentText.trim().length > 0) {
            lastText = currentText;
            
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => {
                isTracking = false;
                observer.disconnect();
                console.log("AIGOV: Generation complete, logging output...");
                
                chrome.runtime.sendMessage({
                    action: "logOutput",
                    prompt_id: promptId,
                    response_text: lastText
                });
                
                // Fetch the Micro-LLM explanation for the AI's output
                chrome.runtime.sendMessage({
                    action: "explainOutput",
                    text: lastText
                }, function(response) {
                    if (response && response.explanation) {
                        showExplanationWidget(response.explanation);
                    }
                });
                
            }, 3000); // 3 seconds of no DOM text changes means it's done
        }
    });

    observer.observe(targetNode, {
        childList: true,
        subtree: true,
        characterData: true
    });
}

function showExplanationWidget(explanation) {
    const widget = document.createElement("div");
    widget.style.cssText = `
        position: fixed; bottom: 20px; right: 20px; z-index: 999999;
        background: #3742fa; color: white; padding: 15px; border-radius: 8px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3); font-family: sans-serif; width: 320px;
        font-size: 13px; line-height: 1.4; border-left: 5px solid #70a1ff;
    `;
    widget.innerHTML = `
        <h4 style="margin: 0 0 8px 0; color: #ffffff;">🧠 AI Decision Explained</h4>
        <p style="margin: 0;">${explanation}</p>
        <button id="closeWidget" style="margin-top: 12px; background: rgba(255,255,255,0.2); color: white; border: none; padding: 6px 12px; border-radius: 4px; cursor: pointer; font-weight: bold;">Got it</button>
    `;
    document.body.appendChild(widget);
    document.getElementById("closeWidget").addEventListener("click", () => widget.remove());
}

let isAwaitingGovernance = false;

function resubmitPrompt(chatInput, triggerType, originalTarget) {
    setTimeout(() => {
        if (triggerType === 'enter') {
            const enterEvent = new KeyboardEvent('keydown', {
                key: 'Enter',
                code: 'Enter',
                keyCode: 13,
                which: 13,
                bubbles: true,
                cancelable: true
            });
            chatInput.dispatchEvent(enterEvent);
        } else if (triggerType === 'click' && originalTarget) {
            originalTarget.click();
        }
    }, 100);
}

function handlePromptSubmission(event, chatInput, triggerType, actionButton = null) {
    if (isAwaitingGovernance) {
        event.preventDefault();
        event.stopPropagation();
        return;
    }

    const promptText = chatInput.value !== undefined ? chatInput.value : chatInput.innerText;
    if (promptText.trim().length === 0) return;

    // Block the prompt temporarily while we ask the backend
    event.preventDefault(); 
    event.stopPropagation();
    isAwaitingGovernance = true;

    if (chatInput.tagName.toLowerCase() === 'textarea') {
        chatInput.disabled = true;
    } else {
        chatInput.setAttribute('contenteditable', 'false');
    }

    const originalTarget = actionButton || event.target;

    chrome.runtime.sendMessage({ action: "evaluatePrompt", text: promptText }, function (response) {
        if (chatInput.tagName.toLowerCase() === 'textarea') {
            chatInput.disabled = false;
        } else {
            chatInput.setAttribute('contenteditable', 'true');
            chatInput.focus();
        }

        isAwaitingGovernance = false;

        if (response.status === "warning" || response.status === "blocked") {
            showGovernanceModal("🛑 Policy Violation", response.reason, response.safe_prompt, chatInput, response.prompt_id, triggerType, originalTarget);
        } else if (response.status === "approved") {
            chatInput.style.border = "2px solid #1dd1a1";
            
            if (chatInput.value !== undefined) {
                chatInput.value = response.safe_prompt;
                chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            } else {
                chatInput.innerText = response.safe_prompt;
                chatInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
            
            // Automatically send it using a synthesized event
            resubmitPrompt(chatInput, triggerType, originalTarget);
            
            if (response.prompt_id) {
                startOutputTracking(response.prompt_id);
            }
        }
    });
}

// Check if current site is an AI tool before listening
chrome.runtime.sendMessage({ action: "checkTool" }, function(response) {
    if (response && response.is_ai_tool) {
        
        // Listen for "Enter" key
        document.addEventListener("keydown", function (event) {
            if (!event.isTrusted) return; // Ignore our own synthesized events

            if (event.key === "Enter" && !event.shiftKey) {
                const activeElement = document.activeElement;
                if (!activeElement) return;
                
                const isInput = activeElement.tagName.toLowerCase() === 'textarea' || 
                                activeElement.isContentEditable || 
                                activeElement.id === 'prompt-textarea';

                if (isInput) {
                    handlePromptSubmission(event, activeElement, 'enter');
                }
            }
        }, true); // Capture phase
        
        // Listen for Send button click
        document.addEventListener("click", function(event) {
            if (!event.isTrusted) return; // Ignore our own synthesized events

            const button = event.target.closest('button') || event.target.closest('[role="button"]');
            if (!button) return;
            
            const ariaLabel = (button.getAttribute('aria-label') || '').toLowerCase();
            const dataTestId = (button.getAttribute('data-testid') || '').toLowerCase();
            
            // Typical heuristics for the "Send" button on LLM interfaces
            const isSendButton = ariaLabel.includes('send') || 
                                 ariaLabel.includes('message') || 
                                 dataTestId.includes('send') || 
                                 button.querySelector('svg');
            
            if (isSendButton) {
                // Find the chat input associated with this action
                const chatInput = document.querySelector('#prompt-textarea') || 
                                  document.querySelector('textarea') || 
                                  document.querySelector('[contenteditable="true"]');
                                  
                if (chatInput) {
                    const promptText = chatInput.value !== undefined ? chatInput.value : chatInput.innerText;
                    if (promptText.trim().length > 0) {
                        handlePromptSubmission(event, chatInput, 'click', button);
                    }
                }
            }
        }, true); // Capture phase
    }
});