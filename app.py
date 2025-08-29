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

# Simple state storage (use Redis in production)
CONVERSATION_STATES = {}

def get_conversation_state(conversation_id):
    """Get conversation state"""
    if conversation_id not in CONVERSATION_STATES:
        CONVERSATION_STATES[conversation_id] = {
            'customer_data': {},
            'service_type': None,
            'customer_type': None,
            'stage': 'start',
            'history': [],
            'asked_fields': set(),
            'lg_question_index': 0,
            'permit_checked': False,
            'needs_permit': False,
            'collection_started': False,
            'lg_intro_given': False,
            'booking_completed': False,
            'lead_sent': False
        }
    return CONVERSATION_STATES[conversation_id]

def save_conversation_state(conversation_id, state):
    """Save conversation state"""
    CONVERSATION_STATES[conversation_id] = state

# --- COMPLETE BUSINESS RULES ---
OFFICE_HOURS = {
    'monday_thursday': {'start': 8, 'end': 17},
    'friday': {'start': 8, 'end': 16.5},
    'saturday': {'start': 9, 'end': 12},
    'sunday': 'closed'
}

SKIP_HIRE_RULES = {
    'A2_heavy_materials': {
        'heavy_materials_max': "For heavy materials such as soil & rubble: the largest skip you can have would be an 8-yard. Shall I get you the cost of an 8-yard skip?",
        'heavy_materials_list': ['soil', 'rubble', 'concrete', 'bricks', 'earth', 'clay', 'muckaway', 'hardcore']
    },
    'A5_prohibited_items': {
        'surcharge_items': {'fridges': 20, 'freezers': 20, 'mattresses': 15, 'upholstered furniture': 15},
        'plasterboard_response': "Plasterboard isn't allowed in normal skips. If you have a lot, we can arrange a special plasterboard skip, or our man and van service can collect it for you",
        'restrictions_response': "There may be restrictions on fridges & mattresses depending on your location",
        'upholstery_alternative': "The following items are prohibited in skips. However, our fully licensed and insured man and van service can remove light waste, including these items, safely and responsibly.",
        'prohibited_list': ['fridges', 'freezers', 'mattresses', 'upholstered furniture', 'paint', 'liquids', 'tyres', 'plasterboard', 'gas cylinders', 'hazardous chemicals', 'asbestos', 'medical waste', 'batteries', 'fluorescent tubes', 'monitors', 'televisions'],
        'full_script': "Just so you know, there are some prohibited items that cannot be placed in skips — including mattresses (£15 charge), fridges (£20 charge), upholstery, plasterboard, asbestos, and paint. Our man and van service is ideal for light rubbish and can remove most items. If you'd prefer, I can connect you with the team to discuss the man and van option. Would you like to speak to the team about that, or continue with skip hire?"
    },
    'A7_quote': {
        'vat_note': 'Prices are + VAT for trade customers',
        'always_include': ["Collection within 72 hours standard", "Level load requirement for skip collection", "Driver calls when en route", "98% recycling rate", "We have insured and licensed teams", "Digital waste transfer notes provided"]
    },
    'delivery_timing': "We usually aim to deliver your skip the next day, but during peak months, it may take a bit longer. Don't worry though – we'll check with the depot to get it to you as soon as we can, and we'll always do our best to get it on the day you need.",
    'not_booking_response': "You haven't booked yet, so I'll send the quote to your mobile — if you choose to go ahead, just click the link to book. Would you like a £10 discount? If you're happy with the service after booking, you'll have the option to leave a review.",
    'permit_check': "Is the skip going on the road or on your property?",
    'permit_required': "You'll need a permit as the skip is going on the road. We'll arrange this for you - it typically costs £35-£85 depending on your council.",
    'no_permit': "Great, no permit needed as it's on your property.",
    'roro_heavy_materials': "For heavy materials like soil & rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only.",
    'largest_skip': "The largest skip is RORO 40 yard. The largest for soil and rubble is 8 yard. Larger skips than that are suitable only for light waste, not heavy materials.",
    'dropped_door_explanation': "Dropped down skips are large waste containers delivered by truck and temporarily placed at a site for collecting and removing bulk waste. The special thing about dropped down skips is their convenience—they allow for easy, on-site disposal of large amounts of waste without multiple trips to a landfill."
}

SKIP_COLLECTION_RULES = {
    'script': "I can help with that. It can take between 1-4 days to collect a skip. Can I have your postcode, first line of the address, your name, your telephone number, is the skip a level load, can you confirm there are no prohibited items in the skip, are there any access issues?",
    'completion': "Thanks we can book your skip collection",
    'level_load_explanation': "A level load means the waste doesn't go above the sides of the skip. Overloaded skips can't be collected for safety reasons.",
    'access_explanation': "Access issues might include parked cars, low trees, narrow roads, or anything that might prevent our lorry from reaching the skip."
}

MAV_RULES = {
    'volume_explanation': "Our team charges by the cubic yard which means we only charge by what we remove. To give you an idea, two washing machines equal about one cubic yard. On average, most clearances we do are around six yards. How many yards do you want to book with us?",
    'heavy_materials_response': "The man and van are ideal for light waste rather than heavy materials - a skip might be more suitable, since our man and van service is designed for lighter waste.",
    'supplement_check': "Can I just check — do you have any mattresses, upholstery, or fridges that need collecting?",
    'sunday_response': "For a collection on a Sunday, it will be a bespoke price. Let me put you through our team and they will be able to help",
    'time_restriction': "We can't guarantee exact times, but collection is typically between 7am-6pm",
    'if_unsure_volume': "Think in terms of washing machine loads or black bags.",
    'pricing_guide': "Typically starts from £90 for 1-2 cubic yards, but final price depends on location and items.",
    'what_we_take': "We take most household items including furniture, appliances, garden waste, and general rubbish. We're fully licensed for fridges and mattresses too."
}

