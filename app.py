import os
import re
import json
import requests
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS

# API Integration
try:
    from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    print("WARNING: Live wasteking_api module not found. The system cannot process bookings.")
    def create_booking(): return {'success': False, 'error': 'API unavailable'}
    def get_pricing(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def complete_booking(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def create_payment_link(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}

# --- COMPREHENSIVE BUSINESS RULES ---
OFFICE_HOURS = {
    'monday_thursday': {'start': 8, 'end': 17},
    'friday': {'start': 8, 'end': 16.5},
    'saturday': {'start': 9, 'end': 12},
    'sunday': 'closed'
}

SKIP_HIRE_RULES = {
    'heavy_materials_response': "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard. Shall I get you the cost of an 8-yard skip?",
    'prohibited_items_full': "Just so you know, there are some prohibited items that cannot be placed in skips — including mattresses (£15 charge), fridges (£20 charge), upholstery, plasterboard, asbestos, and paint. Our man and van service is ideal for light rubbish and can remove most items. If you'd prefer, I can connect you with the team to discuss the man and van option. Would you like to speak to the team about that, or continue with skip hire?",
    'plasterboard_response': "Plasterboard isn't allowed in normal skips. If you have a lot, we can arrange a special plasterboard skip, or our man and van service can collect it for you",
    'fridge_mattress_restrictions': "There may be restrictions on fridges & mattresses depending on your location",
    'delivery_timing': "We usually aim to deliver your skip the next day, but during peak months, it may take a bit longer. Don't worry though – we'll check with the depot to get it to you as soon as we can, and we'll always do our best to get it on the day you need.",
    'not_booking_response': "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book. Would you like a £10 discount? If you're happy with the service after booking, you'll have the option to leave a review.",
    'vat_note': 'If the prices are coming from SMP they are always + VAT',
    'roro_heavy_materials': "For heavy materials like soil & rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only."
}

SKIP_COLLECTION_RULES = {
    'script': "I can help with that. It can take between 1-4 days to collect a skip. Can I have your postcode, first line of the address, your name, your telephone number, is the skip a level load, can you confirm there are no prohibited items in the skip, are there any access issues?",
    'completion': "Thanks we can book your skip collection"
}

MAV_RULES = {
    'volume_explanation': "Our team charges by the cubic yard which means we only charge by what we remove. To give you an idea, two washing machines equal about one cubic yard. On average, most clearances we do are around six yards. How many yards do you want to book with us?",
    'heavy_materials_response': "The man and van are ideal for light waste rather than heavy materials - a skip might be more suitable, since our man and van service is designed for lighter waste.",
    'supplement_check': "Can I just check — do you have any mattresses, upholstery, or fridges that need collecting?",
    'sunday_response': "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help",
    'time_restriction': "We can't guarantee exact times, but collection is typically between 7am-6pm"
}

GRAB_RULES = {
    '6_wheeler_explanation': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry.",
    '8_wheeler_explanation': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
    'mixed_materials_response': "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you.",
    'transfer_message': "Most of the prices for grabs are not on SMP so I'll transfer you to a human specialist."
}

LG_SERVICES_QUESTIONS = {
    'road_sweeper': [
        "Can I take your postcode?",
        "How many hours do you require?",
        "Is there tipping on site or do we have to take it away?", 
        "When do you require this?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'toilet_hire': [
        "Can I take your postcode?",
        "How many portaloos do you require?",
        "Is this for an event or longer term?",
        "How long do you need it for?",
        "What date do you need delivery?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'asbestos': [
        "Can I take your postcode?",
        "Do you need a skip or just a collection?",
        "What type of asbestos is it?",
        "Is this a dismantle & disposal or just a collection & disposal?",
        "How much do you have?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'hazardous_waste': [
        "What's your name?",
        "Can I take your postcode?",
        "What type of hazardous waste do you have?",
        "Do you have a data sheet?",
        "What's the best phone number to contact you on?"
    ],
    'wheelie_bins': [
        "Can I take your postcode?",
        "Are you a domestic or commercial customer?",
        "What is the waste type?",
        "What size bin do you require and how many?",
        "How often will you need a waste collection?",
        "How long do you require it for?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'aggregates': [
        "Can I take your postcode?",
        "Do you need tipper or grab delivery?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'wait_and_load': [
        "Can I take your postcode?",
        "What waste will be going into the skip?",
        "When do you require it?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ],
    'roro': [
        "Can I take your postcode?",
        "What type of waste will you be putting in the RORO?",
        "What's your name?",
        "What's the best phone number to contact you on?"
    ]
}

WASTE_BAGS_INFO = {
    'script': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready"
}

GENERAL_SCRIPTS = {
    'timing_query': "Orders are completed between 6am and 5pm. If you need a specific time, I'll raise a ticket and the team will get back to you shortly. Is there anything else I can help you with?",
    'location_response': "I am based in the head office although we have depots nationwide and local to you.",
    'human_request': "Yes I can see if someone is available. What's your name, your telephone number, what is your company name? What is the call regarding?",
    'lg_transfer_message': "I will take some information from you before passing onto our specialist team to give you a cost and availability",
    'closing': "Is there anything else I can help with? Thanks for trusting Waste King"
}

SKIP_SIZES = ['2yd', '4yd', '6yd', '8yd', '10yd', '12yd', '14yd', '16yd', '20yd']

# Updated OpenAI Functions with comprehensive rules
OPENAI_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "handle_skip_hire",
            "description": "Handle all skip hire inquiries including new bookings, pricing, and questions. Always check for heavy materials and prohibited items. This is the ONLY service that gets immediate pricing and booking.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "postcode": {"type": "string", "description": "Customer's full postcode"},
                    "customer_type": {"type": "string", "enum": ["domestic", "trade"], "description": "Customer type"},
                    "skip_size": {"type": "string", "enum": ["2yd", "4yd", "6yd", "8yd", "10yd", "12yd", "14yd", "16yd", "20yd"], "description": "Skip size requested"},
                    "waste_type": {"type": "string", "description": "Type of waste (heavy materials, general waste, etc.)"},
                    "inquiry_type": {"type": "string", "enum": ["pricing", "booking", "prohibited_items", "delivery_time", "permits"], "description": "Type of skip inquiry"}
                },
                "required": ["customer_type", "inquiry_type"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "complete_skip_booking",
            "description": "Complete skip booking after customer confirms. Only call after pricing provided and customer agrees.",
            "parameters": {
                "type": "object",
                "properties": {
                    "confirmation": {"type": "boolean", "description": "Customer wants to proceed"}
                },
                "required": ["confirmation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_skip_collection",
            "description": "Handle skip collection requests (different from hire). This is an LG service requiring specific questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "postcode": {"type": "string", "description": "Customer's postcode"},
                    "address_line1": {"type": "string", "description": "First line of address"},
                    "level_load": {"type": "string", "description": "Is skip a level load"},
                    "prohibited_check": {"type": "string", "description": "Confirmation no prohibited items"},
                    "access_issues": {"type": "string", "description": "Any access issues"}
                },
                "required": ["customer_name", "phone_number", "postcode"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_mav_service",
            "description": "Handle Man & Van services (house clearance, furniture removal). ALL Man & Van are LG services requiring human callback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "postcode": {"type": "string", "description": "Customer's postcode"},
                    "customer_type": {"type": "string", "enum": ["domestic", "trade"], "description": "Customer type"},
                    "volume_yards": {"type": "string", "description": "Estimated volume in cubic yards"},
                    "when_required": {"type": "string", "description": "When collection needed"},
                    "supplement_items": {"type": "string", "description": "Mattresses, upholstery, fridges"},
                    "collection_location": {"type": "string", "description": "Collection details (floor, access, etc.)"},
                    "waste_type": {"type": "string", "description": "Type of waste to collect"}
                },
                "required": ["customer_name", "phone_number", "postcode", "customer_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_grab_hire",
            "description": "Handle Grab Hire services. ALL Grab services are LG requiring human callback due to pricing not in SMP.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "postcode": {"type": "string", "description": "Customer's postcode"},
                    "customer_type": {"type": "string", "enum": ["domestic", "trade"], "description": "Customer type"},
                    "grab_type": {"type": "string", "enum": ["6_wheeler", "8_wheeler"], "description": "Grab lorry type"},
                    "material_type": {"type": "string", "description": "Material type (soil, rubble, mixed)"},
                    "when_required": {"type": "string", "description": "When service needed"},
                    "access_details": {"type": "string", "description": "Site access information"}
                },
                "required": ["customer_name", "phone_number", "postcode", "customer_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_lg_service",
            "description": "Handle all LG (Lead Generation) services requiring human callback with specific question flows.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_type": {"type": "string", "enum": ["road_sweeper", "toilet_hire", "asbestos", "hazardous_waste", "wheelie_bins", "aggregates", "wait_and_load", "roro"], "description": "LG service type"},
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "postcode": {"type": "string", "description": "Customer's postcode"},
                    "customer_type": {"type": "string", "enum": ["domestic", "trade"], "description": "Customer type"},
                    "service_details": {"type": "object", "description": "Service-specific details collected"}
                },
                "required": ["service_type", "customer_name", "phone_number", "postcode", "customer_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_transfer_request",
            "description": "Handle requests to speak to specific people, complaints, or human agents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "transfer_type": {"type": "string", "enum": ["specific_person", "complaint", "human_agent", "director"], "description": "Type of transfer"},
                    "customer_name": {"type": "string", "description": "Customer's first name"},
                    "phone_number": {"type": "string", "description": "Customer's phone number"},
                    "company_name": {"type": "string", "description": "Company name if applicable"},
                    "reason": {"type": "string", "description": "Reason for transfer/complaint"}
                },
                "required": ["transfer_type", "customer_name", "phone_number", "reason"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "provide_general_info",
            "description": "Provide general information that doesn't require booking or leads.",
            "parameters": {
                "type": "object",
                "properties": {
                    "info_type": {"type": "string", "enum": ["hours", "location", "timing", "waste_bags", "general"], "description": "Type of information"},
                    "question": {"type": "string", "description": "Specific question asked"}
                },
                "required": ["info_type"]
            }
        }
    }
]

# --- HELPER FUNCTIONS ---
def is_business_hours():
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    uk_now = utc_now + timedelta(hours=0)
    day = uk_now.weekday()
    hour = uk_now.hour + (uk_now.minute / 60.0)
    
    if day < 4:  # Monday-Thursday
        return 8 <= hour < 17
    elif day == 4:  # Friday
        return 8 <= hour < 16.5
    elif day == 5:  # Saturday
        return 9 <= hour < 12
    else:  # Sunday
        return False

def send_email(subject, body, recipient=None):
    zoho_email = os.getenv('ZOHO_EMAIL')
    zoho_password = os.getenv('ZOHO_PASSWORD')
    if not zoho_email or not zoho_password:
        print("WARNING: Zoho email credentials not set")
        return False

    recipient = recipient or 'kanchan.ghosh@wasteking.co.uk'
    msg = MIMEMultipart()
    msg['From'] = zoho_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP('smtp.zoho.com', 587)
        server.starttls()
        server.login(zoho_email, zoho_password)
        server.sendmail(zoho_email, recipient, msg.as_string())
        server.quit()
        print(f"✅ Email sent to {recipient}")
        return True
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        return False

def send_lead_email(customer_data, service_type, conversation_history):
    subject = f"{service_type.upper()} Lead - {customer_data.get('customer_name', 'Unknown')}"
    body = f"""
New {service_type.upper()} Lead:

CUSTOMER DETAILS:
- Name: {customer_data.get('customer_name', 'Not provided')}
- Phone: {customer_data.get('phone_number', 'Not provided')}
- Postcode: {customer_data.get('postcode', 'Not provided')}
- Customer Type: {customer_data.get('customer_type', 'Not specified')}
- Service Required: {service_type.upper()}

SPECIFIC DETAILS:
"""
    
    for key, value in customer_data.items():
        if key not in ['customer_name', 'phone_number', 'postcode', 'customer_type'] and value:
            body += f"- {key.replace('_', ' ').title()}: {value}\n"
    
    body += f"""
CONVERSATION HISTORY:
{chr(10).join([msg.get('content', '') for msg in conversation_history[-10:]]) if conversation_history else 'No conversation history'}

ACTION REQUIRED: 
Please call back customer to provide pricing and arrange service.
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    
    return send_email(subject, body, 'kanchan.ghosh@wasteking.co.uk')

def send_sms(name, phone, booking_ref, price, payment_link):
    try:
        twilio_sid = os.getenv('TWILIO_ACCOUNT_SID')
        twilio_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_phone = os.getenv('TWILIO_PHONE_NUMBER')
        
        if not all([twilio_sid, twilio_token, twilio_phone]):
            print("SMS credentials not configured")
            return False
            
        from twilio.rest import Client
        client = Client(twilio_sid, twilio_token)
        formatted_phone = f"+44{phone[1:]}" if phone.startswith('0') else phone
        
        message = f"""Thank You for Choosing Waste King 🌱
 
Please click the secure link below to complete your payment: {payment_link}
 
As part of our service, you'll receive digital waste transfer notes for your records. We're also proud to be planting trees every week to offset our carbon footprint. If you were happy with our service, we'd really appreciate it if you could leave us a review at https://uk.trustpilot.com/review/wastekingrubbishclearance.com.
 
Best regards,
The Waste King Team"""
        
        client.messages.create(body=message, from_=twilio_phone, to=formatted_phone)
        print(f"SMS sent to {phone}")
        return True
    except Exception as e:
        print(f"SMS error: {e}")
        return False

def send_webhook(conversation_id, data, reason):
    try:
        payload = {
            "conversation_id": conversation_id,
            "action_type": reason,
            "timestamp": datetime.now().isoformat(),
            "data": data
        }
        
        webhook_url = os.getenv('WEBHOOK_URL', "https://hook.eu2.make.com/t7bneptowre8yhexo5fjjx4nc09gqdz1")
        requests.post(webhook_url, json=payload, timeout=5)
        print(f"Webhook sent for {reason}: {conversation_id}")
        return True
    except Exception as e:
        print(f"Webhook failed for {conversation_id}: {e}")
        return False

# --- DASHBOARD MANAGER ---
class DashboardManager:
    def __init__(self):
        self.all_calls = {}
        self.recent_calls = {}
    
    def update_call(self, conversation_id, data):
        status = 'active' if data.get('stage') not in ['completed', 'transfer_completed', 'lead_sent'] else 'completed'
        timestamp = datetime.now().isoformat()
        
        call_data = {
            'id': conversation_id,
            'timestamp': timestamp,
            'stage': data.get('stage', 'unknown'),
            'collected_data': data.get('collected_data', {}),
            'history': data.get('history', []),
            'price': data.get('price'),
            'status': status,
            'last_updated': timestamp
        }
        
        self.all_calls[conversation_id] = call_data
        self.recent_calls[conversation_id] = call_data
        self._clean_recent_calls()
    
    def _clean_recent_calls(self):
        cutoff_time = datetime.now() - timedelta(minutes=10)
        calls_to_remove = []
        
        for call_id, call_data in self.recent_calls.items():
            call_time = datetime.fromisoformat(call_data['timestamp'].replace('Z', '+00:00').replace('+00:00', ''))
            is_old = call_time < cutoff_time
            is_inactive = call_data.get('status') in ['completed', 'transfer_completed']
            
            if is_old and is_inactive:
                calls_to_remove.append(call_id)
        
        for call_id in calls_to_remove:
            del self.recent_calls[call_id]
    
    def get_user_dashboard_data(self):
        self._clean_recent_calls()
        active_calls = [call for call in self.recent_calls.values() if call['status'] == 'active']
        return {
            'active_calls': len(active_calls),
            'live_calls': list(self.recent_calls.values()),
            'timestamp': datetime.now().isoformat(),
            'total_calls': len(self.recent_calls),
            'has_data': len(self.recent_calls) > 0
        }
    
    def get_manager_dashboard_data(self):
        total_calls = len(self.all_calls)
        completed_calls = len([call for call in self.all_calls.values() if call['status'] == 'completed'])
        
        services = {}
        for call in self.all_calls.values():
            service = call.get('collected_data', {}).get('service', 'unknown')
            services[service] = services.get(service, 0) + 1
        
        return {
            'total_calls': total_calls,
            'completed_calls': completed_calls,
            'conversion_rate': (completed_calls / total_calls * 100) if total_calls > 0 else 0,
            'service_breakdown': services,
            'timestamp': datetime.now().isoformat(),
            'individual_calls': list(self.all_calls.values()),
            'recent_calls': list(self.all_calls.values())[-50:],
            'active_calls': [call for call in self.all_calls.values() if call['status'] == 'active']
        }

# --- MAIN APPLICATION ---
app = Flask(__name__)
CORS(app)

dashboard_manager = DashboardManager()
conversation_counter = 0
shared_conversations = {}

def get_next_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

SYSTEM_PROMPT = """You are Jennifer, a friendly UK customer service agent for Waste King.

CRITICAL SERVICE RULES - FOLLOW EXACTLY:

1. **ALWAYS ASK CUSTOMER TYPE FIRST**: "Are you a domestic customer or trade customer?"

2. **TRADE CUSTOMERS**: ALL services except skip hire become LG (Lead Generation)
   - If trade customer asks for ANY non-skip service → use handle_lg_service or handle_mav_service

3. **SKIP HIRE ONLY** - Gets immediate pricing/booking:
   - "skip hire", "skip", "container hire" → use handle_skip_hire
   - Heavy materials (soil/rubble): Max 8-yard skip only
   - Always mention prohibited items and charges

4. **SKIP COLLECTION** - Different from skip hire:
   - "skip collection", "collect skip", "pick up skip" → use handle_skip_collection  

5. **ALL OTHER SERVICES** - Create leads only:
   - Man & Van: "clearance", "furniture removal" → handle_mav_service
   - Grab Hire: "grab lorry", "6 wheeler", "8 wheeler" → handle_grab_hire  
   - LG Services: "toilet hire", "asbestos", "road sweeping" → handle_lg_service

CONVERSATION RULES:
- Reduce use of "great", "brilliant", "perfect" - use "I can help with that" instead
- Always ask "Is there anything else I can help with?" before ending
- Don't guarantee specific delivery times
- For timing: "Orders are completed between 6am and 5pm. If you need a specific time, I'll raise a ticket"

SPECIFIC SCRIPTS TO USE:
- Heavy materials + large skip: "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard"
- Not booking: "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book"
- Man & Van volume: "Two washing machines equal about one cubic yard. On average, most clearances we do are around six yards"
- Grab capacities: "6-wheeler is 12-tonne capacity, 8-wheeler is 16-tonne capacity"

Ask questions one at a time. Be natural and conversational."""

@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_next_conversation_id()
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # Get or create conversation state
        state = shared_conversations.get(conversation_id, {
            'history': [{"role": "system", "content": SYSTEM_PROMPT}],
            'collected_data': {},
            'stage': 'initial',
            'booking_ref': None,
            'price': None
        })
        
        # Add customer message to history
        state['history'].append({"role": "user", "content": customer_message})
        
        # Call OpenAI with function calling
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=state['history'],
            tools=OPENAI_FUNCTIONS,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        response_text = ""
        stage = 'conversation'
        
        # Handle function calls
        if assistant_message.tool_calls:
            tool_call = assistant_message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"🤖 AI Function Call: {function_name} with {function_args}")
            
            if function_name == "handle_skip_hire":
                response_text, stage = handle_skip_hire_function(function_args, state, conversation_id)
            elif function_name == "complete_skip_booking":
                response_text, stage = handle_skip_booking_function(state, conversation_id)
            elif function_name == "handle_skip_collection":
                response_text, stage = handle_skip_collection_function(function_args, state['history'])
            elif function_name == "handle_mav_service":
                response_text, stage = handle_mav_function(function_args, state['history'])
            elif function_name == "handle_grab_hire":
                response_text, stage = handle_grab_function(function_args, state['history'])
            elif function_name == "handle_lg_service":
                response_text, stage = handle_lg_function(function_args, state['history'])
            elif function_name == "handle_transfer_request":
                response_text, stage = handle_transfer_function(function_args)
            elif function_name == "provide_general_info":
                response_text, stage = handle_general_info_function(function_args)
            else:
                response_text = "I'll connect you with our team who can help you."
                stage = 'transfer'
        else:
            # Direct AI response
            response_text = assistant_message.content or "How can I help you today?"
            stage = 'conversation'
        
        # Always add closing question if not already present
        if not any(phrase in response_text.lower() for phrase in ["anything else", "further assistance", "help with"]) and stage in ['completed', 'lead_sent', 'transfer']:
            response_text += " " + GENERAL_SCRIPTS['closing']
        
        # Update conversation state
        state['history'].append({"role": "assistant", "content": response_text})
        state['stage'] = stage
        shared_conversations[conversation_id] = state
        
        # Update dashboard
        dashboard_manager.update_call(conversation_id, state)
        
        return jsonify({
            "success": True,
            "message": response_text,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "price": state.get('price')
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "I'll connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

def handle_skip_hire_function(args, state, conversation_id):
    """Handle skip hire with all business rules"""
    inquiry_type = args.get('inquiry_type')
    customer_type = args.get('customer_type')
    skip_size = args.get('skip_size')
    waste_type = args.get('waste_type', '').lower()
    
    # Handle specific inquiries first
    if inquiry_type == 'prohibited_items':
        return SKIP_HIRE_RULES['prohibited_items_full'], 'info_provided'
    
    elif inquiry_type == 'delivery_time':
        return SKIP_HIRE_RULES['delivery_timing'], 'info_provided'
    
    elif inquiry_type == 'permits':
        return "We'll arrange the permit for you and include the cost in your quote. The price varies by council.", 'info_provided'
    
    # Check for heavy materials with large skips
    if skip_size and skip_size in ['10yd', '12yd', '14yd', '16yd', '20yd'] and any(material in waste_type for material in ['soil', 'rubble', 'concrete', 'heavy']):
        return SKIP_HIRE_RULES['heavy_materials_response'], 'sizing_advice'
    
    # Handle prohibited item questions
    if any(item in waste_type for item in ['sofa', 'mattress', 'fridge', 'plasterboard']):
        if 'plasterboard' in waste_type:
            return SKIP_HIRE_RULES['plasterboard_response'], 'info_provided'
        elif any(item in waste_type for item in ['sofa', 'upholstery']):
            return SKIP_HIRE_RULES['prohibited_items_full'], 'info_provided'
        elif any(item in waste_type for item in ['mattress', 'fridge']):
            return SKIP_HIRE_RULES['fridge_mattress_restrictions'], 'info_provided'
    
    # Only proceed with pricing if we have required info
    if not all([args.get('customer_name'), args.get('phone_number'), args.get('postcode')]):
        return "I can help with that. To get you a price, I'll need your name, phone number, and postcode.", 'collecting_info'
    
    # Get pricing - ONLY for skip hire
    if not API_AVAILABLE:
        send_webhook(conversation_id, args, 'api_unavailable')
        return "I'm sorry, our pricing system is currently unavailable. Let me connect you with our team.", 'transfer'
    
    try:
        # Create booking and get pricing
        booking_result = create_booking()
        if not booking_result.get('success'):
            send_webhook(conversation_id, args, 'booking_creation_failed')
            return "Unable to get pricing right now. Let me put you through to our team.", 'transfer'
        
        booking_ref = booking_result['booking_ref']
        skip_size = skip_size or '8yd'  # Default size
        
        price_result = get_pricing(booking_ref, args['postcode'], 'skip', skip_size)
        if not price_result.get('success'):
            send_webhook(conversation_id, args, 'pricing_failed')
            return "I'm having trouble finding pricing for that postcode. Could you please confirm your complete postcode is correct?", 'pricing_error'
        
        price = price_result['price']
        returned_type = price_result.get('type', skip_size)
        
        # Update state
        state['price'] = price
        state['booking_ref'] = booking_ref
        state['collected_data'].update(args)
        state['collected_data']['type'] = returned_type
        
        vat_note = SKIP_HIRE_RULES['vat_note'] if customer_type != 'domestic' else ""
        response = f"{returned_type} skip at {args['postcode']}: {price}"
        if vat_note:
            response += f" ({vat_note})"
        response += ". Would you like to book this?"
        
        return response, 'pricing_provided'
        
    except Exception as e:
        print(f"Skip pricing error: {e}")
        send_webhook(conversation_id, args, 'skip_pricing_error')
        return "I'm sorry, I'm having a technical issue. Let me connect you with our team for immediate help.", 'transfer'

def handle_skip_booking_function(state, conversation_id):
    """Complete skip booking"""
    if not API_AVAILABLE:
        return "Our team will contact you to complete your booking.", 'booking_pending'
    
    try:
        customer_data = state['collected_data'].copy()
        customer_data['price'] = state['price']
        customer_data['booking_ref'] = state['booking_ref']
        
        result = complete_booking(customer_data)
        
        if result.get('success'):
            booking_ref = result['booking_ref']
            price = result['price']
            payment_link = result.get('payment_link')
            
            state['booking_completed'] = True
            
            # Send SMS with payment link
            if payment_link and customer_data.get('phone_number'):
                send_sms(
                    customer_data.get('customer_name'),
                    customer_data.get('phone_number'),
                    booking_ref,
                    price,
                    payment_link
                )
            
            response = f"Booking confirmed! Ref: {booking_ref}, Price: {price}."
            if payment_link:
                response += " A payment link has been sent to your phone."
            
            return response, 'completed'
        else:
            send_webhook(conversation_id, state, 'booking_completion_failed')
            return "Unable to complete booking. Our team will call you back.", 'booking_pending'
            
    except Exception as e:
        print(f"Booking completion error: {e}")
        return "Booking issue occurred. Our team will contact you.", 'booking_pending'

def handle_skip_collection_function(args, conversation_history):
    """Handle skip collection requests"""
    # Check if we have all required info
    required_fields = ['customer_name', 'phone_number', 'postcode', 'address_line1', 'level_load', 'prohibited_check', 'access_issues']
    missing_fields = [field for field in required_fields if not args.get(field)]
    
    if missing_fields:
        # Return the collection script to ask for missing info
        return SKIP_COLLECTION_RULES['script'], 'collecting_collection_info'
    
    # Send email and complete
    send_lead_email(args, 'skip_collection', conversation_history)
    return SKIP_COLLECTION_RULES['completion'], 'lead_sent'

def handle_mav_function(args, conversation_history):
    """Handle Man & Van services - ALL are LG"""
    customer_type = args.get('customer_type')
    
    # Check for heavy materials
    waste_type = args.get('waste_type', '').lower()
    if any(material in waste_type for material in ['soil', 'rubble', 'concrete', 'heavy']):
        return MAV_RULES['heavy_materials_response'], 'advice_given'
    
    # Check for Sunday collection
    when_required = args.get('when_required', '').lower()
    if 'sunday' in when_required:
        return MAV_RULES['sunday_response'], 'transfer_requested'
    
    # Check if we need volume explanation
    if not args.get('volume_yards'):
        return MAV_RULES['volume_explanation'], 'collecting_volume'
    
    # Check for supplement items
    if not args.get('supplement_items'):
        return MAV_RULES['supplement_check'], 'checking_supplements'
    
    # Send lead email
    send_lead_email(args, 'man_and_van', conversation_history)
    
    callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
    response = f"Thank you {args.get('customer_name', '')}, I have all your details. {GENERAL_SCRIPTS['lg_transfer_message']} and our team will call you back {callback_time}."
    
    return response, 'lead_sent'

def handle_grab_function(args, conversation_history):
    """Handle Grab Hire services - ALL are LG due to pricing not in SMP"""
    grab_type = args.get('grab_type')
    
    # Provide grab explanations
    if grab_type == '6_wheeler' and not args.get('explained'):
        args['explained'] = True
        return GRAB_RULES['6_wheeler_explanation'], 'grab_explained'
    elif grab_type == '8_wheeler' and not args.get('explained'):
        args['explained'] = True
        return GRAB_RULES['8_wheeler_explanation'], 'grab_explained'
    
    # Check for mixed materials
    material_type = args.get('material_type', '').lower()
    if any(material in material_type for material in ['mixed', 'wood', 'plastic']) and any(heavy in material_type for heavy in ['soil', 'rubble']):
        return GRAB_RULES['mixed_materials_response'], 'transfer_requested'
    
    # All grabs go to LG due to pricing issues
    send_lead_email(args, 'grab_hire', conversation_history)
    
    callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
    response = f"Thank you {args.get('customer_name', '')}, I have all your grab hire details. {GENERAL_SCRIPTS['lg_transfer_message']} and our specialist team will call you back {callback_time}."
    
    return response, 'lead_sent'

def handle_lg_function(args, conversation_history):
    """Handle all LG services with specific question flows"""
    service_type = args.get('service_type')
    
    # Handle RORO heavy materials check
    if service_type == 'roro':
        waste_type = args.get('service_details', {}).get('waste_type', '').lower()
        if any(material in waste_type for material in ['soil', 'rubble', 'concrete', 'heavy']):
            return SKIP_HIRE_RULES['roro_heavy_materials'], 'roro_advice'
    
    # Send lead email
    send_lead_email(args, service_type, conversation_history)
    
    # Service-specific responses
    service_responses = {
        'asbestos': "Our certified asbestos team will call you back",
        'hazardous_waste': "Our hazardous waste specialists will call you back", 
        'toilet_hire': "Our specialist team will call you back",
        'road_sweeper': "Our specialist team will call you back"
    }
    
    callback_text = service_responses.get(service_type, "Our specialist team will call you back")
    callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
    
    response = f"Thank you {args.get('customer_name', '')}, I have all the details. {callback_text} {callback_time} to confirm cost and availability."
    
    return response, 'lead_sent'

def handle_transfer_function(args):
    """Handle transfer requests"""
    transfer_type = args.get('transfer_type')
    
    if transfer_type == 'specific_person':
        return GENERAL_SCRIPTS['human_request'], 'transfer_requested'
    elif transfer_type == 'complaint':
        if is_business_hours():
            return "I understand your frustration, please bear with me while I transfer you to the appropriate person.", 'transfer_active'
        else:
            return "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow.", 'callback_promised'
    elif transfer_type == 'human_agent':
        return GENERAL_SCRIPTS['human_request'], 'transfer_requested'
    else:
        return "I'll arrange for the right person to call you back.", 'transfer_requested'

def handle_general_info_function(args):
    """Handle general information requests"""
    info_type = args.get('info_type')
    
    if info_type == 'timing':
        return GENERAL_SCRIPTS['timing_query'], 'info_provided'
    elif info_type == 'location':
        return GENERAL_SCRIPTS['location_response'], 'info_provided'
    elif info_type == 'waste_bags':
        return WASTE_BAGS_INFO['script'], 'info_provided'
    elif info_type == 'hours':
        return "We're open Monday-Thursday 8am-5pm, Friday 8am-4:30pm, Saturday 9am-12pm. We're closed Sundays.", 'info_provided'
    else:
        return "I'd be happy to help you with that. What specifically do you need to know?", 'info_provided'

# --- DASHBOARD ROUTES (unchanged) ---
@app.route('/')
def index():
    return redirect(url_for('user_dashboard_page'))

@app.route('/dashboard/user')
def user_dashboard_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Live Calls Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #f5f6fa; }
        .header { background: linear-gradient(135deg, #667eea, #764ba2); color: white; padding: 25px; position: fixed; top: 0; left: 0; right: 0; z-index: 1000; }
        .header h1 { font-size: 28px; margin-bottom: 10px; }
        .stats { display: flex; gap: 30px; margin-top: 15px; font-size: 14px; }
        .live-dot { width: 8px; height: 8px; background: #4caf50; border-radius: 50%; animation: pulse 2s infinite; }
        .main { display: grid; grid-template-columns: 1fr 350px; gap: 20px; padding: 20px; margin-top: 120px; height: calc(100vh - 140px); }
        .calls-section, .form-section { background: white; border-radius: 15px; padding: 25px; overflow-y: auto; }
        .calls-container { min-height: 400px; }
        .call-item { background: #f8f9fa; border-radius: 10px; padding: 20px; margin-bottom: 15px; cursor: pointer; min-height: 120px; }
        .call-item:hover { background: #e9ecef; }
        .call-item.selected { border: 2px solid #667eea; background: #e8f0fe; }
        .call-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
        .call-id { font-weight: bold; color: #667eea; }
        .stage { padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; text-transform: uppercase; }
        .stage-conversation { background: #fff3cd; color: #856404; }
        .stage-collecting_info { background: #fff3cd; color: #856404; }
        .stage-pricing_provided { background: #d4edda; color: #155724; }
        .stage-booking { background: #d4edda; color: #155724; }
        .stage-completed { background: #cce7ff; color: #004085; }
        .stage-lead_sent { background: #e2e3e5; color: #495057; }
        .stage-transfer_completed { background: #e2e3e5; color: #495057; }
        .transcript { background: white; padding: 15px; border-radius: 8px; max-height: 100px; overflow-y: auto; font-size: 13px; margin-top: 10px; }
        .form-section { position: sticky; top: 140px; max-height: calc(100vh - 160px); }
        .form-group { margin-bottom: 15px; min-height: 60px; }
        .form-label { display: block; margin-bottom: 5px; font-weight: bold; font-size: 14px; }
        .form-input { width: 100%; padding: 10px; border: 2px solid #e9ecef; border-radius: 8px; min-height: 40px; }
        .form-input.filled { background: #e8f5e8; border-color: #4caf50; }
        .no-calls { text-align: center; padding: 60px; color: #666; min-height: 200px; display: flex; flex-direction: column; justify-content: center; }
        @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
    </style>
</head>
<body>
    <div class="header">
        <h1>Live Calls Dashboard (Last 10 Minutes)</h1>
        <div class="stats">
            <div style="display: flex; align-items: center; gap: 8px;">
                <div class="live-dot"></div>
                <span id="active-calls">0 Active Calls</span>
            </div>
            <div id="last-update">Last update: Never</div>
        </div>
    </div>
    
    <div class="main">
        <div class="calls-section">
            <h2 style="margin-bottom: 20px;">Live Conversations</h2>
            <div id="calls-container" class="calls-container">
                <div class="no-calls">
                    <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
                    Waiting for live calls...
                </div>
            </div>
        </div>
        
        <div class="form-section">
            <h2 style="margin-bottom: 20px;">Auto-Extracted Data</h2>
            <div class="form-group">
                <label class="form-label">Customer Name</label>
                <input type="text" class="form-input" id="customer-name" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Phone Number</label>
                <input type="text" class="form-input" id="customer-phone" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Postcode</label>
                <input type="text" class="form-input" id="customer-postcode" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Service Type</label>
                <input type="text" class="form-input" id="service-type" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Customer Type</label>
                <input type="text" class="form-input" id="customer-type" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Current Stage</label>
                <input type="text" class="form-input" id="current-stage" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Price Quote</label>
                <input type="text" class="form-input" id="price-quote" readonly>
            </div>
            <div class="form-group">
                <label class="form-label">Transcript</label>
                <textarea class="form-input" id="full-transcript" readonly style="height: 150px; resize: vertical;"></textarea>
            </div>
        </div>
    </div>

    <script>
        let selectedCallId = null;
        let lastCallsJson = '';
        let isUpdating = false;

        function loadDashboard() {
            if (isUpdating) return;
            isUpdating = true;

            fetch('/api/dashboard/user')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const currentCallsJson = JSON.stringify(data.data.live_calls);
                        
                        // Only update calls if data actually changed - PREVENTS BLINKING
                        if (currentCallsJson !== lastCallsJson) {
                            updateCallsDisplay(data.data.live_calls);
                            lastCallsJson = currentCallsJson;
                        }
                        
                        // Update lightweight stats
                        document.getElementById('active-calls').textContent = `${data.data.active_calls} Active Calls`;
                        document.getElementById('last-update').textContent = `Last update: ${new Date().toLocaleTimeString()}`;
                        
                        // Keep selected call highlighted and updated
                        if (selectedCallId) {
                            const selectedCall = data.data.live_calls.find(call => call.id === selectedCallId);
                            if (selectedCall) {
                                updateFormData(selectedCall);
                                highlightSelectedCall();
                            } else {
                                selectedCallId = null;
                                clearForm();
                            }
                        }
                    }
                })
                .catch(error => console.error('Dashboard error:', error))
                .finally(() => {
                    isUpdating = false;
                });
        }
        
        function updateCallsDisplay(calls) {
            const container = document.getElementById('calls-container');
            
            if (!calls || calls.length === 0) {
                if (!container.querySelector('.no-calls')) {
                    container.innerHTML = `
                        <div class="no-calls">
                            <div style="font-size: 48px; margin-bottom: 20px;">📞</div>
                            No calls in the last 10 minutes
                        </div>`;
                }
                return;
            }

            // Remove no-calls message if present
            const noCallsMsg = container.querySelector('.no-calls');
            if (noCallsMsg) noCallsMsg.remove();

            // Get current elements to avoid recreating
            const existingElements = {};
            container.querySelectorAll('[data-call-id]').forEach(el => {
                existingElements[el.getAttribute('data-call-id')] = el;
            });

            // Remove calls that no longer exist
            Object.keys(existingElements).forEach(callId => {
                if (!calls.find(call => call.id === callId)) {
                    existingElements[callId].remove();
                }
            });

            // Add or update calls
            calls.forEach(call => {
                let element = existingElements[call.id];
                
                const collected_data = call.collected_data || {};
                const last_messages = (call.history || []).slice(-3).map(msg => msg.content || msg).join(' | ') || 'No transcript yet...';
                
                const newContent = `
                    <div class="call-header">
                        <div class="call-id">${call.id}</div>
                        <div class="stage stage-${call.stage || 'unknown'}">${call.stage || 'Unknown'}</div>
                    </div>
                    <div><strong>Customer:</strong> ${collected_data.customer_name || 'Not provided'}</div>
                    <div><strong>Service:</strong> ${collected_data.service || 'Identifying...'}</div>
                    <div><strong>Type:</strong> ${collected_data.customer_type || 'Unknown'}</div>
                    <div><strong>Postcode:</strong> ${collected_data.postcode || 'Not provided'}</div>
                    ${call.price ? `<div><strong>Price:</strong> ${call.price}</div>` : ''}
                    <div class="transcript">${last_messages}</div>
                    <div style="font-size: 12px; color: #666; margin-top: 10px;">
                        ${call.timestamp ? new Date(call.timestamp).toLocaleString() : 'Unknown time'}
                    </div>
                `;
                
                if (!element) {
                    // Create new element
                    element = document.createElement('div');
                    element.className = 'call-item';
                    element.setAttribute('data-call-id', call.id);
                    element.onclick = () => selectCall(call.id);
                    container.insertBefore(element, container.firstChild);
                }
                
                // Update content only if changed - PREVENTS UNNECESSARY UPDATES
                if (element.innerHTML !== newContent) {
                    element.innerHTML = newContent;
                }
            });
        }
        
        function selectCall(callId) {
            selectedCallId = callId;
            highlightSelectedCall();
            
            // Update form immediately
            const calls = JSON.parse(lastCallsJson || '[]');
            const callData = calls.find(call => call.id === callId);
            if (callData) {
                updateFormData(callData);
            }
        }
        
        function highlightSelectedCall() {
            // Remove previous selection
            document.querySelectorAll('.call-item').forEach(item => {
                item.classList.remove('selected');
            });
            
            // Highlight selected call
            if (selectedCallId) {
                const selectedElement = document.querySelector(`[data-call-id="${selectedCallId}"]`);
                if (selectedElement) {
                    selectedElement.classList.add('selected');
                }
            }
        }
        
        function updateFormData(callData) {
            const collected = callData.collected_data || {};
            
            updateFormField('customer-name', collected.customer_name || '');
            updateFormField('customer-phone', collected.phone_number || '');
            updateFormField('customer-postcode', collected.postcode || '');
            updateFormField('service-type', collected.service || '');
            updateFormField('customer-type', collected.customer_type || '');
            updateFormField('current-stage', callData.stage || '');
            updateFormField('price-quote', callData.price || '');
            
            const transcript = (callData.history || []).map(msg => msg.content || msg).join('\\n');
            updateFormField('full-transcript', transcript);
        }
        
        function updateFormField(fieldId, value) {
            const input = document.getElementById(fieldId);
            if (input && input.value !== value) {
                input.value = value;
                input.classList.toggle('filled', !!value);
            }
        }
        
        function clearForm() {
            const fields = ['customer-name', 'customer-phone', 'customer-postcode', 'service-type', 'customer-type', 'current-stage', 'price-quote', 'full-transcript'];
            fields.forEach(fieldId => {
                updateFormField(fieldId, '');
            });
        }
        
        document.addEventListener('DOMContentLoaded', loadDashboard);
        setInterval(loadDashboard, 8000);
    </script>
</body>
</html>
""")

@app.route('/api/dashboard/user')
def user_dashboard_api():
    try:
        dashboard_data = dashboard_manager.get_user_dashboard_data()
        return jsonify({"success": True, "data": dashboard_data})
    except Exception as e:
        return jsonify({"success": False, "data": {"active_calls": 0, "live_calls": [], "total_calls": 0}})

@app.route('/api/dashboard/manager')
def manager_dashboard_api():
    try:
        dashboard_data = dashboard_manager.get_manager_dashboard_data()
        return jsonify({"success": True, "data": dashboard_data})
    except Exception as e:
        return jsonify({"success": False, "data": {"total_calls": 0, "completed_calls": 0, "service_breakdown": {}}})

if __name__ == '__main__':
    print("🚀 Starting WasteKing COMPREHENSIVE System...")
    print("✅ Skip services: Full pricing + booking with all business rules")
    print("✅ All other services: Lead generation with specific question flows")
    print("✅ Trade customer routing implemented")
    print("✅ All business rules and scripts included")
    print("✅ Dashboard anti-flicker protection")
    print("✅ Comprehensive prohibited items and charges")
    print("✅ Heavy materials restrictions")
    print("✅ LG service question sequences")
    print("✅ Grab hire capacity explanations")
    print("✅ Man & Van volume explanations")
    print("✅ Skip collection handling")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
