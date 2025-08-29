import os
import re
import json
import requests
import traceback
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from openai import OpenAI
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
from flask_cors import CORS
import logging

# Disable Flask HTTP request logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# API Integration
try:
    from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
    API_AVAILABLE = True
    print("API AVAILABLE")
except ImportError:
    API_AVAILABLE = False
    print("API NOT AVAILABLE - using fallback")

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

# SMS sender
def send_sms(phone, message):
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_PHONE_NUMBER', '+447700900000')
        
        if not account_sid or not auth_token:
            print(f"SMS FALLBACK: Would send to {phone}: {message}")
            return True
            
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_number, to=phone)
        print(f"SMS SENT to {phone}")
        return True
        
    except ImportError:
        print(f"SMS FALLBACK: Would send to {phone}: {message}")
        return True
    except Exception as e:
        print(f"SMS ERROR: {e}")
        return False

# Email sender
def send_email(subject, body, recipient='kanchan.ghosh@wasteking.co.uk'):
    try:
        email_address = os.getenv('WASTEKING_EMAIL')
        email_password = os.getenv('WASTEKING_EMAIL_PASSWORD')
        
        if not email_address or not email_password:
            print(f"EMAIL FALLBACK: {subject}")
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

class WasteKingAgent:
    def __init__(self):
        self.client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        self.conversations = {}
        
    def process_message(self, message, conversation_id):
        print(f"\nCustomer [{conversation_id[-6:]}]: {message}")
        
        state = self.conversations.get(conversation_id, {
            'stage': 'start',
            'customer_data': {},
            'history': [],
            'service_type': None,
            'customer_type': None,
            'data_collected': []
        })
        
        state['history'].append(f"Customer: {message}")
        response = self.route_message(message, state)
        state['history'].append(f"Agent: {response}")
        self.conversations[conversation_id] = state
        
        print(f"Agent [{conversation_id[-6:]}]: {response}")
        return response, state.get('stage', 'conversation')
    
    def route_message(self, message, state):
        msg_lower = message.lower()
        
        # 1. Customer type detection
        if not state.get('customer_type'):
            if any(word in msg_lower for word in ['trade', 'business', 'commercial', 'company']):
                state['customer_type'] = 'trade'
                print(f"CUSTOMER TYPE: trade")
            elif any(word in msg_lower for word in ['domestic', 'home', 'house', 'personal']):
                state['customer_type'] = 'domestic'
                print(f"CUSTOMER TYPE: domestic")
            else:
                return "Are you a domestic or trade customer?"
        
        # 2. Service detection
        if not state.get('service_type'):
            service = self.detect_service(msg_lower)
            if service:
                state['service_type'] = service
                print(f"SERVICE DETECTED: {service}")
        
        # 3. Route to appropriate handler
        service = state.get('service_type')
        
        if service == 'skip_hire':
            return self.handle_skip_hire(message, state, msg_lower)
        elif service == 'mav':
            return self.handle_mav(message, state, msg_lower)
        elif service == 'grab':
            return self.handle_grab(message, state, msg_lower)
        elif service == 'skip_collection':
            return self.handle_skip_collection(message, state, msg_lower)
        elif service in ['toilet_hire', 'asbestos', 'road_sweep', 'hazardous']:
            return self.handle_specialist(message, state, msg_lower, service)
        else:
            return self.handle_general(message, state, msg_lower)
    
    def detect_service(self, msg_lower):
        if any(word in msg_lower for word in ['skip']) and not any(word in msg_lower for word in ['collection', 'collect']):
            return 'skip_hire'
        elif any(phrase in msg_lower for phrase in ['skip collection', 'collect skip', 'pick up skip']):
            return 'skip_collection'
        elif any(phrase in msg_lower for phrase in ['man and van', 'clearance', 'house clearance', 'office clearance']):
            return 'mav'
        elif any(word in msg_lower for word in ['grab', 'wheeler']):
            return 'grab'
        elif 'toilet' in msg_lower or 'portaloo' in msg_lower:
            return 'toilet_hire'
        elif 'asbestos' in msg_lower:
            return 'asbestos'
        elif any(phrase in msg_lower for phrase in ['road sweep', 'street sweep']):
            return 'road_sweep'
        elif 'hazardous' in msg_lower:
            return 'hazardous'
        return None
    
    # SKIP HIRE - AUTO BOOK WITH ALL BUSINESS RULES
    def handle_skip_hire(self, message, state, msg_lower):
        print("PROCESSING SKIP HIRE")
        
        # Business rule checks FIRST
        # Heavy materials with large skips
        large_skips = ['10', '12', '14', '16', '20']
        heavy_materials = ['soil', 'rubble', 'concrete', 'heavy']
        if any(size in msg_lower for size in large_skips) and any(material in msg_lower for material in heavy_materials):
            return SKIP_HIRE_RULES['heavy_materials_max']
        
        # Prohibited items responses
        if 'plasterboard' in msg_lower:
            return SKIP_HIRE_RULES['plasterboard_response']
        elif any(item in msg_lower for item in ['sofa', 'upholstery', 'furniture']):
            return SKIP_HIRE_RULES['prohibited_items_full']
        elif any(item in msg_lower for item in ['mattress', 'fridge', 'freezer']):
            return SKIP_HIRE_RULES['fridge_mattress_restrictions']
        elif 'prohibited' in msg_lower or 'not allowed' in msg_lower:
            return SKIP_HIRE_RULES['prohibited_items_full']
        
        # Delivery timing questions
        if any(phrase in msg_lower for phrase in ['when deliver', 'delivery time', 'when arrive']):
            return SKIP_HIRE_RULES['delivery_timing']
        
        # Permit questions
        if 'permit' in msg_lower:
            return GENERAL_SCRIPTS['permit_response']
        
        # Not booking responses
        if any(phrase in msg_lower for phrase in ['call back', 'think about', 'check with', 'phone around']):
            return SKIP_HIRE_RULES['not_booking_response']
        
        # Extract all data
        self.extract_basic_data(message, state)
        
        # Required fields
        required = ['name', 'phone', 'postcode']
        for field in required:
            if not state['customer_data'].get(field):
                if field == 'name':
                    return "What's your name?"
                elif field == 'phone':
                    return "What's your phone number?"
                elif field == 'postcode':
                    return "What's your postcode?"
        
        # All required data collected - AUTO BOOK IMMEDIATELY
        if not state.get('booking_completed'):
            return self.auto_book_skip(state)
        
        return "Your skip booking is being processed."
    

