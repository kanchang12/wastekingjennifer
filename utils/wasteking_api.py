# ==========================================
# FILE 3: utils/wasteking_api.py - FIXED NO HARDCODING
# ==========================================

import os
import requests
import json
from datetime import datetime

# WasteKing API Configuration - NO HARDCODING
BASE_URL = os.getenv('WASTEKING_BASE_URL', 'https://wk-smp-api-dev.azurewebsites.net')
ACCESS_TOKEN = os.getenv('WASTEKING_ACCESS_TOKEN', 'wk-KZPY-tGF-@d.Aby9fpvMC_VVWkX-GN.i7jCBhF3xceoFfhmawaNc.RH.G_-kwk8*')

def wasteking_request(endpoint, payload, method="POST"):
    """WasteKing API request function - NO HARDCODING"""
    try:
        url = f"{BASE_URL}/{endpoint}"
        headers = {
            "Content-Type": "application/json",
            "x-wasteking-request": ACCESS_TOKEN
        }
        
        print(f"🌐 API REQUEST: {method} {url}")
        print(f"📦 PAYLOAD: {json.dumps(payload, indent=2)}")
        
        if method == "POST":
            response = requests.post(url, json=payload, headers=headers, timeout=15)
        else:
            response = requests.get(url, params=payload, headers=headers, timeout=15)
        
        print(f"📊 RESPONSE: {response.status_code} - {response.text}")
        
        if response.status_code in [200, 201]:
            try:
                return {"success": True, **response.json()}
            except:
                return {"success": True, "response": response.text}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}", "response": response.text}
            
    except Exception as e:
        print(f"❌ API ERROR: {str(e)}")
        return {"success": False, "error": str(e)}

def create_booking():
    """Step 1: Create booking reference - NO HARDCODING"""
    print("📋 STEP 1: Creating booking...")
    payload = {"type": "chatbot", "source": "wasteking.co.uk"}
    result = wasteking_request("api/booking/create", payload)
    
    if result.get('success'):
        booking_ref = result.get('bookingRef') or result.get('booking_ref')
        print(f"✅ BOOKING REF: {booking_ref}")
        return {"success": True, "booking_ref": booking_ref}
    return result

def get_pricing(booking_ref,# FILE 1: app.py (Flask Application) - NO HARDCODING
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
    
    #
