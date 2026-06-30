"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ChatPanel = void 0;
/**
 * aiPlat Chat Panel — WebView side panel with SSE streaming chat.
 *
 * Features:
 *   - SSE streaming from backend
 *   - Code block detection and apply buttons
 *   - Markdown rendering for agent responses
 *   - Implicit feedback tracking (Phase 4.2)
 */
const vscode = __importStar(require("vscode"));
class ChatPanel {
    static currentPanel;
    _panel;
    _disposables = [];
    _baseUrl;
    _lastCodeBlock = '';
    static createOrShow(extensionUri, baseUrl) {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;
        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel._panel.reveal(column);
            return;
        }
        const panel = vscode.window.createWebviewPanel('aiplatChat', 'aiPlat Agent', column || vscode.ViewColumn.Two, {
            enableScripts: true,
            retainContextWhenHidden: true,
        });
        ChatPanel.currentPanel = new ChatPanel(panel, extensionUri, baseUrl);
    }
    constructor(panel, extensionUri, baseUrl) {
        this._panel = panel;
        this._baseUrl = baseUrl;
        this._panel.webview.html = this._getHtml(extensionUri);
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
        this._panel.webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'sendToAgent':
                    await this._handleAgentQuery(message.text);
                    break;
                case 'getCodeBlock':
                    this._sendCodeBlock();
                    break;
                case 'applyCode':
                    this._applyToEditor(message.code);
                    break;
                case 'implicitFeedback':
                    this._sendImplicitFeedback(message.type, message.runId || '');
                    break;
            }
        }, null, this._disposables);
    }
    sendMessage(text) {
        this._panel.webview.postMessage({ command: 'userPrompt', text });
    }
    applyLastSuggestion() {
        if (this._lastCodeBlock) {
            this._applyToEditor(this._lastCodeBlock);
        }
        else {
            this._panel.webview.postMessage({ command: 'getCodeBlock' });
        }
    }
    _applyToEditor(code) {
        const editor = vscode.window.activeTextEditor;
        if (!editor || !code) {
            vscode.window.showWarningMessage('No active editor or no code to apply.');
            return;
        }
        editor.edit((editBuilder) => {
            const selection = editor.selection;
            if (selection && !selection.isEmpty) {
                editBuilder.replace(selection, code);
            }
            else {
                editBuilder.insert(editor.selection.active, code);
            }
        });
        vscode.window.showInformationMessage('Code applied to editor.');
    }
    async _handleAgentQuery(text) {
        try {
            const config = vscode.workspace.getConfiguration('aiplat');
            const base = this._baseUrl.replace(/\/$/, '');
            const response = await fetch(`${base}/api/core/knowledge-graph/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ question: text, history: [] }),
            });
            if (!response.ok) {
                this._postToWebview('agentError', `HTTP ${response.status}`);
                return;
            }
            const reader = response.body?.getReader();
            if (!reader) {
                this._postToWebview('agentError', 'No response stream');
                return;
            }
            const decoder = new TextDecoder();
            let buffer = '';
            let fullResponse = '';
            while (true) {
                const { done, value } = await reader.read();
                if (done)
                    break;
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop() || '';
                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        const payload = line.slice(6).trim();
                        if (payload === '[DONE]')
                            break;
                        try {
                            const parsed = JSON.parse(payload);
                            const token = parsed.token || '';
                            if (token) {
                                fullResponse += token;
                            }
                        }
                        catch {
                            // Skip non-JSON lines
                        }
                        if (payload === '[DONE]')
                            break;
                    }
                }
            }
            if (fullResponse) {
                this._postToWebview('agentResponse', fullResponse);
                this._lastCodeBlock = fullResponse;
            }
            else {
                this._postToWebview('agentResponse', '(No response from agent)');
            }
        }
        catch (e) {
            this._postToWebview('agentError', `Connection failed: ${e.message}`);
        }
    }
    _sendCodeBlock() {
        if (this._lastCodeBlock) {
            this._panel.webview.postMessage({ command: 'codeBlock', text: this._lastCodeBlock });
        }
    }
    _postToWebview(command, text) {
        this._panel.webview.postMessage({ command, text });
    }
    async _sendImplicitFeedback(signalType, runId) {
        if (!signalType || !runId)
            return;
        try {
            await fetch(`${this._baseUrl}/api/core/feedback/implicit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    run_id: runId,
                    signal_type: signalType,
                    session_id: 'vscode',
                }),
            });
        }
        catch {
            // Silently ignore — feedback is best-effort
        }
    }
    dispose() {
        ChatPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d)
                d.dispose();
        }
    }
    _getHtml(extensionUri) {
        return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>aiPlat Agent</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: #0f172a; color: #e2e8f0;
            display: flex; flex-direction: column; height: 100vh;
        }
        #messages {
            flex: 1; overflow-y: auto; padding: 12px;
            display: flex; flex-direction: column; gap: 8px;
        }
        .msg { padding: 8px 12px; border-radius: 8px; max-width: 90%; font-size: 13px; line-height: 1.5; overflow-wrap: break-word; }
        .msg.user { background: #1e40af; align-self: flex-end; color: #bfdbfe; }
        .msg.agent { background: #1e293b; align-self: flex-start; color: #e2e8f0; border: 1px solid #334155; }
        .msg.error { background: #7f1d1d; align-self: flex-start; color: #fca5a5; border: 1px solid #991b1b; }
        .msg.agent pre {
            background: #0f172a; padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 4px;
            position: relative;
        }
        .msg.agent code { font-family: 'Fira Code', 'Cascadia Code', monospace; font-size: 12px; }
        .msg.agent p { margin: 4px 0; }
        .apply-btn {
            background: #22c55e; color: white; border: none; border-radius: 4px;
            padding: 2px 8px; cursor: pointer; font-size: 11px; float: right; margin-left: 8px;
        }
        .apply-btn:hover { background: #16a34a; }
        #input-area {
            display: flex; padding: 8px; border-top: 1px solid #334155; gap: 8px;
        }
        #input {
            flex: 1; background: #1e293b; border: 1px solid #334155; border-radius: 8px;
            padding: 8px 12px; color: #e2e8f0; font-size: 13px; outline: none;
        }
        #input:focus { border-color: #3b82f6; }
        #send {
            background: #3b82f6; color: white; border: none; border-radius: 8px;
            padding: 8px 16px; cursor: pointer; font-size: 13px; font-weight: 600;
        }
        #send:hover { background: #2563eb; }
        #send:disabled { background: #475569; cursor: not-allowed; }
        .header {
            padding: 8px 12px; border-bottom: 1px solid #334155;
            font-size: 13px; font-weight: 600; color: #94a3b8;
            display: flex; align-items: center; justify-content: space-between;
        }
        .status { font-size: 11px; color: #22c55e; }
        .status.error { color: #ef4444; }
    </style>
</head>
<body>
    <div class="header">
        <span>aiPlat Agent</span>
        <span class="status" id="status">Connected</span>
    </div>
    <div id="messages">
        <div class="msg agent">Hello! I'm aiPlat Agent. Ask a question or send code to analyze.</div>
    </div>
    <div id="input-area">
        <input id="input" type="text" placeholder="Ask aiPlat..." onkeydown="if(event.key==='Enter')send()" autofocus />
        <button id="send" onclick="send()">Send</button>
    </div>
    <script>
        const vscode = acquireVsCodeApi();
        const msgs = document.getElementById('messages');
        const input = document.getElementById('input');
        const sendBtn = document.getElementById('send');
        const status = document.getElementById('status');

        function addMessage(text, role) {
            const div = document.createElement('div');
            div.className = 'msg ' + role;
            // Basic markdown: wrap code blocks
            if (role === 'agent' && text.includes('\`\`\`')) {
                let html = text
                    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
                    .replace(/\`\`\`([^\\s]*)\\n([\\s\\S]*?)\`\`\`/g, function(m, lang, code) {
                        return '<pre><button class="apply-btn" onclick="applyCode(this)" data-code="' + escapeHtml(code) + '">Apply</button><code>' + code + '</code></pre>';
                    })
                    .replace(/\\n/g, '<br>')
                    .replace(/\`([^\`]+)\`/g, '<code>$1</code>');
                div.innerHTML = html;
            } else {
                div.textContent = text;
            }
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }

        function escapeHtml(text) {
            return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#039;');
        }

        function applyCode(btn) {
            const code = btn.getAttribute('data-code') || '';
            vscode.postMessage({ command: 'applyCode', code });
        }

        let waiting = false;

        function send() {
            const text = input.value.trim();
            if (!text || waiting) return;
            addMessage(text, 'user');
            input.value = '';
            waiting = true;
            sendBtn.disabled = true;
            status.textContent = 'Thinking...';
            status.className = 'status';
            vscode.postMessage({ command: 'sendToAgent', text });
        }

        window.addEventListener('message', (event) => {
            const msg = event.data;
            switch (msg.command) {
                case 'userPrompt':
                    addMessage(msg.text, 'user');
                    break;
                case 'agentResponse':
                    addMessage(msg.text, 'agent');
                    waiting = false;
                    sendBtn.disabled = false;
                    status.textContent = 'Connected';
                    status.className = 'status';
                    input.focus();
                    break;
                case 'agentError':
                    addMessage(msg.text, 'error');
                    waiting = false;
                    sendBtn.disabled = false;
                    status.textContent = 'Error';
                    status.className = 'status error';
                    input.focus();
                    break;
                case 'getCodeBlock':
                    // Send last code block to extension
                    const blocks = document.querySelectorAll('pre code');
                    if (blocks.length > 0) {
                        const last = blocks[blocks.length - 1];
                        vscode.postMessage({ command: 'codeBlock', text: last.textContent || '' });
                    }
                    break;
            }
        });

        // Implicit Feedback (Phase 4.2)
        let _lastCopyTime = 0;
        document.addEventListener('copy', () => {
            const now = Date.now();
            if (now - _lastCopyTime < 2000) return;
            _lastCopyTime = now;
            const selected = window.getSelection()?.toString() || '';
            if (selected.length > 20) {
                const signalType = selected.length > 100 ? 'copy_full' : 'select_text';
                vscode.postMessage({ command: 'implicitFeedback', type: signalType, runId: '' });
            }
        });
    </script>
</body>
</html>`;
    }
}
exports.ChatPanel = ChatPanel;
//# sourceMappingURL=chatPanel.js.map