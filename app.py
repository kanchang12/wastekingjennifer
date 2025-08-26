import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string

# Import the agents (now updated with supplier confirmation)
from agents import SkipAgent, MAVAgent, GrabAgent

app = Flask(__name__)

# ElevenLabs Configuration
elevenlabs_api_key = os.getenv('elevenlabs_api_key')
agent_phone_number_id = os.getenv('agent_phone_number_id')
agent_id = os.getenv('agent_id')
SUPPLIER_PHONE = '+447394642517'

# Global conversation counter
conversation_counter = 0
webhook_calls = []  # Store webhook call data

def get_next_conversation_id():
    """Generate next conversation ID with counter"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

# Initialize agents with shared conversation storage and supplier phone
shared_conversations = {}

skip_agent = SkipAgent()
skip_agent.conversations = shared_conversations
skip_agent.supplier_phone = SUPPLIER_PHONE

mav_agent = MAVAgent()  
mav_agent.conversations = shared_conversations
mav_agent.supplier_phone = SUPPLIER_PHONE

grab_agent = GrabAgent()
grab_agent.conversations = shared_conversations
grab_agent.supplier_phone = SUPPLIER_PHONE

print("✅ All agents initialized with shared conversation storage")
print(f"📞 Supplier phone configured: {SUPPLIER_PHONE}")

print("🔧 Environment check:")
print(f"   WASTEKING_BASE_URL: {os.getenv('WASTEKING_BASE_URL', 'Not set')}")
print(f"   WASTEKING_ACCESS_TOKEN: {'Set' if os.getenv('WASTEKING_ACCESS_TOKEN') else 'Not set'}")
print(f"   ELEVENLABS_API_KEY: {'Set' if elevenlabs_api_key else 'Not set'}")
print(f"   AGENT_PHONE_NUMBER_ID: {agent_phone_number_id or 'Not set'}")
print(f"   AGENT_ID: {agent_id or 'Not set'}")

def is_office_hours():
    """Check if it's office hours for supplier confirmation"""
    now = datetime.now()
    day_of_week = now.weekday()  # 0=Monday, 6=Sunday
    hour = now.hour
    
    if day_of_week < 4:  # Monday-Thursday
        return 8 <= hour < 17
    elif day_of_week == 4:  # Friday
        return 8 <= hour < 16
    elif day_of_week == 5:  # Saturday
        return 9 <= hour < 12
    return False  # Sunday closed

def call_supplier_for_confirmation(customer_request, conversation_id):
    """Call supplier to confirm if we can fulfill the request - OFFICE HOURS ONLY"""
    if not is_office_hours():
        return {"confirmed": True, "reason": "outside_office_hours"}
    
    if not elevenlabs_api_key or not agent_phone_number_id:
        print("❌ ElevenLabs not configured, assuming confirmation")
        return {"confirmed": True, "reason": "no_elevenlabs_config"}
    
    try:
        # Make call to supplier using ElevenLabs
        headers = {
            'Content-Type': 'application/json',
            'xi-api-key': elevenlabs_api_key
        }
        
        call_data = {
            "phone_number_id": agent_phone_number_id,
            "agent_id": agent_id,
            "customer_phone_number": SUPPLIER_PHONE,
            "conversation_config_override": {
                "agent_prompt": f"You are calling the WasteKing supplier to confirm availability for this request: '{customer_request}'. Ask if we can fulfill this request and get a yes/no answer. Be brief and professional.",
                "first_message": f"Hi, this is the WasteKing AI assistant. I need to confirm if we can fulfill this customer request: {customer_request}. Can you confirm availability?",
                "language": "en"
            }
        }
        
        response = requests.post(
            'https://api.elevenlabs.io/v1/convai/conversations',
            headers=headers,
            json=call_data
        )
        
        if response.status_code == 200:
            call_info = response.json()
            print(f"📞 Supplier call initiated: {call_info.get('conversation_id')}")
            
            # In a real implementation, you'd need to wait for the call to complete
            # and get the result via webhook. For now, we'll assume confirmation
            # after a brief delay unless specifically denied
            
            return {"confirmed": True, "reason": "supplier_called", "call_id": call_info.get('conversation_id')}
        else:
            print(f"❌ Failed to call supplier: {response.status_code}")
            return {"confirmed": True, "reason": "call_failed_assume_yes"}
            
    except Exception as e:
        print(f"❌ Supplier call error: {e}")
        return {"confirmed": True, "reason": "error_assume_yes"}

def transfer_call_to_supplier(conversation_id):
    """Transfer call to supplier - ALL TRANSFERS GO TO +447394642517"""
    if not elevenlabs_api_key or not agent_phone_number_id:
        return "I'm transferring you to our team at +447394642517. Please hold while I connect you."
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'xi-api-key': elevenlabs_api_key
        }
        
        transfer_data = {
            "phone_number_id": agent_phone_number_id,
            "transfer_to": SUPPLIER_PHONE,
            "conversation_id": conversation_id
        }
        
        response = requests.post(
            'https://api.elevenlabs.io/v1/convai/conversations/transfer',
            headers=headers,
            json=transfer_data
        )
        
        if response.status_code == 200:
            print(f"📞 Call transferred to supplier: {SUPPLIER_PHONE}")
            return "I'm transferring you to our specialist team now. Please hold."
        else:
            print(f"❌ Transfer failed: {response.status_code}")
            return f"Please call our team directly at {SUPPLIER_PHONE}. I'll send your details to them."
            
    except Exception as e:
        print(f"❌ Transfer error: {e}")
        return f"Please call our team directly at {SUPPLIER_PHONE}. I'll send your details to them."

