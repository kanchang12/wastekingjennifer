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

# Flask app MUST be here for Gunicorn
app = Flask(__name__)
CORS(app)

# API Integration - NO FALLBACK
from utils.wasteking_api import complete_booking, create_booking, get_pricing, create_payment_link
print("API AVAILABLE")

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
            print(f"SMS WOULD SEND to {phone}: {message}")
            return True
            
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_number, to=phone)
        print(f"SMS SENT to {phone}")
        return True
        
    except ImportError:
        print(f"SMS WOULD SEND to {phone}: {message}")
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
            'asked_fields': set()
        })
        
        state['history'].append(f"Customer: {message}")
        response = self.route_message(message, state)
        state['history'].append(f"Agent: {response}")
        self.conversations[conversation_id] = state
        
        print(f"Agent [{conversation_id[-6:]}]: {response}")
        return response, state.get('stage', 'conversation')
    
    def route_message(self, message, state):
        msg_lower = message.lower()
        
        # ALWAYS extract data from every message
        self.extract_basic_data(message, state)
        
        # 1. Service detection - if not already set
        if not state.get('service_type'):
            service = self.detect_service(msg_lower)
            if service:
                state['service_type'] = service
                print(f"SERVICE DETECTED: {service}")
        
        # 2. Customer type detection - if not already set
        if not state.get('customer_type'):
            if any(word in msg_lower for word in ['trade', 'business', 'commercial', 'company']):
                state['customer_type'] = 'trade'
                print(f"CUSTOMER TYPE: trade")
            elif any(word in msg_lower for word in ['domestic', 'home', 'house', 'personal']):
                state['customer_type'] = 'domestic'
                print(f"CUSTOMER TYPE: domestic")
        
        # 3. Always route to service handler if service is known
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
            # Only ask for service type if truly unknown
            if not state.get('service_type'):
                return "What service do you need - skip hire, man & van clearance, grab hire, or something else?"
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
    
    # SKIP HIRE - AUTO BOOK WITH API ONLY
    def handle_skip_hire(self, message, state, msg_lower):
        print("PROCESSING SKIP HIRE")
        
        # Check completion status
        if state.get('booking_completed'):
            return "Your skip booking has been confirmed. You'll receive SMS confirmation shortly."
        
        # Business rule checks FIRST
        large_skips = ['10', '12', '14', '16', '20']
        heavy_materials = ['soil', 'rubble', 'concrete', 'heavy']
        if any(size in msg_lower for size in large_skips) and any(material in msg_lower for material in heavy_materials):
            return SKIP_HIRE_RULES['heavy_materials_max']
        
        if 'plasterboard' in msg_lower:
            return SKIP_HIRE_RULES['plasterboard_response']
        elif any(item in msg_lower for item in ['sofa', 'upholstery', 'furniture']):
            return SKIP_HIRE_RULES['prohibited_items_full']
        elif any(item in msg_lower for item in ['mattress', 'fridge', 'freezer']):
            return SKIP_HIRE_RULES['fridge_mattress_restrictions']
        
        # Extract data
        self.extract_basic_data(message, state)
        
        # Initialize asked fields if not present
        if 'asked_fields' not in state:
            state['asked_fields'] = set()
        
        # Required fields - check and ask only once
        required = ['name', 'phone', 'postcode']
        for field in required:
            if not state['customer_data'].get(field) and field not in state['asked_fields']:
                state['asked_fields'].add(field)
                if field == 'name':
                    return "What's your name?"
                elif field == 'phone':
                    return "What's your phone number?"
                elif field == 'postcode':
                    return "What's your postcode?"
        
        # All required data collected - AUTO BOOK with API
        if all(state['customer_data'].get(field) for field in required):
            if not state.get('booking_completed'):
                return self.auto_book_skip(state)
        
        return "Please provide the missing information for your skip booking."
    
    def auto_book_skip(self, state):
        """Auto book skip with API ONLY"""
        customer_data = state['customer_data']
        
        # Set default skip size if not specified
        if not customer_data.get('skip_size'):
            customer_data['skip_size'] = '8yd'
        
        name = customer_data['name']
        phone = customer_data['phone']
        postcode = customer_data['postcode']
        skip_size = customer_data['skip_size']
        
        try:
            # Get pricing from API
            price_response = get_pricing(postcode, skip_size)
            price = price_response.get('price', '£250')
            
            # Create booking
            booking_response = create_booking({
                'name': name,
                'phone': phone,
                'postcode': postcode,
                'skip_size': skip_size,
                'price': price
            })
            
            booking_ref = booking_response.get('reference', f"WK{datetime.now().strftime('%H%M%S')}")
            
            # Send SMS
            sms_message = f"Hi {name}, your {skip_size} skip is confirmed for {postcode}. Price: {price}. Ref: {booking_ref}. Delivery within 24hrs. WasteKing"
            send_sms(phone, sms_message)
            
            # Send email to operations
            subject = f"SKIP BOOKING - {name} - {booking_ref}"
            body = f"""
SKIP HIRE BOOKING:

Reference: {booking_ref}
Customer: {name}
Phone: {phone}
Postcode: {postcode}
Skip Size: {skip_size}
Price: {price}
Customer Type: {state.get('customer_type', 'Unknown')}

Action: Schedule delivery within 24 hours
"""
            send_email(subject, body, 'operations@wasteking.co.uk')
            
            state['booking_completed'] = True
            state['stage'] = 'completed'
            
            print(f"API BOOKING SUCCESSFUL: {booking_ref}")
            vat_note = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
            return f"Perfect! Your {skip_size} skip is booked for {postcode} at {price}{vat_note}. Reference: {booking_ref}. You'll receive SMS confirmation shortly. Delivery within 24 hours."
            
        except Exception as e:
            print(f"API BOOKING ERROR: {e}")
            return "There was an error processing your booking. Our team will call you back shortly to complete it manually."
    
    # MAN & VAN - COMPLETE DATA COLLECTION
    def handle_mav(self, message, state, msg_lower):
        print("PROCESSING MAN & VAN")
        
        if state.get('lead_sent'):
            return "Our team will call you back shortly to arrange your man & van service."
        
        # Extract data
        self.extract_basic_data(message, state)
        self.extract_mav_data(message, state, msg_lower)
        
        # Heavy materials check
        if any(material in msg_lower for material in ['soil', 'rubble', 'concrete', 'bricks']):
            return MAV_RULES['heavy_materials_response']
        
        # Initialize asked fields
        if 'asked_fields' not in state:
            state['asked_fields'] = set()
        
        # Required fields - ask only once
        required_fields = ['name', 'phone', 'postcode', 'volume', 'when_required', 'supplement_items']
        
        for field in required_fields:
            if not state['customer_data'].get(field) and field not in state['asked_fields']:
                state['asked_fields'].add(field)
                return self.ask_mav_field(field)
        
        # Sunday check
        if state['customer_data'].get('when_required', '').lower() == 'sunday':
            if not state.get('sunday_lead_sent'):
                self.send_mav_lead(state)
                state['sunday_lead_sent'] = True
                state['lead_sent'] = True
                state['stage'] = 'lead_sent'
                return MAV_RULES['sunday_response']
        
        # All data collected - send lead
        if all(state['customer_data'].get(field) for field in required_fields):
            if not state.get('lead_sent'):
                self.send_mav_lead(state)
                state['lead_sent'] = True
                state['stage'] = 'lead_sent'
                
                name = state['customer_data']['name']
                print(f"MAV LEAD SENT for {name}")
                return f"Perfect {name}, I have all your man & van details. Our team will call you back with pricing and to arrange your clearance."
        
        return "Please provide the missing information for your man & van service."
    
    def ask_mav_field(self, field):
        questions = {
            'name': "What's your name?",
            'phone': "What's your phone number?",
            'postcode': "What's your postcode?",
            'volume': MAV_RULES['volume_explanation'],
            'when_required': "When do you need this collected?",
            'supplement_items': MAV_RULES['supplement_check']
        }
        return questions.get(field, f"Can you tell me about {field}?")
    
    def extract_mav_data(self, message, state, msg_lower):
        # Volume
        if not state['customer_data'].get('volume'):
            volume_patterns = [
                (r'(\d+)\s*washing\s*machine', ' washing machines'),
                (r'(\d+)\s*cubic\s*yard', ' cubic yards'),
                (r'(\d+)\s*bag', ' bags')
            ]
            for pattern, suffix in volume_patterns:
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
    
    # GRAB HIRE
    def handle_grab(self, message, state, msg_lower):
        print("PROCESSING GRAB HIRE")
        
        if state.get('lead_sent'):
            return "Our specialist team will call you back about your grab hire."
        
        self.extract_basic_data(message, state)
        
        # Business rules
        if '6 wheel' in msg_lower and not state.get('grab_6_explained'):
            state['grab_6_explained'] = True
            state['customer_data']['grab_type'] = '6_wheeler'
            return GRAB_RULES['6_wheeler_explanation']
        elif '8 wheel' in msg_lower and not state.get('grab_8_explained'):
            state['grab_8_explained'] = True
            state['customer_data']['grab_type'] = '8_wheeler'
            return GRAB_RULES['8_wheeler_explanation']
        
        # Initialize asked fields
        if 'asked_fields' not in state:
            state['asked_fields'] = set()
        
        # Required fields
        required_fields = ['name', 'phone', 'postcode', 'material_type', 'when_required']
        
        for field in required_fields:
            if not state['customer_data'].get(field) and field not in state['asked_fields']:
                state['asked_fields'].add(field)
                return self.ask_grab_field(field)
        
        # All data collected - send lead
        if all(state['customer_data'].get(field) for field in required_fields):
            if not state.get('lead_sent'):
                self.send_grab_lead(state)
                state['lead_sent'] = True
                state['stage'] = 'lead_sent'
                
                name = state['customer_data']['name']
                print(f"GRAB LEAD SENT for {name}")
                return f"Thanks {name}, I have your grab hire details. {GRAB_RULES['transfer_message']}"
        
        return "Please provide the missing information for your grab hire."
    
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
    
    # SKIP COLLECTION
    def handle_skip_collection(self, message, state, msg_lower):
        print("PROCESSING SKIP COLLECTION")
        
        if state.get('lead_sent'):
            return "Our team will arrange your skip collection."
        
        if not state.get('collection_started'):
            state['collection_started'] = True
            return SKIP_COLLECTION_RULES['script']
        
        self.extract_basic_data(message, state)
        
        # Initialize asked fields
        if 'asked_fields' not in state:
            state['asked_fields'] = set()
        
        # Required fields
        required_fields = ['name', 'phone', 'postcode', 'address', 'level_load', 'prohibited_check', 'access_issues']
        
        # Extract specific collection data
        address_line1 = self.extract_address_line1(message)
        if address_line1: state['customer_data']['address'] = address_line1
        
        if 'level' in msg_lower or 'flush' in msg_lower:
            state['customer_data']['level_load'] = 'yes'
        
        if 'no prohibited' in msg_lower or 'nothing prohibited' in msg_lower:
            state['customer_data']['prohibited_check'] = 'confirmed'
        
        if any(word in msg_lower for word in ['narrow', 'difficult', 'restricted']):
            state['customer_data']['access_issues'] = 'Access restrictions mentioned'
        elif any(phrase in msg_lower for phrase in ['no problem', 'good access', 'fine']):
            state['customer_data']['access_issues'] = 'Good access'
        
        # Ask for missing fields
        for field in required_fields:
            if not state['customer_data'].get(field) and field not in state['asked_fields']:
                state['asked_fields'].add(field)
                if field == 'name': return "What's your name?"
                elif field == 'phone': return "What's your phone number?"
                elif field == 'postcode': return "What's your postcode?"
                elif field == 'address': return "What's the first line of your address?"
                elif field == 'level_load': return "Is the skip a level load?"
                elif field == 'prohibited_check': return "Can you confirm there are no prohibited items?"
                elif field == 'access_issues': return "Are there any access issues?"
        
        # All data collected
        if all(state['customer_data'].get(field) for field in required_fields):
            if not state.get('lead_sent'):
                self.send_collection_lead(state)
                state['lead_sent'] = True
                state['stage'] = 'lead_sent'
                print("SKIP COLLECTION LEAD SENT")
                return SKIP_COLLECTION_RULES['completion']
        
        return "Please provide the missing information for your skip collection."
    
    def send_collection_lead(self, state):
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
    
    # SPECIALIST SERVICES
    def handle_specialist(self, message, state, msg_lower, service):
        print(f"PROCESSING {service.upper()}")
        
        if state.get('lead_sent'):
            return f"Our {service.replace('_', ' ')} team will call you back."
        
        self.extract_basic_data(message, state)
        
        service_config = LG_SERVICES_QUESTIONS.get(service, {})
        questions = service_config.get('questions', [])
        intro = service_config.get('intro', GENERAL_SCRIPTS['lg_transfer_message'])
        
        if not state.get('lg_intro_given'):
            state['lg_intro_given'] = True
            state['lg_question_index'] = 0
            return intro
        
        question_index = state.get('lg_question_index', 0)
        
        if question_index < len(questions):
            question_index += 1
            state['lg_question_index'] = question_index
            
            if question_index < len(questions):
                return questions[question_index]
        
        # All questions completed - send lead
        if not state.get('lead_sent'):
            self.send_specialist_lead(state, service)
            state['lead_sent'] = True
            state['stage'] = 'lead_sent'
            
            name = state['customer_data'].get('name', 'Customer')
            print(f"{service.upper()} LEAD SENT for {name}")
            
            return f"Thanks {name}, I have all the details. Our specialist team will call you back shortly."
        
        return f"Our {service.replace('_', ' ')} team will call you back."
    
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
    
    # GENERAL HANDLER
    def handle_general(self, message, state, msg_lower):
        # Transfer requests
        if any(phrase in msg_lower for phrase in TRANSFER_RULES['management_director']['triggers']):
            if is_business_hours():
                return TRANSFER_RULES['management_director']['office_hours']
            else:
                return TRANSFER_RULES['management_director']['out_of_hours']
        
        elif any(phrase in msg_lower for phrase in TRANSFER_RULES['complaints']['triggers']):
            if is_business_hours():
                return TRANSFER_RULES['complaints']['office_hours']
            else:
                return TRANSFER_RULES['complaints']['out_of_hours']
        
        # Information requests
        elif any(phrase in msg_lower for phrase in ['when deliver', 'delivery time']):
            return SKIP_HIRE_RULES['delivery_timing']
        
        elif 'permit' in msg_lower:
            return GENERAL_SCRIPTS['permit_response']
        
        elif any(word in msg_lower for word in ['price', 'cost', 'quote']):
            return "What service do you need pricing for - skip hire, man & van clearance, or grab hire?"
        
        # Default
        return "What service do you need - skip hire, man & van clearance, grab hire, or something else?"
    
    # HELPER METHODS
    def extract_basic_data(self, message, state):
        """Extract basic customer data from message"""
        # Name extraction
        name_patterns = [
            r"name\s+is\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
            r"i'?m\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
            r"call\s+me\s+([A-Za-z]+)"
        ]
        for pattern in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if name.lower() not in ['yes', 'no', 'hello', 'hi']:
                    state['customer_data']['name'] = name
                    break
        
        # Phone extraction
        phone_patterns = [
            r"\b(07\d{9})\b",
            r"\b(0\d{10})\b",
            r"\b(\d{11})\b"
        ]
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                state['customer_data']['phone'] = match.group(1)
                break
        
        # Postcode extraction
        postcode_pattern = r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b"
        postcode_match = re.search(postcode_pattern, message.upper())
        if postcode_match:
            state['customer_data']['postcode'] = postcode_match.group(1).replace(' ', '')
        
        # Skip size extraction
        skip_sizes = ['4', '6', '8', '10', '12', '14', '16']
        for size in skip_sizes:
            if f"{size} yard" in message.lower() or f"{size}yd" in message.lower():
                state['customer_data']['skip_size'] = f"{size}yd"
                break
    
    def extract_address_line1(self, text):
        """Extract first line of address"""
        address_patterns = [
            r'address\s+(?:is\s+)?(.+)',
            r'first line\s+(?:is\s+)?(.+)', 
            r'(\d+\s+\w+\s+\w+)'
        ]
        for pattern in address_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None

# Initialize agent
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
    </style>
</head>
<body>
    <div class="header">
        <h1>WasteKing System Dashboard</h1>
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
        <h2>Live Conversations</h2>
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
                                    <strong>${conv.id}</strong> - ${conv.stage}
                                </div>
                            `;
                        }).join('');
                        
                        document.getElementById('conversation-list').innerHTML = convHTML || '<p>No conversations yet</p>';
                    }
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
        for conv_id, conv_data in list(conversations.items())[-10:]:
            recent_convs.append({
                'id': conv_id[-8:],
                'stage': conv_data.get('stage', 'unknown')
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
    print("Skip hire: Auto-booking with API")
    print("All services: Complete lead generation")
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
