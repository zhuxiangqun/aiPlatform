"use strict";
/**
 * aiPlat VS Code Extension — Main Entry
 *
 * Commands:
 *   - aiplat.openChat       (Cmd+Shift+A)  — Open chat panel
 *   - aiplat.sendSelection  (Cmd+Shift+E)  — Send selection to Agent
 *   - aiplat.explainCode                   — Explain selected code
 *   - aiplat.applyFix                      — Apply suggested fix
 */
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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const chatPanel_1 = require("./chatPanel");
function activate(context) {
    console.log('aiPlat VS Code extension activated');
    const config = vscode.workspace.getConfiguration('aiplat');
    const baseUrl = config.get('url') || 'http://localhost:8002';
    // ── Command: Open Chat Panel ──
    context.subscriptions.push(vscode.commands.registerCommand('aiplat.openChat', () => {
        chatPanel_1.ChatPanel.createOrShow(context.extensionUri, baseUrl);
    }));
    // ── Command: Send Selection ──
    context.subscriptions.push(vscode.commands.registerCommand('aiplat.sendSelection', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor)
            return;
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected. Select code first.');
            return;
        }
        const fileInfo = `${editor.document.languageId} file \`${editor.document.fileName}\``;
        const prompt = `Context: ${fileInfo}\n\nCode:\n\`\`\`${editor.document.languageId}\n${selection}\n\`\`\``;
        chatPanel_1.ChatPanel.createOrShow(context.extensionUri, baseUrl);
        chatPanel_1.ChatPanel.currentPanel?.sendMessage(prompt);
    }));
    // ── Command: Explain Code ──
    context.subscriptions.push(vscode.commands.registerCommand('aiplat.explainCode', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor)
            return;
        const selection = editor.document.getText(editor.selection);
        if (!selection) {
            vscode.window.showWarningMessage('No code selected.');
            return;
        }
        chatPanel_1.ChatPanel.createOrShow(context.extensionUri, baseUrl);
        chatPanel_1.ChatPanel.currentPanel?.sendMessage(`Explain the following ${editor.document.languageId} code:\n\`\`\`${editor.document.languageId}\n${selection}\n\`\`\``);
    }));
    // ── Command: Apply Fix ──
    context.subscriptions.push(vscode.commands.registerCommand('aiplat.applyFix', async () => {
        chatPanel_1.ChatPanel.currentPanel?.applyLastSuggestion();
    }));
}
function deactivate() { }
//# sourceMappingURL=extension.js.map