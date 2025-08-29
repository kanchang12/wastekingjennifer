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
    print("WARNING: Live wasteking_api module not found")
    def create_booking(): return {'success': False, 'error': 'API unavailable'}
    def get_pricing(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def complete_booking(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}
    def create_payment_link(*args, **kwargs): return {'success': False, 'error': 'API unavailable'}

# --- COMPREHENSIVE BUSINESS RULES ---
SKIP_HIRE_RULES = {
    'heavy_materials_max': "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard. Shall I get you the cost of an 8-yard skip?",
    'prohibited_items_full': "Just so you know, there are some prohibited items that cannot be placed in skips — including mattresses (£15 charge), fridges (£20 charge), upholstery, plasterboard, asbestos, and paint. Our man and van service is ideal for light rubbish and can remove most items. If you'd prefer, I can connect you with the team to discuss the man and van option. Would you like to speak to the team about that, or continue with skip hire?",
    'plasterboard_response': "Plasterboard isn't allowed in normal skips. If you have a lot, we can arrange a special plasterboard skip, or our man and van service can collect it for you",
    'fridge_mattress_restrictions': "There may be restrictions on fridges & mattresses depending on your location",
    'delivery_timing': "We usually aim to deliver your skip the next day, but during peak months, it may take a bit longer. Don't worry though – we'll check with the depot to get it to you as soon as we can, and we'll always do our best to get it on the day you need.",
    'not_booking_response': "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book. Would you like a £10 discount? If you're happy with the service after booking, you'll have the option to leave a review.",
    'vat_note': 'If the prices are coming from SMP they are always + VAT',
    'roro_heavy_materials': "For heavy materials like soil & rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only.",
    'largest_skip_correction': "The largest skip is RORO 40 yard. The largest for soil and rubble is 8 yard. Larger skips than that are suitable only for light waste, not heavy materials.",
    'dropped_door_explanation': "Dropped down skips are large waste containers delivered by truck and temporarily placed at a site for collecting and removing bulk waste. The special thing about dropped down skips is their convenience—they allow for easy, on-site disposal of large amounts of waste without multiple trips to a landfill."
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

LG_SERVICES_QUESTIONS = {
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
            "Do you need tipper or grab delivery?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will take some information from you before passing onto our specialist team to give you a cost and availability"
    },
    'wait_and_load': {
        'questions': [
            "Can I take your postcode?",
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
            "What type of waste will you be putting in the RORO?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will pass you onto our specialist team to give you a quote and availability"
    }
}

WASTE_BAGS_INFO = {
    'script': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready"
}

TRANSFER_RULES = {
    'management_director': {
        'triggers': ['glenn currie', 'director', 'speak to glenn'],
        'office_hours': "I am sorry, Glenn is not available, may I take your details and Glenn will call you back?",
        'out_of_hours': "I can take your details and have our director call you back first thing tomorrow"
    },
    'complaints': {
        'triggers': ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry'],
        'office_hours': "I understand your frustration, please bear with me while I transfer you to the appropriate person.",
        'out_of_hours': "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow."
    },
    'specific_person': {
        'tracey_request': "Yes I can see if she's available. What's your name, your telephone number, what is your company name? What is the call regarding?",
        'human_agent': "Yes I can see if someone is available. What's your name, your telephone number, what is your company name? What is the call regarding?"
    }
}

GENERAL_SCRIPTS = {
    'timing_query': "Orders are completed between 6am and 5pm. If you need a specific time, I'll raise a ticket and the team will get back to you shortly. Is there anything else I can help you with?",
    'location_response': "I am based in the head office although we have depots nationwide and local to you.",
    'lg_transfer_message': "I will take some information from you before passing onto our specialist team to give you a cost and availability",
    'closing': "Is there anything else I can help with? Thanks for trusting Waste King",
    'help_intro': "I can help with that",
    'permit_response': "We'll arrange the permit for you and include the cost in your quote. The price varies by council.",
    'access_requirements': "Access requirements for grab lorries generally include: Width and height clearance of around 3 meters, stable ground conditions, sufficient space for the grab arm to operate safely (about 6 meters radius), and a clear access route suitable for heavy vehicles."
}

# --- HELPER FUNCTIONS ---
def is_business_hours():
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    uk_now = utc_now + timedelta(hours=0)
    day = uk_now.weekday()
    hour = uk_now.hour + (uk_now.minute / 60.0)
    
    if day < 4: return 8 <= hour < 17
    elif day == 4: return 8 <= hour < 16.5
    elif day == 5: return 9 <= hour < 12
    else: return False

def send_email(subject, body, recipient=None):
    # WasteKing email configuration
    email_address = os.getenv('WASTEKING_EMAIL')  # e.g., noreply@wasteking.co.uk
    email_password = os.getenv('WASTEKING_EMAIL_PASSWORD')
    smtp_server = os.getenv('WASTEKING_SMTP_SERVER', 'mail.wasteking.co.uk')  # Default SMTP server
    smtp_port = int(os.getenv('WASTEKING_SMTP_PORT', '587'))  # Default port
    
    if not email_address or not email_password:
        print("WARNING: WasteKing email credentials not set")
        print("Please set WASTEKING_EMAIL and WASTEKING_EMAIL_PASSWORD environment variables")
        return False

    recipient = recipient or 'kanchan.ghosh@wasteking.co.uk'
    
    msg = MIMEMultipart()
    msg['From'] = email_address
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(email_address, email_password)
        server.sendmail(email_address, recipient, msg.as_string())
        server.quit()
        print(f"✅ Email sent from {email_address} to {recipient}")
        return True
    except Exception as e:
        print(f"❌ Email sending failed: {e}")
        print(f"SMTP Server: {smtp_server}:{smtp_port}")
        print("Check your email credentials and SMTP settings")
        return False

def send_lead_email(customer_data, service_type, conversation_history):
    subject = f"{service_type.upper()} Lead - {customer_data.get('name', 'Unknown')}"
    body = f"""
New {service_type.upper()} Lead:

CUSTOMER DETAILS:
- Name: {customer_data.get('name', 'Not provided')}
- Phone: {customer_data.get('phone', 'Not provided')}
- Postcode: {customer_data.get('postcode', 'Not provided')}
- Customer Type: {customer_data.get('customer_type', 'Not specified')}
- Service Required: {service_type.upper()}

SPECIFIC DETAILS:
"""
    for key, value in customer_data.items():
        if key not in ['name', 'phone', 'postcode', 'customer_type'] and value:
            body += f"- {key.replace('_', ' ').title()}: {value}\n"
    
    body += f"""
CONVERSATION HISTORY:
{chr(10).join(conversation_history[-5:]) if conversation_history else 'No conversation history'}

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    return send_email(subject, body, 'kanchan.ghosh@wasteking.co.uk')

def send_booking_email(booking_data):
    """Send manual booking email to operations"""
    subject = f"SKIP BOOKING - {booking_data['name']} - {booking_data['booking_ref']}"
    body = f"""
URGENT SKIP BOOKING - MANUAL PROCESSING REQUIRED

BOOKING DETAILS:
- Reference: {booking_data['booking_ref']}
- Customer: {booking_data['name']}
- Phone: {booking_data['phone']}
- Postcode: {booking_data['postcode']}
- Skip Size: {booking_data['skip_size']}
- Price Quoted: {booking_data['price']}
- Customer Type: {booking_data.get('customer_type', 'Not specified')}

BOOKING STATUS: {'API FALLBACK' if booking_data.get('api_fallback') else 'MANUAL FALLBACK'}

ACTION REQUIRED:
1. Contact customer within 2 hours to confirm delivery
2. Process payment if not already done
3. Schedule delivery with depot
4. Update booking system

Timestamp: {booking_data['timestamp']}
"""
    send_email(subject, body, 'operations@wasteking.co.uk')

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

# --- FAST CONVERSATION HANDLER ---
class FastWasteKingAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.conversations = {}
        
    def process_message(self, message, conversation_id):
        # Get conversation state
        state = self.conversations.get(conversation_id, {
            'stage': 'greeting',
            'customer_data': {},
            'history': [],
            'service_type': None,
            'customer_type': None
        })
        
        state['history'].append(f"Customer: {message}")
        
        # Fast routing logic - no function calls
        response = self.get_fast_response(message, state)
        
        state['history'].append(f"Agent: {response}")
        self.conversations[conversation_id] = state
        
        return response, state.get('stage', 'conversation')
    
    def get_fast_response(self, message, state):
        msg_lower = message.lower()
        
        # 1. CUSTOMER TYPE CHECK - Priority
        if not state.get('customer_type'):
            customer_type = self.detect_customer_type(msg_lower)
            if customer_type:
                state['customer_type'] = customer_type
            else:
                return "Are you a domestic customer or trade customer?"
        
        # 2. SERVICE IDENTIFICATION
        service_type = self.detect_service_type(msg_lower, state)
        if service_type:
            state['service_type'] = service_type
        
        # 3. HANDLE SKIP HIRE - ONLY SERVICE WITH PRICING - NEVER TRANSFERS
        if service_type == 'skip_hire':
            return self.handle_skip_hire_never_transfer(message, state, msg_lower)
        
        # 4. ALL OTHER SERVICES - COMPLETE LEAD GENERATION
        elif service_type in ['mav', 'grab', 'lg_service']:
            return self.handle_complete_lead_generation(message, state, service_type, msg_lower)
        
        # 5. GENERAL CONVERSATION
        else:
            return self.handle_general_conversation(message, state, msg_lower)
    
    def detect_customer_type(self, msg_lower):
        if any(word in msg_lower for word in ['trade', 'business', 'commercial', 'company', 'agency', 'ltd']):
            return 'trade'
        elif any(word in msg_lower for word in ['domestic', 'home', 'house', 'personal', 'private']):
            return 'domestic'
        return None
    
    def detect_service_type(self, msg_lower, state):
        # Skip hire detection
        if any(word in msg_lower for word in ['skip', 'container hire', 'yard skip']) and not any(word in msg_lower for word in ['collection', 'collect', 'pick up']):
            return 'skip_hire'
        
        # Skip collection (different service)
        if any(phrase in msg_lower for phrase in ['skip collection', 'collect skip', 'pick up skip']):
            return 'skip_collection'
        
        # Man & Van
        if any(phrase in msg_lower for phrase in ['man and van', 'clearance', 'furniture removal', 'house clearance', 'office clean']):
            return 'mav'
        
        # Grab hire
        if any(phrase in msg_lower for phrase in ['grab', '6 wheeler', '8 wheeler', 'grab lorry']):
            return 'grab'
        
        # LG Services
        lg_services = ['toilet hire', 'asbestos', 'road sweep', 'aggregates', 'roro', 'hazardous']
        if any(service in msg_lower for service in lg_services):
            return 'lg_service'
        
        return None
    
    def handle_skip_hire_never_transfer(self, message, state, msg_lower):
        """Handle skip hire - NEVER transfers to humans - completely automated"""
        # Check for heavy materials with large skips
        large_skips = ['10', '12', '14', '16', '20']
        heavy_materials = ['soil', 'rubble', 'concrete', 'heavy']
        if any(size in msg_lower for size in large_skips) and any(material in msg_lower for material in heavy_materials):
            return SKIP_HIRE_RULES['heavy_materials_max']
        
        # Handle specific prohibited item questions
        if 'plasterboard' in msg_lower:
            return SKIP_HIRE_RULES['plasterboard_response']
        elif any(item in msg_lower for item in ['sofa', 'upholstery', 'furniture']):
            return SKIP_HIRE_RULES['prohibited_items_full']
        elif any(item in msg_lower for item in ['mattress', 'fridge', 'freezer']):
            return SKIP_HIRE_RULES['fridge_mattress_restrictions']
        elif 'prohibited' in msg_lower or 'not allowed' in msg_lower:
            return SKIP_HIRE_RULES['prohibited_items_full']
        
        # Handle delivery timing questions
        if any(phrase in msg_lower for phrase in ['when deliver', 'delivery time', 'when arrive']):
            return SKIP_HIRE_RULES['delivery_timing']
        
        # Handle permit questions
        if 'permit' in msg_lower:
            return GENERAL_SCRIPTS['permit_response']
        
        # Handle not booking responses
        if any(phrase in msg_lower for phrase in ['call back', 'think about', 'check with', 'phone around']):
            return SKIP_HIRE_RULES['not_booking_response']
        
        # Extract customer data
        name = self.extract_name(message)
        phone = self.extract_phone(message)
        postcode = self.extract_postcode(message)
        skip_size = self.extract_skip_size(message)
        
        if name: state['customer_data']['name'] = name
        if phone: state['customer_data']['phone'] = phone
        if postcode: state['customer_data']['postcode'] = postcode
        if skip_size: state['customer_data']['skip_size'] = skip_size
        
        # Check what we're missing for pricing
        missing = []
        if not state['customer_data'].get('name'): missing.append("your name")
        if not state['customer_data'].get('phone'): missing.append("your phone number") 
        if not state['customer_data'].get('postcode'): missing.append("your postcode")
        
        if missing:
            if len(missing) == 1:
                return f"{GENERAL_SCRIPTS['help_intro']}. Can I get {missing[0]}?"
            else:
                return f"{GENERAL_SCRIPTS['help_intro']}. I'll need {', '.join(missing[:-1])} and {missing[-1]}."
        
        # Check if customer wants to book after pricing
        if state.get('price') and any(word in msg_lower for word in ['yes', 'book', 'proceed', 'go ahead']):
            return self.complete_skip_booking_never_transfer(state)
        
        # Get pricing if not already done
        if not state.get('price'):
            return self.get_skip_pricing_never_transfer(state)
        
        return "Would you like to book this skip?"
    
    def get_skip_pricing_never_transfer(self, state):
        """Get skip pricing - NEVER transfers to humans - always provides pricing"""
        if not API_AVAILABLE:
            return self.get_fallback_skip_pricing(state)
        
        try:
            # Create booking
            booking_result = create_booking()
            if not booking_result.get('success'):
                return self.get_fallback_skip_pricing(state)
            
            # Get pricing
            booking_ref = booking_result['booking_ref']
            postcode = state['customer_data']['postcode']
            skip_size = state['customer_data'].get('skip_size', '8yd')
            
            price_result = get_pricing(booking_ref, postcode, 'skip', skip_size)
            if not price_result.get('success'):
                return self.get_fallback_skip_pricing(state)
            
            price = price_result['price']
            state['price'] = price
            state['booking_ref'] = booking_ref
            state['stage'] = 'pricing_provided'
            
            vat_note = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
            return f"{skip_size} skip at {postcode}: {price}{vat_note}. Would you like to book this?"
            
        except Exception as e:
            print(f"Pricing error: {e}")
            return self.get_fallback_skip_pricing(state)
    
    def get_fallback_skip_pricing(self, state):
        """Fallback pricing system when API fails - NEVER transfers"""
        postcode = state['customer_data']['postcode']
        skip_size = state['customer_data'].get('skip_size', '8yd')
        
        # Regional pricing matrix
        pricing_matrix = {
            'london_zones': {  # E, W, N, S, EC, WC, etc.
                '2yd': '£160', '4yd': '£190', '6yd': '£230', '8yd': '£270',
                '10yd': '£320', '12yd': '£370', '14yd': '£420', '16yd': '£480'
            },
            'midlands': {  # B, CV, WS, WV, etc.
                '2yd': '£140', '4yd': '£170', '6yd': '£210', '8yd': '£250',
                '10yd': '£300', '12yd': '£350', '14yd': '£400', '16yd': '£460'
            },
            'north': {  # M, L, S, LS, etc.
                '2yd': '£130', '4yd': '£160', '6yd': '£200', '8yd': '£240',
                '10yd': '£290', '12yd': '£340', '14yd': '£390', '16yd': '£450'
            },
            'default': {
                '2yd': '£150', '4yd': '£180', '6yd': '£220', '8yd': '£260',
                '10yd': '£310', '12yd': '£360', '14yd': '£410', '16yd': '£470'
            }
        }
        
        # Determine pricing zone
        postcode_upper = postcode.upper()
        if any(postcode_upper.startswith(prefix) for prefix in ['E', 'W', 'N', 'S', 'EC', 'WC', 'NW', 'SW']):
            zone = 'london_zones'
        elif any(postcode_upper.startswith(prefix) for prefix in ['B', 'CV', 'WS', 'WV', 'DY']):
            zone = 'midlands'
        elif any(postcode_upper.startswith(prefix) for prefix in ['M', 'L', 'S', 'LS', 'HX', 'HD']):
            zone = 'north'
        else:
            zone = 'default'
        
        price = pricing_matrix[zone].get(skip_size, pricing_matrix[zone]['8yd'])
        state['price'] = price
        state['booking_ref'] = f"FB{datetime.now().strftime('%Y%m%d%H%M%S')}"
        state['stage'] = 'pricing_provided'
        
        vat_note = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
        return f"{skip_size} skip at {postcode}: {price}{vat_note}. Would you like to book this?"
    
    def complete_skip_booking_never_transfer(self, state):
        """Complete skip booking - NEVER transfers to humans"""
        if not API_AVAILABLE:
            # Create manual booking record when API unavailable
            booking_data = {
                'name': state['customer_data']['name'],
                'phone': state['customer_data']['phone'],
                'postcode': state['customer_data']['postcode'],
                'skip_size': state['customer_data'].get('skip_size', '8yd'),
                'price': state['price'],
                'booking_ref': state['booking_ref'],
                'customer_type': state.get('customer_type'),
                'timestamp': datetime.now().isoformat()
            }
            
            # Send booking email to operations
            send_booking_email(booking_data)
            state['stage'] = 'completed'
            
            return f"Booking confirmed! Reference: {state['booking_ref']}, Price: {state['price']}. Our team will contact you within 2 hours to arrange delivery. {GENERAL_SCRIPTS['closing']}"
        
        try:
            customer_data = state['customer_data'].copy()
            customer_data['price'] = state['price']
            customer_data['booking_ref'] = state['booking_ref']
            
            result = complete_booking(customer_data)
            
            if result.get('success'):
                booking_ref = result['booking_ref']
                price = result['price']
                payment_link = result.get('payment_link')
                
                response = f"Booking confirmed! Ref: {booking_ref}, Price: {price}."
                if payment_link:
                    response += " A payment link has been sent to your phone."
                
                response += f" {GENERAL_SCRIPTS['closing']}"
                state['stage'] = 'completed'
                
                return response
            else:
                # Fallback manual booking - NEVER transfer
                booking_data = {
                    'name': state['customer_data']['name'],
                    'phone': state['customer_data']['phone'],
                    'postcode': state['customer_data']['postcode'],
                    'skip_size': state['customer_data'].get('skip_size', '8yd'),
                    'price': state['price'],
                    'booking_ref': state['booking_ref'],
                    'customer_type': state.get('customer_type'),
                    'timestamp': datetime.now().isoformat(),
                    'api_fallback': True
                }
                
                send_booking_email(booking_data)
                state['stage'] = 'completed'
                
                return f"Booking confirmed! Reference: {state['booking_ref']}, Price: {state['price']}. Our team will contact you within 2 hours to confirm delivery details. {GENERAL_SCRIPTS['closing']}"
                
        except Exception as e:
            print(f"Booking error: {e}")
            # Manual booking fallback - NEVER transfer for skip hire
            booking_data = {
                'name': state['customer_data']['name'],
                'phone': state['customer_data']['phone'],
                'postcode': state['customer_data']['postcode'],
                'skip_size': state['customer_data'].get('skip_size', '8yd'),
                'price': state['price'],
                'booking_ref': state['booking_ref'],
                'customer_type': state.get('customer_type'),
                'timestamp': datetime.now().isoformat(),
                'manual_fallback': True
            }
            
            send_booking_email(booking_data)
            state['stage'] = 'completed'
            
            return f"Booking confirmed! Reference: {state['booking_ref']}, Price: {state['price']}. Our team will contact you within 2 hours to arrange delivery. {GENERAL_SCRIPTS['closing']}"
    
    def handle_complete_lead_generation(self, message, state, service_type, msg_lower):
        """Handle all non-skip services - COMPLETE lead generation - NO premature transfers"""
        # Extract data first
        self.extract_comprehensive_data(message, state, msg_lower, service_type)
        
        # SKIP COLLECTION (separate from skip hire)
        if service_type == 'skip_collection':
            return self.handle_skip_collection_complete(message, state, msg_lower)
        
        # MAN & VAN SERVICE
        elif service_type == 'mav':
            return self.handle_mav_complete(message, state, msg_lower)
        
        # GRAB HIRE SERVICE  
        elif service_type == 'grab':
            return self.handle_grab_complete(message, state, msg_lower)
        
        # LG SERVICES (Road Sweeper, Toilet Hire, Asbestos, etc.)
        elif service_type == 'lg_service':
            return self.handle_lg_service_complete(message, state, msg_lower)
        
        return "Our specialist team will call you back to discuss your requirements."
    
    def extract_comprehensive_data(self, message, state, msg_lower, service_type):
        """Extract ALL possible data from message based on service type"""
        # Basic details for ALL services
        name = self.extract_name(message)
        phone = self.extract_phone(message)
        postcode = self.extract_postcode(message)
        
        if name: state['customer_data']['name'] = name
        if phone: state['customer_data']['phone'] = phone
        if postcode: state['customer_data']['postcode'] = postcode
        
        # Service-specific data extraction
        if service_type == 'mav':
            self.extract_mav_data(message, state, msg_lower)
        elif service_type == 'grab':
            self.extract_grab_data(message, state, msg_lower)
        elif service_type == 'lg_service':
            self.extract_lg_data(message, state, msg_lower)
    
    def extract_mav_data(self, message, state, msg_lower):
        """Extract MAV-specific data"""
        # Volume extraction
        volume_patterns = [
            (r'(\d+)\s*(?:cubic\s*)?yard', 'cubic yards'),
            (r'(\d+)\s*washing\s*machine', 'washing machine loads'),
            (r'(\d+)\s*bag', 'black bags'),
            (r'small\s*amount', '2-3 cubic yards'),
            (r'large\s*amount', '8-10 cubic yards'),
            (r'full\s*house', '15-20 cubic yards'),
            (r'single\s*room', '3-4 cubic yards')
        ]
        
        for pattern, unit in volume_patterns:
            match = re.search(pattern, msg_lower)
            if match and not state['customer_data'].get('volume'):
                if match.groups():
                    state['customer_data']['volume'] = f"{match.group(1)} {unit}"
                else:
                    state['customer_data']['volume'] = unit
                break
        
        # When required
        time_patterns = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap', 'urgent', 'next week']
        for pattern in time_patterns:
            if pattern in msg_lower and not state['customer_data'].get('when_required'):
                state['customer_data']['when_required'] = pattern.title()
                break
        
        # Company name for trade customers
        if state.get('customer_type') == 'trade':
            company_patterns = [
                r'company\s+(?:is\s+|name\s+is\s+)?([A-Z][A-Za-z\s&]+)',
                r'work\s+for\s+([A-Z][A-Za-z\s&]+)',
                r'([A-Z][A-Za-z]+\s+Ltd)',
                r'([A-Z][A-Za-z]+\s+Limited)'
            ]
            
            for pattern in company_patterns:
                match = re.search(pattern, message)
                if match and not state['customer_data'].get('company_name'):
                    state['customer_data']['company_name'] = match.group(1).strip()
                    break
        
        # Supplement items
        if any(item in msg_lower for item in ['mattress', 'fridge', 'upholstery', 'sofa']):
            supplements = []
            if 'mattress' in msg_lower: supplements.append('mattresses')
            if any(word in msg_lower for word in ['fridge', 'freezer']): supplements.append('fridges')  
            if any(word in msg_lower for word in ['upholstery', 'sofa', 'chair']): supplements.append('upholstered furniture')
            state['customer_data']['supplement_items'] = ', '.join(supplements) if supplements else 'none'
        elif any(word in msg_lower for word in ['no', 'none', 'nothing']) and state.get('supplement_checked'):
            state['customer_data']['supplement_items'] = 'none'
        
        # Access details
        if any(word in msg_lower for word in ['narrow', 'difficult', 'restricted', 'stairs', 'lift']):
            state['customer_data']['access_details'] = 'Access restrictions mentioned'
        elif any(phrase in msg_lower for phrase in ['good access', 'easy access', 'ground floor']):
            state['customer_data']['access_details'] = 'Good access'
    
    def extract_grab_data(self, message, state, msg_lower):
        """Extract Grab-specific data"""
        # Grab type
        if '6 wheel' in msg_lower:
            state['customer_data']['grab_type'] = '6_wheeler'
        elif '8 wheel' in msg_lower:
            state['customer_data']['grab_type'] = '8_wheeler'
        
        # Material type
        if any(material in msg_lower for material in ['soil', 'rubble', 'muckaway']):
            state['customer_data']['material_type'] = 'Heavy materials (soil/rubble)'
        elif any(material in msg_lower for material in ['wood', 'general', 'mixed']):
            state['customer_data']['material_type'] = 'General waste'
        
        # When required
        time_patterns = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap', 'urgent', 'next week']
        for pattern in time_patterns:
            if pattern in msg_lower and not state['customer_data'].get('when_required'):
                state['customer_data']['when_required'] = pattern.title()
                break
    
    def extract_lg_data(self, message, state, msg_lower):
        """Extract LG service specific data"""
        # Determine specific service
        if not state.get('lg_service_type'):
            state['lg_service_type'] = self.determine_lg_service(msg_lower)
        
        # When required
        time_patterns = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap', 'urgent', 'next week']
        for pattern in time_patterns:
            if pattern in msg_lower and not state['customer_data'].get('when_required'):
                state['customer_data']['when_required'] = pattern.title()
                break
    
    def handle_mav_complete(self, message, state, msg_lower):
        """Complete MAV flow - collects ALL required information before transfer"""
        customer_type = state.get('customer_type')
        
        # Check for heavy materials first - immediate response
        if any(material in msg_lower for material in ['soil', 'rubble', 'concrete', 'heavy', 'bricks']):
            return MAV_RULES['heavy_materials_response']
        
        # Sunday collection check - immediate transfer ONLY after collecting basic details
        if 'sunday' in msg_lower or (state['customer_data'].get('when_required', '').lower() == 'sunday'):
            basic_required = ['name', 'phone', 'postcode']
            missing_basic = [field for field in basic_required if not state['customer_data'].get(field)]
            
            if missing_basic:
                field = missing_basic[0]
                if field == 'name': return "What's your name?"
                elif field == 'phone': return "What's the best phone number to contact you on?"
                elif field == 'postcode': return "What's your postcode?"
            
            if not state.get('sunday_lead_sent'):
                state['sunday_lead_sent'] = True
                send_lead_email(state['customer_data'], 'mav_sunday', state['history'])
                return MAV_RULES['sunday_response']
        
        # Volume explanation if needed
        if not state['customer_data'].get('volume') and not state.get('volume_explained'):
            state['volume_explained'] = True
            return MAV_RULES['volume_explanation']
        
        # Supplement check if not done
        if not state['customer_data'].get('supplement_items') and not state.get('supplement_checked'):
            state['supplement_checked'] = True
            return MAV_RULES['supplement_check']
        
        # Define required fields based on customer type
        if customer_type == 'trade':
            required_fields = ['name', 'phone', 'postcode', 'volume', 'when_required', 'supplement_items', 'company_name']
        else:
            required_fields = ['name', 'phone', 'postcode', 'volume', 'when_required', 'supplement_items']
        
        # Check for missing fields and ask systematically
        missing_field = self.get_next_missing_field(state, required_fields)
        if missing_field:
            return self.ask_for_field(missing_field, 'mav')
        
        # All data collected - complete lead and transfer
        return self.complete_mav_lead_comprehensive(state)
    
    def handle_grab_complete(self, message, state, msg_lower):
        """Complete Grab flow - all required data before transfer"""
        # Grab capacity explanations
        if '6 wheel' in msg_lower and not state.get('grab_6_explained'):
            state['grab_6_explained'] = True
            state['customer_data']['grab_type'] = '6_wheeler'
            return GRAB_RULES['6_wheeler_explanation']
        elif '8 wheel' in msg_lower and not state.get('grab_8_explained'):
            state['grab_8_explained'] = True
            state['customer_data']['grab_type'] = '8_wheeler'
            return GRAB_RULES['8_wheeler_explanation']
        
        # Mixed materials check
        material_type = state['customer_data'].get('material_type', '')
        msg_materials = msg_lower
        has_soil_rubble = any(material in (material_type + msg_materials) for material in ['soil', 'rubble', 'muckaway'])
        has_other = any(item in (material_type + msg_materials) for item in ['wood', 'furniture', 'plastic', 'metal', 'mixed'])
        
        if has_soil_rubble and has_other and not state.get('mixed_materials_warned'):
            state['mixed_materials_warned'] = True
            return GRAB_RULES['mixed_materials_response']
        
        # Required fields for grab
        required_fields = ['name', 'phone', 'postcode', 'grab_type', 'material_type', 'when_required']
        
        # Check for missing fields
        missing_field = self.get_next_missing_field(state, required_fields)
        if missing_field:
            return self.ask_for_field(missing_field, 'grab')
        
        # Complete grab lead
        return self.complete_grab_lead_comprehensive(state)
    
    def handle_lg_service_complete(self, message, state, msg_lower):
        """Handle LG services with complete data collection"""
        # Determine specific LG service type
        lg_service = self.determine_lg_service(msg_lower)
        if not state.get('lg_service_type'):
            state['lg_service_type'] = lg_service
        
        lg_service = state.get('lg_service_type', lg_service)
        
        # Get service configuration
        service_config = LG_SERVICES_QUESTIONS.get(lg_service, {})
        intro = service_config.get('intro', GENERAL_SCRIPTS['lg_transfer_message'])
        
        # Start with intro if not done
        if not state.get('lg_intro_given'):
            state['lg_intro_given'] = True
            return intro
        
        # Define required fields based on service type
        if lg_service == 'toilet_hire':
            required_fields = ['name', 'phone', 'postcode', 'number_required', 'event_type', 'when_required']
        elif lg_service == 'asbestos':
            required_fields = ['name', 'phone', 'postcode', 'service_type', 'asbestos_type', 'quantity']
        elif lg_service == 'road_sweeper':
            required_fields = ['name', 'phone', 'postcode', 'hours_required', 'when_required']
        else:
            required_fields = ['name', 'phone', 'postcode', 'when_required']
        
        # Extract service-specific data
        self.extract_lg_specific_data(message, state, msg_lower, lg_service)
        
        # Check for missing fields
        missing_field = self.get_next_missing_field(state, required_fields)
        if missing_field:
            return self.ask_for_field(missing_field, lg_service)
        
        # Complete LG service lead
        return self.complete_lg_service_comprehensive(state, lg_service)
    
    def extract_lg_specific_data(self, message, state, msg_lower, lg_service):
        """Extract service-specific LG data"""
        if lg_service == 'toilet_hire':
            # Number required
            number_match = re.search(r'(\d+)', message)
            if number_match and not state['customer_data'].get('number_required'):
                state['customer_data']['number_required'] = f"{number_match.group(1)} toilets"
            
            # Event type
            if any(word in msg_lower for word in ['event', 'wedding', 'party']):
                state['customer_data']['event_type'] = 'Event'
            elif any(word in msg_lower for word in ['long term', 'ongoing']):
                state['customer_data']['event_type'] = 'Long term'
        
        elif lg_service == 'asbestos':
            # Service type
            if 'skip' in msg_lower:
                state['customer_data']['service_type'] = 'Skip'
            elif 'collection' in msg_lower:
                state['customer_data']['service_type'] = 'Collection'
            
            # Quantity
            if not state['customer_data'].get('quantity'):
                quantity_patterns = [r'(\d+\s*(?:bag|sheet|panel|sqm|m2))', r'small\s*amount', r'large\s*amount']
                for pattern in quantity_patterns:
                    match = re.search(pattern, msg_lower)
                    if match:
                        state['customer_data']['quantity'] = match.group(0) if match.groups() else pattern.replace('\\s*', ' ')
                        break
        
        elif lg_service == 'road_sweeper':
            # Hours required
            hours_match = re.search(r'(\d+)\s*hour', msg_lower)
            if hours_match and not state['customer_data'].get('hours_required'):
                state['customer_data']['hours_required'] = f"{hours_match.group(1)} hours"
    
    def get_next_missing_field(self, state, required_fields):
        """Get next missing field in order of priority"""
        for field in required_fields:
            if not state['customer_data'].get(field):
                return field
        return None
    
    def ask_for_field(self, field, service_type):
        """Ask for specific field based on service type"""
        common_questions = {
            'name': "What's your name?",
            'phone': "What's the best phone number to contact you on?",
            'postcode': "What's your postcode?",
            'when_required': "When do you need this?"
        }
        
        mav_questions = {
            'volume': "How much waste do you have? Think in terms of washing machine loads or black bags.",
            'supplement_items': "Do you have any mattresses, fridges, or upholstered furniture that need collecting?",
            'company_name': "What's your company name?"
        }
        
        grab_questions = {
            'grab_type': "Do you need a 6-wheel or 8-wheel grab lorry?",
            'material_type': "What type of material - soil/rubble or general waste?"
        }
        
        lg_questions = {
            'number_required': "How many do you require?",
            'event_type': "Is this for an event or longer term?",
            'service_type': "Do you need a skip or just a collection?",
            'asbestos_type': "What type of asbestos is it?",
            'quantity': "How much do you have?",
            'hours_required': "How many hours do you require?"
        }
        
        # Check common questions first
        if field in common_questions:
            return common_questions[field]
        elif service_type == 'mav' and field in mav_questions:
            return mav_questions[field]
        elif service_type == 'grab' and field in grab_questions:
            return grab_questions[field]
        elif field in lg_questions:
            return lg_questions[field]
        else:
            return f"Can you tell me about your {field.replace('_', ' ')}?"
    
    def complete_mav_lead_comprehensive(self, state):
        """Complete MAV lead with all details collected"""
        if not state.get('mav_lead_sent'):
            state['mav_lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            lead_type = 'trade_mav' if state.get('customer_type') == 'trade' else 'domestic_mav'
            send_lead_email(state['customer_data'], lead_type, state['history'])
            
            callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
            name = state['customer_data'].get('name', '')
            
            return f"Perfect {name}, I have all your details for your man & van clearance. Our team will call you back {callback_time} with exact pricing and to arrange collection. {GENERAL_SCRIPTS['closing']}"
        
        return f"Our team will call you back to arrange your man & van service. {GENERAL_SCRIPTS['closing']}"
    
    def complete_grab_lead_comprehensive(self, state):
        """Complete Grab lead with all details collected"""
        if not state.get('grab_lead_sent'):
            state['grab_lead_sent'] = True 
            state['stage'] = 'lead_sent'
            send_lead_email(state['customer_data'], 'grab_hire', state['history'])
            
            callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
            name = state['customer_data'].get('name', '')
            return f"Thank you {name}, I have all your grab hire details. {GENERAL_SCRIPTS['lg_transfer_message']} and our specialist team will call you back {callback_time}. {GENERAL_SCRIPTS['closing']}"
        
        return f"Our specialist team will call you back regarding your grab hire requirements. {GENERAL_SCRIPTS['closing']}"
    
    def complete_lg_service_comprehensive(self, state, lg_service):
        """Complete LG service with all details collected"""
        if not state.get('lg_lead_sent'):
            state['lg_lead_sent'] = True
            state['stage'] = 'lead_sent'
            send_lead_email(state['customer_data'], lg_service, state['history'])
            
            # Service-specific callback messages
            if lg_service == 'asbestos':
                callback_text = "Our certified asbestos team will call you back"
            elif lg_service == 'hazardous_waste':
                callback_text = "Our hazardous waste specialists will call you back"
            else:
                callback_text = "Our specialist team will call you back"
            
            callback_time = "within the next few hours" if is_business_hours() else "first thing tomorrow"
            name = state['customer_data'].get('name', '')
            
            return f"Thank you {name}, I have all the details. {callback_text} {callback_time} to confirm cost and availability. {GENERAL_SCRIPTS['closing']}"
        
        return f"Our specialist team will call you back regarding your {lg_service} requirements. {GENERAL_SCRIPTS['closing']}"
    
    def determine_lg_service(self, msg_lower):
        """Determine which LG service is being requested"""
        if any(word in msg_lower for word in ['road sweep', 'street sweep']):
            return 'road_sweeper'
        elif any(word in msg_lower for word in ['toilet', 'portaloo', 'portable toilet']):
            return 'toilet_hire'
        elif 'asbestos' in msg_lower:
            return 'asbestos'
        elif any(word in msg_lower for word in ['hazardous', 'chemical', 'dangerous']):
            return 'hazardous_waste'
        elif any(word in msg_lower for word in ['wheelie bin', 'bin hire']):
            return 'wheelie_bins'
        elif any(word in msg_lower for word in ['aggregate', 'sand', 'gravel', 'stone']):
            return 'aggregates'
        elif any(word in msg_lower for word in ['wait and load', 'wait load']):
            return 'wait_and_load'
        elif any(word in msg_lower for word in ['roro', 'roll on', '30 yard', '35 yard', '40 yard']):
            return 'roro'
        else:
            return 'general_lg'
    
    def handle_skip_collection_complete(self, message, state, msg_lower):
        """Handle skip collection with complete data collection"""
        if not state.get('collection_started'):
            state['collection_started'] = True
            return SKIP_COLLECTION_RULES['script']
        
        # Extract specific collection data
        address_line1 = self.extract_address_line1(message)
        level_load = 'yes' if any(word in msg_lower for word in ['level', 'flush', 'not overloaded']) else None
        prohibited_check = 'confirmed' if any(phrase in msg_lower for phrase in ['no prohibited', 'nothing prohibited']) else None
        access_issues = self.extract_access_issues(message)
        
        if address_line1: state['customer_data']['address_line1'] = address_line1
        if level_load: state['customer_data']['level_load'] = level_load
        if prohibited_check: state['customer_data']['prohibited_check'] = prohibited_check
        if access_issues: state['customer_data']['access_issues'] = access_issues
        
        # Check required fields for collection
        required_fields = ['name', 'phone', 'postcode', 'address_line1', 'level_load', 'prohibited_check', 'access_issues']
        missing = [field for field in required_fields if not state['customer_data'].get(field)]
        
        if missing:
            field = missing[0]
            if field == 'name': return "What's your name?"
            elif field == 'phone': return "What's the best phone number to contact you on?"
            elif field == 'postcode': return "What's your postcode?"
            elif field == 'address_line1': return "What's the first line of your address?"
            elif field == 'level_load': return "Is the skip a level load?"
            elif field == 'prohibited_check': return "Can you confirm there are no prohibited items in the skip?"
            elif field == 'access_issues': return "Are there any access issues?"
        
        # Complete collection booking
        if not state.get('collection_lead_sent'):
            state['collection_lead_sent'] = True
            state['stage'] = 'lead_sent'
            send_lead_email(state['customer_data'], 'skip_collection', state['history'])
            return SKIP_COLLECTION_RULES['completion']
        
        return SKIP_COLLECTION_RULES['completion']
    
    def handle_general_conversation(self, message, state, msg_lower):
        """Handle general conversation and info requests"""
        # Transfer requests
        if any(phrase in msg_lower for phrase in ['speak to glenn', 'director', 'glenn currie']):
            return self.handle_director_request(state)
        
        elif any(phrase in msg_lower for phrase in ['complaint', 'complain', 'unhappy', 'frustrated']):
            return self.handle_complaint(state)
        
        elif any(phrase in msg_lower for phrase in ['speak to tracey', 'talk to tracey']):
            return TRANSFER_RULES['specific_person']['tracey_request']
        
        elif any(phrase in msg_lower for phrase in ['speak to human', 'human agent', 'talk to person']):
            return TRANSFER_RULES['specific_person']['human_agent']
        
        # Information requests
        elif any(phrase in msg_lower for phrase in ['when deliver', 'delivery time', 'when arrive']):
            return SKIP_HIRE_RULES['delivery_timing']
        
        elif any(phrase in msg_lower for phrase in ['what time', 'specific time', 'exact time']):
            return GENERAL_SCRIPTS['timing_query']
        
        elif any(phrase in msg_lower for phrase in ['where based', 'local', 'depot', 'close by']):
            return GENERAL_SCRIPTS['location_response']
        
        elif any(phrase in msg_lower for phrase in ['waste bag', 'skip bag', 'skip sack']):
            return WASTE_BAGS_INFO['script']
        
        elif 'permit' in msg_lower:
            return GENERAL_SCRIPTS['permit_response']
        
        elif any(phrase in msg_lower for phrase in ['access', 'requirements', 'vehicle size']):
            return GENERAL_SCRIPTS['access_requirements']
        
        # Use OpenAI for natural responses - SINGLE CALL
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": """You are Jennifer, a friendly UK customer service agent for Waste King. 

Key services: skip hire (gets pricing), man & van clearance, grab hire, specialist services (all others get leads).

IMPORTANT: 
- Keep responses under 2 sentences and conversational
- Don't overuse 'great', 'brilliant', 'perfect' - use 'I can help with that' instead  
- Be natural and friendly but not overly enthusiastic
- Always ask 'Is there anything else I can help with?' when ending conversations
- If customer asks about services, ask if they're domestic or trade customer first"""
                }, {
                    "role": "user", 
                    "content": message
                }],
                max_tokens=60,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"OpenAI error: {e}")
            return f"{GENERAL_SCRIPTS['help_intro']}. What service do you need?"
    
    def handle_director_request(self, state):
        """Handle requests to speak to director"""
        if is_business_hours():
            return TRANSFER_RULES['management_director']['office_hours']
        else:
            return TRANSFER_RULES['management_director']['out_of_hours']
    
    def handle_complaint(self, state):
        """Handle complaint requests"""
        if is_business_hours():
            return TRANSFER_RULES['complaints']['office_hours']
        else:
            return TRANSFER_RULES['complaints']['out_of_hours']
    
    # Helper methods
    def extract_skip_size(self, text):
        """Extract skip size from text"""
        for size in ['2yd', '4yd', '6yd', '8yd', '10yd', '12yd', '14yd', '16yd', '20yd']:
            size_num = size.replace('yd', '')
            if any(variant in text.lower() for variant in [f'{size_num}-yard', f'{size_num} yard', f'{size_num}yd', f'{size_num} yd']):
                return size
        return None
    
    def extract_address_line1(self, text):
        """Extract first line of address"""
        address_patterns = [
            r'address\s+(?:is\s+)?(.+)',
            r'first line\s+(?:is\s+)?(.+)', 
            r'live\s+(?:at\s+)?(.+)',
            r'(\d+\s+\w+\s+\w+)'  # Number + street pattern
        ]
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_access_issues(self, text):
        """Extract access issues information"""
        msg_lower = text.lower()
        if any(issue in msg_lower for issue in ['narrow', 'difficult', 'restricted', 'problem', 'tight']):
            return 'Access restrictions mentioned'
        elif any(phrase in msg_lower for phrase in ['no problem', 'good access', 'easy access', 'fine', 'no issues']):
            return 'Good access'
        return None
    
    def extract_name(self, text):
        # Simple name extraction
        name_patterns = [
            r'[Nn]ame\s+(?:is\s+)?([A-Z][a-z]+)',
            r'[Ii]\'m\s+([A-Z][a-z]+)',
            r'^([A-Z][a-z]+)\s+here',
            r'[Cc]all\s+me\s+([A-Z][a-z]+)'
        ]
        for pattern in name_patterns:
            match = re.search(pattern, text)
            if match:
                name = match.group(1).strip()
                if name.lower() not in ['yes', 'no', 'hello', 'hi', 'what', 'how']:
                    return name
        return None
    
    def extract_phone(self, text):
        phone_patterns = [
            r'\b(07\d{9})\b',  # UK mobile
            r'\b(\d{11})\b',   # 11 digits
            r'\b(\d{5})\s+(\d{6})\b'  # Split format
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, text)
            if match:
                return ''.join(match.groups())
        return None
    
    def extract_postcode(self, text):
        postcode_pattern = r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
        match = re.search(postcode_pattern, text.upper())
        if match:
            return match.group(1).replace(' ', '')
        return None

