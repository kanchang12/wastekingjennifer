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
import redis
import pickle

# Flask app MUST be here for Gunicorn
app = Flask(__name__)
CORS(app)

# --- STATE MANAGEMENT ---
# Use Redis for persistent state across tool calls
try:
    redis_client = redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379"))
    redis_client.ping()
    print("Redis connected for state management")
except:
    print("Redis not available - using in-memory fallback")
    redis_client = None
    CONVERSATION_STATES = {}

def get_conversation_state(conversation_id: str) -> dict:
    """Get conversation state from Redis or memory"""
    if redis_client:
        try:
            state_data = redis_client.get(f"conv:{conversation_id}")
            if state_data:
                return pickle.loads(state_data)
        except:
            pass
    else:
        return CONVERSATION_STATES.get(conversation_id, {})
    
    return {
        'customer_data': {},
        'service_type': None,
        'stage': 'start',
        'history': [],
        'asked_fields': set()
    }

def save_conversation_state(conversation_id: str, state: dict):
    """Save conversation state to Redis or memory"""
    if redis_client:
        try:
            redis_client.setex(
                f"conv:{conversation_id}",
                3600,  # 1 hour TTL
                pickle.dumps(state)
            )
        except:
            pass
    else:
        CONVERSATION_STATES[conversation_id] = state

# --- API INTEGRATION ---
from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
print("API AVAILABLE")

# --- BUSINESS RULES ---
OFFICE_HOURS = {
    'monday_thursday': {'start': 8, 'end': 17},
    'friday': {'start': 8, 'end': 16.5},
    'saturday': {'start': 9, 'end': 12},
    'sunday': 'closed'
}

TRANSFER_RULES = {
    'management_director': {
        'triggers': ['glenn currie', 'director', 'speak to glenn'],
        'office_hours': "I am sorry, Glenn is not available, may I take your details and Glenn will call you back?",
        'out_of_hours': "I can take your details and have our director call you back first thing tomorrow",
        'sms_notify': '+447823656762'
    },
    'complaints': {
        'triggers': ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry'],
        'office_hours': "I understand your frustration, please bear with me while I transfer you to the appropriate person.",
        'out_of_hours': "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow.",
        'action': 'TRANSFER',
        'sms_notify': '+447823656762'
    },
    'specialist_services': {
        'services': ['hazardous waste disposal', 'asbestos removal', 'asbestos collection', 'weee electrical waste', 'chemical disposal', 'medical waste', 'trade waste'],
        'office_hours': 'Transfer immediately',
        'out_of_hours': 'Take details + SMS notification to +447823656762'
    }
}

LG_SERVICES = {
    'skip_collection': {
        'triggers': ['skip collection', 'collect skip', 'pick up skip', 'remove skip', 'collection of skip'],
    },
    'road_sweeper': {
        'triggers': ['road sweeper', 'road sweeping', 'street sweeping'],
    },
    'toilet_hire': {
        'triggers': ['toilet hire', 'portaloo', 'portable toilet'],
    },
    'asbestos': {
        'triggers': ['asbestos'],
    },
    'hazardous_waste': {
        'triggers': ['hazardous waste', 'chemical waste', 'dangerous waste'],
    },
    'wheelie_bins': {
        'triggers': ['wheelie bin', 'wheelie bins', 'bin hire'],
    },
    'aggregates': {
        'triggers': ['aggregates', 'sand', 'gravel', 'stone'],
    },
    'roro_40yard': {
        'triggers': ['40 yard', '40-yard', 'roro', 'roll on roll off', '30 yard', '35 yard'],
    },
    'waste_bags': {
        'triggers': ['skip bag', 'waste bag', 'skip sack'],
    },
    'wait_and_load': {
        'triggers': ['wait and load', 'wait & load', 'wait load'],
    }
}

