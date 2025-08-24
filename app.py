import os
import json
from datetime import datetime
from flask import Flask, request, jsonify

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

# Initialize agents
skip_agent = SkipAgent(rules_processor)
mav_agent = MAVAgent(rules_processor)
grab_agent = GrabAgent(rules_processor)

print("✅ All agents initialized")
print("🔧 Environment check:")
print(f"   WASTEKING_BASE_URL: {os.getenv('WASTEKING_BASE_URL', 'Not set')}")
print(f"   WASTEKING_ACCESS_TOKEN: {'Set' if os.getenv('WASTEKING_ACCESS_TOKEN') else 'Not set'}")

def route_to_agent(message, conversation_id):
    """Route message to appropriate agent"""
    message_lower = message.lower()
    
    # Check for explicit service mentions
    if any(word in message_lower for word in ['skip', 'skip hire']):
        print("🔄 Routing to Skip Agent")
        return skip_agent.process_message(message, conversation_id)
    
    elif any(word in message_lower for word in ['man and van', 'mav', 'van']):
        print("🔄 Routing to MAV Agent") 
        return mav_agent.process_message(message, conversation_id)
    
    elif any(word in message_lower for word in ['grab', 'grab hire']):
        print("🔄 Routing to Grab Agent")
        return grab_agent.process_message(message, conversation_id)
    
    else:
        # Default to skip agent
        print("🔄 Routing to Skip Agent (default)")
        return skip_agent.process_message(message, conversation_id)

@app.route('/')
def index():
    return jsonify({
        "message": "WasteKing Simple System",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "agents": ["Skip", "MAV", "Grab"],
        "features": [
            "4-step WasteKing API booking",
            "Simple agent routing",
            "Rules-based responses",
            "Sequential question asking"
        ]
    })

@app.route('/api/wasteking', methods=['POST'])
def process_message():
    """Main endpoint for processing customer messages"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('elevenlabs_conversation_id', f"conv_{int(datetime.now().timestamp())}")
        
        print(f"📩 Message: {customer_message}")
        print(f"🆔 Conversation: {conversation_id}")
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # Route to appropriate agent
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
    """Test WasteKing API directly"""
    try:
        from utils.wasteking_api import create_booking, get_pricing, complete_booking
        
        data = request.get_json() or {}
        action = data.get('action', 'create_booking')
        
        if action == 'create_booking':
            result = create_booking()
        elif action == 'get_pricing':
            result = get_pricing(
                data.get('booking_ref'),
                data.get('postcode', 'LU1 1DQ'),
                data.get('service', 'skip')
            )
        elif action == 'complete_booking':
            result = complete_booking({
                'firstName': data.get('firstName', 'Test'),
                'phone': data.get('phone', '01234567890'),
                'postcode': data.get('postcode', 'LU1 1DQ'),
                'service': data.get('service', 'skip')
            })
        else:
            result = {"success": False, "error": "Unknown action"}
        
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
        "agents": ["Skip", "MAV", "Grab"],
        "rules_loaded": bool(rules_processor),
        "api_configured": bool(os.getenv('WASTEKING_ACCESS_TOKEN'))
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
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