# --- DASHBOARD MANAGER ---
class DashboardManager:
    def __init__(self):
        self.calls = {}
    
    def update_call(self, conversation_id, stage, data):
        self.calls[conversation_id] = {
            'id': conversation_id,
            'timestamp': datetime.now().isoformat(),
            'stage': stage,
            'data': data,
            'status': 'active' if stage not in ['completed', 'lead_sent'] else 'completed'
        }
    
    def get_dashboard_data(self):
        active = [call for call in self.calls.values() if call['status'] == 'active']
        return {
            'active_calls': len(active),
            'live_calls': list(self.calls.values())[-10:],  # Last 10 calls
            'total_calls': len(self.calls)
        }

# --- FLASK APP ---
app = Flask(__name__)
CORS(app)

agent = FastWasteKingAgent()
dashboard = DashboardManager()
conversation_counter = 0

def get_next_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:08d}"

@app.route('/api/wasteking', methods=['POST'])
def process_message_endpoint():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "message": "No data provided"}), 400
        
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_next_conversation_id()
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        # SINGLE FAST CALL - No multiple function calls
        response_text, stage = agent.process_message(customer_message, conversation_id)
        
        # Update dashboard
        state = agent.conversations.get(conversation_id, {})
        dashboard.update_call(conversation_id, stage, state.get('customer_data', {}))
        
        return jsonify({
            "success": True,
            "message": response_text,
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat(),
            "stage": stage
        })
        
    except Exception as e:
        traceback.print_exc()
        return jsonify({
            "success": False, 
            "message": "I'll connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/')
def index():
    return redirect(url_for('dashboard_page'))

@app.route('/dashboard')
def dashboard_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Admin Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .header { background: #667eea; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: white; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .calls { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .call-item { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #667eea; }
        .status-active { border-left-color: #28a745; }
        .status-completed { border-left-color: #6c757d; }
        .nav-links { margin-bottom: 20px; }
        .nav-links a { background: #667eea; color: white; padding: 10px 15px; text-decoration: none; border-radius: 5px; margin-right: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing Admin Dashboard</h1>
        <p>Real-time system monitoring and call management</p>
    </div>
    
    <div class="nav-links">
        <a href="/dashboard">Admin Dashboard</a>
        <a href="/dashboard/user">User Dashboard</a>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3 id="active-calls">0</h3>
            <p>Active Calls</p>
        </div>
        <div class="stat-box">
            <h3 id="total-calls">0</h3>
            <p>Total Calls</p>
        </div>
        <div class="stat-box">
            <h3 id="response-time">< 1s</h3>
            <p>Avg Response Time</p>
        </div>
        <div class="stat-box">
            <h3 id="system-status">ONLINE</h3>
            <p>System Status</p>
        </div>
    </div>
    
    <div class="calls">
        <h2>Live Call Monitor</h2>
        <div id="calls-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('active-calls').textContent = data.data.active_calls;
                        document.getElementById('total-calls').textContent = data.data.total_calls;
                        
                        const callsHTML = data.data.live_calls.map(call => {
                            const statusClass = call.status === 'active' ? 'status-active' : 'status-completed';
                            return `
                                <div class="call-item ${statusClass}">
                                    <strong>${call.id}</strong> - Stage: ${call.stage}
                                    <br><small>Time: ${new Date(call.timestamp).toLocaleString()}</small>
                                    <br><small>Status: ${call.status}</small>
                                    ${call.data && call.data.name ? `<br><small>Customer: ${call.data.name}</small>` : ''}
                                    ${call.data && call.data.postcode ? `<br><small>Postcode: ${call.data.postcode}</small>` : ''}
                                </div>
                            `;
                        }).join('');
                        
                        document.getElementById('calls-list').innerHTML = callsHTML || 'No calls yet';
                    }
                })
                .catch(error => {
                    document.getElementById('calls-list').innerHTML = '<div style="color: red;">Error loading dashboard data</div>';
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 3000); // Refresh every 3 seconds
    </script>
</body>
</html>
""")

@app.route('/dashboard/user')
def user_dashboard_page():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
    <title>WasteKing - Fast Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .header { background: #667eea; color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }
        .calls { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; }
        .call-item { background: #f8f9fa; padding: 10px; margin: 10px 0; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing Fast System</h1>
        <p>Optimized for sub-1-second response times</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3 id="active-calls">0</h3>
            <p>Active Calls</p>
        </div>
        <div class="stat-box">
            <h3 id="total-calls">0</h3>
            <p>Total Calls</p>
        </div>
    </div>
    
    <div class="calls">
        <h2>Recent Calls</h2>
        <div id="calls-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('active-calls').textContent = data.data.active_calls;
                        document.getElementById('total-calls').textContent = data.data.total_calls;
                        
                        const callsHTML = data.data.live_calls.map(call => `
                            <div class="call-item">
                                <strong>${call.id}</strong> - ${call.stage}
                                <br><small>${new Date(call.timestamp).toLocaleString()}</small>
                            </div>
                        `).join('');
                        
                        document.getElementById('calls-list').innerHTML = callsHTML || 'No calls yet';
                    }
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 5000);
    </script>
</body>
</html>
""")

@app.route('/api/dashboard')
def dashboard_api():
    try:
        return jsonify({"success": True, "data": dashboard.get_dashboard_data()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    print("🚀 Starting WasteKing FIXED System...")
    print("✅ Skip hire: NEVER transfers - fallback pricing + manual booking")
    print("✅ All other services: COMPLETE lead generation before transfer")
    print("✅ Systematic data collection - no premature transfers")
    print("⚡ Optimized for <1 second response times")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