Action: Schedule delivery within 24 hours
"""
        send_email(subject, body, 'operations@wasteking.co.uk')
        
        state['booking_completed'] = True
        state['stage'] = 'completed'
        
        print(f"FALLBACK BOOKING COMPLETED: {booking_ref} - {price}")
        vat_note = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
        return f"Perfect! Your {skip_size} skip is booked for {postcode} at {price}{vat_note}. Reference: {booking_ref}. You'll receive SMS confirmation shortly. Delivery within 24 hours."
    
    def get_fallback_price(self, postcode, skip_size):
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
        elif any(postcode_upper.startswith(p) for p in ['M', 'L', 'S', 'LS']):
            region = 'north'
        else:
            region = 'default'
        
        return pricing[region].get(skip_size, pricing[region]['8yd'])
    
    # MAN & VAN - COMPLETE DATA COLLECTION FIRST
    def handle_mav(self, message, state, msg_lower):
        print("PROCESSING MAN & VAN")
        
        # Extract all data first
        self.extract_basic_data(message, state)
        self.extract_mav_data(message, state, msg_lower)
        
        # Heavy materials check
        if any(material in msg_lower for material in ['soil', 'rubble', 'concrete', 'bricks']):
            return "Man & van is ideal for light waste. For heavy materials like soil and rubble, a skip would be more suitable."
        
        # SYSTEMATIC COLLECTION - one field at a time
        required_fields = ['name', 'phone', 'postcode', 'volume', 'when_required', 'supplement_items']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                return self.ask_mav_field(field)
        
        # Sunday check after all data collected
        if state['customer_data'].get('when_required', '').lower() == 'sunday':
            if not state.get('sunday_lead_sent'):
                self.send_mav_lead(state)
                state['sunday_lead_sent'] = True
                state['stage'] = 'lead_sent'
                return "For Sunday collections, it's a bespoke price. Our team will call you back to arrange this."
        
        # All data collected - send lead
        if not state.get('lead_sent'):
            self.send_mav_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"MAV LEAD SENT for {name}")
            return f"Perfect {name}, I have all your man & van details. Our team will call you back with pricing and to arrange your clearance."
        
        return "Our team will call you back shortly to arrange your man & van service."
    
    def ask_mav_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'volume': "How much waste do you have? Think in terms of washing machine loads - for example, 2 washing machines = 1 cubic yard.",
            'when_required': "When do you need this collected?",
            'supplement_items': "Do you have any mattresses, fridges, or upholstered furniture that need collecting?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def extract_mav_data(self, message, state, msg_lower):
        # Volume
        if not state['customer_data'].get('volume'):
            volume_patterns = [
                (r'(\d+)\s*washing\s*machine', ' washing machines'),
                (r'(\d+)\s*cubic\s*yard', ' cubic yards'),
                (r'(\d+)\s*bag', ' bags'),
                ('small', '2-3 cubic yards'),
                ('large', '8-10 cubic yards')
            ]
            for pattern, suffix in volume_patterns:
                if isinstance(pattern, str):
                    if pattern in msg_lower:
                        state['customer_data']['volume'] = suffix
                        break
                else:
                    match = re.search(pattern, msg_lower)
                    if match:
                        state['customer_data']['volume'] = f"{match.group(1)}{suffix}"
                        break
        
        # When required
        if not state['customer_data'].get('when_required'):
            time_words = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap']
            for word in time_words:
                if word in msg_lower:
                    state['customer_data']['when_required'] = word.title()
                    break
        
        # Supplement items
        if not state['customer_data'].get('supplement_items'):
            if any(item in msg_lower for item in ['mattress', 'fridge', 'sofa']):
                items = []
                if 'mattress' in msg_lower: items.append('mattresses')
                if 'fridge' in msg_lower: items.append('fridges')
                if any(word in msg_lower for word in ['sofa', 'chair']): items.append('furniture')
                state['customer_data']['supplement_items'] = ', '.join(items)
            elif any(word in msg_lower for word in ['no', 'none', 'nothing']):
                state['customer_data']['supplement_items'] = 'none'
    
    def send_mav_lead(self, state):
        customer_data = state['customer_data']
        
        subject = f"MAV LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
MAN & VAN LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
Customer Type: {state.get('customer_type')}
Volume: {customer_data.get('volume')}
When Required: {customer_data.get('when_required')}
Supplement Items: {customer_data.get('supplement_items')}

Action: Call back to discuss pricing and arrange service
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING MAV LEAD for {customer_data.get('name')}")
        send_email(subject, body)
    
    # GRAB HIRE - COMPLETE DATA COLLECTION WITH ALL BUSINESS RULES
    def handle_grab(self, message, state, msg_lower):
        print("PROCESSING GRAB HIRE")
        
        self.extract_basic_data(message, state)
        
        # Business rule: Grab capacity explanations
        if '6 wheel' in msg_lower and not state.get('grab_6_explained'):
            state['grab_6_explained'] = True
            state['customer_data']['grab_type'] = '6_wheeler'
            return GRAB_RULES['6_wheeler_explanation']
        elif '8 wheel' in msg_lower and not state.get('grab_8_explained'):
            state['grab_8_explained'] = True
            state['customer_data']['grab_type'] = '8_wheeler'
            return GRAB_RULES['8_wheeler_explanation']
        
        # Business rule: Mixed materials check
        material_type = state['customer_data'].get('material_type', '')
        msg_materials = msg_lower
        has_soil_rubble = any(material in (material_type + msg_materials) for material in ['soil', 'rubble', 'muckaway'])
        has_other = any(item in (material_type + msg_materials) for item in ['wood', 'furniture', 'plastic', 'metal', 'mixed'])
        
        if has_soil_rubble and has_other and not state.get('mixed_materials_warned'):
            state['mixed_materials_warned'] = True
            return GRAB_RULES['mixed_materials_response']
        
        # Extract material type
        if not state['customer_data'].get('material_type'):
            if any(material in msg_lower for material in ['soil', 'rubble', 'muckaway']):
                state['customer_data']['material_type'] = 'Heavy materials (soil/rubble)'
            elif any(material in msg_lower for material in ['wood', 'general', 'mixed']):
                state['customer_data']['material_type'] = 'General waste'
        
        # Required fields
        required_fields = ['name', 'phone', 'postcode', 'material_type', 'when_required']
        
        for field in required_fields:
            if not state['customer_data'].get(field):
                return self.ask_grab_field(field)
        
        # All data collected - send lead (Business rule: Most grabs not in SMP)
        if not state.get('lead_sent'):
            self.send_grab_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"GRAB LEAD SENT for {name}")
            return f"Thanks {name}, I have your grab hire details. {GRAB_RULES['transfer_message']}"
        
        return "Our specialist team will call you back about your grab hire."
    
    def ask_grab_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'material_type': "What type of material - soil/rubble (muckaway) or general waste?",
            'when_required': "When do you need this?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def send_grab_lead(self, state):
        customer_data = state['customer_data']
        
        subject = f"GRAB HIRE LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
GRAB HIRE LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
Material: {customer_data.get('material_type')}
When Required: {customer_data.get('when_required')}

Action: Call back to arrange service
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING GRAB LEAD")
        send_email(subject, body)
    
    # SPECIALIST SERVICES - WITH COMPLETE BUSINESS RULE QUESTION FLOWS
    def handle_specialist(self, message, state, msg_lower, service):
        print(f"PROCESSING {service.upper()}")
        
        self.extract_basic_data(message, state)
        
        # Get service configuration from business rules
        service_config = LG_SERVICES_QUESTIONS.get(service, {})
        questions = service_config.get('questions', [])
        intro = service_config.get('intro', GENERAL_SCRIPTS['lg_transfer_message'])
        
        # Start with business rule intro
        if not state.get('lg_intro_given'):
            state['lg_intro_given'] = True
            state['lg_question_index'] = 0
            return intro
        
        # Process through business rule questions systematically
        question_index = state.get('lg_question_index', 0)
        
        if question_index < len(questions):
            current_question = questions[question_index]
            
            # Extract service-specific data based on current question
            self.extract_lg_specific_data(message, state, msg_lower, service, current_question)
            
            # Move to next question
            question_index += 1
            state['lg_question_index'] = question_index
            
            if question_index < len(questions):
                return questions[question_index]
        
        # All questions completed - send lead
        if not state.get('lead_sent'):
            self.send_specialist_lead(state, service)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data']['name']
            print(f"{service.upper()} LEAD SENT for {name}")
            
            # Service-specific callback messages from business rules
            if service == 'asbestos':
                callback_text = "Our certified asbestos team will call you back"
            elif service == 'hazardous_waste':
                callback_text = "Our hazardous waste specialists will call you back"
            else:
                callback_text = "Our specialist team will call you back"
            
            callback_time = "shortly" if is_business_hours() else "first thing tomorrow"
            
            return f"Thanks {name}, I have all the details. {callback_text} {callback_time} to confirm cost and availability. {GENERAL_SCRIPTS['closing']}"
        
        return f"Our {service.replace('_', ' ')} team will call you back."
    
    def extract_lg_specific_data(self, message, state, msg_lower, service, current_question):
        """Extract service-specific data based on business rules"""
        if 'postcode' in current_question.lower():
            postcode = self.extract_postcode_from_text(message)
            if postcode: state['customer_data']['postcode'] = postcode
        
        elif 'name' in current_question.lower():
            name = self.extract_name_from_text(message)
            if name: state['customer_data']['name'] = name
        
        elif 'phone' in current_question.lower():
            phone = self.extract_phone_from_text(message)
            if phone: state['customer_data']['phone'] = phone
        
        elif service == 'toilet_hire':
            if 'many' in current_question.lower():
                number_match = re.search(r'(\d+)', message)
                if number_match:
                    state['customer_data']['number_required'] = f"{number_match.group(1)} toilets"
            elif 'event' in current_question.lower():
                if any(word in msg_lower for word in ['event', 'wedding', 'party']):
                    state['customer_data']['event_type'] = 'Event'
                elif any(word in msg_lower for word in ['long term', 'ongoing']):
                    state['customer_data']['event_type'] = 'Long term'
            elif 'delivery' in current_question.lower():
                # Extract delivery date
                date_patterns = [r'(\w+day)', r'(\d{1,2}\/\d{1,2})', r'(\d{1,2}\s+\w+)']
                for pattern in date_patterns:
                    match = re.search(pattern, message)
                    if match:
                        state['customer_data']['delivery_date'] = match.group(1)
                        break
        
        elif service == 'asbestos':
            if 'skip or collection' in current_question.lower():
                if 'skip' in msg_lower:
                    state['customer_data']['service_type'] = 'Skip'
                elif 'collection' in msg_lower:
                    state['customer_data']['service_type'] = 'Collection'
            elif 'type of asbestos' in current_question.lower():
                state['customer_data']['asbestos_type'] = message.strip()
            elif 'dismantle' in current_question.lower():
                if 'dismantle' in msg_lower:
                    state['customer_data']['dismantle_type'] = 'Dismantle & disposal'
                else:
                    state['customer_data']['dismantle_type'] = 'Collection & disposal'
            elif 'much' in current_question.lower():
                state['customer_data']['quantity'] = message.strip()
        
        elif service == 'road_sweeper':
            if 'hours' in current_question.lower():
                hours_match = re.search(r'(\d+)\s*hour', msg_lower)
                if hours_match:
                    state['customer_data']['hours_required'] = f"{hours_match.group(1)} hours"
            elif 'tipping' in current_question.lower():
                if any(phrase in msg_lower for phrase in ['on site', 'onsite']):
                    state['customer_data']['tipping_location'] = 'On site'
                elif any(phrase in msg_lower for phrase in ['take away', 'off site', 'offsite']):
                    state['customer_data']['tipping_location'] = 'Take away'
        
        # Extract when required for all services
        if 'when' in current_question.lower():
            when_patterns = ['today', 'tomorrow', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday', 'asap', 'urgent', 'next week']
            for pattern in when_patterns:
                if pattern in msg_lower:
                    state['customer_data']['when_required'] = pattern.title()
                    break
    
    def ask_specialist_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'when_required': "When do you need this?"
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def send_specialist_lead(self, state, service):
        customer_data = state['customer_data']
        
        subject = f"{service.upper()} LEAD - {customer_data.get('name', 'Unknown')}"
        body = f"""
{service.upper()} LEAD:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Postcode: {customer_data.get('postcode')}
When Required: {customer_data.get('when_required')}

