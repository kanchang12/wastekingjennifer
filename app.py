import os
import json
import requests
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template_string
from collections import defaultdict

app = Flask(__name__)

# ElevenLabs Configuration
elevenlabs_api_key = os.getenv('ELEVENLABS_API_KEY')
agent_phone_number_id = os.getenv('AGENT_PHONE_NUMBER_ID') 
agent_id = os.getenv('AGENT_ID')
SUPPLIER_PHONE = '+447823656762'
# NEW: Make.com Webhook URL
MAKE_WEBHOOK_URL = 'https://hook.eu2.make.com/t7bneptowre8yhexo5fjjx4nc09gqdz1'

# Global conversation counter and call storage
conversation_counter = 0
webhook_calls = []  # Store webhook call data

def get_next_conversation_id():
    """Generate next conversation ID with counter"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

def supplier_enquiry(customer_request, conversation_id, price):
    """NEW: Call supplier for enquiry during pricing - uses ElevenLabs Twilio outbound call"""
    if not elevenlabs_api_key or not agent_phone_number_id or not agent_id:
        print("❌ ElevenLabs not configured for supplier enquiry")
        return {"success": False, "reason": "no_elevenlabs_config"}
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'xi-api-key': elevenlabs_api_key
        }
        
        # Use ElevenLabs Twilio outbound call API
        call_data = {
            "agent_id": agent_id,
            "agent_phone_number_id": agent_phone_number_id, 
            "to_number": SUPPLIER_PHONE,
            "conversation_initiation_client_data": {
                "customer_request": customer_request,
                "conversation_id": conversation_id,
                "quote_price": price,
                "purpose": "supplier_enquiry"
            }
        }
        
        response = requests.post(
            'https://api.elevenlabs.io/v1/convai/twilio/outbound-call',
            headers=headers,
            json=call_data
        )
        
        if response.status_code == 200:
            call_info = response.json()
            print(f"📞 Supplier enquiry call initiated: {call_info}")
            
            # Store the supplier call info
            supplier_call = {
                'id': f"supplier_call_{datetime.now().timestamp()}",
                'timestamp': datetime.now().isoformat(),
                'customer_request': customer_request,
                'conversation_id': conversation_id,
                'quote_price': price,
                'supplier_call_id': call_info.get('call_id'),
                'status': 'initiated'
            }
            webhook_calls.append(supplier_call)
            
            return {"success": True, "call_id": call_info.get('call_id'), "supplier_call": supplier_call}
        else:
            print(f"❌ Failed to call supplier: {response.status_code} - {response.text}")
            return {"success": False, "reason": "api_call_failed", "error": response.text}
            
    except Exception as e:
        print(f"❌ Supplier enquiry error: {e}")
        return {"success": False, "reason": "exception", "error": str(e)}

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

# Import agents after supplier_enquiry function is defined
from agents import SkipAgent, MAVAgent, GrabAgent, set_supplier_enquiry_function, set_transfer_function

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



# Link the supplier_enquiry function to all agents
set_supplier_enquiry_function(supplier_enquiry)

# Link the transfer_call_to_supplier function to all agents
set_transfer_function(transfer_call_to_supplier)

print("✅ All agents initialized with shared conversation storage")
print(f"📞 Supplier phone configured: {SUPPLIER_PHONE}")
print("✅ Supplier enquiry function linked to agents")
print("✅ Transfer function linked to agents")

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

def route_to_agent(message, conversation_id):
    """ENHANCED ROUTING WITH QUALIFYING AGENT FOR NON-STANDARD SERVICES"""
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
    
    # PRIORITY 3: Grab Agent - explicit grab mentions
    elif any(word in message_lower for word in ['grab', 'grab hire', 'grab lorry', '6 wheeler', '8 wheeler']):
        print("🔄 Routing to Grab Agent (explicit grab mention)")
        return grab_agent.process_message(message, conversation_id)
    
    # PRIORITY 4: Continue with existing service if available
    elif existing_service == 'skip':
        print("🔄 Routing to Skip Agent (continuing existing skip conversation)")
        return skip_agent.process_message(message, conversation_id)
    
    elif existing_service == 'mav':
        print("🔄 Routing to MAV Agent (continuing existing mav conversation)")
        return mav_agent.process_message(message, conversation_id)
        
    elif existing_service == 'grab':
        print("🔄 Routing to Grab Agent (continuing existing grab conversation)")
        return grab_agent.process_message(message, conversation_id)
        
    elif existing_service == 'qualifying':
        pass
    
    # PRIORITY 5: NEW - Qualifying Agent handles EVERYTHING ELSE (unknown/other services)
    else:
        print("🔄 Routing to Qualifying Agent (handles all other requests and unknown services)")
        return "nill"
        
# NEW: Function to send the webhook
def send_make_webhook(conversation_data, summary):
    """Sends a webhook with conversation details to Make.com"""
    payload = {
        'Name': conversation_data.get('customer_name', 'N/A'),
        'phone number': conversation_data.get('customer_phone', 'N/A'),
        'product': conversation_data.get('service', 'Unspecified'),
        'post code': conversation_data.get('postcode', 'N/A'),
        'summary': summary
    }
    
    try:
        response = requests.post(MAKE_WEBHOOK_URL, json=payload, timeout=5)
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        print(f"✅ Webhook sent to Make.com successfully. Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Failed to send webhook to Make.com: {e}")

@app.route('/')
def index():
    """ENHANCED: Render the call tracking dashboard with call list, now grouped by conversation ID."""
    
    # Group calls by conversation ID
    grouped_calls = defaultdict(list)
    for call in sorted(webhook_calls, key=lambda x: x.get('timestamp', ''), reverse=True):
        conversation_id = call.get('conversation_id', 'Unassigned')
        grouped_calls[conversation_id].append(call)
        
    html_template = """