SKIP_HIRE_RULES = {
    'A2_heavy_materials': {
        'heavy_materials_max': "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard. Shall I get you the cost of an 8-yard skip?"
    },
    'A5_prohibited_items': {
        'surcharge_items': { 'fridges': 20, 'freezers': 20, 'mattresses': 15, 'upholstered furniture': 15 },
        'plasterboard_response': "Plasterboard isn't allowed in normal skips. If you have a lot, we can arrange a special plasterboard skip, or our man and van service can collect it for you",
        'restrictions_response': "There may be restrictions on fridges & mattresses depending on your location",
        'upholstery_alternative': "The following items are prohibited in skips. However, our fully licensed and insured man and van service can remove light waste, including these items, safely and responsibly.",
        'prohibited_list': [ 'fridges', 'freezers', 'mattresses', 'upholstered furniture', 'paint', 'liquids', 'tyres', 'plasterboard', 'gas cylinders', 'hazardous chemicals', 'asbestos'],
        'full_script': "Just so you know, there are some prohibited items that cannot be placed in skips — including mattresses (£15 charge), fridges (£20 charge), upholstery, plasterboard, asbestos, and paint. Our man and van service is ideal for light rubbish and can remove most items. If you'd prefer, I can connect you with the team to discuss the man and van option. Would you like to speak to the team about that, or continue with skip hire?"
    },
    'A7_quote': {
        'vat_note': 'If the prices are coming from SMP they are always + VAT',
        'always_include': ["Collection within 72 hours standard", "Level load requirement for skip collection", "Driver calls when en route", "98% recycling rate", "We have insured and licensed teams", "Digital waste transfer notes provided"]
    },
    'delivery_timing': "We usually aim to deliver your skip the next day, but during peak months, it may take a bit longer. Don't worry though – we'll check with the depot to get it to you as soon as we can, and we'll always do our best to get it on the day you need.",
    'not_booking_response': "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book. Would you like a £10 discount? If you're happy with the service after booking, you'll have the option to leave a review.",
    'permit_check': "Is the skip going on the road or on your property?",
    'permit_required': "You'll need a permit as the skip is going on the road. We'll arrange this for you - it typically costs £35-£85 depending on your council.",
    'no_permit': "Great, no permit needed as it's on your property."
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
    'time_restriction': "We can't guarantee exact times, but collection is typically between 7am-6pm",
    'if_unsure_volume': "Think in terms of washing machine loads or black bags."
}

GRAB_RULES = {
    '6_wheeler_explanation': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry.",
    '8_wheeler_explanation': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
    'mixed_materials_response': "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you.",
    'transfer_message': "Most of the prices for grabs are not on SMP so I'll transfer you to a human specialist.",
    'capacity_tonnes': "A 6-wheel grab lorry typically has a capacity of around 12 to 14 tonnes, while an 8-wheel grab lorry can usually carry approximately 16 to 18 tonnes."
}

WASTE_BAGS_INFO = {
    'script': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready"
}

RORO_RULES = {
    'heavy_materials': "For heavy materials like soil & rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only.",
    'largest_skip': "The largest skip is RORO 40 yard. The largest for soil and rubble is 8 yard. Larger skips than that are suitable only for light waste, not heavy materials."
}

WAIT_AND_LOAD_RULES = {
    'explanation': "Wait and load service means the driver waits while you load the skip, then takes it away immediately. Perfect for restricted access areas.",
    'time_limit': "You get 30-45 minutes to load the skip while the driver waits.",
    'pricing': "Wait and load is typically 20-30% more expensive than standard skip hire due to the driver waiting time."
}

WHEELIE_BINS_RULES = {
    'sizes': ['120L', '240L', '360L', '660L', '1100L'],
    'commercial_only': "Wheelie bin hire is typically for commercial customers with regular collections.",
    'frequency': "Collection frequency can be daily, weekly, fortnightly, or monthly depending on your needs."
}

AGGREGATES_RULES = {
    'types': ['Sand', 'Gravel', 'Type 1 MOT', 'Crushed concrete', 'Topsoil'],
    'delivery': "We can deliver via tipper truck or grab lorry depending on access and quantity.",
    'minimum': "Minimum order is typically 1 tonne."
}

