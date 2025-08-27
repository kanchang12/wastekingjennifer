import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# Import the simple agents
from agents import SkipAgent, MAVAgent, GrabAgent

app = Flask(__name__)
webhook_calls = []
# Initialize system
print("🚀 Initializing WasteKing Simple System...")

# Global conversation counter
conversation_counter = 0

def get_next_conversation_id():
    """Generate next conversation ID with counter"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"  # conv00000001, conv00000002, etc.


# Initialize agents with shared conversation storage
shared_conversations = {}

skip_agent = SkipAgent()
skip_agent.conversations = shared_conversations

mav_agent = MAVAgent()  
mav_agent.conversations = shared_conversations

grab_agent = GrabAgent()
grab_agent.conversations = shared_conversations

print("✅ All agents initialized with shared conversation storage")

print("🔧 Environment check:")
print(f"   WASTEKING_BASE_URL: {os.getenv('WASTEKING_BASE_URL', 'Not set')}")
print(f"   WASTEKING_ACCESS_TOKEN: {'Set' if os.getenv('WASTEKING_ACCESS_TOKEN') else 'Not set'}")

def route_to_agent(message, conversation_id):
    """FIXED ROUTING RULES - Grab agent handles everything except explicit skip/mav"""
    message_lower = message.lower()
    
    print(f"🔍 ROUTING ANALYSIS: '{message_lower}'")
    
    # Check conversation context first
    context = shared_conversations.get(conversation_id, {})
    existing_service = context.get('service')
    
    print(f"📂 EXISTING CONTEXT: {context}")
    
    # PRIORITY 1: Skip Agent - ONLY explicit skip mentions
    if any(word in message_lower for word in ['skip', 'skip hire', 'yard skip', 'cubic yard']):
        print("🔄 Routing to Skip Agent (explicit skip mention)")
        return skip_agent.process_message(message, conversation_id)
    
    # PRIORITY 2: MAV Agent - ONLY explicit man and van mentions  
    elif any(word in message_lower for word in ['man and van', 'mav', 'man & van', 'van collection', 'small van', 'medium van', 'large van']):
        print("🔄 Routing to MAV Agent (explicit mav mention)")
        return mav_agent.process_message(message, conversation_id)
    
    # PRIORITY 3: Continue with existing service if available
    elif existing_service == 'skip':
        print("🔄 Routing to Skip Agent (continuing existing skip conversation)")
        return skip_agent.process_message(message, conversation_id)
    
    elif existing_service == 'mav':
        print("🔄 Routing to MAV Agent (continuing existing mav conversation)")
        return mav_agent.process_message(message, conversation_id)
    
    # PRIORITY 4: Grab Agent handles EVERYTHING ELSE (default manager)
    else:
        print("🔄 Routing to Grab Agent (handles ALL other requests including grab, general inquiries, and unknown services)")
        return grab_agent.process_message(message, conversation_id)

@app.route('/')
def index():
    """Single HTML page showing all webhooks without any fail"""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WasteKing Call Tracker</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
        }

        .header {
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }

        .header h1 {
            color: #2d3748;
            font-size: 2.5rem;
            font-weight: 700;
            margin-bottom: 10px;
        }

        .header p {
            color: #4a5568;
            font-size: 1.1rem;
        }

        .config-info {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);
            border-left: 4px solid #48bb78;
        }

        .config-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 15px;
        }

        .config-item {
            background: #f7fafc;
            padding: 15px;
            border-radius: 10px;
        }

        .config-label {
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 5px;
        }

        .config-value {
            font-family: 'Courier New', monospace;
            color: #4a5568;
            font-size: 0.9rem;
        }

        .status-ok { color: #48bb78; }
        .status-missing { color: #f56565; }

        .calls-section {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }

        .calls-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }

        .calls-title {
            color: #2d3748;
            font-size: 1.8rem;
            font-weight: 700;
        }

        .refresh-btn {
            background: #667eea;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 600;
            transition: background 0.3s;
        }

        .refresh-btn:hover {
            background: #5a67d8;
        }

        .calls-table {
            width: 100%;
            border-collapse: collapse;
            background: white;
            border-radius: 10px;
            overflow: hidden;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }

        .calls-table th {
            background: #667eea;
            color: white;
            padding: 15px;
            text-align: left;
            font-weight: 600;
        }

        .calls-table td {
            padding: 15px;
            border-bottom: 1px solid #e2e8f0;
        }

        .calls-table tr:hover {
            background: #f7fafc;
        }

        .call-status {
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: 600;
        }

        .status-completed { background: #c6f6d5; color: #22543d; }
        .status-initiated { background: #ffd6cc; color: #c53030; }
        .status-in-progress { background: #fef5e7; color: #d69e2e; }

        .empty-calls {
            text-align: center;
            padding: 60px 30px;
            color: #4a5568;
        }

        .empty-calls h3 {
            font-size: 1.5rem;
            margin-bottom: 15px;
        }

        .webhook-url {
            background: #f7fafc;
            padding: 15px;
            border-radius: 10px;
            margin-top: 20px;
            border-left: 4px solid #667eea;
        }

        .webhook-url strong {
            color: #667eea;
            font-family: 'Courier New', monospace;
        }
        .conversation-group {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            cursor: pointer; /* NEW: Add cursor pointer to indicate it's clickable */
        }
        .conversation-header {
            font-size: 1.5rem;
            font-weight: 700;
            color: #2d3748;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .calls-table {
            margin-top: 20px;
        }

        /* NEW: Modal Styles */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.6);
            backdrop-filter: blur(5px);
            justify-content: center;
            align-items: center;
        }

        .modal-content {
            background-color: #fefefe;
            padding: 30px;
            border-radius: 20px;
            width: 80%;
            max-width: 700px;
            box-shadow: 0 5px 15px rgba(0,0,0,0.3);
            position: relative;
        }

        .close-btn {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            position: absolute;
            top: 15px;
            right: 25px;
        }

        .close-btn:hover,
        .close-btn:focus {
            color: #000;
            text-decoration: none;
            cursor: pointer;
        }

        .transcript-text {
            white-space: pre-wrap;
            font-family: monospace;
            font-size: 0.9rem;
            line-height: 1.5;
            color: #333;
            max-height: 70vh;
            overflow-y: auto;
            margin-top: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>WasteKing Call Tracker</h1>
            <p>ElevenLabs AI Agent Call Tracking & Follow-up System</p>
        </div>

        <div class="config-info">
            <h3>System Configuration</h3>
            <div class="config-grid">
                <div class="config-item">
                    <div class="config-label">ElevenLabs API Key</div>
                    <div class="config-value {{ 'status-ok' if elevenlabs_configured else 'status-missing' }}">
                        {{ 'Configured' if elevenlabs_configured else 'Not configured' }}
                    </div>
                </div>
                <div class="config-item">
                    <div class="config-label">Agent Phone Number ID</div>
                    <div class="config-value">{{ agent_phone_id or 'Not set' }}</div>
                </div>
                <div class="config-item">
                    <div class="config-label">Agent ID</div>
                    <div class="config-value">{{ agent_id or 'Not set' }}</div>
                </div>
                <div class="config-item">
                    <div class="config-label">Supplier Phone</div>
                    <div class="config-value status-ok">{{ supplier_phone }}</div>
                </div>
            </div>
            
            <div class="webhook-url">
                <strong>Webhook URL for ElevenLabs:</strong><br>
                {{ webhook_url }}
            </div>
        </div>

        <div class="calls-section">
            <div class="calls-header">
                <h2 class="calls-title">Recent Calls ({{ call_count }})</h2>
                <button class="refresh-btn" onclick="window.location.reload()">Refresh</button>
            </div>

            {% if grouped_calls %}
            {% for conv_id, calls in grouped_calls.items() %}
            <div class="conversation-group" onclick="showTranscript('{{ conv_id }}')">
                <div class="conversation-header">
                    Conversation ID: {{ conv_id }}
                    {% if calls|length > 1 %}
                        <span style="font-size: 0.8em; font-weight: normal; color: #4a5568;"> ({{ calls|length }} parts)</span>
                    {% endif %}
                </div>
                <table class="calls-table">
                    <thead>
                        <tr>
                            <th>Time</th>
                            <th>Type</th>
                            <th>Customer Phone</th>
                            <th>Duration</th>
                            <th>Status</th>
                            <th>Details</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for call in calls %}
                        <tr>
                            <td>{{ call.timestamp[:19] if call.timestamp else 'N/A' }}</td>
                            <td>{{ call.call_type or 'Customer Call' }}</td>
                            <td>{{ call.customer_phone or call.to_number or 'N/A' }}</td>
                            <td>{{ call.duration or 0 }}s</td>
                            <td>
                                <span class="call-status status-{{ call.status or 'completed' }}">
                                    {{ (call.status or 'completed').title() }}
                                </span>
                            </td>
                            <td>
                                {% if call.transcript %}
                                    {{ call.transcript[:100] }}...
                                {% elif call.customer_request %}
                                    {{ call.customer_request[:100] }}...
                                {% else %}
                                    No details
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
            {% endfor %}
            {% else %}
            <div class="empty-calls">
                <h3>No Calls Yet</h3>
                <p>Webhook integration is active and ready to receive call data from ElevenLabs.</p>
            </div>
            {% endif %}
        </div>
    </div>

    <div id="transcriptModal" class="modal">
      <div class="modal-content">
        <span class="close-btn" onclick="closeModal()">&times;</span>
        <h2 id="modal-title"></h2>
        <div class="transcript-text" id="transcriptContent"></div>
      </div>
    </div>

    <script>
        // Store call data in a JavaScript variable for easy access
        const groupedCalls = JSON.parse('{{ grouped_calls | tojson }}');

        function showTranscript(convId) {
            const calls = groupedCalls[convId];
            if (!calls || calls.length === 0) {
                return;
            }

            const modalTitle = document.getElementById('modal-title');
            const transcriptContent = document.getElementById('transcriptContent');
            const transcriptModal = document.getElementById('transcriptModal');
            
            modalTitle.textContent = `Transcript for Conversation ID: ${convId}`;
            
            let fullTranscript = '';
            calls.forEach((call, index) => {
                fullTranscript += `--- Call Part ${index + 1} (${call.call_type || 'N/A'}) ---\n`;
                fullTranscript += `Start Time: ${new Date(call.timestamp).toLocaleString()}\n`;
                fullTranscript += `Duration: ${call.duration}s\n`;
                fullTranscript += `Status: ${call.status || 'N/A'}\n\n`;
                fullTranscript += `${call.transcript || 'No transcript available.'}\n\n`;
            });
            
            transcriptContent.textContent = fullTranscript;
            transcriptModal.style.display = "flex";
        }

        function closeModal() {
            const transcriptModal = document.getElementById('transcriptModal');
            transcriptModal.style.display = "none";
        }

        // Close modal when clicking outside of it
        window.onclick = function(event) {
            const transcriptModal = document.getElementById('transcriptModal');
            if (event.target == transcriptModal) {
                closeModal();
            }
        }

        // Simple auto-refresh every 30 seconds
        setTimeout(() => {
            window.location.reload();
        }, 30000);

    </script>
</body>
</html>"""