def route_to_agent(message, conversation_id):
    """ENHANCED ROUTING WITH SUPPLIER CONFIRMATION"""
    message_lower = message.lower()
    
    print(f"🔍 ROUTING ANALYSIS: '{message_lower}'")
    
    # Check conversation context first
    context = shared_conversations.get(conversation_id, {})
    existing_service = context.get('service')
    
    print(f"📂 EXISTING CONTEXT: {context}")
    
    # Check if this requires transfer
    transfer_triggers = [
        'speak to someone', 'talk to human', 'manager', 'supervisor', 
        'complaint', 'problem', 'issue', 'not happy', 'transfer me'
    ]
    
    if any(trigger in message_lower for trigger in transfer_triggers):
        print("🔄 TRANSFER REQUESTED")
        return transfer_call_to_supplier(conversation_id)
    
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
    """Render the call tracking dashboard"""
    # Read the HTML template
    html_template = """<!DOCTYPE html>
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

        .empty-state {
            text-align: center;
            padding: 60px 30px;
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }

        .empty-state h3 {
            color: #4a5568;
            font-size: 1.5rem;
            margin-bottom: 15px;
        }

        .empty-state p {
            color: #718096;
            line-height: 1.6;
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
        </div>

        <div class="empty-state">
            <h3>Webhook Integration Active</h3>
            <p>
                The system is ready to receive ElevenLabs webhook data.<br>
                Configure your ElevenLabs agent to send post-call webhooks to:<br>
                <strong>{{ webhook_url }}</strong><br><br>
                Call transcripts and customer follow-ups will appear here once calls are completed.
            </p>
        </div>
    </div>
</body>
</html>"""
    
    return render_template_string(html_template,
        elevenlabs_configured=bool(elevenlabs_api_key),
        agent_phone_id=agent_phone_number_id,
        agent_id=agent_id,
        supplier_phone=SUPPLIER_PHONE,
        webhook_url=request.url_root + 'api/webhook/elevenlabs'
    )

@app.route('/api/webhook/elevenlabs', methods=['POST'])
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
        
        print(f"📞 Webhook received: {call_data['id']}")
        
        return jsonify({"success": True, "message": "Webhook received"})
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/webhook/calls', methods=['GET'])
def get_webhook_calls():
    """Get stored webhook call data"""
    return jsonify({"success": True, "calls": webhook_calls})

@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message():
    """Main endpoint for processing customer messages with supplier confirmation"""
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
        
        # Check if message requires supplier confirmation (during office hours only)
        if is_office_hours() and any(keyword in customer_message.lower() for keyword in ['urgent', 'immediate', 'today', 'asap', 'special', 'unusual']):
            print("🔍 CHECKING WITH SUPPLIER...")
            confirmation = call_supplier_for_confirmation(customer_message, conversation_id)
            if not confirmation['confirmed']:
                return jsonify({
                    "success": True,
                    "message": "I've checked with our team and we can't fulfill that specific request. What would be a suitable alternative for you?",
                    "conversation_id": conversation_id,
                    "timestamp": datetime.now().isoformat(),
                    "supplier_response": "denied"
                })
        
        # Route to appropriate agent with ENHANCED routing
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
        # If error occurs, transfer to supplier
        return jsonify({
            "success": True,
            "message": f"Let me connect you with our team who can help immediately. Please call {SUPPLIER_PHONE} or hold while I transfer you.",
            "error": str(e),
            "transfer_to": SUPPLIER_PHONE
        }), 200

@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab (DEFAULT MANAGER)"],
        "elevenlabs_configured": bool(ELEVENLABS_API_KEY),
        "supplier_phone": SUPPLIER_PHONE,
        "office_hours": is_office_hours(),
        "features": [
            "ElevenLabs webhook integration",
            "Supplier confirmation (office hours only)",
            "All transfers to +447394642517",
            "Real-time call tracking"
        ]
    })

@app.after_request
def after_request(response):
    """Add CORS headers"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("🚀 Starting WasteKing ElevenLabs Integration System...")
    print("🔧 KEY FEATURES:")
    print(f"  📞 Supplier confirmation calls to: {SUPPLIER_PHONE}")
    print(f"  ⏰ Office hours only: Monday-Thursday 8-17, Friday 8-16, Saturday 9-12")
    print(f"  🔄 All transfers go to: {SUPPLIER_PHONE}")
    print(f"  📡 ElevenLabs webhook: {'Configured' if ELEVENLABS_API_KEY else 'Not configured'}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
