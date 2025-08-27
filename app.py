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
    <title>WasteKing Webhook Monitor</title>
    <style>
        body { 
            font-family: Arial, sans-serif; 
            margin: 0; 
            padding: 20px; 
            background: #f5f5f5; 
        }
        
        .header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .webhook-container {
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .webhook-item {
            border: 1px solid #ddd;
            padding: 15px;
            margin-bottom: 15px;
            border-radius: 5px;
            background: #fafafa;
        }
        
        .webhook-header {
            font-weight: bold;
            color: #333;
            margin-bottom: 10px;
            font-size: 14px;
        }
        
        .webhook-data {
            font-family: monospace;
            background: #f0f0f0;
            padding: 10px;
            border-radius: 3px;
            white-space: pre-wrap;
            word-wrap: break-word;
            font-size: 12px;
            max-height: 300px;
            overflow-y: auto;
        }
        
        .refresh-btn {
            background: #007cba;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            margin-bottom: 20px;
        }
        
        .refresh-btn:hover {
            background: #005a87;
        }
        
        .counter {
            float: right;
            background: #28a745;
            color: white;
            padding: 5px 10px;
            border-radius: 15px;
            font-size: 12px;
        }
        
        .empty-message {
            text-align: center;
            color: #666;
            padding: 40px;
        }

        .timestamp {
            color: #666;
            font-size: 11px;
            margin-bottom: 5px;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing Webhook Monitor</h1>
        <span class="counter" id="webhook-counter">0 webhooks</span>
        <p>Real-time webhook data from ElevenLabs</p>
        <p><strong>Webhook URL:</strong> <code>/api/webhook/elevenlabs</code></p>
    </div>
    
    <button class="refresh-btn" onclick="loadWebhooks()">Refresh Now</button>
    
    <div class="webhook-container" id="webhook-container">
        <div class="empty-message">Loading webhooks...</div>
    </div>

    <script>
        function loadWebhooks() {
            fetch('/api/webhook/calls')
                .then(response => response.json())
                .then(data => {
                    const container = document.getElementById('webhook-container');
                    const counter = document.getElementById('webhook-counter');
                    
                    if (data.success && data.calls && data.calls.length > 0) {
                        counter.textContent = `${data.calls.length} webhooks`;
                        
                        // Sort by timestamp (newest first)
                        const sortedCalls = data.calls.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
                        
                        let html = '';
                        sortedCalls.forEach((call, index) => {
                            html += `
                                <div class="webhook-item">
                                    <div class="webhook-header">
                                        Webhook #${index + 1}
                                        <div class="timestamp">${new Date(call.timestamp).toLocaleString()}</div>
                                    </div>
                                    <div class="webhook-data">${JSON.stringify(call, null, 2)}</div>
                                </div>
                            `;
                        });
                        
                        container.innerHTML = html;
                    } else {
                        counter.textContent = '0 webhooks';
                        container.innerHTML = `
                            <div class="empty-message">
                                <h3>No Webhooks Received Yet</h3>
                                <p>Waiting for ElevenLabs webhook data...</p>
                            </div>
                        `;
                    }
                })
                .catch(error => {
                    console.error('Error loading webhooks:', error);
                    document.getElementById('webhook-container').innerHTML = `
                        <div class="empty-message">
                            <h3>Error Loading Webhooks</h3>
                            <p>Error: ${error.message}</p>
                        </div>
                    `;
                });
        }

        // Load webhooks when page loads
        document.addEventListener('DOMContentLoaded', loadWebhooks);
        
        // Auto-refresh every 10 seconds
        setInterval(loadWebhooks, 10000);
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