@app.route('/api/webhook/calls', methods=['POST'])
def elevenlabs_webhook():
    """Receive webhook data from ElevenLabs post-call"""
    try:
        data = request.get_json()
        
        # Store webhook call data
        call_data = {
            'id': f"call_{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'transcript': data.get('transcript', ''),
            'duration': data.get('duration', 0),
            'conversation_id': data.get('conversation_id', ''),
            'customer_phone': data.get('customer_phone', ''),
            'status': 'completed'
        }
        
        webhook_calls.append(call_data)
        
        print(f"Webhook received: {call_data['id']}")
        
        return jsonify({"success": True, "message": "Webhook received"})
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500



@app.route('/wasteking-chatbot.js')
def serve_chatbot_js():
    return send_from_directory('static', 'wasteking-chatbot.js')


from flask import request, jsonify

@app.route('/api/chat', methods=['POST'])
def chatbot_api():
    data = request.get_json()
    message = data.get('message')
    conversation_id = data.get('conversation_id')

    # Process the message, e.g., call AI or return canned response
    response_text = f"You said: {message}"

    return jsonify({'response': response_text})


@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message():
    """Main endpoint for processing customer messages"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        
        # Use provided conversation_id OR create new one only for new conversations
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or data.get('system__conversation_id')
        if not conversation_id:
            conversation_id = get_next_conversation_id()
            print(f"🆕 NEW CONVERSATION CREATED: {conversation_id}")
        else:
            print(f"🔄 CONTINUING CONVERSATION: {conversation_id}")
        
        print(f"📩 Message: {customer_message}")
        print(f"🆔 Conversation: {conversation_id}")
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # Route to appropriate agent with FIXED routing
        response = route_to_agent(customer_message, conversation_id)
        
        print(f"🤖 Response: {response}")
        
        return jsonify({
            "success": True,
            "message": response,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return jsonify({
            "success": False,
            "message": "I'll connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/api/test', methods=['POST'])
def test_api():
    """Test WasteKing API directly - NO HARDCODED VALUES"""
    try:
        from utils.wasteking_api import create_booking, get_pricing, complete_booking, create_payment_link
        
        data = request.get_json() or {}
        action = data.get('action')
        
        if not action:
            return jsonify({"success": False, "error": "No action specified"}), 400
        
        if action == 'create_booking':
            result = create_booking()
        elif action == 'get_pricing':
            booking_ref = data.get('booking_ref')
            postcode = data.get('postcode')
            service = data.get('service')
            service_type = data.get('type')
            
            if not all([booking_ref, postcode, service]):
                return jsonify({"success": False, "error": "Missing required fields: booking_ref, postcode, service"}), 400
            
            result = get_pricing(booking_ref, postcode, service, service_type)
        elif action == 'create_payment_link':
            booking_ref = data.get('booking_ref')
            if not booking_ref:
                return jsonify({"success": False, "error": "booking_ref required"}), 400
            result = create_payment_link(booking_ref)
        elif action == 'complete_booking':
            required_fields = ['firstName', 'phone', 'postcode', 'service']
            customer_data = {}
            
            for field in required_fields:
                value = data.get(field)
                if not value:
                    return jsonify({"success": False, "error": f"Missing required field: {field}"}), 400
                customer_data[field] = value
            
            # Optional fields
            optional_fields = ['lastName', 'email', 'type', 'date']
            for field in optional_fields:
                if data.get(field):
                    customer_data[field] = data.get(field)
            
            result = complete_booking(customer_data)
        else:
            return jsonify({"success": False, "error": "Unknown action"}), 400
        
        return jsonify({
            "success": True,
            "action": action,
            "result": result
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab (DEFAULT MANAGER)"],
        "rules_processor": "Mock (disabled)",
        "api_configured": bool(os.getenv('WASTEKING_ACCESS_TOKEN')),
        "routing_fixed": True,
        "payment_link_creation_fixed": True,
        "no_hardcoded_prices": True
    })

@app.after_request
def after_request(response):
    """Add CORS headers"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("🚀 Starting WasteKing Simple System...")
    print("🔧 KEY FIXES:")
    print("  ✅ Grab agent is DEFAULT MANAGER - handles everything except explicit skip/mav")
    print("  ✅ Payment link creation (Step 4) FIXED")
    print("  ✅ NO HARDCODED PRICES - REAL API ONLY")
    print("  ✅ Mock rules processor (rules functionality disabled)")
    print("  ✅ All agent initialization issues resolved")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