LG_SERVICES_QUESTIONS = {
    'skip_collection': {
        'questions': [
            "What's your postcode?",
            "What's the first line of your address?",
            "What's your name?",
            "What's your telephone number?",
            "Is the skip a level load?",
            "Can you confirm there are no prohibited items in the skip?",
            "Are there any access issues?"
        ]
    },
    'road_sweeper': {
        'questions': [
            "Can I take your postcode?",
            "How many hours do you require?", 
            "Is there tipping on site or do we have to take it away?",
            "When do you require this?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'toilet_hire': {
        'questions': [
            "Can I take your postcode?",
            "How many portaloos do you require?",
            "Is this for an event or longer term?", 
            "How long do you need it for?",
            "What date do you need delivery?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'asbestos': {
        'questions': [
            "Can I take your postcode?",
            "Do you need a skip or just a collection?",
            "What type of asbestos is it?",
            "Is this a dismantle & disposal or just a collection & disposal?",
            "How much do you have?",
            "What's your name?", 
            "What's the best phone number to contact you on?"
        ],
        'intro': "Asbestos requires specialist handling. Let me take a few details and arrange for our certified team to call you back"
    },
    'hazardous_waste': {
        'questions': [
            "What's your name?",
            "Can I take your postcode?",
            "What type of hazardous waste do you have?",
            "Do you have a data sheet?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'wheelie_bins': {
        'questions': [
            "Can I take your postcode?",
            "Are you a domestic or commercial customer?",
            "What is the waste type?",
            "What size bin do you require and how many?", 
            "How often will you need a waste collection?",
            "How long do you require it for?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'aggregates': {
        'questions': [
            "Can I take your postcode?",
            "What type of aggregate do you need?",
            "How many tonnes do you require?",
            "Do you need tipper or grab delivery?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'wait_and_load': {
        'questions': [
            "Can I take your postcode?",
            "What size skip do you need?",
            "What waste will be going into the skip?",
            "When do you require it?", 
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'roro': {
        'questions': [
            "Can I take your postcode?",
            "What size RORO do you need - 20, 30, 35, or 40 yard?",
            "What type of waste will you be putting in the RORO?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will pass you onto our specialist team to give you a quote and availability"
    },
    'waste_bags': {
        'questions': [
            "Can I take your postcode?",
            "What size bag do you need - 1.5, 3.6, or 4.5 cubic yards?",
            "What type of waste will you be putting in?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "Our skip bags are for light waste only. Our man and van service will collect when you're ready."
    }
}

# --- OPENAI FUNCTION CALLING ---
OPENAI_FUNCTIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_skip_pricing",
            "description": "Get a price quote for a skip hire based on postcode and skip size. This function should be called for all skip hire inquiries and related questions, including prohibited items and permits. Also handle skip collection or exchange requests. Do not use for Man & Van or Grab Hire.",
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "The customer's full postcode, e.g., 'SW1A 0AA'."
                    },
                    "skip_size": {
                        "type": "string",
                        "enum": ["2yd", "4yd", "6yd", "8yd", "10yd", "12yd", "14yd", "16yd", "20yd"],
                        "description": "The size of the skip in cubic yards."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "The customer's first name."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's phone number."
                    },
                    "request_type": {
                        "type": "string",
                        "enum": ["new_hire", "collection", "exchange"],
                        "description": "The type of skip service requested."
                    }
                },
                "required": ["postcode", "request_type"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_asbestos_inquiry",
            "description": "Handles all asbestos-related service inquiries. This service requires specific information for a human agent to call back with a quote. This function should be called anytime a customer mentions 'asbestos' or 'asbestos removal'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "The customer's full postcode, e.g., 'SW1A 0AA'."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "The customer's first name."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's phone number."
                    },
                    "skip_or_collection": {
                        "type": "string",
                        "enum": ["skip", "collection"],
                        "description": "Whether the customer needs a skip or a collection service for the asbestos."
                    },
                    "asbestos_type": {
                        "type": "string",
                        "description": "The type of asbestos the customer has, if known."
                    },
                    "quantity": {
                        "type": "string",
                        "description": "The estimated quantity of asbestos, e.g., '5 sheets' or 'one room'."
                    }
                },
                "required": ["postcode", "customer_name", "phone_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_toilet_hire_inquiry",
            "description": "Handles all toilet hire inquiries. This function should be called for any mention of 'toilet hire', 'portaloo', or 'portable toilet'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "The customer's full postcode."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "The customer's first name."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's phone number."
                    },
                    "number_required": {
                        "type": "integer",
                        "description": "The number of portable toilets required."
                    },
                    "event_or_longterm": {
                        "type": "string",
                        "enum": ["event", "longterm"],
                        "description": "Whether the hire is for a specific event or long-term use."
                    },
                    "duration": {
                        "type": "string",
                        "description": "The duration of the hire."
                    }
                },
                "required": ["postcode", "customer_name", "phone_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_man_and_van",
            "description": "Handle man and van clearance service inquiries for light waste removal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "The customer's full postcode."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "The customer's first name."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's phone number."
                    },
                    "volume": {
                        "type": "string",
                        "description": "Volume of waste in cubic yards or washing machine loads."
                    },
                    "when_required": {
                        "type": "string",
                        "description": "When the service is needed."
                    },
                    "supplement_items": {
                        "type": "string",
                        "description": "Any special items like mattresses, fridges, furniture."
                    }
                },
                "required": ["postcode", "customer_name", "phone_number"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "handle_grab_hire",
            "description": "Handle grab lorry hire inquiries for bulk waste removal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "postcode": {
                        "type": "string",
                        "description": "The customer's full postcode."
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "The customer's first name."
                    },
                    "phone_number": {
                        "type": "string",
                        "description": "The customer's phone number."
                    },
                    "material_type": {
                        "type": "string",
                        "description": "Type of material - soil/rubble (muckaway) or general waste."
                    },
                    "grab_type": {
                        "type": "string",
                        "enum": ["6_wheeler", "8_wheeler"],
                        "description": "Type of grab lorry needed."
                    }
                },
                "required": ["postcode", "customer_name", "phone_number"]
            }
        }
    }
]

class WasteKingAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
    def process_message_with_functions(self, message: str, conversation_id: str) -> tuple:
        """Process message using OpenAI function calling with persistent state"""
        
        # Get existing state
        state = get_conversation_state(conversation_id)
        
        # Add message to history
        state['history'].append(f"Customer: {message}")
        
        # Build context from state
        context = self._build_context_from_state(state)
        
        try:
            # Call OpenAI with function calling
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are Jennifer from Waste King, a professional waste management assistant.
                        Current conversation context: {json.dumps(context)}
                        
                        Key behaviors:
                        1. Gather information systematically - name, phone, postcode, service details
                        2. When you have all required info, call the appropriate function IMMEDIATELY
                        3. For skip hire with name, phone, and postcode - call get_skip_pricing
                        4. Check for prohibited items and offer alternatives
                        5. Be direct and professional - no excessive pleasantries
                        
                        Business rules to follow:
                        - For heavy materials (soil/rubble), max skip size is 8 yards
                        - Prohibited items include: {', '.join(SKIP_HIRE_RULES['A5_prohibited_items']['prohibited_list'])}
                        - Always mention surcharges for fridges (£20) and mattresses (£15)
                        """
                    },
                    {"role": "user", "content": message}
                ],
                functions=OPENAI_FUNCTIONS,
                function_call="auto",
                temperature=0.3
            )
            
            # Process the response
            response_message = response.choices[0].message
            
            # Check if function was called
            if response_message.function_call:
                function_name = response_message.function_call.name
                function_args = json.loads(response_message.function_call.arguments)
                
                # Update state with extracted data
                self._update_state_from_function_args(state, function_name, function_args)
                
                # Execute the function
                function_result = self._execute_function(function_name, function_args, state)
                
                # Save state
                save_conversation_state(conversation_id, state)
                
                return function_result, state.get('stage', 'processing')
            else:
                # Regular response without function call
                response_text = response_message.content
                state['history'].append(f"Agent: {response_text}")
                save_conversation_state(conversation_id, state)
                return response_text, state.get('stage', 'conversation')
                
        except Exception as e:
            print(f"ERROR in process_message_with_functions: {e}")
            traceback.print_exc()
            return "I apologize for the technical issue. Let me connect you with our team.", 'error'
    
    def _build_context_from_state(self, state: dict) -> dict:
        """Build context object from conversation state"""
        return {
            'customer_data': state.get('customer_data', {}),
            'service_type': state.get('service_type'),
            'stage': state.get('stage'),
            'messages_count': len(state.get('history', []))
        }
    
    def _update_state_from_function_args(self, state: dict, function_name: str, args: dict):
        """Update state based on function arguments"""
        if 'customer_name' in args:
            state['customer_data']['name'] = args['customer_name']
        if 'phone_number' in args:
            state['customer_data']['phone'] = args['phone_number']
        if 'postcode' in args:
            state['customer_data']['postcode'] = args['postcode']
        
        # Set service type based on function
        if 'skip' in function_name:
            state['service_type'] = 'skip_hire'
            if 'skip_size' in args:
                state['customer_data']['skip_size'] = args['skip_size']
        elif 'asbestos' in function_name:
            state['service_type'] = 'asbestos'
        elif 'toilet' in function_name:
            state['service_type'] = 'toilet_hire'
        elif 'man_and_van' in function_name:
            state['service_type'] = 'man_and_van'
        elif 'grab' in function_name:
            state['service_type'] = 'grab_hire'
    
    def _execute_function(self, function_name: str, args: dict, state: dict) -> str:
        """Execute the called function and return result"""
        
        if function_name == "get_skip_pricing":
            return self._handle_skip_pricing(args, state)
        elif function_name == "handle_asbestos_inquiry":
            return self._handle_asbestos(args, state)
        elif function_name == "handle_toilet_hire_inquiry":
            return self._handle_toilet_hire(args, state)
        elif function_name == "handle_man_and_van":
            return self._handle_man_and_van(args, state)
        elif function_name == "handle_grab_hire":
            return self._handle_grab_hire(args, state)
        else:
            return "I'll process that request for you."
    
    def _handle_skip_pricing(self, args: dict, state: dict) -> str:
        """Handle skip pricing and booking - API ONLY, NO FALLBACK"""
        postcode = args.get('postcode', '')
        skip_size = args.get('skip_size', '8yd')
        customer_name = args.get('customer_name', '')
        phone = args.get('phone_number', '')
        request_type = args.get('request_type', 'new_hire')
        
        if request_type == 'collection':
            # Handle skip collection
            if customer_name and phone and postcode:
                send_email(
                    f"SKIP COLLECTION - {customer_name}",
                    f"Customer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\n\nAction: Arrange collection",
                    'kanchan.g12@gmail.com'
                )
                state['stage'] = 'collection_requested'
                return f"Thanks {customer_name}, I've arranged for your skip collection at {postcode}. Our team will contact you on {phone} to confirm the collection time."
            else:
                return "I need your name, phone number, and postcode to arrange the skip collection."
        
        # For new hire - check if we have all required data
        if not all([customer_name, phone, postcode]):
            missing = []
            if not customer_name: missing.append("name")
            if not phone: missing.append("phone number")  
            if not postcode: missing.append("postcode")
            return f"To get you a price, I need your {' and '.join(missing)}."
        
        try:
            # Get pricing from API - NO FALLBACK
            price_response = get_pricing(postcode, skip_size)
            
            if not price_response.get('success'):
                # API FAILED - ROUTE TO HUMAN
                send_email(
                    f"API FAILURE - MANUAL BOOKING REQUIRED",
                    f"API pricing failed\n\nCustomer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nSkip Size: {skip_size}\n\nAction: Call customer to complete booking"
                )
                return f"Thanks {customer_name}. I'm having a technical issue getting your price. Our team will call you back on {phone} to complete your {skip_size} skip booking for {postcode}."
            
            price = price_response.get('price')
            
            # Create booking
            booking_data = {
                'name': customer_name,
                'phone': phone,
                'postcode': postcode,
                'skip_size': skip_size,
                'price': price
            }
            
            booking_response = create_booking(booking_data)
            
            if booking_response.get('success'):
                booking_ref = booking_response.get('reference', f"WK{datetime.now().strftime('%H%M%S')}")
                
                # Get payment link from API
                payment_link_response = create_payment_link({
                    'booking_ref': booking_ref,
                    'amount': price,
                    'customer_name': customer_name,
                    'phone': phone
                })
                
                if payment_link_response.get('success'):
                    payment_link = payment_link_response.get('payment_link')
                else:
                    # If payment link API fails, use booking ref
                    payment_link = f"https://pay.wasteking.co.uk/{booking_ref}"
                
                # Send SMS with exact format
                sms_message = f"""Thank You for Choosing Waste King 🌱
 
