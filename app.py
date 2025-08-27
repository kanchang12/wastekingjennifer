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

# NEW FEATURE 1: Make.com webhook URL for email notifications
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL')

# Original conversation counter and call storage
conversation_counter = 0
webhook_calls = []

# NEW FEATURE 2: Live conversation tracking
live_conversations = defaultdict(lambda: {
    'conversation_id': '',
    'messages': [],
    'agent_responses': [],
    'customer_data': {},
    'status': 'active',
    'created_at': datetime.now().isoformat(),
    'last_activity': datetime.now().isoformat()
})

def get_next_conversation_id():
    """Generate next conversation ID with counter - ORIGINAL"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

# NEW FEATURE 3: Send email via Make.com webhook
def send_email_notification(conversation_id, customer_data, reason):
    """Send email notification via Make.com webhook"""
    if not MAKE_WEBHOOK_URL:
        print("Make.com webhook URL not configured")
        return False
    
    try:
        email_data = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,  # "callback", "transfer", or "interaction"
            "customer_name": customer_data.get('firstName', 'Not provided'),
            "customer_phone": customer_data.get('phone', 'Not provided'),
            "customer_postcode": customer_data.get('postcode', 'Not provided'),
            "service_requested": customer_data.get('service', 'Not specified'),
            "price": customer_data.get('price', 'Not quoted'),
            "priority": "normal"
        }
        
        print(f"Sending email notification: {email_data}")
        
        response = requests.post(
            MAKE_WEBHOOK_URL,
            json=email_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print("Email notification sent successfully")
            return True
        else:
            print(f"Email notification failed: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Email notification error: {e}")
        return False

# NEW FEATURE 4: Call supplier function
def supplier_enquiry(customer_request, conversation_id, price):
    """Call supplier for enquiry - ORIGINAL ElevenLabs integration"""
    if not elevenlabs_api_key or not agent_phone_number_id or not agent_id:
        print("ElevenLabs not configured for supplier enquiry")
        return {"success": False, "reason": "no_elevenlabs_config"}
    
    try:
        headers = {
            'Content-Type': 'application/json',
            'xi-api-key': elevenlabs_api_key
        }
        
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
            print(f"Supplier enquiry call initiated: {call_info}")
            return {"success": True, "call_id": call_info.get('call_id')}
        else:
            print(f"Failed to call supplier: {response.status_code} - {response.text}")
            return {"success": False, "reason": "api_call_failed", "error": response.text}
            
    except Exception as e:
        print(f"Supplier enquiry error: {e}")
        return {"success": False, "reason": "exception", "error": str(e)}

def transfer_call_to_supplier(conversation_id):
    """Transfer call to supplier - ORIGINAL"""
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
            print(f"Call transferred to supplier: {SUPPLIER_PHONE}")
            return "I'm transferring you to our specialist team now. Please hold."
        else:
            print(f"Transfer failed: {response.status_code}")
            return f"Please call our team directly at {SUPPLIER_PHONE}. I'll send your details to them."
            
    except Exception as e:
        print(f"Transfer error: {e}")
        return f"Please call our team directly at {SUPPLIER_PHONE}. I'll send your details to them."

# Import agents - ORIGINAL agents with original business rules
from agents import SkipAgent, MAVAgent, GrabAgent, set_supplier_enquiry_function, set_transfer_function

# Initialize agents - ORIGINAL setup
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

# Link functions to agents
set_supplier_enquiry_function(supplier_enquiry)
set_transfer_function(transfer_call_to_supplier)

print("All agents initialized with shared conversation storage")
print(f"Supplier phone configured: {SUPPLIER_PHONE}")
print("Supplier enquiry function linked to agents")
print("Transfer function linked to agents")

print("Environment check:")
print(f"   WASTEKING_BASE_URL: {os.getenv('WASTEKING_BASE_URL', 'Not set')}")
print(f"   WASTEKING_ACCESS_TOKEN: {'Set' if os.getenv('WASTEKING_ACCESS_TOKEN') else 'Not set'}")
print(f"   ELEVENLABS_API_KEY: {'Set' if elevenlabs_api_key else 'Not set'}")
print(f"   AGENT_PHONE_NUMBER_ID: {agent_phone_number_id or 'Not set'}")
print(f"   AGENT_ID: {agent_id or 'Not set'}")
print(f"   MAKE_WEBHOOK_URL: {'Set' if MAKE_WEBHOOK_URL else 'Not set'}")

def is_office_hours():
    """Check if it's office hours - ORIGINAL"""
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
    """ORIGINAL ROUTING with minimal new tracking and email features"""
    message_lower = message.lower()
    
    print(f"ROUTING ANALYSIS: '{message_lower}'")
    
    # NEW: Track message in live conversations
    live_conversations[conversation_id]['messages'].append({
        'timestamp': datetime.now().isoformat(),
        'message': message,
        'type': 'customer_message'
    })
    live_conversations[conversation_id]['last_activity'] = datetime.now().isoformat()
    live_conversations[conversation_id]['conversation_id'] = conversation_id
    
    # Original context checking
    context = shared_conversations.get(conversation_id, {})
    existing_service = context.get('service')
    
    print(f"EXISTING CONTEXT: {context}")
    
    # Original transfer triggers
    transfer_triggers = [
        'speak to someone', 'talk to human', 'manager', 'supervisor', 
        'complaint', 'problem', 'issue', 'not happy', 'transfer me'
    ]
    
    if any(trigger in message_lower for trigger in transfer_triggers):
        print("TRANSFER REQUESTED")
        # NEW: Send transfer email
        customer_data = shared_conversations.get(conversation_id, {})
        send_email_notification(conversation_id, customer_data, "transfer")
        return transfer_call_to_supplier(conversation_id)
    
    # ORIGINAL agent routing - UNCHANGED
    response = ""
    agent_type = ""
    
    if any(word in message_lower for word in ['skip', 'skip hire', 'yard skip', 'cubic yard']):
        print("Routing to Skip Agent (explicit skip mention)")
        response = skip_agent.process_message(message, conversation_id)
        agent_type = "skip"
        
        # NEW: Call supplier for SKIP during office hours ONLY
        if is_office_hours() and context.get('service') == 'skip':
            customer_data = shared_conversations.get(conversation_id, {})
            if customer_data.get('postcode'):
                print("Calling supplier for skip hire - office hours")
                supplier_enquiry(f"Skip hire request: {message}", conversation_id, customer_data.get('price', '0'))
    
    elif any(word in message_lower for word in ['man and van', 'mav', 'man & van', 'van collection', 'small van', 'medium van', 'large van']):
        print("Routing to MAV Agent (explicit mav mention)")
        response = mav_agent.process_message(message, conversation_id)
        agent_type = "mav"
    
    elif any(word in message_lower for word in ['grab', 'grab hire', 'grab lorry', '6 wheeler', '8 wheeler']):
        print("Routing to Grab Agent (explicit grab mention)")
        response = grab_agent.process_message(message, conversation_id)
        agent_type = "grab"
    
    elif existing_service == 'skip':
        print("Routing to Skip Agent (continuing existing skip conversation)")
        response = skip_agent.process_message(message, conversation_id)
        agent_type = "skip"
        
        # NEW: Call supplier for existing skip conversations during office hours
        if is_office_hours():
            customer_data = shared_conversations.get(conversation_id, {})
            if customer_data.get('postcode'):
                print("Calling supplier for skip follow-up - office hours")
                supplier_enquiry(f"Skip follow-up: {message}", conversation_id, customer_data.get('price', '0'))
    
    elif existing_service == 'mav':
        print("Routing to MAV Agent (continuing existing mav conversation)")
        response = mav_agent.process_message(message, conversation_id)
        agent_type = "mav"
        
    elif existing_service == 'grab':
        print("Routing to Grab Agent (continuing existing grab conversation)")
        response = grab_agent.process_message(message, conversation_id)
        agent_type = "grab"
        
    else:
        print("Routing to Qualifying Agent (handles all other requests)")
        response = "I can help you with skip hire, man & van services, and grab lorry services. What type of waste removal service do you need?"
        agent_type = "qualifying"

    # NEW: Track agent response
    live_conversations[conversation_id]['agent_responses'].append({
        'timestamp': datetime.now().isoformat(),
        'response': response,
        'agent_type': agent_type
    })
    
    # NEW: Check for callback/transfer phrases and send emails
    callback_phrases = ['call you back', 'callback', 'team will call', 'call back tomorrow']
    transfer_phrases = ['transfer you', 'put you through', 'connect you']
    
    customer_data = shared_conversations.get(conversation_id, {})
    
    if any(phrase in response.lower() for phrase in callback_phrases):
        print("CALLBACK DETECTED - SENDING EMAIL")
        send_email_notification(conversation_id, customer_data, "callback")
    
    if any(phrase in response.lower() for phrase in transfer_phrases):
        print("TRANSFER DETECTED - SENDING EMAIL")
        send_email_notification(conversation_id, customer_data, "transfer")
    
    return response

