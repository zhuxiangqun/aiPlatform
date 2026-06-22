/**
 * aiPlat Chat Panel — WebView side panel for SSE streaming chat.
 */

import * as vscode from 'vscode';

export class ChatPanel {
    public static currentPanel: ChatPanel | undefined;
    private readonly _panel: vscode.WebviewPanel;
    private _disposables: vscode.Disposable[] = [];
    private _baseUrl: string;

    public static createOrShow(extensionUri: vscode.Uri, baseUrl: string) {
        const column = vscode.window.activeTextEditor
            ? vscode.window.activeTextEditor.viewColumn
            : undefined;

        if (ChatPanel.currentPanel) {
            ChatPanel.currentPanel._panel.reveal(column);
            return;
        }

        const panel = vscode.window.createWebviewPanel(
            'aiplatChat',
            'aiPlat Agent',
            column || vscode.ViewColumn.Two,
            {
                enableScripts: true,
                retainContextWhenHidden: true,
            }
        );

        ChatPanel.currentPanel = new ChatPanel(panel, extensionUri, baseUrl);
    }

    private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri, baseUrl: string) {
        this._panel = panel;
        this._baseUrl = baseUrl;

        this._panel.webview.html = this._getHtml(extensionUri);
        this._panel.onDidDispose(() => this.dispose(), null, this._disposables);

        // Handle messages from webview
        this._panel.webview.onDidReceiveMessage(
            async (message) => {
                switch (message.command) {
                    case 'sendToAgent':
                        const response = await this._callAgent(message.text);
                        this._panel.webview.postMessage({
                            command: 'agentResponse',
                            text: response,
                        });
                        break;
                    case 'applyFix':
                        this.applyLastSuggestion();
                        break;
                    case 'implicitFeedback':
                        // Phase 4.2: Forward implicit feedback to server
                        this._sendImplicitFeedback(message.type, message.runId);
                        break;
                }
            },
            null,
            this._disposables
        );
    }

    public sendMessage(text: string) {
        this._panel.webview.postMessage({ command: 'sendToAgent', text });
    }

    public applyLastSuggestion() {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;

        // The webview sends the code block content back
        this._panel.webview.postMessage({ command: 'getCodeBlock' });
        this._panel.webview.onDidReceiveMessage(
            (msg) => {
                if (msg.command === 'codeBlock' && msg.text && editor) {
                    editor.edit((editBuilder) => {
                        editBuilder.replace(editor.selection, msg.text);
                    });
                }
            },
            null,
            this._disposables
        );
    }

    private async _callAgent(text: string): Promise<string> {
        try {
            const config = vscode.workspace.getConfiguration('aiplat');
            const model = config.get<string>('model') || 'qwen2.5-coder:7b';

            // SSE streaming to core
            const response = await fetch(`${this._baseUrl}/api/core/knowledge-graph/ask`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    question: text,
                    options: { stream: false, max_tokens: 2000 },
                }),
            });
            
            if (!response.ok) {
                return `Error: HTTP ${response.status}`;
            }
            
            const data = await response.json() as any;
            return data.answer || data.output?.answer || JSON.stringify(data);
        } catch (e: any) {
            return `Error: ${e.message || 'Connection failed'}`;
        }
    }

    private async _sendImplicitFeedback(signalType: string, runId: string): Promise<void> {
        /** Phase 4.2: Send implicit user feedback to backend */
        if (!signalType || !runId) return;
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
        } catch {
            // Silently ignore — feedback is best-effort
        }
    }

    public dispose() {
        ChatPanel.currentPanel = undefined;
        this._panel.dispose();
        while (this._disposables.length) {
            const d = this._disposables.pop();
            if (d) d.dispose();
        }
    }

    private _getHtml(extensionUri: vscode.Uri): string {
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
        .msg { padding: 8px 12px; border-radius: 8px; max-width: 85%; font-size: 13px; line-height: 1.5; }
        .msg.user { background: #1e40af; align-self: flex-end; color: #bfdbfe; }
        .msg.agent { background: #1e293b; align-self: flex-start; color: #e2e8f0; border: 1px solid #334155; }
        .msg.agent pre { background: #0f172a; padding: 8px; border-radius: 4px; overflow-x: auto; margin-top: 4px; }
        .msg.agent code { font-family: 'Fira Code', monospace; font-size: 12px; }
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
        .header {
            padding: 8px 12px; border-bottom: 1px solid #334155;
            font-size: 13px; font-weight: 600; color: #94a3b8;
            display: flex; align-items: center; justify-content: space-between;
        }
        .status { font-size: 11px; color: #22c55e; }
        .apply-btn {
            background: #22c55e; color: white; border: none; border-radius: 4px;
            padding: 2px 8px; cursor: pointer; font-size: 11px; margin-top: 4px;
        }
        .apply-btn:hover { background: #16a34a; }
    </style>
</head>
<body>
    <div class="header">
        <span>🤖 aiPlat Agent</span>
        <span class="status">● Connected</span>
    </div>
    <div id="messages">
        <div class="msg agent">Hello! I'm aiPlat Agent. Send me code or ask a question.</div>
    </div>
    <div id="input-area">
        <input id="input" type="text" placeholder="Ask aiPlat..." onkeydown="if(event.key==='Enter')send()" />
        <button id="send" onclick="send()">Send</button>
    </div>
    <script>
        const vscode = acquireVsCodeApi();
        const msgs = document.getElementById('messages');
        const input = document.getElementById('input');

        function addMessage(text, role) {
            const div = document.createElement('div');
            div.className = 'msg ' + role;
            div.textContent = text;
            msgs.appendChild(div);
            msgs.scrollTop = msgs.scrollHeight;
        }

        function send() {
            const text = input.value.trim();
            if (!text) return;
            addMessage(text, 'user');
            input.value = '';
            vscode.postMessage({ command: 'sendToAgent', text });
        }

        window.addEventListener('message', (event) => {
            const msg = event.data;
            if (msg.command === 'agentResponse') {
                addMessage(msg.text, 'agent');
                // Track run_id for implicit feedback
                if (msg.runId) window._currentRunId = msg.runId;
            }
        });

        // ── Implicit Feedback (Phase 4.2) ──
        let _lastCopyTime = 0;
        document.addEventListener('copy', () => {
            const now = Date.now();
            if (now - _lastCopyTime < 2000) return; // Debounce 2s
            _lastCopyTime = now;
            const selected = window.getSelection()?.toString() || '';
            if (selected.length > 20) {
                const signalType = selected.length > 100 ? 'copy_full' : 'select_text';
                vscode.postMessage({ command: 'implicitFeedback', type: signalType, runId: window._currentRunId || '' });
            }
        });
    </script>
</body>
</html>`;
    }
}