<!DOCTYPE html>
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
            <div class="conversation-group">
                <div class="conversation-header">Conversation ID: {{ conv_id }}</div>
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

    <script>
        // Simple auto-refresh every 30 seconds - no AJAX calls
        setTimeout(() => {
            window.location.reload();
        }, 30000);
        
        // Remove any error-prone fetch calls
        console.log('Dashboard loaded successfully');
    </script>
</body>
</html>
    """
    
    return render_template_string(html_template,
        elevenlabs_configured=bool(elevenlabs_api_key),
        agent_phone_id=agent_phone_number_id,
        agent_id=agent_id,
        supplier_phone=SUPPLIER_PHONE,
        webhook_url=request.url_root + 'api/webhook/elevenlabs',
        grouped_calls=grouped_calls,  # Pass the grouped dictionary
        call_count=len(webhook_calls)
    )

@app.route('/api/webhook/elevenlabs', methods=['POST'])
def elevenlabs_webhook():
    """ENHANCED: Receive webhook data from ElevenLabs post-call"""
    try:
        data = request.get_json()
        print(f"📞 Received webhook data: {data}")
        
        # Store webhook call data with enhanced structure
        call_data = {
            'id': f"call_{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'transcript': data.get('transcript', ''),
            'duration': data.get('duration', 0),
            'conversation_id': data.get('conversation_id', ''),
            'customer_phone': data.get('customer_phone', '') or data.get('from_number', ''),
            'to_number': data.get('to_number', ''),
            'status': data.get('status', 'completed'),
            'call_type': data.get('call_type', 'customer_call'),  # customer_call or supplier_enquiry
            'agent_id': data.get('agent_id', ''),
            'metadata': data.get('metadata', {}),
            'raw_data': data  # Store full webhook payload
        }
        
        webhook_calls.append(call_data)
        
        print(f"📞 Webhook stored: {call_data['id']} - Status: {call_data['status']}")
        
        return jsonify({"success": True, "message": "Webhook received", "call_id": call_data['id']})
        
    except Exception as e:
        print(f"❌ Webhook error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/webhook/calls', methods=['GET'])
def get_webhook_calls():
    """Get stored webhook call data - API endpoint"""
    try:
        # Optional filtering by query parameters
        call_type = request.args.get('type')  # customer_call or supplier_enquiry
        status = request.args.get('status')   # completed, initiated, in-progress
        limit = int(request.args.get('limit', 100))
        
        filtered_calls = webhook_calls.copy()  # Make a copy to avoid modification issues
        
        if call_type:
            filtered_calls = [call for call in filtered_calls if call.get('call_type') == call_type]
        
        if status:
            filtered_calls = [call for call in filtered_calls if call.get('status') == status]
        
        # Sort by timestamp (newest first) and limit
        try:
            sorted_calls = sorted(filtered_calls, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
        except:
            sorted_calls = filtered_calls[:limit]  # Fallback if sorting fails
        
        response_data = {
            "success": True, 
            "calls": sorted_calls,
            "total_count": len(webhook_calls),
            "filtered_count": len(sorted_calls)
        }
        
        # Ensure proper JSON response
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        print(f"❌ Get calls error: {e}")
        error_response = jsonify({"success": False, "error": str(e), "calls": []})
        error_response.headers['Content-Type'] = 'application/json'
        return error_response, 500

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


@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab"],
        "elevenlabs_configured": bool(elevenlabs_api_key),
        "supplier_phone": SUPPLIER_PHONE,
        "office_hours": is_office_hours(),
        "features": [
            "ElevenLabs webhook integration",
            "Supplier enquiry calls during pricing",
            "Enhanced call tracking dashboard", 
            "Qualifying agent for unknown services",
            "Real-time call display",
            "All transfers to +447394642517"
        ],
        "call_stats": {
            "total_calls": len(webhook_calls),
            "recent_calls": len([call for call in webhook_calls if (datetime.now() - datetime.fromisoformat(call['timestamp'].replace('Z', '+00:00').replace('+00:00', ''))).days < 1]) if webhook_calls else 0
        }
    })

@app.route('/test')
def test_page():
    """Simple test page to verify the app is working"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>WasteKing Test Page</title>
    </head>
    <body>
        <h1>WasteKing System Test</h1>
        <p>If you can see this page, the Flask app is running correctly.</p>
        <p>System Status: <strong>ONLINE</strong></p>
        <ul>
            <li><a href="/">Main Dashboard</a></li>
            <li><a href="/api/health">Health Check API</a></li>
            <li><a href="/api/webhook/calls">Webhook Calls API</a></li>
        </ul>
    </body>
    </html>
    """

@app.after_request
def after_request(response):
    """Add CORS headers"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("🚀 Starting Enhanced WasteKing ElevenLabs Integration System...")
    print("🔧 NEW FEATURES:")
    print(f"  📞 Supplier enquiry calls during pricing to: {SUPPLIER_PHONE}")
    print(f"  📊 Enhanced call tracking dashboard with real-time updates")
    print(f"  🎯 New qualifying agent for unknown/other services")
    print(f"  🔄 All transfers go to: {SUPPLIER_PHONE}")
    print(f"  📡 ElevenLabs webhook: {'Configured' if elevenlabs_api_key else 'Not configured'}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
