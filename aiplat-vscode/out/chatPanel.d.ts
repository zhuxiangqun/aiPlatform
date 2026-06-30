/**
 * aiPlat Chat Panel — WebView side panel with SSE streaming chat.
 *
 * Features:
 *   - SSE streaming from backend
 *   - Code block detection and apply buttons
 *   - Markdown rendering for agent responses
 *   - Implicit feedback tracking (Phase 4.2)
 */
import * as vscode from 'vscode';
export declare class ChatPanel {
    static currentPanel: ChatPanel | undefined;
    private readonly _panel;
    private _disposables;
    private _baseUrl;
    private _lastCodeBlock;
    static createOrShow(extensionUri: vscode.Uri, baseUrl: string): void;
    private constructor();
    sendMessage(text: string): void;
    applyLastSuggestion(): void;
    private _applyToEditor;
    private _handleAgentQuery;
    private _sendCodeBlock;
    private _postToWebview;
    private _sendImplicitFeedback;
    dispose(): void;
    private _getHtml;
}
