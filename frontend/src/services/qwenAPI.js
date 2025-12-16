/**
 * API Service for communicating with Python backend (Qwen LLM)
 */

const PYTHON_API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5000';

class QwenAPIService {
    /**
     * Check Python backend health
     */
    async checkHealth() {
        try {
            const response = await fetch(`${PYTHON_API_URL}/health`);
            return await response.json();
        } catch (error) {
            console.error('Health check failed:', error);
            return { status: 'error', error: error.message };
        }
    }

    /**
     * Check Ollama status
     */
    async checkOllamaStatus() {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/ollama/status`);
            return await response.json();
        } catch (error) {
            console.error('Ollama status check failed:', error);
            return { status: 'error', error: error.message };
        }
    }

    /**
     * Send a chat message to Qwen
     * @param {string} message - User message
     * @param {string} sessionId - Session ID for chat history
     * @param {Array} chatHistory - Previous chat messages
     * @param {Object} inventoryContext - Current inventory data
     * @returns {Promise<Object>} Response with AI message
     */
    async sendMessage(message, sessionId = 'default', chatHistory = [], inventoryContext = null) {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message,
                    session_id: sessionId,
                    chat_history: chatHistory,
                    inventory_context: inventoryContext
                })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to get response from Qwen');
            }

            return await response.json();
        } catch (error) {
            console.error('Send message failed:', error);
            throw error;
        }
    }

    /**
     * Get chat history for a session
     * @param {string} sessionId - Session ID
     */
    async getChatHistory(sessionId) {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/chat/history/${sessionId}`);
            return await response.json();
        } catch (error) {
            console.error('Get chat history failed:', error);
            return { history: [] };
        }
    }

    /**
     * Clear chat history for a session
     * @param {string} sessionId - Session ID
     */
    async clearChatHistory(sessionId) {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/chat/history/${sessionId}`, {
                method: 'DELETE'
            });
            return await response.json();
        } catch (error) {
            console.error('Clear chat history failed:', error);
            throw error;
        }
    }

    /**
     * List all active sessions
     */
    async listSessions() {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/chat/sessions`);
            return await response.json();
        } catch (error) {
            console.error('List sessions failed:', error);
            return { sessions: [] };
        }
    }

    /**
     * Update inventory.json file
     * @param {Object} inventoryData - Inventory data with items array
     */
    async updateInventory(inventoryData) {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/inventory/update`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(inventoryData)
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to update inventory');
            }

            return await response.json();
        } catch (error) {
            console.error('Update inventory failed:', error);
            throw error;
        }
    }

    /**
     * Reset inventory.json to default state
     */
    async resetInventory() {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/inventory/reset`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to reset inventory');
            }

            return await response.json();
        } catch (error) {
            console.error('Reset inventory failed:', error);
            throw error;
        }
    }

    /**
     * Reset settings.json to default state
     */
    async resetSettings() {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/settings/reset`, {
                method: 'POST'
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to reset settings');
            }

            return await response.json();
        } catch (error) {
            console.error('Reset settings failed:', error);
            throw error;
        }
    }

    /**
     * Execute robot command (start, stop, reset)
     * @param {string} command - Command to execute ('start', 'stop', 'reset')
     */
    async robotCommand(command) {
        try {
            const response = await fetch(`${PYTHON_API_URL}/api/robot/command`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ command })
            });

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to execute robot command');
            }

            return await response.json();
        } catch (error) {
            console.error('Robot command failed:', error);
            throw error;
        }
    }
}

// Export singleton instance
export const qwenAPI = new QwenAPIService();
export default qwenAPI;