@app.route('/')
def index():
    """NEW: Live dashboard showing conversations"""
    html_template = """<!DOCTYPE html>
<html>
<head>
    <title>Live Calls Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; padding: 20px; background: #f5f5f5; }
        .header { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .live { color: #28a745; font-weight: bold; animation: blink 1s infinite; }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin-bottom: 20px; }
        .stat-card { background: white; padding: 20px; border-radius: 10px; text-align: center; }
        .stat-number { font-size: 2rem; font-weight: bold; color: #007bff; }
        .conversation-card { background: white; border-radius: 10px; padding: 15px; margin-bottom: 15px; }
        .customer-info { display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px; margin-bottom: 10px; }
        .timeline { background: #f8f9fa; padding: 10px; border-radius: 5px; max-height: 200px; overflow-y: auto; }
        .message { padding: 5px; margin-bottom: 5px; border-radius: 3px; font-size: 0.9rem; }
        .customer { background: #e3f2fd; border-left: 3px solid #2196f3; }
        .agent { background: #e8f5e8; border-left: 3px solid #4caf50; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Live Calls Dashboard <span class="live">● LIVE</span></h1>
        <p>Real-time conversation tracking with email notifications</p>
    </div>

    <div class="stats">
        <div class="stat-card">
            <div class="stat-number">{{ conversation_count }}</div>
            <div>Active Conversations</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ call_count }}</div>
            <div>Total Calls</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ email_status }}</div>
            <div>Email System</div>
        </div>
        <div class="stat-card">
            <div class="stat-number">{{ supplier_status }}</div>
            <div>Supplier Calls</div>
        </div>
    </div>

    <div style="background: white; padding: 20px; border-radius: 10px;">
        <h3>Live Conversations</h3>
        {% if conversations %}
            {% for conv_id, conv_data in conversations %}
            <div class="conversation-card">
                <div class="customer-info">
                    <div><strong>ID:</strong> {{ conv_id }}</div>
                    <div><strong>Name:</strong> {{ shared_conversations.get(conv_id, {}).get('firstName', 'Not provided') }}</div>
                    <div><strong>Phone:</strong> {{ shared_conversations.get(conv_id, {}).get('phone', 'Not provided') }}</div>
                    <div><strong>Service:</strong> {{ shared_conversations.get(conv_id, {}).get('service', 'Not specified') }}</div>
                    <div><strong>Price:</strong> {{ shared_conversations.get(conv_id, {}).get('price', 'Not quoted') }}</div>
                </div>
                <div class="timeline">
                    {% for item in (conv_data.messages + conv_data.agent_responses) | sort(attribute='timestamp') %}
                        {% if item.message %}
                        <div class="message customer">
                            <strong>Customer:</strong> {{ item.message }}
                            <div style="font-size: 0.7rem; color: #666;">{{ item.timestamp[:19] }}</div>
                        </div>
                        {% else %}
                        <div class="message agent">
                            <strong>Agent:</strong> {{ item.response }}
                            <div style="font-size: 0.7rem; color: #666;">{{ item.timestamp[:19] }}</div>
                        </div>
                        {% endif %}
                    {% endfor %}
                </div>
            </div>
            {% endfor %}
        {% else %}
            <p>No active conversations</p>
        {% endif %}
    </div>

    <script>
        // Auto-refresh every 5 seconds
        setTimeout(() => { window.location.reload(); }, 5000);
    </script>
</body>
</html>"""
    
    return render_template_string(html_template,
        conversation_count=len(live_conversations),
        call_count=len(webhook_calls),
        email_status="ON" if MAKE_WEBHOOK_URL else "OFF",
        supplier_status="ON" if elevenlabs_api_key else "OFF",
        conversations=sorted(live_conversations.items(), key=lambda x: x[1].get('last_activity', ''), reverse=True),
        shared_conversations=shared_conversations
    )

