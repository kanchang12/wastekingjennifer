import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory

# Import your existing rules processor
from utils.rules_processor import RulesProcessor

# Import the simple agents
from agents import SkipAgent, MAVAgent, GrabAgent

app = Flask(__name__)

# Initialize system
print("🚀 Initializing WasteKing Simple System...")

# Load rules
rules_processor = RulesProcessor()
print("📋 Rules processor loaded")

# Initialize agents with shared conversation storage
shared_conversations = {}

skip_agent = SkipAgent(rules_processor)
skip_agent.conversations = shared_conversations

mav_agent = MAVAgent(rules_processor)  
mav_agent.conversations = shared_conversations

grab_agent = GrabAgent(rules_processor)
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
    return jsonify({
        "message": "WasteKing Simple System - COMPLETE FIXED VERSION",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab"],
        "routing_rules": {
            "skip": "Handles explicit skip mentions only",
            "mav": "Handles explicit man and van mentions only", 
            "grab": "DEFAULT MANAGER - handles everything else including grab, general inquiries, unknown services"
        },
        "features": [
            "FIXED 4-step WasteKing API booking with payment link creation",
            "FIXED agent routing - Grab handles everything except explicit skip/mav",
            "Rules-based responses with office hours checks",
            "NO HARDCODED PRICES - ALL prices from real API",
            "SMS integration with Twilio"
        ],
        "booking_process": [
            "Step 1: Create booking reference",
            "Step 2: Get pricing with type parameter - REAL API PRICES ONLY",
            "Step 3: Update customer details", 
            "Step 4: CREATE PAYMENT LINK (FIXED)",
            "Step 5: Send SMS with payment link"
        ]
    })

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
        conversation_id = f"conv_{int(datetime.now().timestamp())}"
        
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
        "rules_loaded": bool(rules_processor),
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
    print("  ✅ Office hours checks implemented")
    print("  ✅ Two-situation rule validation")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
