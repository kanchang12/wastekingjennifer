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

# NEW: Make.com webhook URL for out-of-office callbacks
MAKE_WEBHOOK_URL = os.getenv('MAKE_WEBHOOK_URL')

# Global conversation counter and call storage
conversation_counter = 0
webhook_calls = []  # Store webhook call data

# NEW: Enhanced conversation tracking by conversation ID
conversations_by_id = defaultdict(lambda: {
    'conversation_id': '',
    'calls': [],
    'messages': [],
    'customer_data': {},
    'agent_responses': [],
    'status': 'active',
    'created_at': datetime.now().isoformat(),
    'last_activity': datetime.now().isoformat(),
    'call_summary': {}
})

def get_next_conversation_id():
    """Generate next conversation ID with counter"""
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

# NEW: Send callback request to make.com webhook
def send_callback_to_make(conversation_id, customer_data, reason="out_of_office"):
    """Send callback request details to make.com webhook for email notification"""
    if not MAKE_WEBHOOK_URL:
        print("⚠️ MAKE_WEBHOOK_URL not configured")
        return False
    
    try:
        # Prepare callback summary data
        callback_data = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "customer_name": customer_data.get('firstName', 'Not provided'),
            "customer_phone": customer_data.get('phone', 'Not provided'),
            "customer_postcode": customer_data.get('postcode', 'Not provided'),
            "service_requested": customer_data.get('service', 'Not specified'),
            "waste_type": customer_data.get('waste_type', 'Not specified'),
            "callback_type": "out_of_office",
            "priority": "normal"
        }
        
        print(f"📧 Sending callback request to Make.com: {callback_data}")
        
        response = requests.post(
            MAKE_WEBHOOK_URL,
            json=callback_data,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if response.status_code == 200:
            print(f"✅ Callback request sent to Make.com successfully")
            return True
        else:
            print(f"❌ Failed to send callback to Make.com: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Make.com webhook error: {e}")
        return False

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
            
            # NEW: Also add to conversation tracking
            conversations_by_id[conversation_id]['calls'].append(supplier_call)
            
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
print(f"   MAKE_WEBHOOK_URL: {'Set' if MAKE_WEBHOOK_URL else 'Not set'}")

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
    """ENHANCED ROUTING WITH PROPER EMAIL AND SUPPLIER CALLING"""
    message_lower = message.lower()
    
    print(f"🔍 ROUTING ANALYSIS: '{message_lower}'")
    
    # NEW: Track this message in conversation
    conversations_by_id[conversation_id]['messages'].append({
        'timestamp': datetime.now().isoformat(),
        'message': message,
        'type': 'customer_message'
    })
    conversations_by_id[conversation_id]['last_activity'] = datetime.now().isoformat()
    conversations_by_id[conversation_id]['conversation_id'] = conversation_id
    
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
        # Send email for transfer
        customer_data = shared_conversations.get(conversation_id, {})
        send_callback_to_make(conversation_id, customer_data, "transfer_request")
        return transfer_call_to_supplier(conversation_id)
    
    # Route to appropriate agent and handle response
    response = ""
    agent_type = ""
    
    # PRIORITY 1: Skip Agent - ONLY explicit skip mentions
    if any(word in message_lower for word in ['skip', 'skip hire', 'yard skip', 'cubic yard']):
        print("🔄 Routing to Skip Agent (explicit skip mention)")
        response = skip_agent.process_message(message, conversation_id)
        agent_type = "skip"
        
        # CALL SUPPLIER FOR SKIP HIRE DURING OFFICE HOURS ONLY
        if context.get('service') == 'skip' and is_office_hours():
            customer_data = shared_conversations.get(conversation_id, {})
            if customer_data.get('postcode') and customer_data.get('firstName'):
                print("📞 CALLING SUPPLIER FOR SKIP HIRE - OFFICE HOURS")
                supplier_enquiry(f"Skip hire request from {customer_data.get('firstName')} at {customer_data.get('postcode')}", conversation_id, customer_data.get('price', '0'))
    
    # PRIORITY 2: MAV Agent - ONLY explicit man and van mentions  
    elif any(word in message_lower for word in ['man and van', 'mav', 'man & van', 'van collection', 'small van', 'medium van', 'large van']):
        print("🔄 Routing to MAV Agent (explicit mav mention)")
        response = mav_agent.process_message(message, conversation_id)
        agent_type = "mav"
    
    # PRIORITY 3: Grab Agent - explicit grab mentions
    elif any(word in message_lower for word in ['grab', 'grab hire', 'grab lorry', '6 wheeler', '8 wheeler']):
        print("🔄 Routing to Grab Agent (explicit grab mention)")
        response = grab_agent.process_message(message, conversation_id)
        agent_type = "grab"
    
    # PRIORITY 4: Continue with existing service if available
    elif existing_service == 'skip':
        print("🔄 Routing to Skip Agent (continuing existing skip conversation)")
        response = skip_agent.process_message(message, conversation_id)
        agent_type = "skip"
        
        # CALL SUPPLIER FOR SKIP HIRE DURING OFFICE HOURS ONLY
        if is_office_hours():
            customer_data = shared_conversations.get(conversation_id, {})
            if customer_data.get('postcode') and customer_data.get('firstName'):
                print("📞 CALLING SUPPLIER FOR SKIP HIRE - OFFICE HOURS")
                supplier_enquiry(f"Skip hire request from {customer_data.get('firstName')} at {customer_data.get('postcode')}", conversation_id, customer_data.get('price', '0'))
    
    elif existing_service == 'mav':
        print("🔄 Routing to MAV Agent (continuing existing mav conversation)")
        response = mav_agent.process_message(message, conversation_id)
        agent_type = "mav"
        
    elif existing_service == 'grab':
        print("🔄 Routing to Grab Agent (continuing existing grab conversation)")
        response = grab_agent.process_message(message, conversation_id)
        agent_type = "grab"
        
    elif existing_service == 'qualifying':
        pass
    
    # PRIORITY 5: NEW - Qualifying Agent handles EVERYTHING ELSE (unknown/other services)
    else:
        print("🔄 Routing to Qualifying Agent (handles all other requests and unknown services)")
        response = "I can help you with skip hire, man & van services, and grab lorry services. What type of waste removal service do you need?"
        agent_type = "qualifying"

    # NEW: Track agent response
    conversations_by_id[conversation_id]['agent_responses'].append({
        'timestamp': datetime.now().isoformat(),
        'response': response,
        'agent_type': agent_type
    })
    
    # CHECK FOR TRANSFERS AND CALLBACKS - SEND EMAILS
    callback_phrases = [
        'call you back', 'callback', 'team will call', 'call back tomorrow',
        'team call you back', 'our team will contact', 'call you first thing',
        'have our team call', 'specialist team call', 'director call you back'
    ]
    
    transfer_phrases = [
        'transfer you', 'put you through', 'connect you', 'transfer to',
        'speak to our team', 'let me put you through', 'transfer call'
    ]
    
    customer_data = shared_conversations.get(conversation_id, {})
    
    # Send email for callbacks
    if any(phrase in response.lower() for phrase in callback_phrases):
        print("📧 CALLBACK DETECTED - SENDING EMAIL")
        send_callback_to_make(conversation_id, customer_data, "callback_request")
    
    # Send email for transfers
    if any(phrase in response.lower() for phrase in transfer_phrases):
        print("📧 TRANSFER DETECTED - SENDING EMAIL")
        send_callback_to_make(conversation_id, customer_data, "transfer_request")
    
    return response

@app.route('/')
def index():
    """NEW: Enhanced dashboard showing conversations by ID"""
    html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WasteKing Enhanced Call Tracker</title>
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
            max-width: 1600px;
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

        .conversations-section {
            background: rgba(255, 255, 255, 0.9);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
        }

        .conversations-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }

        .conversations-title {
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

        .conversation-card {
            background: white;
            border-radius: 15px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            overflow: hidden;
        }

        .conversation-header {
            background: #667eea;
            color: white;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .conversation-id {
            font-weight: 700;
            font-size: 1.2rem;
        }

        .conversation-status {
            padding: 4px 12px;
            border-radius: 15px;
            font-size: 0.8rem;
            font-weight: 600;
            background: rgba(255, 255, 255, 0.2);
        }

        .conversation-details {
            padding: 20px;
        }

        .customer-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-bottom: 20px;
            padding: 15px;
            background: #f7fafc;
            border-radius: 10px;
        }

        .info-item {
            display: flex;
            flex-direction: column;
        }

        .info-label {
            font-weight: 600;
            color: #4a5568;
            font-size: 0.8rem;
            text-transform: uppercase;
            margin-bottom: 5px;
        }

        .info-value {
            color: #2d3748;
            font-weight: 500;
        }

        .messages-timeline {
            margin-top: 20px;
        }

        .timeline-item {
            display: flex;
            margin-bottom: 15px;
            padding: 15px;
            border-radius: 10px;
        }

        .customer-message {
            background: #e6fffa;
            border-left: 4px solid #38b2ac;
        }

        .agent-response {
            background: #f0fff4;
            border-left: 4px solid #48bb78;
        }

        .message-timestamp {
            font-size: 0.8rem;
            color: #4a5568;
            margin-bottom: 5px;
        }

        .message-content {
            color: #2d3748;
            line-height: 1.5;
        }

        .agent-type {
            display: inline-block;
            padding: 2px 8px;
            background: #667eea;
            color: white;
            border-radius: 12px;
            font-size: 0.7rem;
            margin-left: 10px;
        }

        .empty-conversations {
            text-align: center;
            padding: 60px 30px;
            color: #4a5568;
        }

        .empty-conversations h3 {
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
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>WasteKing Enhanced Call Tracker</h1>
            <p>Complete Conversation Tracking with Make.com Integration</p>
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
                    <div class="config-label">Make.com Webhook</div>
                    <div class="config-value {{ 'status-ok' if make_configured else 'status-missing' }}">
                        {{ 'Configured' if make_configured else 'Not configured' }}
                    </div>
                </div>
                <div class="config-item">
                    <div class="config-label">Supplier Phone</div>
                    <div class="config-value status-ok">{{ supplier_phone }}</div>
                </div>
            </div>
            
            <div class="webhook-url">
                <strong>Webhook URL for ElevenLabs:</strong><br>
                {{ webhook_url }}<br><br>
                <strong>Features:</strong> Out-of-office callback detection & Make.com email integration
            </div>
        </div>

        <div class="conversations-section">
            <div class="conversations-header">
                <h2 class="conversations-title">Live Conversations ({{ conversation_count }})</h2>
                <button class="refresh-btn" onclick="window.location.reload()">Refresh</button>
            </div>

            {% if conversations %}
                {% for conv_id, conv_data in conversations %}
                <div class="conversation-card">
                    <div class="conversation-header">
                        <div class="conversation-id">{{ conv_id }}</div>
                        <div class="conversation-status">{{ conv_data.status.title() }}</div>
                    </div>
                    
                    <div class="conversation-details">
                        <!-- Customer Information -->
                        {% if conv_data.customer_data or shared_conversations.get(conv_id) %}
                        <div class="customer-info">
                            <div class="info-item">
                                <div class="info-label">Customer Name</div>
                                <div class="info-value">{{ shared_conversations.get(conv_id, {}).get('firstName', 'Not provided') }}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Phone</div>
                                <div class="info-value">{{ shared_conversations.get(conv_id, {}).get('phone', 'Not provided') }}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Postcode</div>
                                <div class="info-value">{{ shared_conversations.get(conv_id, {}).get('postcode', 'Not provided') }}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Service</div>
                                <div class="info-value">{{ shared_conversations.get(conv_id, {}).get('service', 'Not specified') }}</div>
                            </div>
                            <div class="info-item">
                                <div class="info-label">Last Activity</div>
                                <div class="info-value">{{ conv_data.last_activity[:19] if conv_data.last_activity else 'N/A' }}</div>
                            </div>
                        </div>
                        {% endif %}

                        <!-- Messages Timeline -->
                        {% if conv_data.messages or conv_data.agent_responses %}
                        <div class="messages-timeline">
                            <h4 style="margin-bottom: 15px; color: #2d3748;">Conversation Timeline</h4>
                            
                            <!-- Combine and sort messages and responses by timestamp -->
                            {% for item in (conv_data.messages + conv_data.agent_responses) | sort(attribute='timestamp') %}
                                {% if item.message %}
                                <!-- Customer Message -->
                                <div class="timeline-item customer-message">
                                    <div style="flex: 1;">
                                        <div class="message-timestamp">Customer - {{ item.timestamp[:19] }}</div>
                                        <div class="message-content">{{ item.message }}</div>
                                    </div>
                                </div>
                                {% else %}
                                <!-- Agent Response -->
                                <div class="timeline-item agent-response">
                                    <div style="flex: 1;">
                                        <div class="message-timestamp">
                                            Agent Response - {{ item.timestamp[:19] }}
                                            <span class="agent-type">{{ item.agent_type.upper() }}</span>
                                        </div>
                                        <div class="message-content">{{ item.response }}</div>
                                    </div>
                                </div>
                                {% endif %}
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                </div>
                {% endfor %}
            {% else %}
            <div class="empty-conversations">
                <h3>No Active Conversations</h3>
                <p>System is ready to track conversations and send callback notifications to Make.com</p>
            </div>
            {% endif %}
        </div>
    </div>

    <script>
        let isUpdating = false;
        let lastUpdateTime = new Date().getTime();
        
        // Real-time polling every 2 seconds
        async function fetchLiveUpdates() {
            if (isUpdating) return;
            
            try {
                isUpdating = true;
                const response = await fetch('/api/conversations?timestamp=' + lastUpdateTime);
                const data = await response.json();
                
                if (data.success && data.conversations.length > 0) {
                    // Check if there are new updates
                    const hasNewData = data.conversations.some(conv => 
                        new Date(conv.last_activity).getTime() > lastUpdateTime
                    );
                    
                    if (hasNewData) {
                        console.log('New conversation data detected - refreshing...');
                        window.location.reload();
                    }
                }
                
                lastUpdateTime = new Date().getTime();
            } catch (error) {
                console.error('Update error:', error);
            } finally {
                isUpdating = false;
            }
        }
        
        // Start real-time updates every 2 seconds
        setInterval(fetchLiveUpdates, 2000);
        
        // Also refresh every 10 seconds as backup
        setInterval(() => {
            window.location.reload();
        }, 10000);
        
        // Visual indicator for live updates
        const header = document.querySelector('.header h1');
        if (header) {
            const liveIndicator = document.createElement('span');
            liveIndicator.innerHTML = ' <span style="color: #48bb78; font-size: 0.8rem;">● LIVE</span>';
            header.appendChild(liveIndicator);
            
            // Blink the live indicator
            setInterval(() => {
                liveIndicator.style.opacity = liveIndicator.style.opacity === '0.5' ? '1' : '0.5';
            }, 1000);
        }
        
        console.log('Real-time dashboard loaded - tracking {{ conversation_count }} conversations');
    </script>
</body>
</html>"""
    
    return render_template_string(html_template,
        elevenlabs_configured=bool(elevenlabs_api_key),
        make_configured=bool(MAKE_WEBHOOK_URL),
        agent_phone_id=agent_phone_number_id,
        agent_id=agent_id,
        supplier_phone=SUPPLIER_PHONE,
        webhook_url=request.url_root + 'api/webhook/elevenlabs',
        conversations=sorted(conversations_by_id.items(), key=lambda x: x[1].get('last_activity', ''), reverse=True),
        conversation_count=len(conversations_by_id),
        shared_conversations=shared_conversations
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
            'call_type': data.get('call_type', 'customer_call'),
            'agent_id': data.get('agent_id', ''),
            'metadata': data.get('metadata', {}),
            'raw_data': data
        }
        
        webhook_calls.append(call_data)
        
        # NEW: Also add to conversation tracking
        conv_id = data.get('conversation_id', '')
        if conv_id:
            conversations_by_id[conv_id]['calls'].append(call_data)
            conversations_by_id[conv_id]['last_activity'] = datetime.now().isoformat()
        
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
        
        filtered_calls = webhook_calls.copy()
        
        if call_type:
            filtered_calls = [call for call in filtered_calls if call.get('call_type') == call_type]
        
        if status:
            filtered_calls = [call for call in filtered_calls if call.get('status') == status]
        
        # Sort by timestamp (newest first) and limit
        try:
            sorted_calls = sorted(filtered_calls, key=lambda x: x.get('timestamp', ''), reverse=True)[:limit]
        except:
            sorted_calls = filtered_calls[:limit]
        
        response_data = {
            "success": True, 
            "calls": sorted_calls,
            "total_count": len(webhook_calls),
            "filtered_count": len(sorted_calls)
        }
        
        response = jsonify(response_data)
        response.headers['Content-Type'] = 'application/json'
        return response
        
    except Exception as e:
        print(f"❌ Get calls error: {e}")
        error_response = jsonify({"success": False, "error": str(e), "calls": []})
        error_response.headers['Content-Type'] = 'application/json'
        return error_response, 500

# NEW: API endpoint to get conversations data with timestamp filtering
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    """Get all conversation data organized by conversation ID with real-time filtering"""
    try:
        timestamp_filter = request.args.get('timestamp')
        
        conversation_list = []
        for conv_id, conv_data in conversations_by_id.items():
            # Include customer data from shared_conversations
            customer_info = shared_conversations.get(conv_id, {})
            conv_summary = {
                'conversation_id': conv_id,
                'status': conv_data['status'],
                'created_at': conv_data['created_at'],
                'last_activity': conv_data['last_activity'],
                'message_count': len(conv_data['messages']),
                'response_count': len(conv_data['agent_responses']),
                'call_count': len(conv_data['calls']),
                'customer_data': {
                    'name': customer_info.get('firstName', ''),
                    'phone': customer_info.get('phone', ''),
                    'postcode': customer_info.get('postcode', ''),
                    'service': customer_info.get('service', ''),
                    'waste_type': customer_info.get('waste_type', ''),
                    'price': customer_info.get('price', ''),
                    'supplements': customer_info.get('supplements', [])  # NEW: Include supplements
                },
                'messages': conv_data['messages'],
                'agent_responses': conv_data['agent_responses'],
                'calls': conv_data['calls']
            }
            
            # Filter by timestamp if provided
            if timestamp_filter:
                try:
                    filter_time = float(timestamp_filter) / 1000  # Convert JS timestamp to seconds
                    last_activity_time = datetime.fromisoformat(conv_data['last_activity']).timestamp()
                    if last_activity_time <= filter_time:
                        continue  # Skip this conversation as it hasn't been updated
                except:
                    pass  # If timestamp parsing fails, include all conversations
            
            conversation_list.append(conv_summary)
        
        # Sort by last activity
        conversation_list.sort(key=lambda x: x['last_activity'], reverse=True)
        
        return jsonify({
            "success": True,
            "conversations": conversation_list,
            "total_count": len(conversation_list),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Get conversations error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message():
    """Main endpoint for processing customer messages with enhanced supplier enquiry"""
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
        
        # Route to appropriate agent with ENHANCED routing including callback detection
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
        "agents": ["Skip", "MAV", "Grab"],
        "elevenlabs_configured": bool(elevenlabs_api_key),
        "make_webhook_configured": bool(MAKE_WEBHOOK_URL),
        "supplier_phone": SUPPLIER_PHONE,
        "office_hours": is_office_hours(),
        "features": [
            "ElevenLabs webhook integration",
            "Supplier enquiry calls during pricing",
            "Enhanced conversation tracking by ID", 
            "Make.com callback email integration",
            "Real-time conversation display",
            "All transfers to +447394642517"
        ],
        "stats": {
            "total_calls": len(webhook_calls),
            "active_conversations": len(conversations_by_id),
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
        <h1>WasteKing Enhanced System Test</h1>
        <p>If you can see this page, the Flask app is running correctly.</p>
        <p>System Status: <strong>ONLINE</strong></p>
        <p>New Features: <strong>Conversation tracking + Make.com integration</strong></p>
        <ul>
            <li><a href="/">Main Dashboard</a></li>
            <li><a href="/api/health">Health Check API</a></li>
            <li><a href="/api/webhook/calls">Webhook Calls API</a></li>
            <li><a href="/api/conversations">Conversations API</a></li>
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
    print("🚀 Starting Enhanced WasteKing System with Make.com Integration...")
    print("🔧 NEW FEATURES:")
    print(f"  📞 Supplier enquiry calls during pricing to: {SUPPLIER_PHONE}")
    print(f"  📊 Complete conversation tracking by ID")
    print(f"  📧 Out-of-office callback detection & Make.com email integration")
    print(f"  🔄 All transfers go to: {SUPPLIER_PHONE}")
    print(f"  📡 ElevenLabs webhook: {'Configured' if elevenlabs_api_key else 'Not configured'}")
    print(f"  🔗 Make.com webhook: {'Configured' if MAKE_WEBHOOK_URL else 'Not configured'}")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