@app.route('/api/webhook/elevenlabs', methods=['POST'])
def elevenlabs_webhook():
    """Receive webhook data from ElevenLabs - ORIGINAL"""
    try:
        data = request.get_json()
        print(f"Received webhook data: {data}")
        
        call_data = {
            'id': f"call_{datetime.now().timestamp()}",
            'timestamp': datetime.now().isoformat(),
            'transcript': data.get('transcript', ''),
            'duration': data.get('duration', 0),
            'conversation_id': data.get('conversation_id', ''),
            'customer_phone': data.get('customer_phone', '') or data.get('from_number', ''),
            'to_number': data.get('to_number', ''),
            'status': data.get('status', 'completed'),
            'call_type': data.get('call_type', 'customer_call'),
            'agent_id': data.get('agent_id', ''),
            'metadata': data.get('metadata', {}),
            'raw_data': data
        }
        
        webhook_calls.append(call_data)
        
        print(f"Webhook stored: {call_data['id']} - Status: {call_data['status']}")
        
        return jsonify({"success": True, "message": "Webhook received", "call_id": call_data['id']})
        
    except Exception as e:
        print(f"Webhook error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """NEW: Get live conversation data"""
    try:
        conversation_list = []
        for conv_id, conv_data in live_conversations.items():
            customer_info = shared_conversations.get(conv_id, {})
            conv_summary = {
                'conversation_id': conv_id,
                'status': conv_data['status'],
                'created_at': conv_data['created_at'],
                'last_activity': conv_data['last_activity'],
                'message_count': len(conv_data['messages']),
                'response_count': len(conv_data['agent_responses']),
                'customer_data': {
                    'name': customer_info.get('firstName', ''),
                    'phone': customer_info.get('phone', ''),
                    'postcode': customer_info.get('postcode', ''),
                    'service': customer_info.get('service', ''),
                    'price': customer_info.get('price', '')
                },
                'messages': conv_data['messages'],
                'agent_responses': conv_data['agent_responses']
            }
            conversation_list.append(conv_summary)
        
        conversation_list.sort(key=lambda x: x['last_activity'], reverse=True)
        
        return jsonify({
            "success": True,
            "conversations": conversation_list,
            "total_count": len(conversation_list)
        })
        
    except Exception as e:
        print(f"Get conversations error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message():
    """ORIGINAL message processing endpoint - UNCHANGED business logic"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        
        # Use provided conversation_id OR create new one
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or data.get('system__conversation_id')
        if not conversation_id:
            conversation_id = get_next_conversation_id()
            print(f"NEW CONVERSATION CREATED: {conversation_id}")
        else:
            print(f"CONTINUING CONVERSATION: {conversation_id}")
        
        print(f"Message: {customer_message}")
        print(f"Conversation: {conversation_id}")
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # Route to appropriate agent - ORIGINAL routing with minimal new features
        response = route_to_agent(customer_message, conversation_id)
        
        print(f"Response: {response}")
        
        return jsonify({
            "success": True,
            "message": response,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({
            "success": True,
            "message": f"Let me connect you with our team who can help immediately. Please call {SUPPLIER_PHONE} or hold while I transfer you.",
            "error": str(e),
            "transfer_to": SUPPLIER_PHONE
        }), 200

@app.route('/api/health')
def health():
    """Health check - ORIGINAL with new feature status"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab"],
        "elevenlabs_configured": bool(elevenlabs_api_key),
        "make_webhook_configured": bool(MAKE_WEBHOOK_URL),
        "supplier_phone": SUPPLIER_PHONE,
        "office_hours": is_office_hours(),
        "features": [
            "Original business rules A1-A7, B1-B6, C1-C5",
            "Email notifications via Make.com",
            "Live conversation tracking",
            "Supplier calling (skip only, office hours)",
            "ElevenLabs webhook integration"
        ],
        "stats": {
            "total_calls": len(webhook_calls),
            "active_conversations": len(live_conversations)
        }
    })

@app.after_request
def after_request(response):
    """Add CORS headers - ORIGINAL"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

if __name__ == '__main__':
    print("Starting WasteKing System with Original Business Rules + Minimal New Features...")
    print("NEW FEATURES:")
    print(f"  📧 Email notifications via Make.com: {'ON' if MAKE_WEBHOOK_URL else 'OFF'}")
    print(f"  📊 Live conversation tracking: ON")
    print(f"  📞 Supplier calling (skip only, office hours): {'ON' if elevenlabs_api_key else 'OFF'}")
    print("PRESERVED:")
    print(f"  ✅ All original business rules A1-A7, B1-B6, C1-C5")
    print(f"  ✅ Original API calls: create_booking, get_pricing, complete_booking")
    print(f"  ✅ Original agent routing and transfer logic")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