Service: {service.replace('_', ' ').title()}
Action: Specialist callback within 2 hours
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print(f"SENDING {service.upper()} LEAD")
        send_email(subject, body)
    
    # SKIP COLLECTION - WITH COMPLETE BUSINESS RULES
    def handle_skip_collection(self, message, state, msg_lower):
        print("PROCESSING SKIP COLLECTION")
        
        if not state.get('collection_started'):
            state['collection_started'] = True
            return SKIP_COLLECTION_RULES['script']
        
        self.extract_basic_data(message, state)
        
        # Extract specific collection data from business rules
        address_line1 = self.extract_address_line1(message)
        level_load = 'yes' if any(word in msg_lower for word in ['level', 'flush', 'not overloaded']) else None
        prohibited_check = 'confirmed' if any(phrase in msg_lower for phrase in ['no prohibited', 'nothing prohibited']) else None
        access_issues = self.extract_access_issues(message)
        
        if address_line1: state['customer_data']['address'] = address_line1
        if level_load: state['customer_data']['level_load'] = level_load
        if prohibited_check: state['customer_data']['prohibited_check'] = prohibited_check
        if access_issues: state['customer_data']['access_issues'] = access_issues
        
        # Business rule: All required fields for collection
        required_fields = ['name', 'phone', 'postcode', 'address', 'level_load', 'prohibited_check', 'access_issues']
        missing = [field for field in required_fields if not state['customer_data'].get(field)]
        
        if missing:
            field = missing[0]
            if field == 'name': return "What's your name?"
            elif field == 'phone': return "What's the best phone number to contact you on?"
            elif field == 'postcode': return "What's your postcode?"
            elif field == 'address': return "What's the first line of your address?"
            elif field == 'level_load': return "Is the skip a level load?"
            elif field == 'prohibited_check': return "Can you confirm there are no prohibited items in the skip?"
            elif field == 'access_issues': return "Are there any access issues?"
        
        if not state.get('lead_sent'):
            self.send_collection_lead(state)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            print("SKIP COLLECTION LEAD SENT")
            return SKIP_COLLECTION_RULES['completion']
        
        return "Our team will arrange your skip collection."
    
    # GENERAL CONVERSATION - WITH ALL BUSINESS RULES
    def handle_general(self, message, state, msg_lower):
        # Business rule: Transfer requests
        if any(phrase in msg_lower for phrase in TRANSFER_RULES['management_director']['triggers']):
            return self.handle_director_request(state)
        
        elif any(phrase in msg_lower for phrase in TRANSFER_RULES['complaints']['triggers']):
            return self.handle_complaint(state)
        
        elif any(phrase in msg_lower for phrase in ['speak to tracey', 'talk to tracey']):
            return TRANSFER_RULES['specific_person']['tracey_request']
        
        elif any(phrase in msg_lower for phrase in ['speak to human', 'human agent', 'talk to person']):
            return TRANSFER_RULES['specific_person']['human_agent']
        
        # Business rule: Information requests
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
        
        # Business rule: Price/cost inquiries
        elif any(word in msg_lower for word in ['price', 'cost', 'quote']):
            return "I can help with pricing. What service do you need - skip hire, man & van clearance, or something else?"
        
        # Use AI for other natural conversation
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{
                    "role": "system",
                    "content": "You are Jennifer from Waste King. Be helpful and direct. Ask what service they need if unclear. Keep responses under 2 sentences."
                }, {
                    "role": "user",
                    "content": message
                }],
                max_tokens=50,
                temperature=0.3
            )
            return response.choices[0].message.content.strip()
        except:
            return f"{GENERAL_SCRIPTS['help_intro']}. What service do you need?"
    
    def handle_director_request(self, state):
        """Business rule: Handle requests to speak to director"""
        if is_business_hours():
            return TRANSFER_RULES['management_director']['office_hours']
        else:
            return TRANSFER_RULES['management_director']['out_of_hours']
    
    def handle_complaint(self, state):
        """Business rule: Handle complaint requests"""
        if is_business_hours():
            return TRANSFER_RULES['complaints']['office_hours']
        else:
            return TRANSFER_RULES['complaints']['out_of_hours']
    
    # HELPER EXTRACTION METHODS - ALL BUSINESS RULE DATA
    def extract_address_line1(self, text):
        """Extract first line of address for skip collection"""
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
    
    def extract_postcode_from_text(self, text):
        """Extract postcode with validation"""
        postcode_pattern = r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b'
        match = re.search(postcode_pattern, text.upper())
        if match:
            return match.group(1).replace(' ', '')
        return None
    
    def extract_name_from_text(self, text):
        """Extract name with validation"""
        name_patterns = [
            r'name\s+is\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'i\'?m\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'call\s+me\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
            r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)

