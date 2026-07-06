import * as vscode from 'vscode';
import * as WebSocket from 'ws';

let outputChannel: vscode.OutputChannel;
let currentPanel: vscode.WebviewPanel | undefined;
let wsClient: WebSocket | undefined;
let reconnectTimer: NodeJS.Timeout | undefined;

export function activate(context: vscode.ExtensionContext) {
    outputChannel = vscode.window.createOutputChannel('aiPlat ACP');
    outputChannel.appendLine('aiPlat ACP extension activated.');

    // Register commands
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat-acp.openChat', openChatPanel)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat-acp.reviewCode', reviewSelectedCode)
    );
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat-acp.executeCommand', executeTerminalCommand)
    );

    // Connect on activation
    connect();

    outputChannel.appendLine('ACP extension ready. Commands: aiplat-acp.openChat, aiplat-acp.reviewCode, aiplat-acp.executeCommand');
}

export function deactivate() {
    disconnect();
    if (currentPanel) { currentPanel.dispose(); }
}

function getServerUrl(): string {
    return vscode.workspace.getConfiguration('aiplat-acp').get<string>('serverUrl', 'ws://localhost:8005/acp');
}

function connect() {
    const url = getServerUrl();
    outputChannel.appendLine(`Connecting to ACP server: ${url}...`);

    try {
        wsClient = new WebSocket(url);

        wsClient.on('open', () => {
            outputChannel.appendLine('✅ Connected to aiPlat ACP server');
            if (currentPanel) {
                currentPanel.webview.postMessage({ type: 'connection', status: 'connected' });
            }
        });

        wsClient.on('message', (data: WebSocket.Data) => {
            try {
                const msg = JSON.parse(data.toString());
                if (currentPanel) {
                    currentPanel.webview.postMessage(msg);
                }
                outputChannel.appendLine(`← ACP: ${msg.type}`);
            } catch {
                if (currentPanel) {
                    currentPanel.webview.postMessage({ type: 'error', content: data.toString() });
                }
            }
        });

        wsClient.on('close', () => {
            outputChannel.appendLine('⚠️ ACP connection closed');
            if (currentPanel) {
                currentPanel.webview.postMessage({ type: 'connection', status: 'disconnected' });
            }
            autoReconnect();
        });

        wsClient.on('error', (err: Error) => {
            outputChannel.appendLine(`❌ ACP error: ${err.message}`);
            autoReconnect();
        });
    } catch (err: any) {
        outputChannel.appendLine(`❌ ACP connect failed: ${err.message}`);
        autoReconnect();
    }
}

function autoReconnect() {
    if (!vscode.workspace.getConfiguration('aiplat-acp').get<boolean>('autoReconnect', true)) {
        return;
    }
    if (reconnectTimer) { clearTimeout(reconnectTimer); }
    reconnectTimer = setTimeout(() => {
        outputChannel.appendLine('🔄 Auto-reconnecting...');
        connect();
    }, 5000);
}

function disconnect() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); }
    if (wsClient) {
        wsClient.close();
        wsClient = undefined;
    }
}

function sendToAcp(msg: object) {
    if (!wsClient || wsClient.readyState !== WebSocket.OPEN) {
        vscode.window.showErrorMessage('ACP server not connected. Check ws://localhost:8005/acp');
        return;
    }
    wsClient.send(JSON.stringify(msg));
}

function openChatPanel() {
    if (currentPanel) {
        currentPanel.reveal(vscode.ViewColumn.Two);
        return;
    }

    currentPanel = vscode.window.createWebviewPanel(
        'aiplatAcpChat',
        'aiPlat Agent Chat',
        vscode.ViewColumn.Two,
        {
            enableScripts: true,
            retainContextWhenHidden: true,
        }
    );

    currentPanel.onDidDispose(() => {
        currentPanel = undefined;
    });

    currentPanel.webview.html = getChatHtml();

    currentPanel.webview.onDidReceiveMessage((msg) => {
        if (msg.command === 'send') {
            sendToAcp({ type: 'chat', content: msg.content });
        } else if (msg.command === 'status') {
            sendToAcp({ type: 'status' });
        }
    });
}

async function reviewSelectedCode() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
        vscode.window.showInformationMessage('No active editor');
        return;
    }

    const selection = editor.selection;
    const code = selection.isEmpty
        ? editor.document.getText()
        : editor.document.getText(selection);

    if (!code) {
        vscode.window.showInformationMessage('No code to review');
        return;
    }

    sendToAcp({
        type: 'diff',
        content: code,
        language: editor.document.languageId,
    });

    // Open chat panel to show results
    openChatPanel();
    vscode.window.showInformationMessage('Code sent for agent review. Check chat panel.');
}