GRAB_RULES = {
    '6_wheeler_explanation': "I understand you need a 6-wheeler grab lorry. That's a 12-tonne capacity lorry.",
    '8_wheeler_explanation': "I understand you need an 8-wheeler grab lorry. That's a 16-tonne capacity lorry.",
    'mixed_materials_response': "The majority of grabs will only take muckaway which is soil & rubble. Let me put you through to our team and they will check if we can take the other materials for you.",
    'transfer_message': "Most of the prices for grabs are not on SMP so I'll transfer you to a human specialist.",
    'capacity_tonnes': "A 6-wheel grab lorry typically has a capacity of around 12 to 14 tonnes, while an 8-wheel grab lorry can usually carry approximately 16 to 18 tonnes.",
    'reach_explanation': "Grab lorries can typically reach over walls and fences up to 6 meters from where the lorry parks.",
    'access_requirements': "Grab lorries need good access - roughly 3 meters wide and 4 meters high clearance, plus stable ground to support the weight."
}

WASTE_BAGS_INFO = {
    'script': "Our skip bags are for light waste only. Is this for light waste and our man and van service will collect the rubbish? We can deliver a bag out to you and you can fill it and then we collect and recycle the rubbish. We have 3 sizes: 1.5, 3.6, 4.5 cubic yards bags. Bags are great as there's no time limit and we collect when you're ready",
    'pricing': "Bags cost from £15-25 for delivery, then collection is priced by volume when you're ready.",
    'restrictions': "Skip bags are for light waste only - no soil, rubble, or heavy materials."
}

RORO_RULES = {
    'sizes': ['20 yard', '30 yard', '35 yard', '40 yard'],
    'heavy_materials': "For heavy materials like soil & rubble in RoRo skips, we recommend a 20 yard RoRo skip. 30/35/40 yard RoRos are for light materials only.",
    'largest_skip': "The largest skip is RORO 40 yard. The largest for soil and rubble is 8 yard.",
    'typical_uses': "RoRo skips are ideal for large commercial projects, demolition work, and major clearances.",
    'access_requirements': "RoRo skips need significant space - about 20 meters length for delivery and good access for our lorry."
}

WAIT_AND_LOAD_RULES = {
    'explanation': "Wait and load service means the driver waits while you load the skip, then takes it away immediately. Perfect for restricted access areas.",
    'time_limit': "You get 30-45 minutes to load the skip while the driver waits.",
    'pricing': "Wait and load is typically 20-30% more expensive than standard skip hire due to the driver waiting time.",
    'ideal_for': "Ideal for busy roads, permit restrictions, or where you can't leave a skip."
}

WHEELIE_BINS_RULES = {
    'sizes': ['120L', '240L', '360L', '660L', '1100L'],
    'commercial_only': "Wheelie bin hire is typically for commercial customers with regular collections.",
    'frequency': "Collection frequency can be daily, weekly, fortnightly, or monthly depending on your needs.",
    'waste_types': "We offer general waste, mixed recycling, food waste, and glass collection services."
}

AGGREGATES_RULES = {
    'types': ['Sand', 'Gravel', 'Type 1 MOT', 'Crushed concrete', 'Topsoil', 'Ballast', 'Sharp sand', 'Building sand'],
    'delivery': "We can deliver via tipper truck or grab lorry depending on access and quantity.",
    'minimum': "Minimum order is typically 1 tonne.",
    'pricing': "Prices vary by material and location - our team will provide a quote."
}