# Flask App
app = Flask(__name__)
CORS(app)

agent = WasteKingAgent()
conversation_counter = 0

def get_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:06d}"

@app.route('/api/wasteking', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_conversation_id()
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        response_text, stage = agent.process_message(customer_message, conversation_id)
        
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
            "message": "I'll connect you with our team who can help immediately.",
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
        .conversations { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .conv-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }
        .conv-item.completed { border-left-color: #28a745; }
        .conv-item.lead-sent { border-left-color: #ffc107; }
        .customer-details { margin-top: 8px; font-size: 14px; }
        .service-badge { background: #007bff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }
        .refresh-btn { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing System Dashboard</h1>
        <p>Live conversation monitoring with full customer details</p>
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
        <h2>Live Conversations 
            <button class="refresh-btn" onclick="loadDashboard()">Refresh Now</button>
        </h2>
        <div id="conversation-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('total-conversations').textContent = data.total || 0;
                        document.getElementById('active-conversations').textContent = data.active || 0;
                        document.getElementById('bookings-completed').textContent = data.completed || 0;
                        document.getElementById('leads-sent').textContent = data.leads || 0;
                        
                        const convHTML = (data.conversations || []).map(conv => {
                            const statusClass = conv.stage === 'completed' ? 'completed' : (conv.stage === 'lead_sent' ? 'lead-sent' : '');
                            return `
                                <div class="conv-item ${statusClass}">
                                    <strong>${conv.id}</strong> - Stage: ${conv.stage}
                                    ${conv.service ? `<span class="service-badge">${conv.service.toUpperCase()}</span>` : ''}
                                    <br><small>Time: ${conv.timestamp}</small>
                                    <div class="customer-details">
                                        ${conv.name ? `<strong>Name:</strong> ${conv.name}<br>` : ''}
                                        ${conv.phone ? `<strong>Phone:</strong> ${conv.phone}<br>` : ''}
                                        ${conv.postcode ? `<strong>Postcode:</strong> ${conv.postcode}<br>` : ''}
                                        ${conv.customer_type ? `<strong>Type:</strong> ${conv.customer_type}<br>` : ''}
                                        ${conv.details ? `<strong>Details:</strong> ${conv.details}` : ''}
                                    </div>
                                </div>
                            `;
                        }).join('');
                        
                        document.getElementById('conversation-list').innerHTML = convHTML || '<p>No conversations yet</p>';
                    }
                })
                .catch(error => {
                    document.getElementById('conversation-list').innerHTML = '<div style="color: red;">Error loading dashboard data</div>';
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 3000);
    </script>
</body>
</html>"""
    return render_template_string(html_template)

@app.route('/api/dashboard')
def dashboard_api():
    try:
        conversations = agent.conversations
        
        total = len(conversations)
        active = sum(1 for conv in conversations.values() if conv.get('stage') not in ['completed', 'lead_sent'])
        completed = sum(1 for conv in conversations.values() if conv.get('stage') == 'completed')
        leads = sum(1 for conv in conversations.values() if conv.get('stage') == 'lead_sent')
        
        recent_convs = []
        for conv_id, conv_data in list(conversations.items())[-15:]:  # Show last 15 conversations
            customer_data = conv_data.get('customer_data', {})
            
            # Build details string
            details_parts = []
            if customer_data.get('volume'):
                details_parts.append(f"Volume: {customer_data['volume']}")
            if customer_data.get('when_required'):
                details_parts.append(f"When: {customer_data['when_required']}")
            if customer_data.get('skip_size'):
                details_parts.append(f"Size: {customer_data['skip_size']}")
            if customer_data.get('material_type'):
                details_parts.append(f"Material: {customer_data['material_type']}")
            
            recent_convs.append({
                'id': conv_id[-8:],  # Show last 8 chars for readability
                'stage': conv_data.get('stage', 'unknown'),
                'service': conv_data.get('service_type', ''),
                'name': customer_data.get('name', ''),
                'phone': customer_data.get('phone', ''),
                'postcode': customer_data.get('postcode', ''),
                'customer_type': conv_data.get('customer_type', ''),
                'details': ' | '.join(details_parts) if details_parts else '',
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
        
        return jsonify({
            "success": True,
            "total": total,
            "active": active,
            "completed": completed,
            "leads": leads,
            "conversations": recent_convs
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    print("WasteKing Agent Starting...")
    print("Skip hire: Auto-booking with SMS confirmations")
    print("All services: Complete lead generation before transfer")
    print("Clean console logging enabled")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

        ]
        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower() not in ['yes', 'no', 'hello', 'hi', 'what', 'how']:
                    return name
        return None
    
    def extract_phone_from_text(self, text):
        """Extract UK phone numbers"""
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
    
    def send_collection_lead(self, state):
        """Send skip collection lead with all details"""
        customer_data = state['customer_data']
        
        subject = f"SKIP COLLECTION - {customer_data.get('name', 'Unknown')}"
        body = f"""
SKIP COLLECTION REQUEST:

Customer: {customer_data.get('name')}
Phone: {customer_data.get('phone')}
Address: {customer_data.get('address')}
Postcode: {customer_data.get('postcode')}
Level Load: {customer_data.get('level_load', 'Not confirmed')}
Prohibited Items: {customer_data.get('prohibited_check', 'Not confirmed')}
Access Issues: {customer_data.get('access_issues', 'Not specified')}

Action: Arrange collection (1-4 days typically)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        print("SENDING SKIP COLLECTION REQUEST")
        send_email(subject, body)

# Flask App
app = Flask(__name__)
CORS(app)

agent = WasteKingAgent()
conversation_counter = 0

def get_conversation_id():
    global conversation_counter
    conversation_counter += 1
    return f"conv{conversation_counter:06d}"

@app.route('/api/wasteking', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id') or get_conversation_id()
        
        if not customer_message:
            return jsonify({"success": False, "message": "No message provided"}), 400
        
        response_text, stage = agent.process_message(customer_message, conversation_id)
        
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
            "message": "I'll connect you with our team who can help immediately.",
            "error": str(e)
        }), 500

@app.route('/')
def index():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    return render_template_string("""<!DOCTYPE html>
<html>
<head>
    <title>WasteKing Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
        .stats { display: flex; gap: 20px; margin-bottom: 20px; }
        .stat-box { background: white; border: 1px solid #ddd; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .conversations { background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .conv-item { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; border-left: 4px solid #007bff; }
        .conv-item.completed { border-left-color: #28a745; }
        .conv-item.lead-sent { border-left-color: #ffc107; }
        .customer-details { margin-top: 8px; font-size: 14px; }
        .service-badge { background: #007bff; color: white; padding: 2px 8px; border-radius: 12px; font-size: 12px; margin-left: 10px; }
        .refresh-btn { background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing System Dashboard</h1>
        <p>Live conversation monitoring with full customer details</p>
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
        <h2>Live Conversations 
            <button class="refresh-btn" onclick="loadDashboard()">Refresh Now</button>
        </h2>
        <div id="conversation-list">Loading...</div>
    </div>

    <script>
        function loadDashboard() {
            fetch('/api/dashboard')
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('total-conversations').textContent = data.total || 0;
                        document.getElementById('active-conversations').textContent = data.active || 0;
                        document.getElementById('bookings-completed').textContent = data.completed || 0;
                        document.getElementById('leads-sent').textContent = data.leads || 0;
                        
                        const convHTML = (data.conversations || []).map(conv => {
                            const statusClass = conv.stage === 'completed' ? 'completed' : (conv.stage === 'lead_sent' ? 'lead-sent' : '');
                            return `
                                <div class="conv-item ${statusClass}">
                                    <strong>${conv.id}</strong> - Stage: ${conv.stage}
                                    ${conv.service ? `<span class="service-badge">${conv.service.toUpperCase()}</span>` : ''}
                                    <br><small>Time: ${conv.timestamp}</small>
                                    <div class="customer-details">
                                        ${conv.name ? `<strong>Name:</strong> ${conv.name}<br>` : ''}
                                        ${conv.phone ? `<strong>Phone:</strong> ${conv.phone}<br>` : ''}
                                        ${conv.postcode ? `<strong>Postcode:</strong> ${conv.postcode}<br>` : ''}
                                        ${conv.customer_type ? `<strong>Type:</strong> ${conv.customer_type}<br>` : ''}
                                        ${conv.details ? `<strong>Details:</strong> ${conv.details}` : ''}
                                    </div>
                                </div>
                            `;
                        }).join('');
                        
                        document.getElementById('conversation-list').innerHTML = convHTML || '<p>No conversations yet</p>';
                    }
                })
                .catch(error => {
                    document.getElementById('conversation-list').innerHTML = '<div style="color: red;">Error loading dashboard data</div>';
                });
        }
        
        loadDashboard();
        setInterval(loadDashboard, 3000);
    </script>
</body>
</html>""")

@app.route('/api/dashboard')
def dashboard_api():
    try:
        conversations = agent.conversations
        
        total = len(conversations)
        active = sum(1 for conv in conversations.values() if conv.get('stage') not in ['completed', 'lead_sent'])
        completed = sum(1 for conv in conversations.values() if conv.get('stage') == 'completed')
        leads = sum(1 for conv in conversations.values() if conv.get('stage') == 'lead_sent')
        
        recent_convs = []
        for conv_id, conv_data in list(conversations.items())[-15:]:  # Show last 15 conversations
            customer_data = conv_data.get('customer_data', {})
            
            # Build details string
            details_parts = []
            if customer_data.get('volume'):
                details_parts.append(f"Volume: {customer_data['volume']}")
            if customer_data.get('when_required'):
                details_parts.append(f"When: {customer_data['when_required']}")
            if customer_data.get('skip_size'):
                details_parts.append(f"Size: {customer_data['skip_size']}")
            if customer_data.get('material_type'):
                details_parts.append(f"Material: {customer_data['material_type']}")
            
            recent_convs.append({
                'id': conv_id[-8:],  # Show last 8 chars for readability
                'stage': conv_data.get('stage', 'unknown'),
                'service': conv_data.get('service_type', ''),
                'name': customer_data.get('name', ''),
                'phone': customer_data.get('phone', ''),
                'postcode': customer_data.get('postcode', ''),
                'customer_type': conv_data.get('customer_type', ''),
                'details': ' | '.join(details_parts) if details_parts else '',
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
        
        return jsonify({
            "success": True,
            "total": total,
            "active": active,
            "completed": completed,
            "leads": leads,
            "conversations": recent_convs
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    print("WasteKing Agent Starting...")
    print("Skip hire: Auto-booking with SMS confirmations")
    print("All services: Complete lead generation before transfer")
    print("Clean console logging enabled")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