async function executeTerminalCommand() {
    const command = await vscode.window.showInputBox({
        prompt: 'Enter command to execute via aiPlat Agent',
        placeHolder: 'e.g., "find . -name "*.py" | head -20',
    });

    if (!command) { return; }

    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri?.fsPath || '.';
    sendToAcp({
        type: 'exec',
        command: command,
        cwd: workspaceRoot,
    });

    openChatPanel();
    vscode.window.showInformationMessage('Command sent for agent execution. Check chat panel.');
}

function getChatHtml(): string {
    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<title>aiPlat Agent Chat</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font:13px/1.5 var(--vscode-font-family,monospace);color:var(--vscode-foreground);background:var(--vscode-editor-background);padding:0;display:flex;flex-direction:column;height:100vh}
.header{padding:8px 12px;border-bottom:1px solid var(--vscode-panel-border);display:flex;align-items:center;gap:8px}
.header .dot{width:8px;height:8px;border-radius:50%;background:#888}
.header .dot.connected{background:#4caf50}
.header .title{font-weight:600;font-size:12px}
.messages{flex:1;overflow-y:auto;padding:12px}
.msg{margin-bottom:10px;padding:8px 12px;border-radius:6px;max-width:90%}
.msg.user{align-self:flex-end;background:var(--vscode-button-background);color:var(--vscode-button-foreground);margin-left:auto}
.msg.agent{background:var(--vscode-input-background);color:var(--vscode-input-foreground)}
.msg.error{background:var(--vscode-inputValidation-errorBackground);color:var(--vscode-inputValidation-errorForeground)}
.msg .type{font-size:10px;opacity:.6;margin-bottom:2px}
.msg .time{font-size:9px;opacity:.4;float:right}
.msg pre{background:var(--vscode-textCodeBlock-background);padding:8px;border-radius:4px;margin-top:4px;overflow-x:auto;font-size:11px}
.input-bar{display:flex;padding:8px 12px;border-top:1px solid var(--vscode-panel-border);gap:8px}
.input-bar input{flex:1;padding:6px 10px;border:1px solid var(--vscode-input-border);border-radius:4px;background:var(--vscode-input-background);color:var(--vscode-input-foreground);font:inherit;outline:none}
.input-bar input:focus{border-color:var(--vscode-focusBorder)}
.input-bar button{padding:6px 14px;border:none;border-radius:4px;background:var(--vscode-button-background);color:var(--vscode-button-foreground);cursor:pointer;font:inherit}
.input-bar button:hover{background:var(--vscode-button-hoverBackground)}
</style>
</head>
<body>
<div class="header">
  <span class="dot" id="statusDot"></span>
  <span class="title">aiPlat Agent Chat</span>
  <span style="font-size:10px;opacity:.5" id="statusText">connecting...</span>
</div>
<div class="messages" id="messages"></div>
<div class="input-bar">
  <input id="input" type="text" placeholder="Ask the agent..." onkeydown="if(event.key==='Enter')send()">
  <button onclick="send()">Send</button>
  <button onclick="status()" style="font-size:11px;opacity:.6">⟳</button>
</div>
<script>
const vscode = acquireVsCodeApi();
const msgs = document.getElementById('messages');
const input = document.getElementById('input');
const dot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

window.addEventListener('message', e => {
    const msg = e.data;
    if (msg.type === 'connection') {
        dot.className = 'dot' + (msg.status === 'connected' ? ' connected' : '');
        statusText.textContent = msg.status;
        if (msg.status === 'connected') { appendMsg('system', 'Connected to aiPlat Agent'); }
    } else if (msg.type === 'chat_response') {
        appendMsg('agent', msg.content || msg.error);
    } else if (msg.type === 'diff_response') {
        appendMsg('agent', '📋 Code Review:\n' + (msg.analysis || msg.error));
    } else if (msg.type === 'exec_response') {
        appendMsg('agent', '💻 Exec: ' + (msg.stdout || msg.error || 'done') + (msg.exit_code ? ' (exit '+msg.exit_code+')' : ''));
    } else if (msg.type === 'status_response') {
        appendMsg('system', 'Agent: ' + msg.model + ' | Protocol v' + msg.protocol_version);
    } else if (msg.type === 'error') {
        appendMsg('error', msg.content);
    }
});

function send() {
    const text = input.value.trim();
    if (!text) return;
    appendMsg('user', text);
    vscode.postMessage({ command: 'send', content: text });
    input.value = '';
}

function status() { vscode.postMessage({ command: 'status' }); }

function appendMsg(role, text) {
    const d = new Date();
    const time = [d.getHours(),d.getMinutes(),d.getSeconds()].map(x=>String(x).padStart(2,'0')).join(':');
    const el = document.createElement('div');
    el.className = 'msg ' + role;
    el.innerHTML = '<span class="time">' + time + '</span>' +
        (role === 'user' ? '' : '<span class="type">' + role.toUpperCase() + '</span>') +
        '<div>' + (text || '').replace(/</g,'&lt;').replace(/\n/g,'<br>') + '</div>';
    msgs.appendChild(el);
    msgs.scrollTop = msgs.scrollHeight;
}
</script>
</body>
</html>`;
}
