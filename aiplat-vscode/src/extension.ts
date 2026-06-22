/**
 * aiPlat VS Code Extension — Main Entry
 *
 * Commands:
 *   - aiplat.openChat       (Cmd+Shift+A)  — Open chat panel
 *   - aiplat.sendSelection  (Cmd+Shift+E)  — Send selection to Agent
 *   - aiplat.explainCode                   — Explain selected code
 *   - aiplat.applyFix                      — Apply suggested fix
 */

import * as vscode from 'vscode';
import { ChatPanel } from './chatPanel';

export function activate(context: vscode.ExtensionContext) {
    console.log('aiPlat VS Code extension activated');

    const config = vscode.workspace.getConfiguration('aiplat');
    const baseUrl = config.get<string>('url') || 'http://localhost:8002';

    // ── Command: Open Chat Panel ──
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat.openChat', () => {
            ChatPanel.createOrShow(context.extensionUri, baseUrl);
        })
    );

    // ── Command: Send Selection ──
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat.sendSelection', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const selection = editor.document.getText(editor.selection);
            if (!selection) {
                vscode.window.showWarningMessage('No code selected. Select code first.');
                return;
            }

            const fileInfo = `${editor.document.languageId} file \`${editor.document.fileName}\``;
            const prompt = `Context: ${fileInfo}\n\nCode:\n\`\`\`${editor.document.languageId}\n${selection}\n\`\`\``;

            ChatPanel.createOrShow(context.extensionUri, baseUrl);
            ChatPanel.currentPanel?.sendMessage(prompt);
        })
    );

    // ── Command: Explain Code ──
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat.explainCode', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;

            const selection = editor.document.getText(editor.selection);
            if (!selection) {
                vscode.window.showWarningMessage('No code selected.');
                return;
            }

            ChatPanel.createOrShow(context.extensionUri, baseUrl);
            ChatPanel.currentPanel?.sendMessage(
                `Explain the following ${editor.document.languageId} code:\n\`\`\`${editor.document.languageId}\n${selection}\n\`\`\``
            );
        })
    );

    // ── Command: Apply Fix ──
    context.subscriptions.push(
        vscode.commands.registerCommand('aiplat.applyFix', async () => {
            ChatPanel.currentPanel?.applyLastSuggestion();
        })
    );
}

export function deactivate() {}
