/**
 * WasteKing Chatbot Widget
 * Embed this script on any website to add the chatbot
 * Usage: <script src="wasteking-chatbot.js"></script>
 */
(function() {
    'use strict';

    // Configuration
    const CONFIG = {
        apiUrl: 'https://double-angelia-onewebonly-cf4e958c.koyeb.app/api/chat',
        botName: 'WasteKing Assistant',
        primaryColor: '#2563eb',
        secondaryColor: '#1f2937',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
    };

    // Prevent multiple instances
    if (window.WasteKingChatbot) {
        return;
    }

    class WasteKingChatbot {
        constructor() {
            this.isOpen = false;
            this.messages = [];
            this.conversationId = this.generateId();
            this.init();
        }

        generateId() {
            return 'chat_' + Math.random().toString(36).substr(2, 9) + Date.now().toString(36);
        }

        init() {
            this.createStyles();
            this.createHTML();
            this.attachEventListeners();
            this.addWelcomeMessage();
        }

        createStyles() {
            const style = document.createElement('style');
            style.textContent = `
                .wk-chatbot * {
                    box-sizing: border-box;
                    margin: 0;
                    padding: 0;
                }

                .wk-chatbot {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 10000;
                    font-family: ${CONFIG.fontFamily};
                }

                .wk-chat-bubble {
                    width: 60px;
                    height: 60px;
                    background: linear-gradient(135deg, ${CONFIG.primaryColor} 0%, #3b82f6 100%);
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    cursor: pointer;
                    box-shadow: 0 8px 25px rgba(37, 99, 235, 0.3);
                    transition: all 0.3s ease;
                    position: relative;
                    overflow: hidden;
                }

                .wk-chat-bubble:hover {
                    transform: scale(1.1);
                    box-shadow: 0 12px 35px rgba(37, 99, 235, 0.4);
                }

                .wk-chat-bubble:active {
                    transform: scale(0.95);
                }

                .wk-chat-bubble::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.1) 50%, transparent 70%);
                    transform: translateX(-100%);
                    transition: transform 0.6s;
                }

                .wk-chat-bubble:hover::before {
                    transform: translateX(100%);
                }

                .wk-bubble-icon {
                    color: white;
                    font-size: 24px;
                    transition: transform 0.3s ease;
                }

                .wk-chat-bubble.open .wk-bubble-icon {
                    transform: rotate(45deg);
                }

                .wk-notification-dot {
                    position: absolute;
                    top: 8px;
                    right: 8px;
                    width: 12px;
                    height: 12px;
                    background: #ef4444;
                    border-radius: 50%;
                    border: 2px solid white;
                    animation: wk-pulse 2s infinite;
                }

                @keyframes wk-pulse {
                    0% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.2); opacity: 0.7; }
                    100% { transform: scale(1); opacity: 1; }
                }

                .wk-chat-window {
                    position: absolute;
                    bottom: 80px;
                    right: 0;
                    width: 380px;
                    height: 500px;
                    background: white;
                    border-radius: 20px;
                    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
                    display: none;
                    flex-direction: column;
                    overflow: hidden;
                    transform: scale(0.8) translateY(20px);
                    opacity: 0;
                    transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
                }

                .wk-chat-window.open {
                    display: flex;
                    transform: scale(1) translateY(0);
                    opacity: 1;
                }

                @media (max-width: 420px) {
                    .wk-chat-window {
                        width: calc(100vw - 40px);
                        height: calc(100vh - 140px);
                        bottom: 80px;
                        right: 20px;
                        left: 20px;
                    }
                }

                .wk-chat-header {
                    background: linear-gradient(135deg, ${CONFIG.primaryColor} 0%, #3b82f6 100%);
                    color: white;
                    padding: 20px;
                    text-align: center;
                    position: relative;
                    overflow: hidden;
                }

                .wk-chat-header::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grain" width="100" height="100" patternUnits="userSpaceOnUse"><circle cx="25" cy="25" r="1" fill="%23ffffff" opacity="0.05"/><circle cx="75" cy="75" r="1" fill="%23ffffff" opacity="0.05"/><circle cx="50" cy="10" r="0.5" fill="%23ffffff" opacity="0.03"/></pattern></defs><rect width="100" height="100" fill="url(%23grain)"/></svg>');
                    pointer-events: none;
                }

                .wk-chat-title {
                    font-size: 18px;
                    font-weight: 600;
                    margin-bottom: 4px;
                    position: relative;
                    z-index: 1;
                }

                .wk-chat-status {
                    font-size: 12px;
                    opacity: 0.9;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    gap: 6px;
                    position: relative;
                    z-index: 1;
                }

                .wk-online-dot {
                    width: 8px;
                    height: 8px;
                    background: #10b981;
                    border-radius: 50%;
                    animation: wk-pulse 2s infinite;
                }

                .wk-close-btn {
                    position: absolute;
                    top: 15px;
                    right: 15px;
                    background: none;
                    border: none;
                    color: white;
                    font-size: 20px;
                    cursor: pointer;
                    width: 30px;
                    height: 30px;
                    border-radius: 50%;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: background-color 0.2s;
                    z-index: 2;
                }

                .wk-close-btn:hover {
                    background: rgba(255, 255, 255, 0.1);
                }

                .wk-messages-container {
                    flex: 1;
                    overflow-y: auto;
                    padding: 20px;
                    background: #f8fafc;
                    display: flex;
                    flex-direction: column;
                    gap: 12px;
                }

                .wk-messages-container::-webkit-scrollbar {
                    width: 6px;
                }

                .wk-messages-container::-webkit-scrollbar-track {
                    background: transparent;
                }

                .wk-messages-container::-webkit-scrollbar-thumb {
                    background: rgba(0, 0, 0, 0.2);
                    border-radius: 3px;
                }

                .wk-message {
                    max-width: 80%;
                    padding: 12px 16px;
                    border-radius: 18px;
                    word-wrap: break-word;
                    animation: wk-messageSlide 0.3s ease-out;
                    line-height: 1.4;
                    font-size: 14px;
                }

                .wk-message.user {
                    background: ${CONFIG.primaryColor};
                    color: white;
                    align-self: flex-end;
                    border-bottom-right-radius: 4px;
                }

                .wk-message.bot {
                    background: white;
                    color: ${CONFIG.secondaryColor};
                    align-self: flex-start;
                    border-bottom-left-radius: 4px;
                    border: 1px solid #e5e7eb;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
                    white-space: pre-line;
                }

                @keyframes wk-messageSlide {
                    from {
                        opacity: 0;
                        transform: translateY(10px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                .wk-typing-indicator {
                    display: none;
                    align-self: flex-start;
                    padding: 12px 16px;
                    background: white;
                    border-radius: 18px;
                    border-bottom-left-radius: 4px;
                    border: 1px solid #e5e7eb;
                    box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
                }

                .wk-typing-dots {
                    display: flex;
                    gap: 3px;
                }

                .wk-typing-dot {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    background: #9ca3af;
                    animation: wk-typing 1.4s infinite ease-in-out both;
                }

                .wk-typing-dot:nth-child(1) { animation-delay: -0.32s; }
                .wk-typing-dot:nth-child(2) { animation-delay: -0.16s; }

                @keyframes wk-typing {
                    0%, 80%, 100% {
                        transform: scale(0.8);
                        opacity: 0.5;
                    }
                    40% {
                        transform: scale(1);
                        opacity: 1;
                    }
                }

                .wk-input-container {
                    padding: 20px;
                    background: white;
                    border-top: 1px solid #e5e7eb;
                    display: flex;
                    gap: 12px;
                    align-items: flex-end;
                }

                .wk-message-input {
                    flex: 1;
                    padding: 12px 16px;
                    border: 2px solid #e5e7eb;
                    border-radius: 25px;
                    font-size: 14px;
                    font-family: ${CONFIG.fontFamily};
                    outline: none;
                    transition: border-color 0.2s;
                    resize: none;
                    max-height: 100px;
                    min-height: 44px;
                }

                .wk-message-input:focus {
                    border-color: ${CONFIG.primaryColor};
                }

                .wk-message-input::placeholder {
                    color: #9ca3af;
                }

                .wk-send-btn {
                    background: ${CONFIG.primaryColor};
                    border: none;
                    color: white;
                    width: 44px;
                    height: 44px;
                    border-radius: 50%;
                    cursor: pointer;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    transition: all 0.2s;
                    font-size: 16px;
                    flex-shrink: 0;
                }

                .wk-send-btn:hover {
                    background: #1d4ed8;
                    transform: scale(1.05);
                }

                .wk-send-btn:active {
                    transform: scale(0.95);
                }

                .wk-send-btn:disabled {
                    opacity: 0.5;
                    cursor: not-allowed;
                    transform: none;
                }

                .wk-error-message {
                    background: #fef2f2 !important;
                    color: #dc2626 !important;
                    border: 1px solid #fecaca !important;
                }

                .wk-quick-replies {
                    padding: 0 20px 20px;
                    background: white;
                    display: none;
                    flex-wrap: wrap;
                    gap: 8px;
                }

                .wk-quick-reply {
                    background: #f3f4f6;
                    border: 1px solid #d1d5db;
                    padding: 8px 12px;
                    border-radius: 15px;
                    font-size: 12px;
                    cursor: pointer;
                    transition: all 0.2s;
                    color: ${CONFIG.secondaryColor};
                }

                .wk-quick-reply:hover {
                    background: ${CONFIG.primaryColor};
                    color: white;
                    border-color: ${CONFIG.primaryColor};
                }
            `;
            document.head.appendChild(style);
        }

        createHTML() {
            const chatbotHTML = `
                <div class="wk-chatbot">
                    <div class="wk-chat-bubble" id="wk-chat-bubble">
                        <div class="wk-bubble-icon">💬</div>
                        <div class="wk-notification-dot" id="wk-notification-dot"></div>
                    </div>
                    
                    <div class="wk-chat-window" id="wk-chat-window">
                        <div class="wk-chat-header">
                            <button class="wk-close-btn" id="wk-close-btn">×</button>
                            <div class="wk-chat-title">${CONFIG.botName}</div>
                            <div class="wk-chat-status">
                                <div class="wk-online-dot"></div>
                                Online now
                            </div>
                        </div>
                        
                        <div class="wk-messages-container" id="wk-messages">
                            <div class="wk-typing-indicator" id="wk-typing">
                                <div class="wk-typing-dots">
                                    <div class="wk-typing-dot"></div>
                                    <div class="wk-typing-dot"></div>
                                    <div class="wk-typing-dot"></div>
                                </div>
                            </div>
                        </div>
                        
                        <div class="wk-quick-replies" id="wk-quick-replies">
                            <div class="wk-quick-reply" data-message="I need skip hire">Skip Hire</div>
                            <div class="wk-quick-reply" data-message="I need man and van">Man & Van</div>
                            <div class="wk-quick-reply" data-message="I need grab hire">Grab Hire</div>
                            <div class="wk-quick-reply" data-message="Get pricing">Get Quote</div>
                        </div>
                        
                        <div class="wk-input-container">
                            <textarea class="wk-message-input" id="wk-message-input" 
                                     placeholder="Type your message..." 
                                     rows="1"></textarea>
                            <button class="wk-send-btn" id="wk-send-btn">
                                <span>→</span>
                            </button>
                        </div>
                    </div>
                </div>
            `;

            document.body.insertAdjacentHTML('beforeend', chatbotHTML);
        }

        attachEventListeners() {
            const bubble = document.getElementById('wk-chat-bubble');
            const closeBtn = document.getElementById('wk-close-btn');
            const sendBtn = document.getElementById('wk-send-btn');
            const input = document.getElementById('wk-message-input');
            const quickReplies = document.getElementById('wk-quick-replies');

            bubble.addEventListener('click', () => this.toggleChat());
            closeBtn.addEventListener('click', () => this.closeChat());
            sendBtn.addEventListener('click', () => this.sendMessage());
            
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            input.addEventListener('input', this.autoResize);

            quickReplies.addEventListener('click', (e) => {
                if (e.target.classList.contains('wk-quick-reply')) {
                    const message = e.target.getAttribute('data-message');
                    this.sendMessage(message);
                }
            });

            // Hide notification dot after first interaction
            bubble.addEventListener('click', () => {
                const dot = document.getElementById('wk-notification-dot');
                if (dot) dot.style.display = 'none';
            }, { once: true });
        }

        autoResize() {
            const input = document.getElementById('wk-message-input');
            if (input) {
                input.style.height = 'auto';
                input.style.height = Math.min(input.scrollHeight, 100) + 'px';
            }
        }

        toggleChat() {
            const window = document.getElementById('wk-chat-window');
            const bubble = document.getElementById('wk-chat-bubble');
            
            this.isOpen = !this.isOpen;
            
            if (this.isOpen) {
                window.classList.add('open');
                bubble.classList.add('open');
                this.showQuickReplies();
                this.scrollToBottom();
                setTimeout(() => {
                    const input = document.getElementById('wk-message-input');
                    if (input) input.focus();
                }, 300);
            } else {
                window.classList.remove('open');
                bubble.classList.remove('open');
            }
        }

        closeChat() {
            const window = document.getElementById('wk-chat-window');
            const bubble = document.getElementById('wk-chat-bubble');
            
            this.isOpen = false;
            window.classList.remove('open');
            bubble.classList.remove('open');
        }

        addWelcomeMessage() {
            const welcomeText = `👋 Hi! I'm your ${CONFIG.botName}. I can help you with:

• Skip Hire (4yd to 12yd)
• Man & Van Services 
• Grab Hire Services
• Pricing & Availability

What can I help you with today?`;

            this.addMessage(welcomeText, 'bot');
        }

        showQuickReplies() {
            const quickReplies = document.getElementById('wk-quick-replies');
            if (this.messages.length <= 1) {
                quickReplies.style.display = 'flex';
            }
        }

        hideQuickReplies() {
            const quickReplies = document.getElementById('wk-quick-replies');
            quickReplies.style.display = 'none';
        }

        addMessage(text, sender, isError = false) {
            const messagesContainer = document.getElementById('wk-messages');
            const messageDiv = document.createElement('div');
            messageDiv.className = `wk-message ${sender}`;
            if (isError) {
                messageDiv.className += ' wk-error-message';
            }
            messageDiv.textContent = text;
            
            // Insert before typing indicator
            const typingIndicator = document.getElementById('wk-typing');
            messagesContainer.insertBefore(messageDiv, typingIndicator);
            
            this.messages.push({ text, sender, timestamp: Date.now() });
            this.scrollToBottom();
        }

        showTyping() {
            const typing = document.getElementById('wk-typing');
            if (typing) {
                typing.style.display = 'block';
                this.scrollToBottom();
            }
        }

        hideTyping() {
            const typing = document.getElementById('wk-typing');
            if (typing) {
                typing.style.display = 'none';
            }
        }

        scrollToBottom() {
            const container = document.getElementById('wk-messages');
            if (container) {
                setTimeout(() => {
                    container.scrollTop = container.scrollHeight;
                }, 100);
            }
        }

        async sendMessage(messageText = null) {
            const input = document.getElementById('wk-message-input');
            const sendBtn = document.getElementById('wk-send-btn');
            
            const message = messageText || (input ? input.value.trim() : '');
            if (!message) return;

            // Clear input and reset height
            if (!messageText && input) {
                input.value = '';
                input.style.height = '44px';
            }

            // Add user message
            this.addMessage(message, 'user');
            this.hideQuickReplies();

            // Disable input while processing
            if (sendBtn) sendBtn.disabled = true;
            if (input) input.disabled = true;
            this.showTyping();

            try {
                const response = await this.callAPI(message);
                this.hideTyping();
                
                if (response && response.response) {
                    this.addMessage(response.response, 'bot');
                } else {
                    this.addMessage("I'm having trouble connecting right now. Please try again in a moment.", 'bot', true);
                }
            } catch (error) {
                console.error('WasteKing Chatbot API Error:', error);
                this.hideTyping();
                this.addMessage("Sorry, I'm experiencing technical difficulties. Please try again later.", 'bot', true);
            } finally {
                if (sendBtn) sendBtn.disabled = false;
                if (input) {
                    input.disabled = false;
                    input.focus();
                }
            }
        }

        async callAPI(message) {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000); // 30 second timeout

            try {
                const response = await fetch(CONFIG.apiUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        message: message,
                        conversation_id: this.conversationId
                    }),
                    signal: controller.signal
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                return await response.json();
            } catch (error) {
                clearTimeout(timeoutId);
                throw error;
            }
        }
    }

    // Initialize when DOM is ready
    function initChatbot() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                window.WasteKingChatbot = new WasteKingChatbot();
            });
        } else {
            window.WasteKingChatbot = new WasteKingChatbot();
        }
    }

    // Start initialization
    initChatbot();

})();
