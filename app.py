import os
import json
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, render_template
from collections import defaultdict

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
    
    # Group calls by conversation ID for the dashboard view
    grouped_calls = defaultdict(list)
    for call in sorted(webhook_calls, key=lambda x: x.get('timestamp', ''), reverse=True):
        conversation_id = call.get('conversation_id', 'Unassigned')
        grouped_calls[conversation_id].append(call)
        
    return render_template(
        'index.html',
        grouped_calls=grouped_calls,
        call_count=len(webhook_calls)
    )

@app.route('/api/dashboard/live_calls', methods=['GET'])
def get_live_calls():
    """New endpoint for the dashboard to get live call updates."""
    try:
        last_conv_id = request.args.get('last_id')
        new_calls = []
        found_last = False
        
        # Iterate backward to find the last received call
        for call in reversed(webhook_calls):
            if call.get('conversation_id') == last_conv_id:
                found_last = True
                break
            new_calls.append(call)
        
        # Reverse the list to get them in chronological order
        new_calls.reverse()
        
        return jsonify({
            "success": True,
            "new_calls": new_calls,
            "total_count": len(webhook_calls)
        })
    except Exception as e:
        print(f"Live calls API error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/wasteking-chatbot.js')
def serve_chatbot_js():
    return send_from_directory('static', 'wasteking-chatbot.js')
@app.route('/api/dashboard/live_calls', methods=['GET'])
def get_live_calls():
    """New endpoint for the dashboard to get live call updates."""
    try:
        last_conv_id = request.args.get('last_id')
        new_calls = []
        found_last = False
        
        # Iterate backward to find the last received call
        for call in reversed(webhook_calls):
            if call.get('conversation_id') == last_conv_id:
                found_last = True
                break
            new_calls.append(call)
        
        # Reverse the list to get them in chronological order
        new_calls.reverse()
        
        return jsonify({
            "success": True,
            "new_calls": new_calls,
            "total_count": len(webhook_calls)
        })
    except Exception as e:
        print(f"Live calls API error: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

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
    print("   ✅ Grab agent is DEFAULT MANAGER - handles everything except explicit skip/mav")
    print("   ✅ Payment link creation (Step 4) FIXED")
    print("   ✅ NO HARDCODED PRICES - REAL API ONLY")
    print("   ✅ Mock rules processor (rules functionality disabled)")
    print("   ✅ All agent initialization issues resolved")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