LG_SERVICES = {
    'skip_collection': {
        'triggers': ['skip collection', 'collect skip', 'pick up skip', 'remove skip', 'collection of skip', 'empty skip']
    },
    'road_sweeper': {
        'triggers': ['road sweeper', 'road sweeping', 'street sweeping', 'road cleaning']
    },
    'toilet_hire': {
        'triggers': ['toilet hire', 'portaloo', 'portable toilet', 'site toilet', 'event toilet']
    },
    'asbestos': {
        'triggers': ['asbestos', 'asbestos removal', 'asbestos disposal']
    },
    'hazardous_waste': {
        'triggers': ['hazardous waste', 'chemical waste', 'dangerous waste', 'special waste']
    },
    'wheelie_bins': {
        'triggers': ['wheelie bin', 'wheelie bins', 'bin hire', 'commercial bins', 'waste bins']
    },
    'aggregates': {
        'triggers': ['aggregates', 'sand', 'gravel', 'stone', 'topsoil', 'type 1', 'ballast']
    },
    'roro': {
        'triggers': ['40 yard', '30 yard', '35 yard', 'roro', 'roll on roll off', 'large skip']
    },
    'waste_bags': {
        'triggers': ['skip bag', 'waste bag', 'skip sack', 'hippo bag']
    },
    'wait_and_load': {
        'triggers': ['wait and load', 'wait & load', 'wait load', 'same day']
    }
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
        ],
        'intro': SKIP_COLLECTION_RULES['script']
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
        'intro': WHEELIE_BINS_RULES['commercial_only'] + " Let me take your details."
    },
    'aggregates': {
        'questions': [
            "Can I take your postcode?",
            "What type of aggregate do you need?",
            "How many tonnes do you require?",
            "Do you need tipper or grab delivery?",
            "When do you need delivery?",
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
        'intro': WAIT_AND_LOAD_RULES['explanation'] + " Let me take your details."
    },
    'roro': {
        'questions': [
            "Can I take your postcode?",
            "What size RORO do you need - 20, 30, 35, or 40 yard?",
            "What type of waste will you be putting in the RORO?",
            "Is this for heavy materials or light waste?",
            "When do you need delivery?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': "I will pass you onto our specialist team to give you a quote and availability for RORO skip hire"
    },
    'waste_bags': {
        'questions': [
            "Can I take your postcode?",
            "What size bag do you need - 1.5, 3.6, or 4.5 cubic yards?",
            "What type of waste will you be putting in?",
            "When would you like the bag delivered?",
            "What's your name?",
            "What's the best phone number to contact you on?"
        ],
        'intro': WASTE_BAGS_INFO['script']
    }
}

TRANSFER_RULES = {
    'management_director': {
        'triggers': ['glenn currie', 'director', 'speak to glenn', 'managing director', 'ceo', 'owner'],
        'office_hours': "I am sorry, Glenn is not available, may I take your details and Glenn will call you back?",
        'out_of_hours': "I can take your details and have our director call you back first thing tomorrow",
        'sms_notify': '+447823656762'
    },
    'complaints': {
        'triggers': ['complaint', 'complain', 'unhappy', 'disappointed', 'frustrated', 'angry', 'terrible service', 'disgusted', 'appalled'],
        'office_hours': "I understand your frustration, please bear with me while I transfer you to the appropriate person.",
        'out_of_hours': "I understand your frustration. I can take your details and have our customer service team call you back first thing tomorrow.",
        'action': 'TRANSFER'
    },
    'specific_person': {
        'tracey_request': "Yes I can see if she's available. What's your name, your telephone number, what is your company name? What is the call regarding?",
        'human_agent': "Yes I can see if someone is available. What's your name, your telephone number, what is your company name? What is the call regarding?"
    },
    'specialist_services': {
        'services': ['hazardous waste disposal', 'asbestos removal', 'asbestos collection', 'weee electrical waste', 'chemical disposal', 'medical waste', 'trade waste'],
        'office_hours': 'Transfer immediately',
        'out_of_hours': 'Take details + SMS notification to +447823656762'
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

# Helper functions
def is_business_hours():
    """Check if currently in business hours"""
    from datetime import datetime, timezone, timedelta
    utc_now = datetime.now(timezone.utc)
    uk_now = utc_now + timedelta(hours=0)  # Adjust for BST/GMT as needed
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

def send_sms(phone, message):
    """Send SMS via Twilio"""
    try:
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        from_number = os.getenv('TWILIO_PHONE_NUMBER', '+447700900000')
        
        if not account_sid or not auth_token:
            print(f"SMS WOULD SEND to {phone}: {message[:50]}...")
            return True
            
        from twilio.rest import Client
        client = Client(account_sid, auth_token)
        client.messages.create(body=message, from_=from_number, to=phone)
        print(f"SMS SENT to {phone}")
        return True
    except Exception as e:
        print(f"SMS ERROR: {e}")
        return False

def send_email(subject, body, recipient='kanchan.ghosh@wasteking.co.uk'):
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

def extract_customer_data(message, state):
    """Extract customer data from message"""
    msg_lower = message.lower()
    cd = state.get('customer_data', {})
    
    # Postcode extraction with better patterns
    postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b', message.upper())
    if postcode_match and not cd.get('postcode'):
        cd['postcode'] = postcode_match.group(1).replace(' ', '')
    
    # Phone extraction - UK numbers
    phone_patterns = [
        r'\b(07\d{9})\b',  # UK mobile
        r'\b(0\d{10})\b',  # UK landline
        r'\b(\+447\d{9})\b'  # International format
    ]
    for pattern in phone_patterns:
        phone_match = re.search(pattern, message)
        if phone_match and not cd.get('phone'):
            cd['phone'] = phone_match.group(1)
            break
    
    # Name extraction with multiple patterns
    if not cd.get('name'):
        name_patterns = [
            (r'my name is\s+([A-Za-z]+)', 1),
            (r"i'm\s+([A-Za-z]+)", 1),
            (r"i am\s+([A-Za-z]+)", 1),
            (r"call me\s+([A-Za-z]+)", 1),
            (r"this is\s+([A-Za-z]+)", 1),
            (r'^([A-Z][a-z]+)[\s,.]', 1)  # Name at start of message
        ]
        for pattern, group in name_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(group).strip()
                if name.lower() not in ['yes', 'no', 'hello', 'hi', 'thanks', 'please', 'skip', 'need']:
                    cd['name'] = name.capitalize()
                    break
    
    # Skip size extraction
    skip_sizes = ['2', '4', '6', '8', '10', '12', '14', '16', '20', '30', '35', '40']
    for size in skip_sizes:
        if f"{size} yard" in msg_lower or f"{size}yd" in msg_lower or f"{size}-yard" in msg_lower:
            cd['skip_size'] = f"{size}yd"
            break
    
    # Customer type detection
    if 'trade' in msg_lower or 'business' in msg_lower or 'company' in msg_lower or 'builder' in msg_lower or 'commercial' in msg_lower:
        state['customer_type'] = 'trade'
    elif 'domestic' in msg_lower or 'home' in msg_lower or 'house' in msg_lower or 'personal' in msg_lower or 'residential' in msg_lower:
        state['customer_type'] = 'domestic'
    
    # Address extraction
    if 'first line' in msg_lower or 'address' in msg_lower:
        # Extract everything after "is" or "at"
        address_patterns = [
            r'(?:address is|first line is|live at)\s+(.+)',
            r'(\d+\s+[A-Za-z\s]+(?:street|road|lane|avenue|way|drive|close|place))',
        ]
        for pattern in address_patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                cd['address'] = match.group(1).strip()
                break
    
    # Volume for man and van
    volume_patterns = [
        (r'(\d+)\s*cubic\s*yard', lambda m: f"{m.group(1)} cubic yards"),
        (r'(\d+)\s*washing\s*machine', lambda m: f"{m.group(1)} washing machines"),
        (r'(\d+)\s*bag', lambda m: f"{m.group(1)} bags"),
        (r'about\s+(\d+)', lambda m: f"about {m.group(1)} cubic yards")
    ]
    for pattern, formatter in volume_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            cd['volume'] = formatter(match)
            break
    
    # When required
    time_indicators = {
        'today': 'Today',
        'tomorrow': 'Tomorrow',
        'asap': 'ASAP',
        'urgent': 'Urgent',
        'monday': 'Monday',
        'tuesday': 'Tuesday',
        'wednesday': 'Wednesday',
        'thursday': 'Thursday',
        'friday': 'Friday',
        'saturday': 'Saturday',
        'sunday': 'Sunday',
        'next week': 'Next week',
        'this week': 'This week'
    }
    for key, value in time_indicators.items():
        if key in msg_lower:
            cd['when_required'] = value
            break
    
    # Material type for grab/RORO
    if 'soil' in msg_lower or 'rubble' in msg_lower or 'muckaway' in msg_lower or 'hardcore' in msg_lower:
        cd['material_type'] = 'Heavy materials (soil/rubble)'
    elif 'general' in msg_lower or 'mixed' in msg_lower or 'light' in msg_lower:
        cd['material_type'] = 'General/light waste'
    
    # Supplement items for man and van
    supplement_items = []
    if 'mattress' in msg_lower:
        supplement_items.append('mattresses')
    if 'fridge' in msg_lower or 'freezer' in msg_lower:
        supplement_items.append('fridges/freezers')
    if 'sofa' in msg_lower or 'furniture' in msg_lower or 'chair' in msg_lower:
        supplement_items.append('furniture')
    if supplement_items:
        cd['supplement_items'] = ', '.join(supplement_items)
    elif any(word in msg_lower for word in ['no', 'none', 'nothing']):
        cd['supplement_items'] = 'None'
    
    state['customer_data'] = cd
    return state

def handle_skip_booking(state):
    """Complete skip booking with API"""
    cd = state['customer_data']
    vat_text = " (+ VAT)" if state.get('customer_type') == 'trade' else ""
    permit_text = " + permit (£35-85)" if state.get('needs_permit') else ""
    
    try:
        # Get pricing from API
        price_resp = get_pricing(cd['postcode'], cd.get('skip_size', '8yd'))
        if not price_resp.get('success'):
            # API failed - send to human
            send_email(
                f"API FAILURE - {cd.get('name', 'Unknown')}",
                f"Pricing API failed\n\nCustomer: {cd.get('name')}\nPhone: {cd.get('phone')}\nPostcode: {cd.get('postcode')}\nSkip Size: {cd.get('skip_size', '8yd')}\n\nAction: Call customer to complete booking"
            )
            return f"Technical issue getting your price. Our team will call you on {cd['phone']} to complete your {cd.get('skip_size', '8yd')} skip booking."
        
        price = price_resp['price']
        
        # Create booking
        booking_resp = create_booking({
            'name': cd['name'],
            'phone': cd['phone'],
            'postcode': cd['postcode'],
            'skip_size': cd.get('skip_size', '8yd'),
            'price': price,
            'customer_type': state.get('customer_type', 'domestic'),
            'needs_permit': state.get('needs_permit', False)
        })
        
        if not booking_resp.get('success'):
            send_email(
                f"BOOKING API FAILED - {cd['name']}",
                f"Booking creation failed\n\nCustomer: {cd.get('name')}\nPhone: {cd.get('phone')}\nPostcode: {cd.get('postcode')}\n\nAction: Manual booking required"
            )
            return f"Booking system issue. Our team will call you on {cd['phone']} within the hour to complete your booking."
        
        ref = booking_resp['reference']
        
        # Get payment link
        payment_resp = create_payment_link({
            'booking_ref': ref,
            'amount': price,
            'customer_name': cd['name'],
            'phone': cd['phone']
        })
        
        if not payment_resp.get('success'):
            # Payment link failed but booking succeeded
            send_email(
                f"PAYMENT LINK FAILED - {cd['name']}",
                f"Payment link API failed\n\nBooking Ref: {ref}\nCustomer: {cd['name']}\nPhone: {cd['phone']}\nAmount: {price}\n\nAction: Send payment link manually"
            )
            response = f"Your {cd.get('skip_size', '8yd')} skip is booked! Reference: {ref}\n"
            response += f"Price: {price}{vat_text}{permit_text}\n\n"
            response += "Our team will call you shortly with the payment link."
            state['stage'] = 'booking_complete_payment_pending'
            return response
        
        link = payment_resp['payment_link']
        
        # Send SMS with exact format
        sms = f"""Thank You for Choosing Waste King 🌱
 
Please click the secure link below to complete your payment: {link}
 
As part of our service, you'll receive digital waste transfer notes for your records. We're also proud to be planting trees every week to offset our carbon footprint. If you were happy with our service, we'd really appreciate it if you could leave us a review at https://uk.trustpilot.com/review/wastekingrubbishclearance.com. Find out more about us at www.wastekingrubbishclearance.co.uk.
 
Best regards,
The Waste King Team"""
        
        send_sms(cd['phone'], sms)
        
        # Send email confirmation
        send_email(
            f"SKIP BOOKING CONFIRMED - {cd['name']} - {ref}",
            f"Booking confirmed:\n\nReference: {ref}\nCustomer: {cd['name']}\nPhone: {cd['phone']}\nPostcode: {cd['postcode']}\nSkip Size: {cd.get('skip_size', '8yd')}\nPrice: {price}{vat_text}{permit_text}\nPayment Link Sent: Yes\n\nAction: Schedule delivery within 24 hours"
        )
        
        response = f"Perfect {cd['name']}! Your {cd.get('skip_size', '8yd')} skip is booked for {cd['postcode']}.\n\n"
        response += f"📋 Reference: {ref}\n"
        response += f"💷 Price: {price}{vat_text}{permit_text}\n\n"
        response += SKIP_HIRE_RULES['delivery_timing'] + "\n\n"
        response += "📱 Check your phone for the payment link."
        
        state['stage'] = 'completed'
        state['booking_completed'] = True
        state['booking_ref'] = ref
        
        return response
        
    except Exception as e:
        print(f"ERROR in handle_skip_booking: {e}")
        traceback.print_exc()
        send_email(
            f"SYSTEM ERROR - {cd.get('name', 'Unknown')}",
            f"System error during booking\n\nError: {str(e)}\n\nCustomer: {cd.get('name')}\nPhone: {cd.get('phone')}\nPostcode: {cd.get('postcode')}\n\nAction: Immediate callback required"
        )
        return f"Technical issue with our booking system. Our team will call you on {cd.get('phone', 'your phone')} immediately to complete your booking."

# Main message processing
@app.route('/api/wasteking', methods=['POST'])
def process_message():
    try:
        data = request.get_json()
        customer_message = data.get('customerquestion', '').strip()
        conversation_id = data.get('conversation_id') or data.get('elevenlabs_conversation_id', '')
        
        if not customer_message:
            return jsonify({"success": True, "message": "Hi! What service do you need today? Skip hire, man & van clearance, grab hire, or something else?"}), 200
        
        if not conversation_id:
            conversation_id = f"conv_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        print(f"\n[{conversation_id}] Customer: {customer_message}")
        msg_lower = customer_message.lower()
        
        # Get state
        state = get_conversation_state(conversation_id)
        state['history'].append(f"Customer: {customer_message}")
        
        # Always extract data from every message
        state = extract_customer_data(customer_message, state)
        
        # Initialize response
        response = ""
        
        # COMPLAINTS/DIRECTOR TRANSFER - Check first
        if any(word in msg_lower for word in TRANSFER_RULES['complaints']['triggers']):
            if is_business_hours():
                response = TRANSFER_RULES['complaints']['office_hours']
            else:
                response = TRANSFER_RULES['complaints']['out_of_hours']
            save_conversation_state(conversation_id, state)
            print(f"[{conversation_id}] Agent: {response}")
            return jsonify({"success": True, "message": response}), 200
        
        elif any(phrase in msg_lower for phrase in TRANSFER_RULES['management_director']['triggers']):
            if is_business_hours():
                response = TRANSFER_RULES['management_director']['office_hours']
            else:
                response = TRANSFER_RULES['management_director']['out_of_hours']
            save_conversation_state(conversation_id, state)
            return jsonify({"success": True, "message": response}), 200
        
        # SKIP HIRE DETECTION AND COMPLETE HANDLING
        elif ('skip' in msg_lower and not any(word in msg_lower for word in ['collect', 'collection', 'pick up', 'remove'])) or state.get('service_type') == 'skip_hire':
            state['service_type'] = 'skip_hire'
            
            # Check if already completed
            if state.get('booking_completed'):
                response = f"Your skip is already booked! Reference: {state.get('booking_ref')}. Check your phone for the payment link."
            
            # Check heavy materials rule
            elif any(word in msg_lower for word in SKIP_HIRE_RULES['A2_heavy_materials']['heavy_materials_list']) and any(size in msg_lower for size in ['10', '12', '14', '16', '20', '30', '35', '40']):
                state['customer_data']['skip_size'] = '8yd'
                response = SKIP_HIRE_RULES['A2_heavy_materials']['heavy_materials_max']
            
            # Check prohibited items
            elif any(item in msg_lower for item in SKIP_HIRE_RULES['A5_prohibited_items']['prohibited_list']):
                if 'plasterboard' in msg_lower:
                    response = SKIP_HIRE_RULES['A5_prohibited_items']['plasterboard_response']
                elif 'asbestos' in msg_lower:
                    response = "Asbestos cannot go in normal skips. We have a specialist asbestos service - shall I arrange for our certified team to call you?"
                else:
                    response = SKIP_HIRE_RULES['A5_prohibited_items']['full_script']
            
            # Delivery timing question
            elif any(phrase in msg_lower for phrase in ['when deliver', 'delivery time', 'how long', 'when arrive', 'what time']):
                response = SKIP_HIRE_RULES['delivery_timing']
            
            # Not booking response
            elif any(phrase in msg_lower for phrase in ['think about', 'call back later', 'shop around', 'check with', 'speak to']):
                response = SKIP_HIRE_RULES['not_booking_response']
            
            # RORO check
            elif any(size in msg_lower for size in ['30', '35', '40']) and 'yard' in msg_lower:
                state['service_type'] = 'roro'
                response = "For 30+ yard skips, that's a RoRo service. " + RORO_RULES['heavy_materials']
            
            # Continue with booking flow
            else:
                cd = state['customer_data']
                
                # Check what we need
                if not cd.get('name'):
                    response = "What's your name?"
                elif not cd.get('phone'):
                    response = "What's your phone number?"
                elif not cd.get('postcode'):
                    response = "What's your postcode?"
                elif not state.get('customer_type'):
                    response = "Are you a domestic or trade customer?"
                elif not cd.get('skip_size'):
                    response = "What size skip do you need? We have 4, 6, 8, and 12 yard skips available."
                elif not state.get('permit_checked'):
                    state['permit_checked'] = True
                    response = SKIP_HIRE_RULES['permit_check']
                elif state.get('permit_checked') and not state.get('permit_answered'):
                    if 'road' in msg_lower or 'street' in msg_lower or 'outside' in msg_lower:
                        state['needs_permit'] = True
                        state['permit_answered'] = True
                        response = SKIP_HIRE_RULES['permit_required'] + "\n\nNow let me complete your booking..."
                        # Continue to booking
                        booking_response = handle_skip_booking(state)
                        response = booking_response
                    elif 'property' in msg_lower or 'drive' in msg_lower or 'garden' in msg_lower or 'land' in msg_lower:
                        state['needs_permit'] = False
                        state['permit_answered'] = True
                        response = SKIP_HIRE_RULES['no_permit'] + "\n\nNow let me complete your booking..."
                        # Continue to booking
                        booking_response = handle_skip_booking(state)
                        response = booking_response
                    else:
                        response = "Sorry, I need to know - will the skip be on the road or on your property?"
                else:
                    # All data collected - book it!
                    response = handle_skip_booking(state)
        
        # SKIP COLLECTION
        elif any(phrase in msg_lower for phrase in ['skip collection', 'collect skip', 'pick up skip', 'remove skip', 'empty skip']):
            state['service_type'] = 'skip_collection'
            
            if not state.get('collection_started'):
                state['collection_started'] = True
                response = SKIP_COLLECTION_RULES['script']
            else:
                cd = state['customer_data']
                
                # Check collection data systematically
                if not cd.get('postcode'):
                    response = "What's your postcode?"
                elif not cd.get('address'):
                    response = "What's the first line of your address?"
                elif not cd.get('name'):
                    response = "What's your name?"
                elif not cd.get('phone'):
                    response = "What's your telephone number?"
                elif not cd.get('level_load'):
                    if any(word in msg_lower for word in ['yes', 'level', 'flush', 'not over']):
                        cd['level_load'] = 'Yes - level load'
                    elif any(word in msg_lower for word in ['no', 'over', 'above', 'high']):
                        cd['level_load'] = 'No - overloaded'
                    response = "Is the skip a level load? (not above the sides)"
                elif not cd.get('no_prohibited'):
                    if any(word in msg_lower for word in ['yes', 'confirm', 'nothing', 'no prohibited']):
                        cd['no_prohibited'] = 'Confirmed - no prohibited items'
                    elif any(word in msg_lower for word in ['no', 'some', 'mattress', 'fridge']):
                        cd['no_prohibited'] = 'Has prohibited items'
                    response = "Can you confirm there are no prohibited items in the skip?"
                elif not cd.get('access_issues'):
                    if any(word in msg_lower for word in ['no', 'fine', 'good', 'clear']):
                        cd['access_issues'] = 'No access issues'
                    elif any(word in msg_lower for word in ['yes', 'cars', 'narrow', 'tight', 'problem']):
                        cd['access_issues'] = 'Access issues present'
                    response = "Are there any access issues we should know about?"
                else:
                    # All collection data gathered
                    send_email(
                        f"SKIP COLLECTION REQUEST - {cd['name']}",
                        f"Collection requested:\n\nCustomer: {cd['name']}\nPhone: {cd['phone']}\nPostcode: {cd['postcode']}\nAddress: {cd.get('address')}\nLevel Load: {cd.get('level_load')}\nProhibited Items: {cd.get('no_prohibited')}\nAccess: {cd.get('access_issues')}\n\nAction: Arrange collection within 1-4 days"
                    )
                    response = SKIP_COLLECTION_RULES['completion'] + " Our team will contact you to confirm collection time."
                    state['stage'] = 'collection_booked'
        
        # MAN AND VAN
        elif any(phrase in msg_lower for phrase in ['man and van', 'man & van', 'clearance', 'rubbish removal', 'waste removal', 'house clear', 'office clear']) or state.get('service_type') == 'man_and_van':
            state['service_type'] = 'man_and_van'
            
            # Check if already sent lead
            if state.get('lead_sent'):
                response = "Our man and van team will call you back shortly with pricing and availability."
            
            # Heavy materials check
            elif any(mat in msg_lower for mat in ['soil', 'rubble', 'concrete', 'bricks', 'earth', 'hardcore']):
                response = MAV_RULES['heavy_materials_response']
            
            # Sunday check
            elif 'sunday' in msg_lower and not state.get('sunday_noted'):
                state['sunday_noted'] = True
                response = MAV_RULES['sunday_response']
            
            else:
                cd = state['customer_data']
                
                # Systematic data collection
                if not cd.get('name'):
                    response = "What's your name?"
                elif not cd.get('phone'):
                    response = "What's your phone number?"
                elif not cd.get('postcode'):
                    response = "What's your postcode?"
                elif not cd.get('volume'):
                    # Check if they answered volume question
                    if any(word in msg_lower for word in ['cubic', 'yard', 'washing', 'machine', 'bag', 'van', 'load']):
                        # Volume was provided, move on
                        pass
                    else:
                        response = MAV_RULES['volume_explanation']
                elif not cd.get('supplement_items'):
                    # Check if they answered supplement question
                    if cd.get('supplement_items') or any(word in msg_lower for word in ['yes', 'no', 'none', 'nothing', 'mattress', 'fridge', 'sofa']):
                        # Supplement answer provided
                        pass
                    else:
                        response = MAV_RULES['supplement_check']
                elif not cd.get('when_required'):
                    response = "When do you need this collected?"
                else:
                    # All data collected - send lead
                    send_email(
                        f"MAN & VAN LEAD - {cd['name']}",
                        f"Man & Van service requested:\n\nCustomer: {cd['name']}\nPhone: {cd['phone']}\nPostcode: {cd['postcode']}\nVolume: {cd.get('volume', 'Not specified')}\nWhen: {cd.get('when_required', 'Not specified')}\nSpecial Items: {cd.get('supplement_items', 'None')}\n\nAction: Call back with pricing within 1 hour"
                    )
                    response = f"Perfect {cd['name']}! I have all your details. Our man and van team will call you back within the hour with pricing and to arrange your clearance."
                    state['lead_sent'] = True
                    state['stage'] = 'lead_sent'
        
        # GRAB HIRE
        elif any(word in msg_lower for word in ['grab', 'muckaway', 'tipper']) or state.get('service_type') == 'grab_hire':
            state['service_type'] = 'grab_hire'
            
            # Check if already sent lead
            if state.get('lead_sent'):
                response = "Our grab hire specialist will call you back shortly."
            
            # 6/8 wheeler explanations
            elif '6 wheel' in msg_lower or '6wheel' in msg_lower or 'six wheel' in msg_lower:
                state['customer_data']['grab_type'] = '6-wheeler'
                response = GRAB_RULES['6_wheeler_explanation']
            elif '8 wheel' in msg_lower or '8wheel' in msg_lower or 'eight wheel' in msg_lower:
                state['customer_data']['grab_type'] = '8-wheeler'
                response = GRAB_RULES['8_wheeler_explanation']
            
            # Mixed materials check
            elif 'mixed' in msg_lower or ('soil' in msg_lower and any(word in msg_lower for word in ['wood', 'general', 'waste'])):
                response = GRAB_RULES['mixed_materials_response']
            
            else:
                cd = state['customer_data']
                
                if not cd.get('name'):
                    response = "What's your name?"
                elif not cd.get('phone'):
                    response = "What's your phone number?"
                elif not cd.get('postcode'):
                    response = "What's your postcode?"
                elif not cd.get('material_type'):
                    response = "What type of material do you need to remove - soil/rubble (muckaway) or general waste?"
                elif not cd.get('when_required'):
                    response = "When do you need the grab lorry?"
                else:
                    # Send lead
                    send_email(
                        f"GRAB HIRE LEAD - {cd['name']}",
                        f"Grab hire requested:\n\nCustomer: {cd['name']}\nPhone: {cd['phone']}\nPostcode: {cd['postcode']}\nMaterial: {cd.get('material_type')}\nGrab Type: {cd.get('grab_type', 'Not specified')}\nWhen: {cd.get('when_required')}\n\nAction: Specialist callback required"
                    )
                    response = f"Thanks {cd['name']}. {GRAB_RULES['transfer_message']}"
                    state['lead_sent'] = True
                    state['stage'] = 'lead_sent'
        
        # Check all LG services
        else:
            service_detected = False
            
            for service_key, service_data in LG_SERVICES.items():
                if any(trigger in msg_lower for trigger in service_data['triggers']):
                    state['service_type'] = service_key
                    service_detected = True
                    
                    questions_config = LG_SERVICES_QUESTIONS.get(service_key, {})
                    questions = questions_config.get('questions', [])
                    intro = questions_config.get('intro', GENERAL_SCRIPTS['lg_transfer_message'])
                    
                    # Give intro if first time
                    if not state.get('lg_intro_given'):
                        state['lg_intro_given'] = True
                        state['lg_question_index'] = 0
                        response = intro
                    else:
                        # Process through questions
                        index = state.get('lg_question_index', 0)
                        
                        # Store answer from previous question
                        if index > 0:
                            # Extract and store relevant data based on the service
                            pass
                        
                        # Ask next question
                        if index < len(questions):
                            response = questions[index]
                            state['lg_question_index'] = index + 1
                        else:
                            # All questions asked - send lead
                            cd = state['customer_data']
                            service_name = service_key.replace('_', ' ').upper()
                            
                            send_email(
                                f"{service_name} LEAD - {cd.get('name', 'Unknown')}",
                                f"{service_name} service requested:\n\nCustomer: {cd.get('name')}\nPhone: {cd.get('phone')}\nPostcode: {cd.get('postcode')}\n\nService: {service_name}\nAction: Specialist callback required"
                            )
                            
                            if service_key == 'asbestos':
                                response = f"Thanks {cd.get('name', '')}. Asbestos requires specialist handling. Our certified team will call you back within 2 hours."
                            elif service_key == 'wait_and_load':
                                response = f"Thanks {cd.get('name', '')}. {WAIT_AND_LOAD_RULES['explanation']} Our team will call you back shortly."
                            elif service_key == 'waste_bags':
                                response = f"Thanks {cd.get('name', '')}. Our team will call you back to arrange delivery of your waste bags."
                            else:
                                response = f"Thanks {cd.get('name', '')}. Our specialist team will call you back shortly with pricing and availability."
                            
                            state['lead_sent'] = True
                            state['stage'] = 'lead_sent'
                    break
            
            # No service detected - check for general queries
            if not service_detected:
                # Timing queries
                if any(phrase in msg_lower for phrase in ['what time', 'specific time', 'exact time', 'delivery time']):
                    response = GENERAL_SCRIPTS['timing_query']
                
                # Location queries
                elif any(phrase in msg_lower for phrase in ['where are you', 'location', 'based', 'depot', 'local']):
                    response = GENERAL_SCRIPTS['location_response']
                
                # Permit queries
                elif 'permit' in msg_lower:
                    response = GENERAL_SCRIPTS['permit_response']
                
                # Access requirements
                elif 'access' in msg_lower or 'requirements' in msg_lower:
                    response = GENERAL_SCRIPTS['access_requirements']
                
                # Human agent request
                elif any(phrase in msg_lower for phrase in ['speak to someone', 'human', 'person', 'agent']):
                    response = TRANSFER_RULES['specific_person']['human_agent']
                
                # Default - ask what service
                else:
                    response = "What service do you need today? We offer:\n• Skip hire (4-12 yard)\n• Man & van clearance\n• Grab lorry hire\n• Skip collection\n• Specialist services (asbestos, hazardous waste, etc.)\n\nHow can I help you?"
        
        # Save state and return response
        state['history'].append(f"Agent: {response}")
        save_conversation_state(conversation_id, state)
        
        print(f"[{conversation_id}] Agent: {response}")
        return jsonify({"success": True, "message": response}), 200
        
    except Exception as e:
        print(f"ERROR in process_message: {e}")
        traceback.print_exc()
        # Don't expose errors to customer
        return jsonify({"success": True, "message": "Let me connect you with our team to help with that."}), 200

# Dashboard routes
@app.route('/')
def index():
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WasteKing System Dashboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1400px; margin: 0 auto; }
        .header { 
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(10px);
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
            margin-bottom: 30px;
        }
        h1 { 
            color: #2d3436;
            font-size: 2.5em;
            margin-bottom: 10px;
        }
        .subtitle { color: #636e72; font-size: 1.1em; }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-value {
            font-size: 3em;
            font-weight: bold;
            background: linear-gradient(135deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 5px;
        }
        .stat-label { color: #636e72; font-size: 1.1em; }
        .conversations-panel {
            background: white;
            padding: 30px;
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0,0,0,0.1);
        }
        .conv-header { 
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        h2 { color: #2d3436; }
        .refresh-btn {
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            border: none;
            padding: 12px 25px;
            border-radius: 10px;
            cursor: pointer;
            font-size: 1em;
            transition: opacity 0.3s;
        }
        .refresh-btn:hover { opacity: 0.9; }
        .conv-list { max-height: 600px; overflow-y: auto; }
        .conv-item {
            background: #f8f9fa;
            padding: 20px;
            margin-bottom: 15px;
            border-radius: 12px;
            border-left: 4px solid #667eea;
            transition: all 0.3s;
        }
        .conv-item:hover { 
            background: #f1f3f5;
            transform: translateX(5px);
        }
        .conv-item.completed { border-left-color: #00b894; }
        .conv-item.lead-sent { border-left-color: #fdcb6e; }
        .conv-id { 
            font-weight: bold;
            color: #2d3436;
            margin-bottom: 8px;
        }
        .conv-details { 
            color: #636e72;
            line-height: 1.6;
        }
        .service-badge {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.85em;
            margin-left: 10px;
        }
        .status-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 15px;
            font-size: 0.85em;
            margin-left: 10px;
            font-weight: 500;
        }
        .status-badge.active { background: #e3f2fd; color: #1976d2; }
        .status-badge.completed { background: #e8f5e9; color: #388e3c; }
        .status-badge.lead-sent { background: #fff3e0; color: #f57c00; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚛 WasteKing System Dashboard</h1>
            <p class="subtitle">Real-time conversation monitoring and booking management</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="total">0</div>
                <div class="stat-label">Total Conversations</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="active">0</div>
                <div class="stat-label">Active Now</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="bookings">0</div>
                <div class="stat-label">Bookings Completed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="leads">0</div>
                <div class="stat-label">Leads Generated</div>
            </div>
        </div>
        
        <div class="conversations-panel">
            <div class="conv-header">
                <h2>Recent Conversations</h2>
                <button class="refresh-btn" onclick="loadDashboard()">🔄 Refresh</button>
            </div>
            <div class="conv-list" id="conversation-list">
                <p style="color: #636e72; text-align: center; padding: 40px;">Loading conversations...</p>
            </div>
        </div>
    </div>
    
    <script>
        async function loadDashboard() {
            try {
                const response = await fetch('/api/dashboard');
                const data = await response.json();
                
                document.getElementById('total').textContent = data.total || 0;
                document.getElementById('active').textContent = data.active || 0;
                document.getElementById('bookings').textContent = data.bookings || 0;
                document.getElementById('leads').textContent = data.leads || 0;
                
                const convList = document.getElementById('conversation-list');
                
                if (data.conversations && data.conversations.length > 0) {
                    convList.innerHTML = data.conversations.map(conv => {
                        const statusClass = conv.stage === 'completed' ? 'completed' : 
                                          conv.stage === 'lead_sent' ? 'lead-sent' : '';
                        const statusBadge = conv.stage === 'completed' ? '<span class="status-badge completed">✓ Completed</span>' :
                                          conv.stage === 'lead_sent' ? '<span class="status-badge lead-sent">📞 Lead Sent</span>' :
                                          '<span class="status-badge active">● Active</span>';
                        
                        return `
                            <div class="conv-item ${statusClass}">
                                <div class="conv-id">
                                    Conversation #${conv.id}
                                    ${conv.service ? `<span class="service-badge">${conv.service}</span>` : ''}
                                    ${statusBadge}
                                </div>
                                <div class="conv-details">
                                    ${conv.name ? `<strong>Customer:</strong> ${conv.name}<br>` : ''}
                                    ${conv.phone ? `<strong>Phone:</strong> ${conv.phone}<br>` : ''}
                                    ${conv.postcode ? `<strong>Postcode:</strong> ${conv.postcode}<br>` : ''}
                                    ${conv.details ? `<strong>Details:</strong> ${conv.details}` : ''}
                                </div>
                            </div>
                        `;
                    }).join('');
                } else {
                    convList.innerHTML = '<p style="color: #636e72; text-align: center; padding: 40px;">No conversations yet. Waiting for customers...</p>';
                }
            } catch (error) {
                console.error('Dashboard error:', error);
                document.getElementById('conversation-list').innerHTML = 
                    '<p style="color: #e74c3c; text-align: center; padding: 40px;">Error loading dashboard data</p>';
            }
        }
        
        // Initial load
        loadDashboard();
        
        // Auto-refresh every 5 seconds
        setInterval(loadDashboard, 5000);
    </script>
</body>
</html>"""
    return render_template_string(html)

@app.route('/api/dashboard')
def dashboard_api():
    try:
        conversations = []
        
        for conv_id, state in CONVERSATION_STATES.items():
            cd = state.get('customer_data', {})
            
            # Build details string
            details = []
            if cd.get('skip_size'):
                details.append(f"Skip: {cd['skip_size']}")
            if cd.get('volume'):
                details.append(f"Volume: {cd['volume']}")
            if cd.get('material_type'):
                details.append(f"Material: {cd['material_type']}")
            if state.get('customer_type'):
                details.append(f"Type: {state['customer_type']}")
            
            conversations.append({
                'id': conv_id[-8:],
                'stage': state.get('stage', 'active'),
                'service': state.get('service_type', '').replace('_', ' ').title() if state.get('service_type') else None,
                'name': cd.get('name'),
                'phone': cd.get('phone'),
                'postcode': cd.get('postcode'),
                'details': ' | '.join(details) if details else None
            })
        
        # Calculate stats
        total = len(CONVERSATION_STATES)
        active = sum(1 for s in CONVERSATION_STATES.values() if s.get('stage') not in ['completed', 'lead_sent', 'collection_booked'])
        bookings = sum(1 for s in CONVERSATION_STATES.values() if s.get('stage') == 'completed')
        leads = sum(1 for s in CONVERSATION_STATES.values() if s.get('stage') in ['lead_sent', 'collection_booked'])
        
        return jsonify({
            'success': True,
            'total': total,
            'active': active,
            'bookings': bookings,
            'leads': leads,
            'conversations': conversations[-20:]  # Last 20 conversations
        })
    except Exception as e:
        print(f"Dashboard API error: {e}")
        return jsonify({'success': False, 'error': str(e)})

if __name__ == '__main__':
    print("=" * 60)
    print("WASTEKING AGENT STARTING")
    print("=" * 60)
    print("✓ All services active")
    print("✓ Direct detection enabled")
    print("✓ API integration ready")
    print("✓ Dashboard available at /dashboard")
    print("=" * 60)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