Please click the secure link below to complete your payment: {payment_link}
 
As part of our service, you'll receive digital waste transfer notes for your records. We're also proud to be planting trees every week to offset our carbon footprint. If you were happy with our service, we'd really appreciate it if you could leave us a review at https://uk.trustpilot.com/review/wastekingrubbishclearance.com. Find out more about us at www.wastekingrubbishclearance.co.uk.
 
Best regards,
The Waste King Team"""
                send_sms(phone, sms_message)
                
                # Send email to operations
                send_email(
                    f"SKIP BOOKING - {customer_name} - {booking_ref}",
                    f"Reference: {booking_ref}\nCustomer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nSkip Size: {skip_size}\nPrice: {price}\n\nAction: Schedule delivery within 24 hours"
                )
                
                state['stage'] = 'booking_completed'
                state['booking_ref'] = booking_ref
                
                return f"Perfect {customer_name}! Your {skip_size} skip is booked for {postcode}. Price: {price} (+ VAT for trade). Reference: {booking_ref}. You'll receive an SMS confirmation to {phone}. Delivery within 24 hours."
            else:
                # Booking API failed - send to human
                send_email(
                    f"BOOKING API FAILED - {customer_name}",
                    f"Booking API failed\n\nCustomer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nSkip Size: {skip_size}\nPrice: {price}\n\nAction: Manual booking required"
                )
                return f"Thanks {customer_name}. I'm having a technical issue completing your booking. Our team will call you back on {phone} to confirm your {skip_size} skip for {postcode} at {price}."
                
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
            send_email(
                f"SYSTEM ERROR - {customer_name}",
                f"System error - immediate callback required\n\nError: {str(e)}\n\nCustomer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nSkip Size: {skip_size}",
                'operations@wasteking.co.uk'
            )
            return f"Thanks {customer_name}. Our team will call you on {phone} immediately to complete your {skip_size} skip booking for {postcode}."
    
    def _handle_asbestos(self, args: dict, state: dict) -> str:
        """Handle asbestos inquiry"""
        customer_name = args.get('customer_name', '')
        phone = args.get('phone_number', '')
        postcode = args.get('postcode', '')
        
        if not all([customer_name, phone, postcode]):
            missing = []
            if not customer_name: missing.append("name")
            if not phone: missing.append("phone number")
            if not postcode: missing.append("postcode")
            return f"For asbestos services, I need your {' and '.join(missing)}."
        
        # Send lead
        send_email(
            f"ASBESTOS LEAD - {customer_name}",
            f"Customer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nType: {args.get('asbestos_type', 'Not specified')}\nQuantity: {args.get('quantity', 'Not specified')}\n\nAction: Specialist callback required"
        )
        
        state['stage'] = 'lead_sent'
        return f"Thanks {customer_name}. Asbestos requires specialist handling. Our certified team will call you on {phone} within 2 hours to discuss your requirements and provide a quote."
    
    def _handle_toilet_hire(self, args: dict, state: dict) -> str:
        """Handle toilet hire inquiry"""
        customer_name = args.get('customer_name', '')
        phone = args.get('phone_number', '')
        
        if not all([customer_name, phone]):
            missing = []
            if not customer_name: missing.append("name")
            if not phone: missing.append("phone number")
            return f"For toilet hire, I need your {' and '.join(missing)}."
        
        send_email(
            f"TOILET HIRE LEAD - {customer_name}",
            f"Customer: {customer_name}\nPhone: {phone}\nPostcode: {args.get('postcode', '')}\nNumber: {args.get('number_required', 'Not specified')}\nDuration: {args.get('duration', 'Not specified')}\n\nAction: Call back with quote"
        )
        
        state['stage'] = 'lead_sent'
        return f"Thanks {customer_name}. Our team will call you on {phone} shortly to discuss your toilet hire requirements and provide a quote."
    
    def _handle_man_and_van(self, args: dict, state: dict) -> str:
        """Handle man and van service"""
        customer_name = args.get('customer_name', '')
        phone = args.get('phone_number', '')
        postcode = args.get('postcode', '')
        
        if not all([customer_name, phone, postcode]):
            missing = []
            if not customer_name: missing.append("name")
            if not phone: missing.append("phone number")
            if not postcode: missing.append("postcode")
            return f"For man and van service, I need your {' and '.join(missing)}."
        
        send_email(
            f"MAN & VAN LEAD - {customer_name}",
            f"Customer: {customer_name}\nPhone: {phone}\nPostcode: {postcode}\nVolume: {args.get('volume', 'Not specified')}\nWhen: {args.get('when_required', 'Not specified')}\nSpecial items: {args.get('supplement_items', 'None')}\n\nAction: Call back with pricing"
        )
        
        state['stage'] = 'lead_sent'
        return f"Perfect {customer_name}. Our man and van team will call you on {phone} within the hour to confirm pricing and arrange collection from {postcode}."
    
    def _handle_grab_hire(self, args: dict, state: dict) -> str:
        """Handle grab hire inquiry"""
        customer_name = args.get('customer_name', '')
        phone = args.get('phone_number', '')
        
        if not all([customer_name, phone]):
            missing = []
            if not customer_name: missing.append("name")
            if not phone: missing.append("phone number")
            return f"For grab hire, I need your {' and '.join(missing)}."
        
        send_email(
            f"GRAB HIRE LEAD - {customer_name}",
            f"Customer: {customer_name}\nPhone: {phone}\nPostcode: {args.get('postcode', '')}\nMaterial: {args.get('material_type', 'Not specified')}\nType: {args.get('grab_type', 'Not specified')}\n\nAction: Specialist callback"
        )
        
        state['stage'] = 'lead_sent'
        return f"Thanks {customer_name}. Grab hire pricing varies by location and material type. Our specialist team will call you on {phone} shortly with availability and pricing."
    
    def _get_fallback_price(self, postcode: str, skip_size: str) -> str:
        """Get fallback pricing based on postcode region"""
        pricing = {
            'london': {'4yd': '£190', '6yd': '£230', '8yd': '£270', '12yd': '£370'},
            'midlands': {'4yd': '£170', '6yd': '£210', '8yd': '£250', '12yd': '£350'},
            'north': {'4yd': '£160', '6yd': '£200', '8yd': '£240', '12yd': '£340'},
            'default': {'4yd': '£180', '6yd': '£220', '8yd': '£260', '12yd': '£360'}
        }
        
        postcode_upper = postcode.upper()
        if any(postcode_upper.startswith(p) for p in ['E', 'W', 'N', 'S', 'EC', 'WC']):
            region = 'london'
        elif any(postcode_upper.startswith(p) for p in ['B', 'CV', 'WS', 'WV']):
            region = 'midlands'
        elif any(postcode_upper.startswith(p) for p in ['M', 'L', 'LS']):
            region = 'north'
        else:
            region = 'default'
        
        return pricing[region].get(skip_size.replace('yd', 'yd'), pricing[region].get('8yd', '£260'))

# Helper functions
def send_sms(phone: str, message: str) -> bool:
    """Send SMS via Twilio"""
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_PHONE_NUMBER', '+447700900000')
        
        if not account_sid or not auth_token:
            print(f"SMS WOULD SEND to {phone}: {message}")
            return True
            
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_number, to=phone)
        print(f"SMS SENT to {phone}")
        return True
    except Exception as e:
        print(f"SMS ERROR: {e}")
        return False

def send_email(subject: str, body: str, recipient: str = 'kanchan.ghosh@wasteking.co.uk') -> bool:
    """Send email notification"""
    try:
        email_address = os.getenv('WASTEKING_EMAIL')
        email_password = os.getenv('WASTEKING_EMAIL_PASSWORD')
        
        if not email_address or not email_password:
            print(f"EMAIL WOULD SEND: {subject}")
            return True
            
        msg = MIMEMultipart()
        msg['From'] = email_address
        msg['To'] = recipient
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP('mail.wasteking.co.uk', 587)
        server.starttls()
        server.login(email_address, email_password)
        server.sendmail(email_address, recipient, msg.as_string())
        server.quit()
        
        print(f"EMAIL SENT: {subject}")
        return True
    except Exception as e:
        print(f"EMAIL ERROR: {e}")
        return False

# Initialize agent
agent = WasteKingAgent()

# Flask routes
@app.route('/api/wasteking', methods=['POST', 'GET'])
def process_message():
    try:
        data = request.get_json()
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id', '')
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        if not conversation_id:
            conversation_id = f"conv_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        print(f"\n[{conversation_id}] Customer: {customer_message}")
        
        # Process with OpenAI function calling
        response_text, stage = agent.process_message_with_functions(customer_message, conversation_id)
        
        print(f"[{conversation_id}] Agent: {response_text}")
        
        return jsonify({
            "success": True,
            "message": response_text,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "stage": stage
        })
        
    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        return jsonify({
            "success": False,
            "message": "I'll connect you with our team immediately.",
            "error": str(e)
        }), 500

@app.route('/')
def index():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    html_template = """<!DOCTYPE html>
<html>
<head>
    <title>WasteKing Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-box h3 { margin: 0; color: #2c3e50; font-size: 2em; }
        .stat-box p { margin: 5px 0 0 0; color: #7f8c8d; }
        .conversations { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .conv-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }
        .conv-item.completed { border-left-color: #28a745; background: #f1f8f4; }
        .conv-item.lead-sent { border-left-color: #ffc107; background: #fffdf0; }
        .customer-details { margin-top: 8px; font-size: 14px; color: #495057; }
        .service-badge { background: #007bff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; display: inline-block; }
        .refresh-btn { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; }
        .refresh-btn:hover { background: #0056b3; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing System Dashboard</h1>
        <p>Live conversation monitoring with OpenAI function calling</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3 id="total-conversations">0</h3>
            <p>Total Conversations</p>
        </div>
        <div class="stat-box">
            <h3 id="active-conversations">0</h3>
            <p>Active Now</p>
        </div>
        <div class="stat-box">
            <h3 id="bookings-completed">0</h3>
            <p>Bookings Completed</p>
        </div>
        <div class="stat-box">
            <h3 id="leads-sent">0</h3>
            <p>Leads Generated</p>
        </div>
    </div>
    
    <div class="conversations">
        <h2>Recent Conversations 
            <button class="refresh-btn" onclick="loadDashboard()">Refresh</button>
        </h2>
        <div id="conversation-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('total-conversations').textContent = '0';
                    document.getElementById('active-conversations').textContent = '0';
                    document.getElementById('bookings-completed').textContent = '0';
                    document.getElementById('leads-sent').textContent = '0';
                    document.getElementById('conversation-list').innerHTML = '<p>Redis state management active - conversations tracked in backend</p>';
                })
                .catch(error => {
                    console.error('Dashboard error:', error);
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 5000);
    </script>
</body>
</html>"""
    return render_template_string(html_template)

@app.route('/api/dashboard')
def dashboard_api():
    return jsonify({"success": True, "message": "Dashboard API active"})

if __name__ == '__main__':
    print("WasteKing Agent Starting...")
    print("OpenAI Function Calling: ENABLED")
    print("State Management: Redis/Memory")
    print("Business Rules: LOADED")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
